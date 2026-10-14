import type { InvestigationContext } from './types';
import { checkAuthoredFinding } from './authored-finding';

export const RESULT_USES_SCOPE = 'direct-frozen-artifact-inputs/v1';
export type ResultUseTarget = { investigationId: string; artifactId: string };
export type ResultUse = {
  investigationId: string; investigationTitle: string; contextId: string; ownerVersion: string;
  isCurrent: boolean; questionExcerpt: string; rationaleExcerpt: string; matchingInputCount: number;
};
export type ResultUsesPage = {
  scope: typeof RESULT_USES_SCOPE; source: ResultUseTarget; version: string; unchanged: false;
  uses: ResultUse[]; nextCursor: string | null;
};
export type ResultUseDetail = {
  scope: typeof RESULT_USES_SCOPE; source: ResultUseTarget; investigationId: string; investigationTitle: string;
  contextId: string; ownerVersion: string; isCurrent: boolean;
  context: InvestigationContext; matchingInputIndexes: number[];
};
export type ResultUsesState = {
  target: ResultUseTarget | null; expanded: boolean; page: ResultUsesPage | null; cursor: string; previous: string[];
  loading: boolean; inspecting: string | null; detail: ResultUseDetail | null; error: string; refreshRequired: boolean;
};
const initial = (): ResultUsesState => ({ target: null, expanded: false, page: null, cursor: '', previous: [], loading: false, inspecting: null, detail: null, error: '', refreshRequired: false });
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const nonempty = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const id = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && [...v].length <= 200;
const excerpt = (v: unknown): v is string => typeof v === 'string' && [...v].length <= 240;
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(nonempty);
const sameSource = (v: unknown, target: ResultUseTarget): boolean => object(v) && v.investigationId === target.investigationId && v.artifactId === target.artifactId;
export const resultUseKey = (row: ResultUse): string => JSON.stringify([row.investigationId, row.contextId, row.ownerVersion]);
const rowKey = (row: ResultUse): string => JSON.stringify([row.investigationId, row.contextId]);

export function readResultUses(value: unknown, target: ResultUseTarget): ResultUsesPage {
  if (!object(value) || value.scope !== RESULT_USES_SCOPE || !sameSource(value.source, target)
      || !id(value.version) || value.unchanged !== false || !Array.isArray(value.uses) || value.uses.length > 20
      || (value.nextCursor !== null && (typeof value.nextCursor !== 'string' || !value.nextCursor || value.nextCursor.length > 16384))) {
    throw Error('Saved uses returned an invalid page. Refresh saved uses.');
  }
  for (const row of value.uses) {
    if (!object(row) || !id(row.investigationId) || !id(row.contextId) || !id(row.ownerVersion)
        || !excerpt(row.investigationTitle) || !excerpt(row.questionExcerpt) || !excerpt(row.rationaleExcerpt)
        || typeof row.isCurrent !== 'boolean' || !integer(row.matchingInputCount) || row.matchingInputCount < 1) {
      throw Error('Saved uses returned an invalid context reference. Refresh saved uses.');
    }
  }
  const page = value as ResultUsesPage;
  if (new Set(page.uses.map(rowKey)).size !== page.uses.length) throw Error('Saved uses returned ambiguous context references. Refresh saved uses.');
  return page;
}

/** Validate the fields rendered below without discarding unknown saved fields or
 * re-resolving any upstream owner. The server's owner version pins this read. */
function readableContext(value: unknown): value is InvestigationContext {
  if (!object(value) || !id(value.id) || typeof value.question !== 'string' || typeof value.projectedPrompt !== 'string'
      || !Array.isArray(value.records) || !Array.isArray(value.selections)
      || (value.artifactInputs !== undefined && !Array.isArray(value.artifactInputs))) return false;
  if (!value.records.every(record => object(record) && integer(record.seq) && record.seq > 0 && nonempty(record.threadId)
      && nonempty(record.source) && nonempty(record.direction) && (record.method === null || nonempty(record.method))
      && typeof record.rawText === 'string' && typeof record.sha256 === 'string' && /^[a-f0-9]{64}$/.test(record.sha256))) return false;
  if (!value.selections.every(selection => object(selection) && nonempty(selection.threadId) && integer(selection.startSeq)
      && integer(selection.endSeq) && selection.startSeq > 0 && selection.endSeq >= selection.startSeq && typeof selection.rationale === 'string')) return false;
  return (value.artifactInputs ?? []).every((input: unknown) => {
    if (!object(input) || !id(input.investigationId) || !id(input.artifactId) || !id(input.sourceContextId)
        || typeof input.rationale !== 'string' || !object(input.artifact)) return false;
    const artifact = input.artifact;
    if (artifact.id !== input.artifactId || artifact.contextId !== input.sourceContextId || typeof artifact.text !== 'string'
        || (artifact.kind !== undefined && typeof artifact.kind !== 'string')
        || !Array.isArray(artifact.citations) || !artifact.citations.every(integer)
        || !Array.isArray(artifact.unsupportedCitations) || !artifact.unsupportedCitations.every(integer)
        || (artifact.artifactCitations !== undefined && !strings(artifact.artifactCitations))
        || (artifact.unsupportedArtifactCitations !== undefined && !strings(artifact.unsupportedArtifactCitations))) return false;
    return input.sourceAdoption === null || (object(input.sourceAdoption)
      && ['adopt', 'reject'].includes(input.sourceAdoption.decision as string) && typeof input.sourceAdoption.note === 'string');
  });
}

