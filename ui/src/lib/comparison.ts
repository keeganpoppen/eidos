import type { Investigation, InvestigationContext, InvestigationArtifact, InvestigationAttempt } from './types';
import type { InquiryBinding } from './reflection';
import { resolveInquiryBinding } from './reflection';

// A surface has one arrangement of scoped views. These are presentation references,
// never copies of investigations, native continuations, or authority.
export type ApertureTarget = { investigationId: string; contextId: string; artifactId?: string };
export type Arrangement = {
  left: ApertureTarget;
  right: ApertureTarget;
  lens: 'result' | 'context';
  layout: 'beside' | 'stacked';
  intent?: 'evidence-chain' | 'alternative-review';
  inquiry?: InquiryBinding;
  experimentId?: string;
};
export type Attention = ApertureTarget & {
  artifactId?: string;
  blockId?: string;
  seq?: number;
  threadId?: string;
};
export type Composition = {
  version: 1;
  open: boolean;
  arrangement: Arrangement | null;
  undo: Array<Arrangement | null>;
  focus: Attention | null;
};
export const compositionKey = 'nema.composition.v1';
export const emptyComposition = (): Composition => ({ version: 1, open: false, arrangement: null, undo: [], focus: null });

function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function target(value: unknown): value is ApertureTarget {
  return object(value) && typeof value.investigationId === 'string' && !!value.investigationId &&
    typeof value.contextId === 'string' && !!value.contextId;
}
function arrangement(value: unknown): Arrangement | null {
  if (!object(value) || !target(value.left) || !target(value.right) ||
    !['result', 'context'].includes(String(value.lens)) || !['beside', 'stacked'].includes(String(value.layout))) return null;
  return {
    left: copyTarget(value.left),
    right: copyTarget(value.right),
    lens: value.lens as Arrangement['lens'], layout: value.layout as Arrangement['layout'],
    ...(value.intent === 'evidence-chain' || value.intent === 'alternative-review' ? { intent: value.intent } : {}),
    ...(object(value.inquiry) && typeof value.inquiry.continuationId === 'string' && typeof value.inquiry.inquiryId === 'string' ? { inquiry: {
      continuationId: value.inquiry.continuationId, inquiryId: value.inquiry.inquiryId,
      ...(typeof value.inquiry.responseId === 'string' ? { responseId: value.inquiry.responseId } : {}),
      ...(typeof value.inquiry.evidenceContextId === 'string' ? { evidenceContextId: value.inquiry.evidenceContextId } : {})
    } } : {}),
    ...(typeof value.experimentId === 'string' ? { experimentId: value.experimentId } : {})
  };
}

function copyTarget(value: ApertureTarget): ApertureTarget {
  return { investigationId: value.investigationId, contextId: value.contextId,
    ...(typeof value.artifactId === 'string' && value.artifactId ? { artifactId: value.artifactId } : {}) };
}

export function artifacts(investigation: Investigation | undefined): InvestigationArtifact[] {
  return [investigation?.artifact, investigation?.nativeArtifact, ...(investigation?.artifactHistory ?? [])].filter((item): item is InvestigationArtifact => !!item)
    .filter((item, index, values) => values.findIndex((other) => other.id === item.id) === index);
}

export function outputEvidence(artifact: InvestigationArtifact | null | undefined): string {
  return artifact?.kind === 'eidos-evidence-review' ? 'Local Eidos decision receipt' : artifact?.executionEvidence === 'synthetic' ? 'Synthetic output · no model called' : artifact?.executionEvidence === 'native-observed' ? 'Observed native output' : 'Recorded output · execution origin unverified';
}

export function attempts(investigation: Investigation | undefined): InvestigationAttempt[] {
  return [investigation?.attempt, ...(investigation?.attemptHistory ?? [])].filter((item): item is InvestigationAttempt => !!item);
}

