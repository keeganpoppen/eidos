import type { AuthoredFinding, Investigation, InvestigationContext } from './types';

export const FINDING_KEY = 'nema.authored-finding.v1';
export const MAX_FINDING_BYTES = 128 * 1024;
const MAX_BODY = 256 * 1024;
const MAX_SLOT = 512 * 1024;
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;
export type FindingDraft = {
  version: 1; source: { investigationId: string; contextId: string; title: string; question: string };
  text: string | null; request: string | null; savedId: string | null;
};
export type FindingState = { draft: FindingDraft | null; finding: AuthoredFinding | null; busy: boolean; unavailable: boolean; error: string; refusal: string };
export const emptyFindingState = (): FindingState => ({ draft: null, finding: null, busy: false, unavailable: false, error: '', refusal: '' });
const utf8 = new TextEncoder();
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const shape = (v: unknown, fields: string[]): v is Record<string, unknown> => object(v) && Object.keys(v).sort().join('|') === [...fields].sort().join('|');
const validUnicode = (v: string) => !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v);
const text = (v: unknown, max: number, blank = false): v is string => typeof v === 'string' && v.length <= max && validUnicode(v) && utf8.encode(v).length <= max && (blank || !!v.trim());
const id = (v: unknown): v is string => text(v, 200);
const findingId = (v: unknown): v is string => typeof v === 'string' && /^artifact_[a-f0-9]{64}$/.test(v);
const sequence = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const requestId = (v: unknown): v is string => typeof v === 'string' && /^[\x20-\x7e]{1,128}$/.test(v) && !!v.trim();

