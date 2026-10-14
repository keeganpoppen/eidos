import { bytesBase64, sha256 } from './history-import';
import type { LocalTextEvidence } from './types';

export const SUPPLIED_TEXT_KEY = 'nema.supplied-text.v1';
export const TEXT_FORMAT = 'supplied-text/v1';
export const TEXT_PARSER = 'supplied-text-admission/v1';
export const MAX_TEXT_BYTES = 65536;
const utf8 = new TextEncoder();
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const shape = (v: unknown, keys: string[]): v is Record<string, unknown> => object(v) && Object.keys(v).sort().join('|') === [...keys].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const count = (v: unknown, max = Number.MAX_SAFE_INTEGER): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= max;
const label = (v: unknown, max = 255): v is string => typeof v === 'string' && !!v.trim() && utf8.encode(v).length <= max
  && !/[\u0000-\u001f\u007f]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v);
const filename = (v: unknown): v is string => label(v) && !/[\\/]/.test(v) && !['.', '..'].includes(v);
const requestId = (v: unknown): v is string => typeof v === 'string' && /^[\x20-\x7e]{1,128}$/.test(v) && !!v.trim();
const message = (cause: unknown): string => cause instanceof Error ? cause.message : 'Text admission was not confirmed. Check this same request again.';

export type TextPreview = {
  format: typeof TEXT_FORMAT; fileName: string; fileSha256: string; byteLength: number; parserVersion: string;
  previewFingerprint: string; classification: 'local-owner-supplied'; textExcerpt: string; truncated: boolean; discoverableFieldCount: number;
};
export type TextReceipt = TextPreview & {
  id: string; requestId: string; admittedAtMs: number; source: string; threadId: string; turnId: string; itemId: string; seq: number; hostRecordSha256: string;
};
export type TextRequest = Pick<TextPreview, 'format' | 'fileName' | 'fileSha256' | 'byteLength' | 'parserVersion' | 'previewFingerprint'> & { version: 1; requestId: string };
export type SuppliedTextState = {
  fileName: string; byteLength: number; hasFile: boolean; reading: boolean; previewing: boolean; sending: boolean; checking: boolean; downloading: boolean;
  pending: TextRequest | null; preview: TextPreview | null; receipt: TextReceipt | null; error: string; refusal: string; unavailable: boolean;
};
export const emptyTextState = (): SuppliedTextState => ({ fileName: '', byteLength: 0, hasFile: false, reading: false, previewing: false, sending: false, checking: false, downloading: false, pending: null, preview: null, receipt: null, error: '', refusal: '', unavailable: false });
const requestKeys = ['version', 'requestId', 'format', 'fileName', 'fileSha256', 'byteLength', 'parserVersion', 'previewFingerprint'];
const previewKeys = ['format', 'fileName', 'fileSha256', 'byteLength', 'parserVersion', 'previewFingerprint', 'classification', 'textExcerpt', 'truncated', 'discoverableFieldCount'];

