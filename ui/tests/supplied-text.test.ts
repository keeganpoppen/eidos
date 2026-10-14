import { describe, expect, test } from 'bun:test';
import { SuppliedTextClient, SUPPLIED_TEXT_KEY, TEXT_FORMAT, TEXT_PARSER, readTextRequest, readTextPreview, readTextReceipt, frozenText, sourceOnly, type TextPreview, type TextReceipt, type TextRequest } from '../src/lib/supplied-text';
import { bytesBase64, sha256 } from '../src/lib/history-import';
import { projectEvidence } from '../src/lib/semantic';
import { evidenceFieldLabel, readEvidenceSource } from '../src/lib/evidence-discovery';
import type { ContextRecord, EvidenceHit, LocalTextEvidence } from '../src/lib/types';

const utf8 = new TextEncoder();
const literal = '\uFEFFbaseline: 1,2\r\ncurrent: 0,0\r\n![remote](https://never-fetch.invalid/a.png)\n<script>not code</script>\n{"method":"turn/completed"}';
const bytes = utf8.encode(literal);
const hash = await sha256(bytes);
const preview: TextPreview = { format: TEXT_FORMAT, fileName: 'observation.txt', fileSha256: hash, byteLength: bytes.length, parserVersion: TEXT_PARSER, previewFingerprint: 'b'.repeat(64), classification: 'local-owner-supplied', textExcerpt: literal, truncated: false, discoverableFieldCount: 1 };
const request: TextRequest = { version: 1, requestId: 'request-one', format: TEXT_FORMAT, fileName: preview.fileName, fileSha256: hash, byteLength: bytes.length, parserVersion: TEXT_PARSER, previewFingerprint: preview.previewFingerprint };
const receipt: TextReceipt = { ...preview, id: 'file_one', requestId: request.requestId, admittedAtMs: 1, source: 'local-source', threadId: 'local-document_one', turnId: 'document-turn', itemId: 'document-item', seq: 5, hostRecordSha256: 'c'.repeat(64) };
const response = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));
const deferred = () => { let resolve!: (response: Response) => void; const promise = new Promise<Response>(r => resolve = r); return { promise, resolve }; };
const file = (data = bytes, name = preview.fileName) => ({ name, size: data.length, arrayBuffer: async () => data.slice().buffer });
function storage(initial?: string) {
  const values = new Map<string, string>([['nema.investigation.v1', 'independent-dirty-pending'], ['nema.history-import.v1', 'independent-import'], ['nema.authored-finding.v1', 'independent-finding'], ['nema.source-focus.v1', 'independent-source']]);
  if (initial !== undefined) values.set(SUPPLIED_TEXT_KEY, initial);
  return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}
const normal = (path: string) => response(path.endsWith('/preview') ? { preview } : { receipt }, path.endsWith('/preview') ? 200 : 201);
async function prepared(fetcher = normal, memory = storage()) {
  const client = new SuppliedTextClient(memory, () => {}, fetcher, () => request.requestId);
  client.restore(); await client.choose(file()); await client.preview(); return client;
}

