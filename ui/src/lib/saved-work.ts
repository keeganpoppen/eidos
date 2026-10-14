import type { Investigation, InvestigationArtifact, InvestigationAttempt, InvestigationContext, WorkbenchExperiment } from './types';
import type { ArtifactSourceTarget } from './artifact-inputs';
import { checkAuthoredFinding } from './authored-finding';

export type WorkSummary = Pick<Investigation, 'id' | 'title' | 'status' | 'createdAtMs' | 'currentContextId'> & {
  contextCount: number; artifactCount: number; attemptStatus: string | null; hasInquiry: boolean; version: string;
};
export type ResultSummary = {
  investigationId: string; investigationTitle: string; artifactId: string; contextId: string; attemptId: string | null;
  kind?: string; executionEvidence?: string; continuedFrom?: unknown; createdAtMs: number;
  match?: { field: 'title' | 'question' | 'result'; excerpt: string };
};
export type CatalogItem = WorkSummary | ResultSummary;
export type CatalogKind = 'catalog' | 'artifacts';
export type CatalogPage = { version: string; items: CatalogItem[]; nextCursor: string | null };
export type ArtifactSource = {
  version: string; investigationId: string; investigationTitle: string; artifact: InvestigationArtifact;
  context: InvestigationContext; attempt: InvestigationAttempt | null; adoption: Investigation['adoption'];
};
type View = { version?: string; investigation: Investigation };
type Fetcher = (path: string) => Promise<Response>;

export const catalogKey = (item: CatalogItem): string => 'artifactId' in item
  ? JSON.stringify([item.investigationId, item.artifactId]) : item.id;

/** A selected reference remains selectable when it is outside the current search page. */
export function catalogChoices(page: CatalogItem[], selected?: CatalogItem): CatalogItem[] {
  return selected && !page.some((item) => catalogKey(item) === catalogKey(selected)) ? [selected, ...page] : page;
}

/** A previous query's retained selection is not evidence of a current match.
 * Preserve its original context pin if a later row reuses the same result key. */
export function catalogSelection(page: CatalogItem[], value: string, selected?: CatalogItem): { item?: CatalogItem; onPage: boolean } {
  const retained = selected && catalogKey(selected) === value ? selected : undefined;
  const current = page.find((item) => catalogKey(item) === value);
  const sameResult = !retained || !current || !('artifactId' in retained) || !('artifactId' in current)
    || (retained.contextId === current.contextId && retained.attemptId === current.attemptId);
  return current && sameResult ? { item: current, onPage: true } : { item: retained, onPage: false };
}

/** Shared read cache. It contains server views, never editable browser draft fields. */
export class SavedWorkClient {
  private pages = new Map<string, CatalogPage>();
  private views = new Map<string, View>();
  private generations = new Map<string, number>();
  private pending = new Map<string, Promise<unknown>>();
  constructor(private fetcher: Fetcher = (path) => fetch(path)) {}

  private async read(path: string) {
    const response = await this.fetcher(path);
    const value = await response.json();
    if (!response.ok) throw new Error(value.error ?? `Could not load saved work (${response.status}).`);
    return value;
  }

  private once<T>(key: string, request: () => Promise<T>): Promise<T> {
    const existing = this.pending.get(key);
    if (existing) return existing as Promise<T>;
    const result = request().finally(() => { if (this.pending.get(key) === result) this.pending.delete(key); });
    this.pending.set(key, result);
    return result;
  }

  catalog(kind: CatalogKind, q = '', cursor = ''): Promise<CatalogPage> {
    const query = new URLSearchParams({ limit: '20', q });
    if (cursor) query.set('cursor', cursor);
    const path = `/api/investigations/${kind}?${query}`;
    return this.once(path, async () => {
      const previous = this.pages.get(path);
      const value = await this.read(path + (previous ? `&knownVersion=${encodeURIComponent(previous.version)}` : ''));
      if (value.unchanged) {
        if (!previous) throw new Error('Saved work returned no page for this search. Retry the search.');
        return previous;
      }
      const page = { version: value.version, items: value[kind === 'catalog' ? 'investigations' : 'artifacts'], nextCursor: value.nextCursor };
      this.pages.set(path, page);
      // Bound metadata retained after browsing many different searches.
      if (this.pages.size > 80) this.pages.delete(this.pages.keys().next().value!);
      return page;
    });
  }

  /** Mutation responses supersede older conditional reads, including their cached versions. */
  remember(investigation: Investigation): void {
    this.generations.set(investigation.id, (this.generations.get(investigation.id) ?? 0) + 1);
    this.views.set(investigation.id, { investigation });
  }

  view(id: string): Promise<Investigation> {
    const generation = this.generations.get(id) ?? 0;
    return this.once(`view:${id}:${generation}`, async () => {
      const previous = this.views.get(id);
      const query = previous?.version ? `?knownVersion=${encodeURIComponent(previous.version)}` : '';
      let value;
      try { value = await this.read(`/api/investigations/${encodeURIComponent(id)}/view${query}`); }
      catch (cause) {
        if ((this.generations.get(id) ?? 0) !== generation) return this.views.get(id)!.investigation;
        throw cause;
      }
      if ((this.generations.get(id) ?? 0) !== generation) return this.views.get(id)!.investigation;
      if (value.unchanged) {
        if (!previous) throw new Error('Saved investigation returned no initial view. Retry loading it.');
        return previous.investigation;
      }
      if (value.investigation.id !== id) throw new Error('The saved investigation does not match the requested reference.');
      this.views.set(id, { version: value.version, investigation: value.investigation });
      return value.investigation;
    });
  }

  source(target: ArtifactSourceTarget): Promise<ArtifactSource> {
    const query = target.contextId ? `?contextId=${encodeURIComponent(target.contextId)}` : '';
    const path = `/api/investigations/${encodeURIComponent(target.investigationId)}/artifacts/${encodeURIComponent(target.artifactId)}/source${query}`;
    return this.once(path, async () => {
      const source: ArtifactSource = await this.read(path);
      const authored = source.artifact?.kind === 'owner-authored-finding';
      if (authored) await checkAuthoredFinding(source.artifact, target.investigationId);
      if (source.investigationId !== target.investigationId || source.artifact.id !== target.artifactId ||
        (target.contextId && source.context.id !== target.contextId) || source.artifact.contextId !== source.context.id ||
        (authored ? source.attempt !== null || source.adoption !== null
          : !source.attempt || source.artifact.attemptId !== source.attempt.id || source.attempt.contextId !== source.context.id)) {
        throw new Error('This exact result, source context, or attempt is unavailable. No newer result has been substituted.');
      }
      return source;
    });
  }

  /** Review state can change independently of an owner's version. Deduplicate
   * concurrent reads, but re-read only on explicit navigation/refresh. */
  experiment(ownerId: string, experimentId: string): Promise<WorkbenchExperiment> {
    const path = `/api/investigations/${encodeURIComponent(ownerId)}/experiments/${encodeURIComponent(experimentId)}`;
    return this.once(path, async () => {
      const value: WorkbenchExperiment = await this.read(path);
      if (value.id !== experimentId || value.investigationId !== ownerId) throw new Error('The saved experiment does not match this owner and experiment reference.');
      return value;
    });
  }
}

export const savedWork = new SavedWorkClient();
