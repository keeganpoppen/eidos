import { resolveTarget, type ApertureTarget, type Arrangement } from './comparison';
import type { ArtifactSource, SavedWorkClient } from './saved-work';
import type { FrozenArtifactInput, Investigation, InvestigationArtifact, InvestigationContext } from './types';

export type SuppliedComparisonRequest = {
  consumer: ApertureTarget & { artifactId: string };
  artifact: InvestigationArtifact;
  manifestId: string | null;
  input: FrozenArtifactInput;
};
export type SuppliedComparisonProposal = { arrangement: Arrangement; owners: Investigation[]; request: SuppliedComparisonRequest; consumer: ArtifactSource; supplied: ArtifactSource };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).filter(([, child]) => child !== undefined)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`).join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}
const same = (a: unknown, b: unknown) => canonical(a) === canonical(b);
const targetOf = (input: FrozenArtifactInput) => ({ investigationId: input.investigationId, contextId: input.sourceContextId, artifactId: input.artifactId });

/** Capture the displayed result and its cited frozen input, never editor state. */
export function suppliedComparisonRequest(owner: string, artifact: InvestigationArtifact, context: InvestigationContext, input: FrozenArtifactInput): SuppliedComparisonRequest {
  if (artifact.contextId !== context.id || !artifact.artifactCitations?.includes(input.artifactId)
      || !context.artifactInputs?.some(value => same(value, input))) throw Error('This result does not cite that exact supplied input.');
  return structuredClone({ consumer: { investigationId: owner, contextId: context.id, artifactId: artifact.id }, artifact, manifestId: context.manifestId ?? null, input });
}

function exactSource(source: ArtifactSource, target: ApertureTarget) {
  return source.investigationId === target.investigationId && source.context.id === target.contextId
    && source.artifact.id === target.artifactId && source.artifact.contextId === target.contextId;
}

/** Validate source content, not mutable current-owner review metadata. */
export function validateSuppliedComparison(request: SuppliedComparisonRequest, consumer: ArtifactSource, supplied: ArtifactSource, owners: Investigation[]): Arrangement {
  const left = targetOf(request.input), right = request.consumer;
  if (!exactSource(consumer, right) || !same(consumer.artifact, request.artifact)
      || (consumer.context.manifestId ?? null) !== request.manifestId
      || !consumer.artifact.artifactCitations?.includes(left.artifactId)
      || !consumer.context.artifactInputs?.some(value => same(value, request.input))) {
    throw Error('The displayed result or its exact supplied input changed. The previous comparison was retained.');
  }
  if (!exactSource(supplied, left) || !same(supplied.artifact, request.input.artifact)
      || (supplied.context.manifestId ?? null) !== request.input.sourceManifestId
      || (supplied.attempt?.manifestId ?? null) !== request.input.sourceAttemptManifestId) {
    throw Error('The original result disagrees with its frozen supplied copy or source pins. The copy remains available in provenance.');
  }
  for (const [source, target] of [[consumer, right], [supplied, left]] as const) {
    const resolved = resolveTarget(owners, target);
    if (!resolved.context || !resolved.artifact || !same(resolved.context, source.context) || !same(resolved.artifact, source.artifact)) {
      throw Error('The exact saved owner, context or result is unavailable or changed during inspection. No newer result was substituted.');
    }
  }
  return { left, right: { ...right }, lens: 'result', layout: 'beside' };
}

/** Cancellation scopes read completion only; it never mutates a composition. */
export function createSuppliedComparisonLoader(reads: Pick<SavedWorkClient, 'source' | 'view'>) {
  let generation = 0, disposed = false;
  return {
    cancel() { generation++; },
    dispose() { disposed = true; generation++; },
    async load(value: SuppliedComparisonRequest): Promise<SuppliedComparisonProposal | null> {
      if (disposed) return null;
      const request = structuredClone(value), current = ++generation;
      const ownerIds = [...new Set([request.consumer.investigationId, request.input.investigationId])];
      try {
        const [consumer, supplied, owners] = await Promise.all([
          reads.source(request.consumer), reads.source(targetOf(request.input)),
          Promise.all(ownerIds.map(id => reads.view(id)))
        ]);
        if (disposed || current !== generation) return null;
        return { arrangement: validateSuppliedComparison(request, consumer, supplied, owners), owners, request, consumer, supplied };
      } catch (cause) {
        if (disposed || current !== generation) return null;
        throw cause;
      }
    }
  };
}
