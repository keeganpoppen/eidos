import type { Investigation, InvestigationContext, InvestigationArtifact } from './types';

// A surface has one arrangement of scoped views. These are presentation references,
// never copies of investigations, native continuations, or authority.
export type ApertureTarget = { investigationId: string; contextId: string; artifactId?: string };
export type Arrangement = {
  left: ApertureTarget;
  right: ApertureTarget;
  lens: 'result' | 'context';
  layout: 'beside' | 'stacked';
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
    lens: value.lens as Arrangement['lens'], layout: value.layout as Arrangement['layout']
  };
}

function copyTarget(value: ApertureTarget): ApertureTarget {
  return { investigationId: value.investigationId, contextId: value.contextId,
    ...(typeof value.artifactId === 'string' && value.artifactId ? { artifactId: value.artifactId } : {}) };
}

export function artifacts(investigation: Investigation | undefined): InvestigationArtifact[] {
  return [investigation?.artifact, investigation?.nativeArtifact].filter((item): item is InvestigationArtifact => !!item)
    .filter((item, index, values) => values.findIndex((other) => other.id === item.id) === index);
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
  const context = investigation?.contexts.find((item) => item.id === ref?.contextId);
  // A context is not an artifact version. Missing historical pins remain
  // unresolved until an explicit arrangement edit; never follow 'current'.
  const artifact = artifacts(investigation).find((item) => item.id === ref?.artifactId && item.contextId === ref?.contextId);
  return { investigation, context, artifact };
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