describe('supplied text intake and exact recovery', () => {
  test('preview sends untouched UTF8/BOM/CRLF bytes; no request is persisted until deliberate commit', async () => {
    const memory = storage(); const calls: [string, RequestInit | undefined][] = [];
    const client = new SuppliedTextClient(memory, () => {}, (path, init) => { calls.push([path, init]); return normal(path); }, () => request.requestId);
    client.restore(); expect(calls).toHaveLength(0); await client.choose(file()); expect(calls).toHaveLength(0);
    await client.preview(); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBeNull();
    expect(JSON.parse(calls[0][1]!.body as string)).toEqual({ format: TEXT_FORMAT, fileName: preview.fileName, contentBase64: bytesBase64(bytes) });
    expect(client.state.preview?.textExcerpt).toBe(literal);
    await client.commit(); expect(readTextRequest(memory.getItem(SUPPLIED_TEXT_KEY)!)).toEqual(request);
    expect(memory.getItem(SUPPLIED_TEXT_KEY)).not.toContain('never-fetch'); expect(client.state.receipt).toEqual(receipt);
    expect([...memory.values].filter(([key]) => key !== SUPPLIED_TEXT_KEY)).toEqual([...storage().values]);
  });
  test('persists metadata before POST and refuses sending on storage failure', async () => {
    const memory = storage(); let committed = 0;
    const client = await prepared((path, init?: RequestInit) => { if (path === '/api/evidence/files') { committed++; expect(readTextRequest(memory.getItem(SUPPLIED_TEXT_KEY)!)).toEqual(request); } return normal(path); }, memory);
    await client.commit(); expect(committed).toBe(1);
    const broken = storage(); broken.setItem = () => { throw Error('full'); }; let posts = 0;
    const other = await prepared(path => { if (!path.endsWith('/preview')) posts++; return normal(path); }, broken);
    await other.commit(); expect(posts).toBe(0); expect(other.state.error).toContain('preserve');
  });
  test('lost commit reply survives reload; receipt GET never reuploads', async () => {
    const memory = storage(), calls: string[] = [];
    const client = await prepared(path => path.endsWith('/preview') ? normal(path) : Promise.reject(Error('reply lost')), memory);
    await client.commit(); const exact = memory.getItem(SUPPLIED_TEXT_KEY); expect(client.state.pending).toEqual(request);
    client.dispose();
    const reopened = new SuppliedTextClient(memory, () => {}, path => { calls.push(path); return response({ receipt }); }); reopened.restore();
    expect(calls).toHaveLength(0); await reopened.checkReceipt();
    expect(calls).toEqual(['/api/evidence/files/requests/request-one']); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBe(exact); expect(reopened.state.receipt).toEqual(receipt);
  });
  test('pending reselect rejects different bytes and exact retry retains the original basename and request', async () => {
    const memory = storage(JSON.stringify(request)), calls: RequestInit[] = [];
    const client = new SuppliedTextClient(memory, () => {}, (_path, init) => { calls.push(init!); return response({ receipt }); }); client.restore();
    await client.choose(file(utf8.encode('wrong'))); expect(client.state.hasFile).toBe(false); await client.commit(); expect(calls).toHaveLength(0);
    await client.choose(file(bytes, 'renamed.txt')); await client.commit();
    expect(JSON.parse(calls[0].body as string)).toEqual({ format: TEXT_FORMAT, fileName: request.fileName, contentBase64: bytesBase64(bytes), requestId: request.requestId, previewFingerprint: request.previewFingerprint });
  });
  test('GET404 and network/5xx/malformed success retain pending identity', async () => {
    for (const failure of [() => response({ error: 'missing' }, 404), () => response({ error: 'server' }, 503), () => response({ receipt: { ...receipt, fileSha256: 'd'.repeat(64) } }), () => Promise.resolve(new Response('broken')), () => Promise.reject(Error('offline'))]) {
      const memory = storage(JSON.stringify(request)), raw = memory.getItem(SUPPLIED_TEXT_KEY);
      const client = new SuppliedTextClient(memory, () => {}, failure); client.restore(); await client.checkReceipt();
      expect(client.state.receipt).toBeNull(); expect(client.state.error).not.toBe(''); expect(client.state.refusal).toBe('');
      client.startAnother(true); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBe(raw);
    }
  });
  test('authoritative POST refusal needs deliberate dismissal; it never clears automatically', async () => {
    for (const status of [400, 409, 413, 422]) {
      const memory = storage(); const client = await prepared(path => path.endsWith('/preview') ? normal(path) : response({ error: 'refused' }, status), memory);
      await client.commit(); expect(client.state.refusal).toBe('refused'); expect(memory.getItem(SUPPLIED_TEXT_KEY)).not.toBeNull();
      client.startAnother(); expect(memory.getItem(SUPPLIED_TEXT_KEY)).not.toBeNull(); client.startAnother(true); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBeNull();
    }
  });
  test('foreign/malformed/oversized metadata remains untouched and blocks a new request', async () => {
    for (const raw of ['bad', JSON.stringify({ ...request, extra: true }), ' '.repeat(4097), JSON.stringify({ ...request, fileName: '../file' })]) {
      const memory = storage(raw); let calls = 0;
      const client = new SuppliedTextClient(memory, () => {}, () => { calls++; return normal(''); }); client.restore(); await client.choose(file()); await client.commit();
      expect(client.state.unavailable).toBe(true); expect(calls).toBe(0); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBe(raw);
    }
    const memory = storage(), client = await prepared(normal, memory); memory.setItem(SUPPLIED_TEXT_KEY, 'another tab'); await client.commit();
    expect(client.state.unavailable).toBe(true); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBe('another tab');
  });
  test('invalidUTF8/oversize/basename refusal happens before preview and does not normalize bytes', async () => {
    let calls = 0; const client = new SuppliedTextClient(storage(), () => {}, () => { calls++; return normal(''); });
    for (const input of [file(new Uint8Array([0xff])), file(new Uint8Array(65537)), file(bytes, '../bad'), file(bytes, '🧭'.repeat(64))]) { await client.choose(input); await client.preview(); expect(client.state.hasFile).toBe(false); }
    expect(calls).toBe(0); await client.choose(file(new Uint8Array(0))); expect(client.state.hasFile).toBe(true);
  });
  test('preview rejects mismatched filename/hash/classification and overlong codepoint excerpt', () => {
    const expected = { fileName: preview.fileName, fileSha256: hash, byteLength: bytes.length };
    for (const patch of [{ fileName: 'other' }, { fileSha256: 'a'.repeat(64) }, { classification: 'native-observed' }, { textExcerpt: '🧭'.repeat(481) }, { parserVersion: 'future' }]) expect(() => readTextPreview({ preview: { ...preview, ...patch } }, expected)).toThrow();
    expect(readTextPreview({ preview: { ...preview, textExcerpt: '🧭'.repeat(480), truncated: true } }, expected).textExcerpt).toHaveLength(960);
  });
  for (const change of ['close', 'navigate', 'file', 'disposed']) test(`${change} cancels held preview without stale success/refusal`, async () => {
    const held = deferred(); let signal: AbortSignal | undefined;
    const client = new SuppliedTextClient(storage(), () => {}, (_url, init) => { signal = init!.signal!; return held.promise; });
    await client.choose(file()); const pending = client.preview();
    if (change === 'close') client.navigate(false); if (change === 'navigate') client.navigate(); if (change === 'file') await client.choose(file(utf8.encode('other'))); if (change === 'disposed') client.dispose();
    expect(signal?.aborted).toBe(true); held.resolve(new Response(JSON.stringify({ preview }))); await pending;
    expect(client.state.preview).toBeNull(); expect(client.state.error).toBe('');
  });
  test('late file read cannot replace a new selection or revive after closing', async () => {
    let release!: (bytes: ArrayBuffer) => void;
    const client = new SuppliedTextClient(storage(), () => {});
    const pending = client.choose({ name: 'old.txt', size: 2, arrayBuffer: () => new Promise(resolve => release = resolve) });
    await client.choose(file()); release(new ArrayBuffer(2)); await pending;
    expect(client.state.fileName).toBe(preview.fileName); expect(client.state.byteLength).toBe(bytes.length);
  });
  test('closed or disposed commit cannot publish or change a replacement client recovery slot', async () => {
    for (const change of ['close', 'dispose']) {
      const held = deferred(), memory = storage();
      const client = await prepared(path => path.endsWith('/preview') ? normal(path) : held.promise, memory);
      const pending = client.commit(), exact = memory.getItem(SUPPLIED_TEXT_KEY);
      if (change === 'close') client.navigate(false); else client.dispose();
      const next = new SuppliedTextClient(memory, () => {}, () => response({ receipt })); next.restore();
      held.resolve(new Response(JSON.stringify({ receipt }), { status: 201 })); await pending;
      expect(client.state.receipt).toBeNull(); expect(memory.getItem(SUPPLIED_TEXT_KEY)).toBe(exact);
      await next.checkReceipt(); expect(next.state.receipt).toEqual(receipt);
    }
  });
  test('late refusal cannot enable dismissal for a closed request', async () => {
    const held = deferred(), memory = storage(); const client = await prepared(path => path.endsWith('/preview') ? normal(path) : held.promise, memory);
    const pending = client.commit(); client.navigate(false); held.resolve(new Response('{"error":"old refusal"}', { status: 409 })); await pending;
    client.navigate(true); client.startAnother(true); expect(client.state.refusal).toBe(''); expect(memory.getItem(SUPPLIED_TEXT_KEY)).not.toBeNull();
  });
  test('receipt mismatch never follows a new group; a confirmed receipt cannot be replaced', async () => {
    for (const patch of [{ requestId: 'other' }, { fileName: 'other' }, { byteLength: 0 }, { threadId: 'native-thread' }, { seq: 0 }, { parserVersion: 'future' }]) expect(() => readTextReceipt({ receipt: { ...receipt, ...patch } }, request)).toThrow();
    let changed = false; const client = await prepared(path => changed ? response({ receipt: { ...receipt, id: 'replacement', threadId: 'local-document_other' } }) : normal(path));
    await client.commit(); changed = true; await client.checkReceipt(); expect(client.state.receipt).toEqual(receipt); expect(client.state.error).toContain('changed');
  });
  test('original download is explicit, exact and independently hash checked', async () => {
    const calls: string[] = [];
    const client = await prepared(path => { calls.push(path); return path === '/api/evidence/files/file_one' ? response({ receipt: Object.fromEntries(Object.entries(receipt).reverse()), contentBase64: bytesBase64(bytes) }) : normal(path); });
    await client.commit(); expect(calls).toHaveLength(2); const original = await client.original();
    expect(original?.bytes).toEqual(bytes); expect(original?.receipt.id).toBe(receipt.id); expect(calls.at(-1)).toBe('/api/evidence/files/file_one');
    const bad = await prepared(path => path.endsWith('/file_one') ? response({ receipt, contentBase64: bytesBase64(utf8.encode('altered')) }) : normal(path)); await bad.commit();
    expect(await bad.original()).toBeNull(); expect(bad.state.error).toContain('do not match');
  });
  test('closing an original-byte read prevents download eligibility', async () => {
    const held = deferred(); const client = await prepared(path => path.endsWith('/file_one') ? held.promise : normal(path)); await client.commit();
    const pending = client.original(); client.navigate(false); held.resolve(new Response(JSON.stringify({ receipt, contentBase64: bytesBase64(bytes) })));
    expect(await pending).toBeNull(); expect(client.canUse(receipt)).toBe(false);
  });
  test('oversized replies fail bounded and leave exact pending recovery', async () => {
    const client = new SuppliedTextClient(storage(JSON.stringify(request)), () => {}, () => Promise.resolve(new Response(' '.repeat(131073)))); client.restore(); await client.checkReceipt();
    expect(client.state.error).toContain('128 KiB'); expect(client.state.pending).toEqual(request);
  });
});

