import type { EvidenceHit, EvidenceHitSource, EvidenceSearchPage } from './types';
import { frozenText, isLocalTextEvidence } from './supplied-text';

export const EVIDENCE_SCOPE = 'displayed-history-text/v1';
export function evidenceFieldLabel(field: string): string {
  if (field === 'suppliedText.text') return 'Supplied text';
  if (field === 'agentMessage.text') return 'Assistant message';
  if (/^userMessage\.content\/\d+\/text$/.test(field)) return 'User message';
  if (/^turn\.input\/\d+\/text$/.test(field)) return 'Turn input';
  if (/^reasoning\.summary\/-?\d+$/.test(field)) return 'Exposed reasoning summary';
  if (/^reasoning\.content\/-?\d+$/.test(field)) return 'Exposed reasoning content';
  if (field === 'commandExecution.command') return 'Recorded command';
  if (field === 'commandExecution.output') return 'Recorded command output';
  if (/^fileChange\.changes\/\d+\/path$/.test(field)) return 'Changed file path';
  return 'Unknown source field';
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 1024;
const seq = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
export function readEvidenceHit(value: unknown): EvidenceHit {
  if (!object(value) || !['id', 'version', 'threadId', 'turnId', 'field'].every(k => text(value[k]))
      || (value.itemId !== null && !text(value.itemId)) || evidenceFieldLabel(value.field as string) === 'Unknown source field'
      || !Array.isArray(value.recordSeqs) || !value.recordSeqs.length || value.recordSeqs.length > 256
      || value.recordSeqs.some((n, i, a) => !seq(n) || (i > 0 && n <= a[i - 1]))
      || value.anchorSeq !== value.recordSeqs[0] || typeof value.excerpt !== 'string' || [...value.excerpt].length > 240) throw Error('Search returned an invalid exact source reference. Refresh the search.');
  return value as EvidenceHit;
}
export function evidenceHitKey(hit: EvidenceHit): string {
  return JSON.stringify([hit.id, hit.version, hit.threadId, hit.turnId, hit.itemId, hit.field, hit.anchorSeq, hit.recordSeqs, hit.excerpt]);
}
export async function readEvidenceSource(value: unknown, expected: EvidenceHit): Promise<EvidenceHitSource> {
  if (!object(value) || value.scope !== EVIDENCE_SCOPE || evidenceHitKey(readEvidenceHit(value.hit)) !== evidenceHitKey(expected)
      || !Array.isArray(value.records) || value.records.length !== expected.recordSeqs.length) throw Error('The source response does not match the inspected hit. Refresh the search.');
  let bytes = 0;
  for (const [i, record] of value.records.entries()) {
    if (!object(record) || record.seq !== expected.recordSeqs[i] || record.threadId !== expected.threadId
        || !text(record.source) || !text(record.direction) || (record.method !== null && !text(record.method))
        || typeof record.rawText !== 'string' || typeof record.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(record.sha256)) throw Error('Exact source records are unavailable. Nothing was selected.');
    const raw = new TextEncoder().encode(record.rawText);
    bytes += raw.byteLength;
    if (bytes > 131072) throw Error('Exact source exceeds the 128 KiB inspection limit. Nothing was selected.');
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(n => n.toString(16).padStart(2, '0')).join('');
    if (hash !== record.sha256) throw Error('Source bytes do not match their recorded hash. Nothing was selected.');
    if (expected.field === 'suppliedText.text' || record.localEvidence !== undefined) {
      const text = frozenText(record.rawText, record.localEvidence, record.sha256);
      if (expected.field !== 'suppliedText.text' || text === null || !isLocalTextEvidence(record.localEvidence)) throw Error('Supplied text provenance is unavailable. Nothing was selected.');
      const fileHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(n => n.toString(16).padStart(2, '0')).join('');
      if (fileHash !== record.localEvidence.fileSha256) throw Error('Supplied file bytes do not match their recorded hash. Nothing was selected.');
    }
  }
  return value as EvidenceHitSource;
}

type Fetcher = (path: string) => Promise<Response>;
export type EvidenceDiscoveryState = {
  q: string; threadId: string; page: EvidenceSearchPage | null; previous: string[]; cursor: string;
  loading: boolean; inspecting: string | null; source: EvidenceHitSource | null; error: string; refreshRequired: boolean;
};
export class EvidenceDiscoveryClient {
  state: EvidenceDiscoveryState = { q: '', threadId: '', page: null, previous: [], cursor: '', loading: false, inspecting: null, source: null, error: '', refreshRequired: false };
  private generation = 0;
  private active = true;
  private disposed = false;
  constructor(private changed: (state: EvidenceDiscoveryState) => void, private fetcher: Fetcher = path => fetch(path)) {}
  private update(patch: Partial<EvidenceDiscoveryState>) { this.state = { ...this.state, ...patch }; if (!this.disposed) this.changed(this.state); }
  /** Completed inspection remains a reference; pending reads never follow navigation. */
  navigate(active = this.active) { this.active = active; this.generation++; this.update({ loading: false, inspecting: null }); }
  clearSearch() { this.generation++; this.update({ q: '', page: null, source: null, previous: [], cursor: '', loading: false, inspecting: null, error: '', refreshRequired: false }); }
  dispose() { this.disposed = true; this.generation++; }
  private current(generation: number) { return !this.disposed && this.active && generation === this.generation; }
  private async read(path: string) {
    const response = await this.fetcher(path);
    const value = await response.json();
    if (!response.ok) throw Object.assign(Error(typeof value?.error === 'string' ? value.error : `Source read failed (${response.status}).`), { status: response.status });
    return value;
  }
  async search(q: string, threadId = '') {
    if (!this.active || this.disposed) return;
    q = q.trim();
    this.generation++;
    this.update({ q, threadId, page: null, previous: [], cursor: '', source: null, inspecting: null, error: '', refreshRequired: false });
    if (!q || [...q].length > 200) { this.update({ error: 'Enter between 1 and 200 characters to search recorded evidence.' }); return; }
    await this.load();
  }
  async move(forward: boolean) {
    if (this.state.loading || this.state.refreshRequired || !this.active) return;
    const cursor = forward ? this.state.page?.nextCursor : this.state.previous.at(-1);
    if (cursor == null) return;
    this.update({ cursor, previous: forward ? [...this.state.previous, this.state.cursor] : this.state.previous.slice(0, -1), page: null, source: null });
    await this.load();
  }
  async refresh() { await this.search(this.state.q, this.state.threadId); }
  private async load() {
    const generation = ++this.generation;
    this.update({ loading: true, inspecting: null, error: '', source: null });
    const query = new URLSearchParams({ q: this.state.q, limit: '20' });
    if (this.state.threadId) query.set('threadId', this.state.threadId);
    if (this.state.cursor) query.set('cursor', this.state.cursor);
    try {
      const value = await this.read(`/api/evidence/search?${query}`);
      if (!this.current(generation)) return;
      if (!object(value) || value.scope !== EVIDENCE_SCOPE || value.unchanged !== false || !text(value.version)
          || !Array.isArray(value.hits) || value.hits.length > 20 || (value.nextCursor !== null && (typeof value.nextCursor !== 'string' || !value.nextCursor || value.nextCursor.length > 16384))) throw Error('Search returned an invalid page. Refresh the search.');
      const hits = value.hits.map(readEvidenceHit);
      if (new Set(hits.map(h => h.id)).size !== hits.length || (this.state.threadId && hits.some(h => h.threadId !== this.state.threadId))) throw Error('Search returned a mismatched source page.');
      this.update({ page: { ...value, hits } as EvidenceSearchPage });
    } catch (cause) { if (this.current(generation)) this.update({ error: cause instanceof Error ? cause.message : 'Search failed.', refreshRequired: (cause as { status?: number }).status === 409 }); }
    finally { if (this.current(generation)) this.update({ loading: false }); }
  }
  async inspect(hit: EvidenceHit) {
    if (!this.active || this.disposed || this.state.refreshRequired || !this.state.page?.hits.some(h => evidenceHitKey(h) === evidenceHitKey(hit))) return;
    const generation = ++this.generation;
    this.update({ source: null, inspecting: hit.id, error: '' });
    try {
      const query = new URLSearchParams({ q: this.state.q, version: hit.version });
      const value = await this.read(`/api/evidence/hits/${encodeURIComponent(hit.id)}?${query}`);
      if (!this.current(generation)) return;
      const source = await readEvidenceSource(value, hit);
      if (this.current(generation)) this.update({ source });
    } catch (cause) { if (this.current(generation)) this.update({ error: cause instanceof Error ? cause.message : 'Source inspection failed.', refreshRequired: (cause as { status?: number }).status === 409 }); }
    finally { if (this.current(generation)) this.update({ inspecting: null }); }
  }
  inspected(): EvidenceHitSource | null {
    const source = this.state.source;
    return this.active && !this.disposed && !this.state.refreshRequired && source
      && this.state.page?.hits.some(h => evidenceHitKey(h) === evidenceHitKey(source.hit)) ? source : null;
  }
}