export function readTextRequest(raw: string): TextRequest {
  if (utf8.encode(raw).length > 4096) throw Error('Text recovery exceeds 4 KiB. Its entry was retained.');
  const v: unknown = JSON.parse(raw);
  if (!shape(v, requestKeys) || v.version !== 1 || !requestId(v.requestId) || v.format !== TEXT_FORMAT || !filename(v.fileName)
      || !hash(v.fileSha256) || !count(v.byteLength, MAX_TEXT_BYTES) || !label(v.parserVersion, 200) || !hash(v.previewFingerprint)) throw Error('Text recovery metadata is unavailable. Its entry was retained.');
  return v as TextRequest;
}
function previewFields(v: unknown): v is TextPreview {
  return object(v) && v.format === TEXT_FORMAT && filename(v.fileName) && hash(v.fileSha256) && count(v.byteLength, MAX_TEXT_BYTES)
    && label(v.parserVersion, 200) && hash(v.previewFingerprint) && v.classification === 'local-owner-supplied'
    && typeof v.textExcerpt === 'string' && [...v.textExcerpt].length <= 480 && typeof v.truncated === 'boolean' && count(v.discoverableFieldCount, 1);
}
const sameReceipt = (a: TextReceipt, b: TextReceipt) => Object.keys(a).every(key => a[key as keyof TextReceipt] === b[key as keyof TextReceipt]);
export function readTextPreview(value: unknown, file: { fileName: string; fileSha256: string; byteLength: number }): TextPreview {
  if (!shape(value, ['preview']) || !shape(value.preview, previewKeys) || !previewFields(value.preview)
      || value.preview.parserVersion !== TEXT_PARSER || value.preview.fileName !== file.fileName || value.preview.fileSha256 !== file.fileSha256 || value.preview.byteLength !== file.byteLength) throw Error('Text preview does not match the chosen file. Preview it again.');
  return value.preview;
}
export function readTextReceipt(value: unknown, expected: TextRequest): TextReceipt {
  if (!shape(value, ['receipt']) || !shape(value.receipt, [...previewKeys, 'id', 'requestId', 'admittedAtMs', 'source', 'threadId', 'turnId', 'itemId', 'seq', 'hostRecordSha256'])
      || !previewFields(value.receipt)) throw Error('Text receipt is unavailable. Check this same request again.');
  const v = value.receipt as TextPreview & Record<string, unknown>;
  if (!['format', 'fileName', 'fileSha256', 'byteLength', 'parserVersion', 'previewFingerprint', 'requestId'].every(key => v[key] === expected[key as keyof TextRequest])
      || !['id', 'source', 'threadId', 'turnId', 'itemId'].every(key => label(v[key], 256))
      || !(v.threadId as string).startsWith('local-document_') || !count(v.admittedAtMs) || !count(v.seq) || !v.seq || !hash(v.hostRecordSha256)) throw Error('Text receipt does not match this exact request. Its recovery identity was retained.');
  return v as TextReceipt;
}
export function isLocalTextEvidence(v: unknown): v is LocalTextEvidence {
  return object(v) && v.kind === 'supplied-text' && v.version === 1 && label(v.id, 200) && filename(v.fileName)
    && hash(v.fileSha256) && count(v.byteLength, MAX_TEXT_BYTES) && v.classification === 'local-owner-supplied'
    && label(v.parserVersion, 200) && hash(v.hostRecordSha256);
}
/** Prefix/metadata may deny native messaging; neither establishes document provenance. */
export function sourceOnly(id: string, value?: { sourceOnly?: boolean; sourceKind?: string } | null): boolean {
  return id.startsWith('local-document_') || value?.sourceOnly === true || value?.sourceKind === 'supplied-text';
}
/** Frozen descriptive metadata is retained separately from the generated envelope. */
export function frozenText(raw: string, evidence: unknown, hostHash: string): string | null {
  if (!isLocalTextEvidence(evidence) || evidence.hostRecordSha256 !== hostHash) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!object(value) || value.method !== '$local/document' || !object(value.params) || !object(value.params.item)
        || value.params.item.type !== 'suppliedText' || typeof value.params.item.text !== 'string') return null;
    return utf8.encode(value.params.item.text).length === evidence.byteLength ? value.params.item.text : null;
  } catch { return null; }
}
async function responseJson(response: Response): Promise<unknown> {
  const reader = response.body?.getReader(); if (!reader) throw Error('Text response is unavailable.');
  let total = 0; const chunks: Uint8Array[] = [];
  try {
    while (true) { const { done, value } = await reader.read(); if (done) break; total += value.byteLength;
      if (total > 131072) { await reader.cancel(); throw Error('Text response exceeds 128 KiB.'); } chunks.push(value); }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;
type FileInput = Pick<File, 'name' | 'size' | 'arrayBuffer'>;

export class SuppliedTextClient {
  state = emptyTextState();
  private stored: string | null = null;
  private bytes: Uint8Array<ArrayBuffer> | null = null;
  private fileHash = '';
  private generation = 0;
  private active = true;
  private disposed = false;
  private abort: AbortController | null = null;
  private operation: Promise<void> | null = null;
  constructor(private storage: Storage, private changed: (state: SuppliedTextState) => void, private fetcher: Fetcher = (url, init) => fetch(url, init), private newId = () => crypto.randomUUID()) {}
  private update(patch: Partial<SuppliedTextState>) { if (!this.disposed) { this.state = { ...this.state, ...patch }; this.changed(this.state); } }
  private current(generation: number) { return !this.disposed && this.active && generation === this.generation; }
  private slot() {
    if (this.disposed) return false;
    try { if (this.state.unavailable || this.storage.getItem(SUPPLIED_TEXT_KEY) !== this.stored) throw Error('Text recovery changed in another view. Reload before continuing.'); return true; }
    catch (cause) { this.update({ error: message(cause), unavailable: true }); return false; }
  }
  restore() {
    if (this.disposed) return;
    try { this.stored = this.storage.getItem(SUPPLIED_TEXT_KEY); const pending = this.stored === null ? null : readTextRequest(this.stored);
      this.update({ pending, ...(pending ? { fileName: pending.fileName, byteLength: pending.byteLength } : {}) }); }
    catch (cause) { this.update({ error: message(cause), unavailable: true }); }
  }
  private persist(pending: TextRequest | null) {
    if (!this.slot()) return false;
    try { const raw = pending === null ? null : JSON.stringify(pending);
      if (raw !== null) { readTextRequest(raw); this.storage.setItem(SUPPLIED_TEXT_KEY, raw); } else this.storage.removeItem(SUPPLIED_TEXT_KEY);
      this.stored = raw; this.update({ pending, error: '' }); return true;
    } catch (cause) { this.update({ error: `Could not preserve text recovery. No new request was sent. ${message(cause)}` }); return false; }
  }
  navigate(active = this.active) { this.active = active; this.generation++; this.abort?.abort(); this.abort = null; this.update({ reading: false, previewing: false, downloading: false }); }
  dispose() { this.navigate(false); this.disposed = true; }
  async choose(file: FileInput) {
    if (!this.active || this.disposed || this.operation || this.state.receipt || !this.slot()) return;
    this.navigate(); const generation = this.generation; this.bytes = null; this.fileHash = '';
    this.update({ hasFile: false, preview: null, error: '' });
    try {
      if (!count(file.size, MAX_TEXT_BYTES)) throw Error('Choose a UTF-8 file no larger than 64 KiB.');
      if (!filename(file.name)) throw Error('Choose a display basename of at most 255 UTF-8 bytes.');
      this.update({ reading: true, fileName: this.state.pending?.fileName ?? file.name, byteLength: this.state.pending?.byteLength ?? file.size });
      const bytes = new Uint8Array(await file.arrayBuffer()); if (!this.current(generation)) return;
      if (bytes.length !== file.size) throw Error('The chosen file changed while reading. Choose it again.');
      new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
      const digest = await sha256(bytes); if (!this.current(generation)) return;
      const pending = this.state.pending;
      if (pending && (digest !== pending.fileSha256 || bytes.length !== pending.byteLength)) throw Error('This file does not match the pending request. Reselect the exact original bytes.');
      this.bytes = bytes; this.fileHash = digest; this.update({ hasFile: true });
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
    finally { if (this.current(generation)) this.update({ reading: false }); }
  }
  async preview() {
    if (!this.active || this.disposed || this.operation || this.state.pending || !this.bytes || !this.slot()) return;
    this.navigate(); const generation = this.generation, abort = this.abort = new AbortController();
    const expected = { fileName: this.state.fileName, fileSha256: this.fileHash, byteLength: this.bytes.length };
    this.update({ previewing: true, preview: null, error: '' });
    try {
      const response = await this.fetcher('/api/evidence/files/preview', { method: 'POST', signal: abort.signal, headers: { 'content-type': 'application/json' }, body: JSON.stringify({ format: TEXT_FORMAT, fileName: expected.fileName, contentBase64: bytesBase64(this.bytes) }) });
      const value = await responseJson(response); if (!this.current(generation)) return;
      if (!response.ok) throw Error(object(value) && typeof value.error === 'string' ? value.error : 'Text preview failed. Nothing was added.');
      this.update({ preview: readTextPreview(value, expected) });
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
    finally { if (this.current(generation)) this.update({ previewing: false }); }
  }
  commit(): Promise<void> {
    if (this.operation) return this.operation;
    if (!this.active || this.disposed || this.state.receipt || !this.bytes || !this.state.hasFile || !this.slot()) return Promise.resolve();
    const p = this.state.preview;
    if (!this.state.pending && !p) return Promise.resolve();
    const request: TextRequest = this.state.pending ?? { version: 1, requestId: this.newId(), format: TEXT_FORMAT, fileName: p!.fileName, fileSha256: p!.fileSha256, byteLength: p!.byteLength, parserVersion: p!.parserVersion, previewFingerprint: p!.previewFingerprint };
    if (request.fileSha256 !== this.fileHash || request.byteLength !== this.bytes.length || !this.persist(request)) return Promise.resolve();
    this.navigate(); this.update({ sending: true, refusal: '', error: '' });
    this.operation = this.resolve(request, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ format: request.format, fileName: request.fileName, contentBase64: bytesBase64(this.bytes), requestId: request.requestId, previewFingerprint: request.previewFingerprint }) }).finally(() => { this.operation = null; this.update({ sending: false }); });
    return this.operation;
  }
  checkReceipt(): Promise<void> {
    if (this.operation) return this.operation;
    if (!this.active || this.disposed || !this.state.pending || !this.slot()) return Promise.resolve();
    this.navigate(); this.update({ checking: true, refusal: '', error: '' });
    this.operation = this.resolve(this.state.pending).finally(() => { this.operation = null; this.update({ checking: false }); }); return this.operation;
  }
  private async resolve(request: TextRequest, init?: RequestInit) {
    const generation = this.generation;
    try {
      const response = await this.fetcher(init ? '/api/evidence/files' : `/api/evidence/files/requests/${encodeURIComponent(request.requestId)}`, init);
      const value = await responseJson(response); if (!this.current(generation) || !this.slot()) return;
      if (!response.ok) {
        if (!init && response.status === 404) throw Error('No receipt was found. The outcome remains unknown; reselect the exact file to retry this request.');
        if (init && [400, 409, 413, 422].includes(response.status) && shape(value, ['error']) && label(value.error, 1000)) { this.update({ refusal: value.error }); return; }
        throw Error(object(value) && typeof value.error === 'string' ? value.error : 'Text admission was not confirmed. Check this same request again.');
      }
      const receipt = readTextReceipt(value, request);
      if (this.state.receipt && !sameReceipt(receipt, this.state.receipt)) throw Error('The saved text receipt changed. The previous exact reference was retained.');
      this.update({ receipt, error: '', hasFile: false }); this.bytes = null; this.fileHash = '';
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
  }
  canUse(receipt: TextReceipt) { return !this.disposed && this.active && this.state.receipt?.id === receipt.id && this.slot(); }
  async original(): Promise<{ receipt: TextReceipt; bytes: Uint8Array<ArrayBuffer> } | null> {
    const receipt = this.state.receipt, request = this.state.pending;
    if (!receipt || !request || !this.canUse(receipt) || this.operation || this.state.downloading) return null;
    this.navigate(); const generation = this.generation, abort = this.abort = new AbortController(); this.update({ downloading: true, error: '' });
    try {
      const response = await this.fetcher(`/api/evidence/files/${encodeURIComponent(receipt.id)}`, { signal: abort.signal });
      const value = await responseJson(response); if (!this.current(generation) || !this.slot()) return null;
      if (!response.ok || !shape(value, ['receipt', 'contentBase64']) || typeof value.contentBase64 !== 'string') throw Error('Original file bytes are unavailable.');
      const actual = readTextReceipt({ receipt: value.receipt }, request);
      if (!sameReceipt(actual, receipt)) throw Error('Original file receipt changed. Check the exact receipt again.');
      const bytes = Uint8Array.from(atob(value.contentBase64), c => c.charCodeAt(0));
      if (bytesBase64(bytes) !== value.contentBase64 || bytes.length !== receipt.byteLength || await sha256(bytes) !== receipt.fileSha256) throw Error('Original file bytes do not match their receipt.');
      if (this.current(generation) && this.slot()) return { receipt, bytes };
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
    finally { if (this.current(generation)) this.update({ downloading: false }); }
    return null;
  }
  startAnother(refused = false) {
    if (!this.active || this.disposed || this.operation || (refused ? !this.state.refusal : !this.state.receipt) || !this.persist(null)) return;
    this.navigate(); this.bytes = null; this.fileHash = ''; this.update(emptyTextState());
  }
}
