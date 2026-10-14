import { describe, expect, test } from 'bun:test';
import { HistoryImportClient, HISTORY_IMPORT_KEY, IMPORT_FORMAT, IMPORT_PARSER, IMPORT_SCOPE, MAX_IMPORT_BYTES, MAX_IMPORT_RESPONSE,
  bytesBase64, operationFingerprint, readImportRequest, readImportReceipt, sha256, type ImportPreview, type ImportReceipt, type ImportRequest } from '../src/lib/history-import';

const original = new TextEncoder().encode('{"method":"item/completed","unknown":"KEEP_原文"}\r\n\r{"other":true}\n');
function file(bytes = original, name = 'history.jsonl') { return { size: bytes.byteLength, name, arrayBuffer: async () => bytes.slice().buffer }; }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function store() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
async function previewFor(bytes = original, source = 'imported-history', direction: ImportRequest['direction'] = 'appserver_to_client'): Promise<ImportPreview> {
  const identity = { format: IMPORT_FORMAT, source, direction, fileSha256: await sha256(bytes), byteLength: bytes.byteLength };
  return { format: IMPORT_FORMAT, parserVersion: IMPORT_PARSER, discoveryScope: IMPORT_SCOPE, fileSha256: identity.fileSha256, byteLength: identity.byteLength,
    operationFingerprint: await operationFingerprint(identity), previewFingerprint: 'b'.repeat(64), recordCount: 2, blankLineCount: 1, physicalLineCount: 3,
    summary: { threadCount: 1, turnCount: 1, unscopedRecordCount: 1, discoverableFieldCount: 1 },
    warnings: ['file-local-preview', 'single-direction-capture', 'unscoped-records'], committable: true, reason: null };
}
function receiptFor(preview: ImportPreview, overrides: Partial<ImportReceipt> = {}): ImportReceipt {
  const { committable, reason, ...rest } = preview;
  return { ...rest, id: 'im-test', requestId: 'request-one', source: 'imported-history', direction: 'appserver_to_client', fileName: 'history.jsonl',
    captureSource: 'history-import:im-test', createdAtMs: 42, ...overrides };
}
function pendingFor(preview: ImportPreview): ImportRequest {
  return { requestId: 'request-one', format: IMPORT_FORMAT, source: 'imported-history', direction: 'appserver_to_client', fileName: 'history.jsonl',
    fileSha256: preview.fileSha256, byteLength: preview.byteLength, previewFingerprint: preview.previewFingerprint, operationFingerprint: preview.operationFingerprint };
}
async function setup(send?: (path: string, init?: RequestInit) => Promise<Response>) {
  const storage = store(), preview = await previewFor(), calls: { path: string; init?: RequestInit }[] = [];
  const client = new HistoryImportClient(storage, () => {}, async (path, init) => {
    calls.push({ path, init });
    if (path.endsWith('/preview')) return response({ preview });
    return send ? send(path, init) : response({ receipt: receiptFor(preview) }, init ? 201 : 200);
  }, () => 'request-one');
  client.restore(); await client.choose(file()); await client.preview();
  return { client, storage, preview, calls };
}