export function readComposition(raw: string | null): Composition {
  try {
    const value: unknown = JSON.parse(raw ?? 'null');
    if (!object(value) || value.version !== 1) return emptyComposition();
    let focus: Attention | null = null;
    if (target(value.focus) && object(value.focus)) {
      const f = value.focus as ApertureTarget & Record<string, unknown>;
      focus = { investigationId: f.investigationId, contextId: f.contextId };
      if (typeof f.artifactId === 'string') focus.artifactId = f.artifactId;
      if (typeof f.blockId === 'string') focus.blockId = f.blockId;
      if (typeof f.seq === 'number' && Number.isSafeInteger(f.seq) && f.seq > 0 && typeof f.threadId === 'string') {
        focus.seq = f.seq; focus.threadId = f.threadId;
      }
    }
    return {
      version: 1, open: value.open === true, arrangement: arrangement(value.arrangement), focus,
      undo: Array.isArray(value.undo) ? value.undo.slice(-12).map(arrangement) : []
    };
  } catch { return emptyComposition(); }
}

export function resolveTarget(investigations: Investigation[], ref: ApertureTarget | null | undefined) {
  const investigation = investigations.find((item) => item.id === ref?.investigationId);
  const context = contexts(investigation).find((item) => item.id === ref?.contextId);
  // A context is not an artifact version. Missing historical pins remain
  // unresolved until an explicit arrangement edit; never follow 'current'.
  const artifact = artifacts(investigation).find((item) => item.id === ref?.artifactId && item.contextId === ref?.contextId);
  return { investigation, context, artifact };
}

/** Offered evidence stays a separate frozen packet, never the native input. */
export function contexts(investigation: Investigation | undefined): InvestigationContext[] {
  return [...(investigation?.contexts ?? []), ...(investigation?.continuation?.inquiry?.responses.flatMap((response) => response.evidenceContext ? [response.evidenceContext] : []) ?? [])];
}

/** A semantic intent lowers into ordinary immutable compositor bindings. */
export function evidenceChain(investigation: Investigation): Arrangement | null {
  const continuation = investigation.continuation;
  const inquiry = continuation?.inquiry;
  const original = investigation.nativeArtifact ?? investigation.artifact;
  if (!continuation || !inquiry || !original) return null;
  const response = inquiry.responses.find((item) => item.decision !== 'defer');
  const result = investigation.artifact?.continuedFrom?.continuationId === continuation.id ? investigation.artifact : artifacts(investigation).find((item) => item.kind === 'eidos-evidence-review' && item.continuationId === continuation.id);
  return {
    left: { investigationId: investigation.id, contextId: original.contextId, artifactId: original.id },
    right: { investigationId: investigation.id, contextId: result?.contextId ?? original.contextId, ...(result ? { artifactId: result.id } : {}) },
    lens: 'result', layout: 'beside', intent: 'evidence-chain',
    inquiry: { continuationId: continuation.id, inquiryId: inquiry.id,
      ...(response ? { responseId: response.id } : {}),
      ...(response?.evidenceContext ? { evidenceContextId: response.evidenceContext.id } : {}) }
  };
}

export function validateEvidenceChain(investigations: Investigation[], value: Arrangement): string | null {
  if (value.intent !== 'evidence-chain') return null;
  if (value.lens !== 'result') return 'An evidence chain requires its evidence, question, and receipt lens.';
  if (!value.inquiry || !value.left.artifactId) return 'An evidence chain requires the exact original artifact and inquiry.';
  const bound = resolveInquiryBinding(investigations, value.left, value.inquiry);
  if (bound.error) return bound.error;
  const original = bound.investigation?.nativeArtifact ?? bound.investigation?.artifact;
  if (original?.id !== value.left.artifactId || original?.contextId !== value.left.contextId) return 'This chain must retain its original native artifact.';
  if (value.right.investigationId !== value.left.investigationId) return 'The result must belong to the same investigation.';
  if (value.right.artifactId) {
    const result = resolveTarget(investigations, value.right).artifact;
    if (!result || !bound.response || bound.response.decision === 'defer') return 'The result requires an exact terminal response.';
    if (result.kind === 'eidos-evidence-review') {
      if (result.contextId !== original.contextId || result.nativeArtifactId !== original.id || result.continuationId !== value.inquiry.continuationId) return 'The result is not the receipt for this original artifact and terminal decision.';
      if ((result.evidenceContextId ?? undefined) !== value.inquiry.evidenceContextId) return 'The receipt and separately offered evidence do not match.';
    } else {
      const lineage = result.continuedFrom;
      const attempt = attempts(bound.investigation).find((item) => item.id === result.attemptId);
      if (!lineage || lineage.investigationId !== value.left.investigationId || lineage.continuationId !== value.inquiry.continuationId || lineage.inquiryId !== value.inquiry.inquiryId || lineage.responseId !== value.inquiry.responseId || lineage.nativeArtifactId !== original.id || lineage.attemptId !== bound.continuation?.attemptId || (lineage.evidenceContextId ?? undefined) !== value.inquiry.evidenceContextId || !attempt || attempt.contextId !== result.contextId || attempt.continuedFrom?.responseId !== lineage.responseId) return 'The result is not the separately admitted follow-up for this inquiry.';
    }
  }
  return null;
}

