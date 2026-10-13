import { artifacts, attempts, contexts } from './comparison';
import type { ArtifactInputSelection, FrozenArtifactInput, Investigation, InvestigationArtifact } from './types';

export type ArtifactSourceTarget = { investigationId: string; artifactId: string; contextId?: string };
export const artifactInputKey = (input: ArtifactSourceTarget): string => JSON.stringify([input.investigationId, input.artifactId]);

/** Browser preferences retain descriptions of selected references, never copied results. */
export function readArtifactInputs(value: unknown): ArtifactInputSelection[] {
  if (!Array.isArray(value)) return [];
  const selected: ArtifactInputSelection[] = [];
  for (const item of value.slice(0, 32)) {
    if (!item || typeof item !== 'object' ||
      typeof item.investigationId !== 'string' || !item.investigationId.trim() || item.investigationId.length > 200 ||
      typeof item.artifactId !== 'string' || !item.artifactId.trim() || item.artifactId.length > 200 ||
      typeof item.rationale !== 'string' || item.rationale.length > 2000) continue;
    const ref = { investigationId: item.investigationId, artifactId: item.artifactId, rationale: item.rationale };
    if (!selected.some((existing) => artifactInputKey(existing) === artifactInputKey(ref))) selected.push(ref);
  }
  return selected;
}

export function sameArtifactInputs(left: ArtifactInputSelection[] = [], right: ArtifactInputSelection[] = []): boolean {
  return left.length === right.length && left.every((item, index) =>
    artifactInputKey(item) === artifactInputKey(right[index]) && item.rationale === right[index].rationale);
}

export function artifactInputDiff(before: ArtifactInputSelection[] = [], after: ArtifactInputSelection[] = []) {
  const missing = (from: ArtifactInputSelection[], to: ArtifactInputSelection[]) => from.filter((item) => !to.some((other) => artifactInputKey(item) === artifactInputKey(other)));
  return {
    added: missing(after, before), removed: missing(before, after),
    updated: after.filter((item) => before.some((other) => artifactInputKey(item) === artifactInputKey(other) && item.rationale !== other.rationale))
  };
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).filter(([, child]) => child !== undefined).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`).join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}

/** Re-selecting an unchanged artifact can freeze a different source review or pin. */
export function changedFrozenArtifactInputs(before: FrozenArtifactInput[] = [], after: FrozenArtifactInput[] = []): FrozenArtifactInput[] {
  const snapshot = ({ rationale: _rationale, ...input }: FrozenArtifactInput) => canonical(input);
  return after.filter((input) => before.some((previous) => artifactInputKey(previous) === artifactInputKey(input) && snapshot(previous) !== snapshot(input)));
}

export function resolveArtifactSource(investigation: Investigation, target: ArtifactSourceTarget) {
  if (investigation.id !== target.investigationId) return null;
  const artifact = artifacts(investigation).find((item) => item.id === target.artifactId && (!target.contextId || item.contextId === target.contextId));
  if (!artifact) return null;
  const context = contexts(investigation).find((item) => item.id === artifact.contextId);
  const attempt = attempts(investigation).find((item) => item.id === artifact.attemptId && item.contextId === artifact.contextId);
  return context && attempt ? { artifact, context, attempt } : null;
}

export function artifactKind(artifact: { kind?: string; continuedFrom?: unknown }): string {
  if (artifact.kind === 'eidos-evidence-review') return 'Evidence decision receipt';
  if (artifact.kind === 'native-needs-evidence') return 'Specialist evidence inquiry';
  if (artifact.kind === 'native-inquiry-invalid') return 'Invalid evidence inquiry';
  if (artifact.continuedFrom) return 'Follow-up specialist result';
  return artifact.kind ?? 'Specialist result';
}