export function isAuthoredFinding(value: unknown): value is AuthoredFinding {
  if (!shape(value, ['id', 'kind', 'contextId', 'text', 'citations', 'unsupportedCitations', 'artifactCitations', 'unsupportedArtifactCitations', 'authorship'])
      || !findingId(value.id) || value.kind !== 'owner-authored-finding' || !id(value.contextId) || !text(value.text, MAX_FINDING_BYTES)
      || !shape(value.authorship, ['kind', 'createdAtMs']) || value.authorship.kind !== 'local-owner'
      || typeof value.authorship.createdAtMs !== 'number' || !Number.isSafeInteger(value.authorship.createdAtMs) || value.authorship.createdAtMs < 0) return false;
  for (const field of ['citations', 'unsupportedCitations']) {
    const values = value[field];
    if (!Array.isArray(values) || values.some((n, i) => !(sequence(n) || field === 'unsupportedCitations' && n === 0) || i > 0 && n <= values[i - 1])) return false;
  }
  for (const field of ['artifactCitations', 'unsupportedArtifactCitations']) {
    const values = value[field];
    if (!Array.isArray(values) || values.some((n, i) => typeof n !== 'string' || !/^[A-Za-z0-9_-]+$/.test(n) || i > 0 && n <= values[i - 1])) return false;
  }
  return true;
}
export function findingSupport(finding: AuthoredFinding): string {
  return finding.citations.length || finding.artifactCitations.length ? 'Cited sources supplied; claims not verified' : 'No cited support';
}
export async function authoredFindingId(owner: string, finding: Omit<AuthoredFinding, 'id' | 'authorship'>): Promise<string> {
  const content = { domain: 'eidos.owner-authored-finding/v1', investigationId: owner, kind: finding.kind, contextId: finding.contextId,
    text: finding.text, citations: finding.citations, unsupportedCitations: finding.unsupportedCitations,
    artifactCitations: finding.artifactCitations, unsupportedArtifactCitations: finding.unsupportedArtifactCitations };
  const canonical = JSON.stringify(Object.fromEntries(Object.entries(content).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)));
  const hash = await crypto.subtle.digest('SHA-256', utf8.encode(canonical));
  return 'artifact_' + [...new Uint8Array(hash)].map(n => n.toString(16).padStart(2, '0')).join('');
}
export async function checkAuthoredFinding(value: unknown, owner: string): Promise<AuthoredFinding> {
  if (!isAuthoredFinding(value) || await authoredFindingId(owner, value) !== value.id) throw Error('The authored finding does not match its recorded owner and content.');
  return value;
}
function readRequest(raw: string): { requestId: string; contextId: string; text: string } {
  if (utf8.encode(raw).length > MAX_BODY) throw Error('The exact finding request exceeds 256 KiB.');
  const v = JSON.parse(raw);
  if (!shape(v, ['requestId', 'contextId', 'text']) || !requestId(v.requestId) || !id(v.contextId) || !text(v.text, MAX_FINDING_BYTES)) throw Error('Saved finding request is unavailable. Its recovery entry was retained.');
  return v as { requestId: string; contextId: string; text: string };
}
export function readFindingDraft(raw: string): FindingDraft {
  if (raw.length > MAX_SLOT || utf8.encode(raw).length > MAX_SLOT) throw Error('Finding recovery exceeds its 512 KiB limit. Its entry was retained.');
  const v = JSON.parse(raw);
  if (!shape(v, ['version', 'source', 'text', 'request', 'savedId']) || v.version !== 1
      || !shape(v.source, ['investigationId', 'contextId', 'title', 'question']) || !id(v.source.investigationId) || !id(v.source.contextId)
      || !text(v.source.title, 800) || !text(v.source.question, 64000)) throw Error('Finding recovery is unavailable. Its entry was retained.');
  if (v.request === null) {
    if (!text(v.text, MAX_FINDING_BYTES, true) || v.savedId !== null) throw Error('Invalid staged finding metadata.');
  } else {
    if (typeof v.request !== 'string' || v.text !== null || v.savedId !== null && !findingId(v.savedId)) throw Error('Invalid pending finding metadata.');
    if (readRequest(v.request).contextId !== v.source.contextId) throw Error('Saved finding request has a different context pin.');
  }
  return v as FindingDraft;
}
export function findingDraftText(draft: FindingDraft): string { return draft.request === null ? draft.text! : readRequest(draft.request).text; }
async function readResponse(response: Response): Promise<unknown> {
  const reader = response.body?.getReader();
  if (!reader) throw Error('The finding response is unavailable.');
  let total = 0;
  const chunks: Uint8Array[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      total += value.byteLength;
      if (total > MAX_BODY) { await reader.cancel(); throw Error('The finding response exceeds 256 KiB.'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'Finding save was not confirmed. Check this exact request again.';

export class AuthoredFindingClient {
  state: FindingState = emptyFindingState();
  private raw: string | null = null;
  private operation: Promise<void> | null = null;
  private disposed = false;
  constructor(private storage: Storage, private changed: (state: FindingState) => void,
    private fetcher: Fetcher = (url, init) => fetch(url, init), private newId: () => string = () => crypto.randomUUID()) {}
  private update(patch: Partial<FindingState>) { this.state = { ...this.state, ...patch }; if (!this.disposed) this.changed(this.state); }
  private sameSlot() {
    try {
      if (this.state.unavailable || this.storage.getItem(FINDING_KEY) !== this.raw) throw Error('Finding recovery changed in another view. Reload before continuing.');
      return true;
    } catch (cause) { this.update({ unavailable: true, error: message(cause) }); return false; }
  }
  restore() {
    try {
      this.raw = this.storage.getItem(FINDING_KEY);
      this.update({ draft: this.raw === null ? null : readFindingDraft(this.raw), error: '' });
    } catch (cause) { this.update({ unavailable: true, error: message(cause) }); }
  }
  private persist(draft: FindingDraft | null): boolean {
    if (this.disposed || !this.sameSlot()) return false;
    try {
      const raw = draft === null ? null : JSON.stringify(draft);
      if (raw !== null) { readFindingDraft(raw); this.storage.setItem(FINDING_KEY, raw); }
      else this.storage.removeItem(FINDING_KEY);
      this.raw = raw;
      this.update({ draft, error: '' }); return true;
    } catch (cause) { this.update({ error: `Could not preserve finding recovery. ${message(cause)}` }); return false; }
  }
  stage(owner: Investigation, context: InvestigationContext): boolean {
    const pinned = owner.contexts.find(c => c.id === context.id);
    if (this.disposed || this.operation || this.state.draft || !pinned) return false;
    const okay = this.persist({ version: 1, source: { investigationId: owner.id, contextId: pinned.id, title: owner.title, question: pinned.question }, text: '', request: null, savedId: null });
    if (okay) this.update({ finding: null, refusal: '' });
    return okay;
  }
  edit(value: string) {
    if (this.disposed || this.operation || !this.state.draft || this.state.draft.request !== null) return;
    if (!text(value, MAX_FINDING_BYTES, true)) { this.update({ error: 'Finding text must be valid UTF-8 and at most 128 KiB. The previous draft was retained.' }); return; }
    this.persist({ ...this.state.draft, text: value });
  }
  save(): Promise<void> {
    if (this.operation) return this.operation;
    const draft = this.state.draft;
    if (this.disposed || !draft || draft.savedId || !findingDraftText(draft).trim() || !this.sameSlot()) return Promise.resolve();
    const request = draft.request ?? JSON.stringify({ requestId: this.newId(), contextId: draft.source.contextId, text: draft.text });
    if (!this.persist({ ...draft, text: null, request })) return Promise.resolve();
    this.update({ busy: true, error: '', refusal: '' });
    this.operation = this.resolve(this.state.draft!, true).finally(() => { this.operation = null; this.update({ busy: false }); });
    return this.operation;
  }
  checkReceipt(): Promise<void> {
    if (this.operation) return this.operation;
    const draft = this.state.draft;
    if (this.disposed || !draft?.request || !this.sameSlot()) return Promise.resolve();
    this.update({ busy: true, error: '', refusal: '' });
    this.operation = this.resolve(draft, false).finally(() => { this.operation = null; this.update({ busy: false }); });
    return this.operation;
  }
  private async resolve(draft: FindingDraft, sending: boolean) {
    try {
      const request = readRequest(draft.request!);
      const route = `/api/investigations/${encodeURIComponent(draft.source.investigationId)}/findings`;
      const response = await this.fetcher(sending ? route : `${route}/requests/${encodeURIComponent(request.requestId)}`, sending
        ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: draft.request! } : undefined);
      const value = await readResponse(response);
      if (this.disposed || !this.sameSlot()) return;
      if (!response.ok) {
        if (!sending && response.status === 404) throw Error('No finding receipt was found. The outcome remains unknown; retry preserves this exact request.');
        if (sending && [400, 404, 409, 413].includes(response.status) && shape(value, ['error']) && text(value.error, 2000)) {
          this.update({ refusal: `Server refused this request (${response.status}): ${value.error}` }); return;
        }
        throw Error(object(value) && typeof value.error === 'string' ? value.error.slice(0, 2000) : 'Finding save was not confirmed. Check this exact request again.');
      }
      if (!shape(value, ['finding'])) throw Error('Finding receipt is unavailable. Its recovery identity was retained.');
      const finding = await checkAuthoredFinding(value.finding, draft.source.investigationId);
      if (finding.contextId !== request.contextId || finding.text !== request.text || draft.savedId !== null && finding.id !== draft.savedId) throw Error('The receipt does not match the exact saved finding request.');
      if (this.disposed || !this.sameSlot()) return;
      if (this.persist({ ...draft, savedId: finding.id })) this.update({ finding, error: '', refusal: '' });
    } catch (cause) { if (!this.disposed) this.update({ error: message(cause) }); }
  }
  dismiss() {
    if (this.disposed || this.operation || !this.state.draft || this.state.draft.request && !this.state.draft.savedId && !this.state.refusal) return;
    if (this.persist(null)) this.update({ finding: null, refusal: '' });
  }
  dispose() { this.disposed = true; }
}