export type AttentionRequest = { version: 1; intent: 'evidence-chain' | 'alternative-review'; investigationId?: string; experimentId?: string };
export function matchesExperiment(value: Arrangement, experiment: { id: string; baseline: ApertureTarget; alternative: ApertureTarget }): boolean {
  const same = (a: ApertureTarget, b: ApertureTarget) => a.investigationId === b.investigationId && a.contextId === b.contextId && a.artifactId === b.artifactId;
  return value.experimentId === experiment.id && same(value.left, experiment.baseline) && same(value.right, experiment.alternative);
}
export function compileAttentionRequest(value: unknown, investigations: Investigation[], experiments: Array<{ id: string; baseline: ApertureTarget; alternative: ApertureTarget }>): Arrangement {
  if (!object(value) || value.version !== 1) throw new Error('Attention requests require version 1.');
  if (value.intent === 'evidence-chain') {
    const investigation = investigations.find((item) => item.id === value.investigationId);
    const result = investigation && evidenceChain(investigation);
    if (!result) throw new Error('The requested investigation has no available original artifact and inquiry.');
    return result;
  }
  if (value.intent === 'alternative-review') {
    const experiment = experiments.find((item) => item.id === value.experimentId);
    if (!experiment || !resolveTarget(investigations, experiment.baseline).artifact || !resolveTarget(investigations, experiment.alternative).artifact) throw new Error('The named experiment or its exact results are unavailable.');
    return { left: copyTarget(experiment.baseline), right: copyTarget(experiment.alternative), lens: 'result', layout: 'beside', intent: 'alternative-review', experimentId: experiment.id };
  }
  throw new Error('Unsupported attention intent. No action was performed.');
}

/** A remembered source must still be cited by this exact artifact/context/block. */
export function resolveAttention(investigations: Investigation[], focus: Attention | null, blockCitations: number[] = []) {
  const resolved = resolveTarget(investigations, focus);
  const boundArtifact = resolved.artifact ?? null;
  const record = resolved.context?.records.find((item) => item.seq === focus?.seq && item.threadId === focus?.threadId &&
    (!focus?.artifactId || (boundArtifact?.citations.includes(item.seq) && blockCitations.includes(item.seq))));
  return { ...resolved, artifact: boundArtifact, record };
}

export function contextText(context: InvestigationContext | undefined): string {
  if (!context) return '';
  return [
    `Question: ${context.question}`,
    ...context.selections.map((s) => `${s.threadId} · ${s.startSeq}–${s.endSeq}\nWhy: ${s.rationale || '(no rationale)'}`),
    ...context.records.map((r) => `[evidence:${r.seq}] ${r.threadId} · SHA-256 ${r.sha256}`)
  ].join('\n\n');
}

export function sameArrangement(a: Arrangement | null, b: Arrangement | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function applyArrangement(state: Composition, next: Arrangement): Composition {
  if (sameArrangement(state.arrangement, next)) return state;
  return { ...state, arrangement: structuredClone(next), undo: [...state.undo, state.arrangement].slice(-12) };
}

export function undoArrangement(state: Composition): Composition {
  if (!state.undo.length) return state;
  return { ...state, arrangement: state.undo.at(-1) ?? null, undo: state.undo.slice(0, -1) };
}
