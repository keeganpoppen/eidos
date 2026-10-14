export const HISTORY_IMPORT_KEY = 'nema.history-import.v1';
export const IMPORT_FORMAT = 'appserver-jsonl/v1';
export const IMPORT_PARSER = 'history-import-parser/v1';
export const IMPORT_SCOPE = 'displayed-history-text/v1';
export const MAX_IMPORT_BYTES = 8 * 1024 * 1024;
export const MAX_IMPORT_RESPONSE = 128 * 1024;
export type ImportDirection = 'appserver_to_client' | 'client_to_appserver';
export type ImportSummary = { threadCount: number; turnCount: number; unscopedRecordCount: number; discoverableFieldCount: number };
export type ImportPreview = {
  format: typeof IMPORT_FORMAT; parserVersion: string; discoveryScope: string; fileSha256: string; byteLength: number;
  operationFingerprint: string; previewFingerprint: string; recordCount: number; blankLineCount: number; physicalLineCount: number;
  summary: ImportSummary; warnings: string[]; committable: boolean; reason: null | 'no-discoverable-history';
};
export type ImportRequest = {
  requestId: string; format: typeof IMPORT_FORMAT; source: string; direction: ImportDirection;
  fileSha256: string; byteLength: number; previewFingerprint: string; operationFingerprint: string; fileName: string;
};
export type ImportReceipt = Omit<ImportPreview, 'committable' | 'reason'> & {
  id: string; requestId: string; fileName: string; source: string; captureSource: string; direction: ImportDirection; createdAtMs: number;
};
export type ImportState = {
  source: string; direction: ImportDirection; fileName: string; byteLength: number; hasFile: boolean;
  reading: boolean; previewing: boolean; sending: boolean; checking: boolean; unavailable: boolean;
  preview: ImportPreview | null; pending: ImportRequest | null; receipt: ImportReceipt | null; error: string;
  refusal: { status: number; message: string } | null;
};
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;
type ChosenFile = Pick<File, 'size' | 'name' | 'arrayBuffer'>;
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const shape = (v: unknown, keys: string[]): v is Record<string, unknown> => object(v) && Object.keys(v).sort().join('|') === [...keys].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const count = (v: unknown, maximum = Number.MAX_SAFE_INTEGER): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= maximum;
const utf8 = new TextEncoder();
const label = (v: unknown, maximum: number): v is string => typeof v === 'string' && !!v.trim() && v.length <= maximum
  && !/[\u0000-\u001f\u007f]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v) && utf8.encode(v).byteLength <= maximum;
const filename = (v: unknown): v is string => label(v, 255) && !/[\\/]/.test(v);
const direction = (v: unknown): v is ImportDirection => v === 'appserver_to_client' || v === 'client_to_appserver';
const requestId = (v: unknown): v is string => typeof v === 'string' && /^[\x20-\x7e]{1,128}$/.test(v) && !!v.trim();
const warnings = new Set(['file-local-preview', 'single-direction-capture', 'unscoped-records', 'no-discoverable-history']);
const requestKeys = ['requestId', 'format', 'source', 'direction', 'fileSha256', 'byteLength', 'previewFingerprint', 'operationFingerprint', 'fileName'];
const previewKeys = ['format', 'parserVersion', 'discoveryScope', 'fileSha256', 'byteLength', 'operationFingerprint', 'previewFingerprint',
  'recordCount', 'blankLineCount', 'physicalLineCount', 'summary', 'warnings', 'committable', 'reason'];

export const emptyImportState = (): ImportState => ({ source: 'imported-history', direction: 'appserver_to_client', fileName: '', byteLength: 0,
  hasFile: false, reading: false, previewing: false, sending: false, checking: false, unavailable: false,
  preview: null, pending: null, receipt: null, error: '', refusal: null });