describe('exact-file import recovery', () => {
  test('preview sends exact mixed endings and Unicode, then commit persists only metadata before sending', async () => {
    const { client, storage, preview, calls } = await setup();
    expect(storage.values.size).toBe(0);
    expect(client.state.preview).toEqual(preview);
    const previewBody = JSON.parse(calls[0].init!.body as string);
    expect(Buffer.from(previewBody.contentBase64, 'base64')).toEqual(Buffer.from(original));
    await client.commit();
    expect(client.state.receipt?.recordCount).toBe(2);
    const raw = storage.getItem(HISTORY_IMPORT_KEY)!;
    expect(readImportRequest(raw)).toEqual(pendingFor(preview));
    expect(raw).not.toContain('contentBase64'); expect(raw).not.toContain('KEEP_');
    expect([...storage.values.keys()]).toEqual([HISTORY_IMPORT_KEY]);
    expect(JSON.parse(calls[1].init!.body as string)).toEqual({ ...previewBody, requestId: 'request-one', previewFingerprint: preview.previewFingerprint });
  });

  test('lost commit response keeps exact retry identity across reload and receipt GET makes no POST', async () => {
    const { client, storage, preview } = await setup(async () => { throw Error('connection lost'); });
    await client.commit();
    const raw = storage.getItem(HISTORY_IMPORT_KEY)!;
    expect(client.state.pending?.requestId).toBe('request-one'); expect(client.state.receipt).toBeNull();
    const calls: [string, RequestInit | undefined][] = [];
    const restored = new HistoryImportClient(storage, () => {}, async (path, init) => { calls.push([path, init]); return response({ receipt: receiptFor(preview) }); });
    restored.restore(); expect(calls).toEqual([]); expect(restored.state.hasFile).toBe(false);
    await restored.checkReceipt();
    expect(calls).toEqual([['/api/history/imports/requests/request-one', undefined]]);
    expect(restored.state.receipt?.id).toBe('im-test'); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(raw);
  });

  test('receipt 404 stays pending; wrong file refuses; renamed exact reselect retries original request', async () => {
    const { client, storage, preview } = await setup(async () => { throw Error('lost reply'); });
    await client.commit(); const raw = storage.getItem(HISTORY_IMPORT_KEY)!;
    const posts: string[] = [];
    const restored = new HistoryImportClient(storage, () => {}, async (_path, init) => {
      if (!init) return response({ error: 'unknown' }, 404);
      posts.push(init.body as string); return response({ receipt: receiptFor(preview) });
    }, () => { throw Error('must not create another ID'); });
    restored.restore(); await restored.checkReceipt();
    expect(restored.state.error).toContain('outcome remains unknown'); expect(restored.state.refusal).toBeNull();
    await restored.choose(file(new TextEncoder().encode('wrong'))); await restored.commit();
    expect(restored.state.error).toContain('does not match'); expect(posts).toEqual([]);
    restored.edit('source', 'changed'); restored.edit('direction', 'client_to_appserver');
    expect(restored.state.source).toBe('imported-history');
    await restored.choose(file(original, 'renamed.jsonl')); await restored.commit();
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0])).toMatchObject({ requestId: 'request-one', source: 'imported-history', direction: 'appserver_to_client', fileName: 'history.jsonl' });
    expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(raw);
  });

  test('persist failure prevents POST and keeps unrelated editor bytes intact', async () => {
    const { client, storage, calls } = await setup();
    storage.values.set('nema.investigation-draft.v1', '{"pendingRequest":{"id":"UNTOUCHED"}}');
    storage.setItem = () => { throw Error('quota'); };
    await client.commit();
    expect(calls).toHaveLength(1); expect(client.state.error).toContain('No new request was sent');
    expect(storage.getItem('nema.investigation-draft.v1')).toBe('{"pendingRequest":{"id":"UNTOUCHED"}}');
  });

  test('pending identity is in storage when fetch executes and double clicks send once', async () => {
    const held = deferred<Response>();
    const { client, storage, calls } = await setup(async () => {
      expect(readImportRequest(storage.getItem(HISTORY_IMPORT_KEY)!).requestId).toBe('request-one');
      return held.promise;
    });
    const first = client.commit(), second = client.commit();
    expect(first).toBe(second);
    held.resolve(response({ error: 'wait' }, 503)); await first;
    expect(calls).toHaveLength(2); expect(client.state.pending).not.toBeNull();
  });

  test.each(['not JSON', '{"foreign":"entry"}', ' '.repeat(4097)])('malformed recovery remains unchanged and sends nothing', async raw => {
    const storage = store(); storage.values.set(HISTORY_IMPORT_KEY, raw);
    let calls = 0;
    const client = new HistoryImportClient(storage, () => {}, async () => { calls++; return response({}); });
    client.restore(); await client.choose(file()); await client.preview(); await client.commit(); await client.checkReceipt(); client.startAnother(); client.dismissRefusal();
    expect(client.state.unavailable).toBe(true); expect(calls).toBe(0); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(raw);
  });

  test('another tab changing the slot prevents send and cannot be replaced by late receipt/refusal', async () => {
    const held = deferred<Response>();
    const { client, storage, preview, calls } = await setup(async () => held.promise);
    const sending = client.commit();
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(calls).toHaveLength(2);
    const other = JSON.stringify({ ...pendingFor(preview), requestId: 'other-view' });
    storage.values.set(HISTORY_IMPORT_KEY, other);
    held.resolve(response({ error: 'collision' }, 409)); await sending;
    expect(client.state.unavailable).toBe(true); expect(client.state.refusal).toBeNull();
    client.dismissRefusal(); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(other);
  });

  test('new foreign slot between preview and commit blocks sending', async () => {
    const { client, storage, calls } = await setup(); storage.values.set(HISTORY_IMPORT_KEY, 'foreign');
    await client.commit(); expect(calls).toHaveLength(1); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe('foreign');
  });

  test.each(['requestId', 'fileSha256', 'byteLength', 'operationFingerprint', 'previewFingerprint', 'source', 'direction', 'format', 'captureSource'])('receipt validates %s', async key => {
    const preview = await previewFor();
    const bad = { ...receiptFor(preview), [key]: key === 'byteLength' ? 1 : 'foreign' };
    const { client, storage } = await setup(async () => response({ receipt: bad }));
    await client.commit();
    expect(client.state.receipt).toBeNull(); expect(client.state.pending).not.toBeNull(); expect(storage.getItem(HISTORY_IMPORT_KEY)).not.toBeNull();
  });

  test('receipt filename and historical parser labels may differ without changing operation', async () => {
    const preview = await previewFor();
    expect(readImportReceipt({ receipt: receiptFor(preview, { fileName: 'old-name.jsonl', parserVersion: 'older-recorded-parser', discoveryScope: 'older-recorded-scope' }) }, pendingFor(preview)).fileName).toBe('old-name.jsonl');
  });

  test('tampered canonical fingerprint is refused before a restored GET', async () => {
    const preview = await previewFor(), storage = store();
    const raw = JSON.stringify({ ...pendingFor(preview), source: 'tampered' }); storage.values.set(HISTORY_IMPORT_KEY, raw);
    let calls = 0;
    const client = new HistoryImportClient(storage, () => {}, async () => { calls++; return response({}); });
    client.restore(); await client.checkReceipt();
    expect(calls).toBe(0); expect(client.state.error).toContain('does not match'); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(raw);
  });

  test.each([400, 409, 413, 422])('well-formed POST %i needs explicit refusal dismissal', async status => {
    const { client, storage } = await setup(async () => response({ error: 'Server refused this request.' }, status));
    await client.commit(); expect(client.state.refusal?.status).toBe(status); expect(storage.getItem(HISTORY_IMPORT_KEY)).not.toBeNull();
    client.dismissRefusal(); expect(storage.getItem(HISTORY_IMPORT_KEY)).toBeNull(); expect(client.state.pending).toBeNull();
  });

  test.each([response({ error: 'unavailable' }, 503), response({ nope: 'bad' }, 409), new Response('bad JSON', { status: 400 }), response({ receipt: {} })])('uncertain or malformed responses never authorize dismissal', async res => {
    const { client, storage } = await setup(async () => res);
    await client.commit(); const raw = storage.getItem(HISTORY_IMPORT_KEY);
    expect(client.state.refusal).toBeNull(); client.dismissRefusal();
    expect(storage.getItem(HISTORY_IMPORT_KEY)).toBe(raw); expect(client.state.pending).not.toBeNull();
  });

  test('confirmed receipt metadata remains until explicit new import; no automatic new request', async () => {
    const { client, storage, calls } = await setup(); await client.commit();
    expect(storage.getItem(HISTORY_IMPORT_KEY)).not.toBeNull(); client.startAnother();
    expect(storage.getItem(HISTORY_IMPORT_KEY)).toBeNull(); expect(client.state.receipt).toBeNull(); expect(calls).toHaveLength(2);
  });
});