describe('supplied text projection and non-native source controls', () => {
  async function record(): Promise<ContextRecord> {
    const rawText = JSON.stringify({ method: '$local/document', params: { version: 1, item: { id: 'document', type: 'suppliedText', text: literal } } });
    const digest = await sha256(utf8.encode(rawText));
    const localEvidence: LocalTextEvidence = { kind: 'supplied-text', version: 1, id: receipt.id, fileName: preview.fileName, fileSha256: hash, byteLength: bytes.length, classification: 'local-owner-supplied', parserVersion: TEXT_PARSER, hostRecordSha256: digest };
    return { seq: 5, threadId: receipt.threadId, direction: 'internal', method: '$local/document', source: receipt.source, rawText, sha256: digest, localEvidence };
  }
  test('frozen evidence renders literal text from retained descriptors without a live source lookup', async () => {
    const r = await record(); expect(frozenText(r.rawText, r.localEvidence, r.sha256)).toBe(literal);
    expect(projectEvidence(r.rawText, r.localEvidence, r.sha256)).toMatchObject({ kind: 'supplied-text', type: 'Supplied text', text: literal });
    expect(projectEvidence(r.rawText).kind).toBe('unknown');
    expect(projectEvidence(r.rawText, { ...r.localEvidence, hostRecordSha256: 'a'.repeat(64) }, r.sha256).kind).toBe('unknown');
    expect(projectEvidence(r.rawText.replace('suppliedText', 'agentMessage')).kind).toBe('unknown');
  });
  test('discovery validates the new exact field, descriptor and separate file hash', async () => {
    const r = await record(); const hit: EvidenceHit = { id: 'hit', version: 'v1', threadId: r.threadId, turnId: receipt.turnId, itemId: receipt.itemId, field: 'suppliedText.text', anchorSeq: 5, recordSeqs: [5], excerpt: 'current: 0,0' };
    const value = { scope: 'displayed-history-text/v1', hit, records: [r] };
    expect(evidenceFieldLabel(hit.field)).toBe('Supplied text'); expect(await readEvidenceSource(value, hit)).toEqual(value);
    for (const localEvidence of [undefined, { ...r.localEvidence, fileSha256: 'a'.repeat(64) }, { ...r.localEvidence, classification: 'native-observed' }]) await expect(readEvidenceSource({ ...value, records: [{ ...r, localEvidence }] }, hit)).rejects.toThrow();
  });
  test('local source prefix or metadata denies messaging without authenticating it', () => {
    expect(sourceOnly('local-document_missing')).toBe(true);
    expect(sourceOnly('opaque', { sourceOnly: true })).toBe(true);
    expect(sourceOnly('opaque', { sourceKind: 'supplied-text' })).toBe(true);
    expect(sourceOnly('ordinary', { sourceOnly: false })).toBe(false);
    expect(sourceOnly('ordinary')).toBe(false);
  });
});