export async function readResultUseDetail(value: unknown, target: ResultUseTarget, row: ResultUse): Promise<ResultUseDetail> {
  if (!object(value) || value.scope !== RESULT_USES_SCOPE || !sameSource(value.source, target)
      || value.investigationId !== row.investigationId || value.contextId !== row.contextId || value.ownerVersion !== row.ownerVersion
      || value.isCurrent !== row.isCurrent || typeof value.investigationTitle !== 'string' || !readableContext(value.context)
      || value.context.id !== row.contextId || !Array.isArray(value.matchingInputIndexes)) {
    throw Error('The saved context does not match this exact use. Refresh saved uses; no newer context was substituted.');
  }
  const indexes = (value.context.artifactInputs ?? []).flatMap((input, index) => sameSource(input, target) ? [index] : []);
  const matching = value.matchingInputIndexes;
  if (!indexes.length || indexes.length !== row.matchingInputCount || indexes.length !== matching.length
      || indexes.some((index, position) => matching[position] !== index)) {
    throw Error('The saved context does not contain the expected frozen result inputs. Refresh saved uses.');
  }
  for (const input of value.context.artifactInputs ?? []) {
    if (input.artifact.kind === 'owner-authored-finding') await checkAuthoredFinding(input.artifact, input.investigationId);
  }
  return value as ResultUseDetail;
}

type Fetcher = (path: string, init: { signal: AbortSignal }) => Promise<Response>;
/** Read-only, instance-local navigation. Never shares mutable draft state or
 * retains snapshots in browser storage. Aborts also guard fetchers that ignore signals. */
export class ResultUsesClient {
  state = initial();
  private generation = 0;
  private controller: AbortController | null = null;
  private disposed = false;
  constructor(private changed: (state: ResultUsesState) => void, private fetcher: Fetcher = (path, init) => fetch(path, init)) {}
  private update(patch: Partial<ResultUsesState>) { if (!this.disposed) { this.state = { ...this.state, ...patch }; this.changed(this.state); } }
  private invalidate() { this.generation++; this.controller?.abort(); this.controller = null; }
  private current(generation: number) { return !this.disposed && !!this.state.target && generation === this.generation; }
  target(target: ResultUseTarget | null) {
    this.invalidate();
    this.update({ ...initial(), target: target ? { investigationId: target.investigationId, artifactId: target.artifactId } : null });
  }
  dispose() { this.invalidate(); this.disposed = true; }
  private base(target: ResultUseTarget) { return `/api/investigations/${encodeURIComponent(target.investigationId)}/artifacts/${encodeURIComponent(target.artifactId)}/uses`; }
  private async read(path: string, signal: AbortSignal) {
    const response = await this.fetcher(path, { signal });
    const value: unknown = await response.json();
    if (!response.ok) throw Object.assign(Error(object(value) && typeof value.error === 'string' ? value.error : `Saved use read failed (${response.status}).`), { status: response.status });
    return value;
  }
  async refresh() {
    if (!this.state.target || this.disposed) return;
    this.update({ expanded: true, page: null, cursor: '', previous: [], detail: null, error: '', refreshRequired: false });
    await this.load();
  }
  async move(forward: boolean) {
    if (!this.state.target || this.disposed || this.state.loading || this.state.refreshRequired) return;
    const cursor = forward ? this.state.page?.nextCursor : this.state.previous.at(-1);
    if (cursor == null) return;
    this.update({ cursor, previous: forward ? [...this.state.previous, this.state.cursor] : this.state.previous.slice(0, -1), page: null, detail: null });
    await this.load();
  }
  private async load() {
    this.invalidate();
    const generation = this.generation, target = this.state.target!;
    const controller = this.controller = new AbortController();
    this.update({ loading: true, inspecting: null, detail: null, error: '' });
    const query = new URLSearchParams({ limit: '20' });
    if (this.state.cursor) query.set('cursor', this.state.cursor);
    try {
      const value = await this.read(`${this.base(target)}?${query}`, controller.signal);
      if (this.current(generation)) this.update({ page: readResultUses(value, target) });
    } catch (cause) { if (this.current(generation)) this.update({ error: cause instanceof Error ? cause.message : 'Saved uses could not be read.', refreshRequired: (cause as { status?: number }).status === 409 }); }
    finally { if (this.current(generation)) this.update({ loading: false }); }
  }
  isCurrentDetail(detail: ResultUseDetail): boolean { return !this.disposed && !!this.state.target && this.state.detail === detail; }
  async inspect(row: ResultUse): Promise<ResultUseDetail | null> {
    const target = this.state.target;
    const selected = this.state.page?.uses.find(candidate => resultUseKey(candidate) === resultUseKey(row));
    if (!target || this.disposed || this.state.loading || this.state.refreshRequired
        || !selected) return null;
    row = selected;
    this.invalidate();
    const generation = this.generation, controller = this.controller = new AbortController();
    this.update({ inspecting: resultUseKey(row), detail: null, error: '' });
    const query = new URLSearchParams({ expectedVersion: row.ownerVersion });
    try {
      const value = await this.read(`${this.base(target)}/${encodeURIComponent(row.investigationId)}/contexts/${encodeURIComponent(row.contextId)}?${query}`, controller.signal);
      if (this.current(generation)) {
        const detail = await readResultUseDetail(value, target, row);
        if (!this.current(generation)) return null;
        this.update({ detail });
        return detail;
      }
    } catch (cause) { if (this.current(generation)) this.update({ error: cause instanceof Error ? cause.message : 'The exact saved context could not be read.', refreshRequired: (cause as { status?: number }).status === 409 }); }
    finally { if (this.current(generation)) this.update({ inspecting: null }); }
    return null;
  }
}