describe('bounded preview and asynchronous file isolation', () => {
  test('oversize file is refused before reading and UTF-8 basename/source bounds are enforced', async () => {
    const storage = store(); let reads = 0, calls = 0;
    const client = new HistoryImportClient(storage, () => {}, async () => { calls++; return response({}); }); client.restore();
    await client.choose({ size: MAX_IMPORT_BYTES + 1, name: 'large.jsonl', arrayBuffer: async () => { reads++; return new ArrayBuffer(0); } });
    expect(reads).toBe(0); expect(client.state.error).toContain('8 MiB');
    await client.choose(file(original, '語'.repeat(100))); expect(client.state.hasFile).toBe(false);
    await client.choose(file()); client.edit('source', '語'.repeat(100)); await client.preview(); expect(calls).toBe(0);
  });

  test('size mismatch and zero-byte input cannot reach preview', async () => {
    const client = new HistoryImportClient(store(), () => {}); client.restore();
    await client.choose({ size: 2, name: 'bad.jsonl', arrayBuffer: async () => new ArrayBuffer(3) }); expect(client.state.hasFile).toBe(false);
    await client.choose(file(new Uint8Array(0))); expect(client.state.hasFile).toBe(false);
  });

  test.each(['source', 'direction', 'file', 'navigation'])('late preview is discarded after %s change', async action => {
    const held = deferred<Response>(), preview = await previewFor();
    const client = new HistoryImportClient(store(), () => {}, async () => held.promise); client.restore(); await client.choose(file());
    const task = client.preview(); await new Promise(resolve => setTimeout(resolve, 0));
    if (action === 'source') client.edit('source', 'new-origin');
    if (action === 'direction') client.edit('direction', 'client_to_appserver');
    if (action === 'file') await client.choose(file(new TextEncoder().encode('different')));
    if (action === 'navigation') client.navigate(false);
    held.resolve(response({ preview })); await task;
    expect(client.state.preview).toBeNull(); expect(client.state.previewing).toBe(false);
  });

  test('late file read cannot replace a new selection or resurrect after close', async () => {
    const held = deferred<ArrayBuffer>(), client = new HistoryImportClient(store(), () => {}); client.restore();
    const old = client.choose({ size: original.length, name: 'old.jsonl', arrayBuffer: () => held.promise });
    await client.choose(file(original, 'new.jsonl')); held.resolve(original.slice().buffer); await old;
    expect(client.state.fileName).toBe('new.jsonl');
    const held2 = deferred<ArrayBuffer>();
    const reading = client.choose({ size: original.length, name: 'closed.jsonl', arrayBuffer: () => held2.promise });
    client.navigate(false); held2.resolve(original.slice().buffer); await reading;
    expect(client.state.hasFile).toBe(false);
  });

  test('changing options while file read is pending invalidates that read', async () => {
    const held = deferred<ArrayBuffer>(), client = new HistoryImportClient(store(), () => {}); client.restore();
    const reading = client.choose({ size: original.length, name: 'old.jsonl', arrayBuffer: () => held.promise });
    client.edit('direction', 'client_to_appserver'); held.resolve(original.slice().buffer); await reading;
    expect(client.state.hasFile).toBe(false); expect(client.state.direction).toBe('client_to_appserver');
  });

  test('unsupported valid file can be reviewed but never committed', async () => {
    const preview = await previewFor(); preview.summary.discoverableFieldCount = 0; preview.committable = false; preview.reason = 'no-discoverable-history'; preview.warnings.push('no-discoverable-history');
    let calls = 0;
    const client = new HistoryImportClient(store(), () => {}, async () => { calls++; return response({ preview }); }); client.restore(); await client.choose(file()); await client.preview(); await client.commit();
    expect(client.state.preview?.committable).toBe(false); expect(client.state.pending).toBeNull(); expect(calls).toBe(1);
  });

  test.each(['fileSha256', 'byteLength', 'operationFingerprint', 'parserVersion', 'discoveryScope'])('mismatched preview %s is refused before commitment', async key => {
    const preview = await previewFor(), bad = { ...preview, [key]: key === 'byteLength' ? 1 : 'foreign' };
    const storage = store(); let calls = 0;
    const client = new HistoryImportClient(storage, () => {}, async () => { calls++; return response({ preview: bad }); }); client.restore(); await client.choose(file()); await client.preview(); await client.commit();
    expect(client.state.preview).toBeNull(); expect(calls).toBe(1); expect(storage.values.size).toBe(0);
  });

  test('complete HTTP response bound refuses an oversized success', async () => {
    const { client } = await setup(async () => new Response(' '.repeat(MAX_IMPORT_RESPONSE + 1)));
    await client.commit(); expect(client.state.error).toContain('128 KiB'); expect(client.state.receipt).toBeNull(); expect(client.state.pending).not.toBeNull();
  });

  test('base64 chunk boundaries preserve arbitrary exact bytes', () => {
    const bytes = new Uint8Array(32769); for (let i = 0; i < bytes.length; i++) bytes[i] = i % 256;
    expect(Buffer.from(bytesBase64(bytes), 'base64')).toEqual(Buffer.from(bytes));
  });
});