/** Recovery stores only bounded identity metadata, never file contents. */
export function readImportRequest(raw: string): ImportRequest {
  if (raw.length > 4096) throw Error('Import recovery metadata exceeds its limit. It was retained.');
  const v: unknown = JSON.parse(raw);
  if (!shape(v, requestKeys) || v.format !== IMPORT_FORMAT || !requestId(v.requestId) || !label(v.source, 256) || !direction(v.direction)
      || !hash(v.fileSha256) || !hash(v.previewFingerprint) || !hash(v.operationFingerprint) || !count(v.byteLength, MAX_IMPORT_BYTES)
      || v.byteLength === 0 || !filename(v.fileName)) throw Error('Import recovery metadata is unavailable. Its entry was retained.');
  return v as ImportRequest;
}
export async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
}
export async function operationFingerprint(v: Pick<ImportRequest, 'format' | 'source' | 'direction' | 'fileSha256' | 'byteLength'>): Promise<string> {
  // Exact sorted-key UTF-8 canonical object used by the byte importer.
  return sha256(utf8.encode(JSON.stringify({ byteLength: v.byteLength, direction: v.direction, fileSha256: v.fileSha256, format: v.format, source: v.source })));
}
export function bytesBase64(bytes: Uint8Array): string {
  let text = '';
  for (let i = 0; i < bytes.length; i += 16384) text += String.fromCharCode(...bytes.subarray(i, i + 16384));
  return btoa(text);
}
function checkedSummary(v: Record<string, unknown>): void {
  if (!count(v.recordCount, 20000) || !v.recordCount || !count(v.blankLineCount, 20000) || !count(v.physicalLineCount, 20000)
      || v.recordCount + v.blankLineCount !== v.physicalLineCount
      || !shape(v.summary, ['threadCount', 'turnCount', 'unscopedRecordCount', 'discoverableFieldCount'])
      || !Object.values(v.summary).every(n => count(n)) || (v.summary.unscopedRecordCount as number) > v.recordCount
      || !Array.isArray(v.warnings) || v.warnings.length > 4 || !v.warnings.every(w => typeof w === 'string' && warnings.has(w))
      || new Set(v.warnings).size !== v.warnings.length) throw Error('Import summary is unavailable. Nothing was confirmed.');
}
export function readImportPreview(value: unknown, expected: { fileSha256: string; byteLength: number; operationFingerprint: string }): ImportPreview {
  if (!shape(value, ['preview']) || !shape(value.preview, previewKeys)) throw Error('Import preview is unavailable. Review the file again.');
  const v = value.preview;
  if (v.format !== IMPORT_FORMAT || v.parserVersion !== IMPORT_PARSER || v.discoveryScope !== IMPORT_SCOPE
      || v.fileSha256 !== expected.fileSha256 || v.byteLength !== expected.byteLength || v.operationFingerprint !== expected.operationFingerprint
      || !hash(v.previewFingerprint) || typeof v.committable !== 'boolean' || ![null, 'no-discoverable-history'].includes(v.reason as null)) throw Error('Import preview does not match the chosen file and options.');
  checkedSummary(v);
  const readable = (v.summary as ImportSummary).discoverableFieldCount > 0;
  if (v.committable !== readable || v.reason !== (readable ? null : 'no-discoverable-history')) throw Error('Import preview has inconsistent readable-history counts.');
  return v as ImportPreview;
}
export function readImportReceipt(value: unknown, expected: ImportRequest): ImportReceipt {
  if (!shape(value, ['receipt']) || !object(value.receipt)) throw Error('Import receipt is unavailable. Check this same request again.');
  const v = value.receipt;
  if (!shape(v, [...previewKeys.filter(k => k !== 'committable' && k !== 'reason'), 'id', 'requestId', 'fileName', 'source', 'captureSource', 'direction', 'createdAtMs'])
      || !label(v.id, 200) || !filename(v.fileName) || !label(v.captureSource, 256) || !count(v.createdAtMs)
      || !label(v.parserVersion, 200) || !label(v.discoveryScope, 200)
      || !['requestId', 'format', 'source', 'direction', 'fileSha256', 'byteLength', 'previewFingerprint', 'operationFingerprint'].every(k => v[k] === expected[k as keyof ImportRequest])
      || v.captureSource !== `history-import:${v.id}`) throw Error('Import receipt does not match this exact request. Its recovery identity was retained.');
  checkedSummary(v);
  return v as ImportReceipt;
}
async function responseJson(response: Response): Promise<unknown> {
  const reader = response.body?.getReader();
  if (!reader) throw Error('Import response is unavailable.');
  let total = 0;
  const chunks: Uint8Array[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_IMPORT_RESPONSE) { await reader.cancel(); throw Error('Import response exceeds its 128 KiB limit.'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(joined));
}
const message = (cause: unknown): string => cause instanceof Error ? cause.message : 'Import was not confirmed. Check this same request again.';

export class HistoryImportClient {
  state: ImportState = emptyImportState();
  private stored: string | null = null;
  private bytes: Uint8Array<ArrayBuffer> | null = null;
  private fileHash = '';
  private generation = 0;
  private active = true;
  private disposed = false;
  private readAbort: AbortController | null = null;
  private operation: Promise<void> | null = null;
  constructor(private storage: Storage, private changed: (state: ImportState) => void,
    private fetcher: Fetcher = (url, init) => fetch(url, init), private newId: () => string = () => crypto.randomUUID()) {}
  private update(patch: Partial<ImportState>) { this.state = { ...this.state, ...patch }; if (!this.disposed) this.changed(this.state); }
  private current(generation: number) { return !this.disposed && this.active && generation === this.generation; }
  private slot(): boolean {
    try {
      if (this.state.unavailable || this.storage.getItem(HISTORY_IMPORT_KEY) !== this.stored) throw Error('Import recovery changed in another view. Reload before continuing.');
      return true;
    } catch (cause) { this.update({ error: message(cause), unavailable: true }); return false; }
  }
  restore() {
    try {
      this.stored = this.storage.getItem(HISTORY_IMPORT_KEY);
      const pending = this.stored === null ? null : readImportRequest(this.stored);
      this.update({ pending, ...(pending ? { source: pending.source, direction: pending.direction, fileName: pending.fileName, byteLength: pending.byteLength } : {}), error: '' });
    } catch (cause) { this.update({ unavailable: true, error: message(cause) }); }
  }
  private persist(pending: ImportRequest | null): boolean {
    if (!this.slot()) return false;
    try {
      const raw = pending === null ? null : JSON.stringify(pending);
      if (raw !== null) { readImportRequest(raw); this.storage.setItem(HISTORY_IMPORT_KEY, raw); }
      else this.storage.removeItem(HISTORY_IMPORT_KEY);
      this.stored = raw;
      this.update({ pending, error: '' });
      return true;
    } catch (cause) { this.update({ error: `Could not preserve import recovery. No new request was sent. ${message(cause)}` }); return false; }
  }
  /** Closing or navigating cancels previews; exact commit/receipt work never opens a view. */
  navigate(active = this.active) {
    this.active = active; this.generation++; this.readAbort?.abort(); this.readAbort = null;
    this.update({ reading: false, previewing: false });
  }
  dispose() { this.disposed = true; this.navigate(false); }
  edit(field: 'source' | 'direction', value: string) {
    if (this.state.pending || this.state.unavailable || this.disposed) return;
    if (field === 'direction' && !direction(value)) return;
    const wasReading = this.state.reading;
    this.navigate();
    this.update({ [field]: value, preview: null, error: '', ...(wasReading ? { hasFile: false, fileName: '', byteLength: 0 } : {}) });
  }
  async choose(file: ChosenFile) {
    if (!this.active || this.disposed || this.operation || this.state.receipt || !this.slot()) return;
    this.navigate();
    const generation = this.generation;
    this.bytes = null; this.fileHash = '';
    this.update({ hasFile: false, preview: null, error: '', reading: false });
    try {
      if (!count(file.size, MAX_IMPORT_BYTES) || !file.size) throw Error('Choose a nonempty file no larger than 8 MiB.');
      if (!filename(file.name)) throw Error('Choose a file with a basename no longer than 255 UTF-8 bytes.');
      this.update({ reading: true, fileName: file.name, byteLength: file.size });
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (!this.current(generation)) return;
      if (bytes.byteLength !== file.size) throw Error('The chosen file size changed while reading. Choose it again.');
      const fileHash = await sha256(bytes);
      if (!this.current(generation)) return;
      const pending = this.state.pending;
      if (pending && (fileHash !== pending.fileSha256 || bytes.byteLength !== pending.byteLength)) throw Error('This file does not match the pending import. Reselect the original bytes.');
      this.bytes = bytes; this.fileHash = fileHash;
      this.update({ hasFile: true, ...(pending ? { fileName: pending.fileName, byteLength: pending.byteLength } : {}) });
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
    finally { if (this.current(generation)) this.update({ reading: false }); }
  }
  async preview() {
    if (!this.active || this.disposed || this.state.pending || !this.bytes || !this.state.hasFile || !this.slot()) return;
    this.navigate();
    const generation = this.generation;
    const bytes = this.bytes, fileSha256 = this.fileHash;
    const { source, direction, fileName } = this.state;
    this.update({ previewing: true, preview: null, error: '' });
    const abort = this.readAbort = new AbortController();
    try {
      if (!label(source, 256)) throw Error('Enter an origin label of 1–256 UTF-8 bytes without control characters.');
      const expected = { fileSha256, byteLength: bytes.byteLength, operationFingerprint: await operationFingerprint({ format: IMPORT_FORMAT, source, direction, fileSha256, byteLength: bytes.byteLength }) };
      if (!this.current(generation)) return;
      const response = await this.fetcher('/api/history/imports/preview', { method: 'POST', signal: abort.signal, headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ format: IMPORT_FORMAT, source, direction, fileName, contentBase64: bytesBase64(bytes) }) });
      const value = await responseJson(response);
      if (!this.current(generation)) return;
      if (!response.ok) throw Error(object(value) && typeof value.error === 'string' ? value.error.slice(0, 1000) : 'File preview failed. No history was imported.');
      this.update({ preview: readImportPreview(value, expected) });
    } catch (cause) { if (this.current(generation)) this.update({ error: message(cause) }); }
    finally { if (this.current(generation)) this.update({ previewing: false }); }
  }
  commit(): Promise<void> {
    if (this.operation) return this.operation;
    if (!this.active || this.disposed || this.state.receipt || !this.bytes || !this.state.hasFile || !this.slot()) return Promise.resolve();
    const { preview, pending, source, direction, fileName } = this.state;
    if (!pending && !preview?.committable) return Promise.resolve();
    const request = pending ?? { requestId: this.newId(), format: IMPORT_FORMAT, source, direction, fileName,
      fileSha256: this.fileHash, byteLength: this.bytes.byteLength, previewFingerprint: preview!.previewFingerprint, operationFingerprint: preview!.operationFingerprint };
    if (request.fileSha256 !== this.fileHash || request.byteLength !== this.bytes.byteLength || !this.persist(request)) return Promise.resolve();
    const contentBase64 = bytesBase64(this.bytes);
    this.update({ sending: true, error: '', refusal: null });
    this.operation = this.resolve(request, { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ format: request.format, source: request.source, direction: request.direction, fileName: request.fileName,
        contentBase64, requestId: request.requestId, previewFingerprint: request.previewFingerprint }) }).finally(() => {
      this.operation = null; this.update({ sending: false });
    });
    return this.operation;
  }
  checkReceipt(): Promise<void> {
    if (this.operation) return this.operation;
    const pending = this.state.pending;
    if (!this.active || this.disposed || !pending || !this.slot()) return Promise.resolve();
    this.update({ checking: true, error: '', refusal: null });
    this.operation = this.resolve(pending).finally(() => { this.operation = null; this.update({ checking: false }); });
    return this.operation;
  }
  private async resolve(request: ImportRequest, init?: RequestInit) {
    try {
      if (await operationFingerprint(request) !== request.operationFingerprint) throw Error('Saved import identity does not match its file and options. Recovery metadata was retained.');
      if (!this.slot()) return;
      const response = await this.fetcher(init ? '/api/history/imports' : `/api/history/imports/requests/${encodeURIComponent(request.requestId)}`, init);
      const value = await responseJson(response);
      if (!this.slot()) return;
      if (!response.ok) {
        if (!init && response.status === 404) throw Error('No receipt was found in this workbench. The outcome remains unknown; reselect the same file to retry this request.');
        if (init && [400, 409, 413, 422].includes(response.status) && shape(value, ['error']) && typeof value.error === 'string' && value.error.trim() && value.error.length <= 1000) {
          this.update({ refusal: { status: response.status, message: value.error }, error: '' });
          return;
        }
        throw Error(object(value) && typeof value.error === 'string' ? value.error.slice(0, 1000) : 'Import was not confirmed. Check this same request again.');
      }
      this.update({ receipt: readImportReceipt(value, request), error: '' });
      this.bytes = null; this.fileHash = '';
      this.update({ hasFile: false });
    } catch (cause) { this.update({ error: message(cause) }); }
  }
  startAnother() {
    if (this.disposed || this.operation || !this.state.receipt || !this.persist(null)) return;
    this.navigate(); this.bytes = null; this.fileHash = '';
    this.update(emptyImportState());
  }
  dismissRefusal() {
    if (this.disposed || this.operation || !this.state.refusal || !this.persist(null)) return;
    this.navigate(); this.bytes = null; this.fileHash = '';
    this.update(emptyImportState());
  }
}
