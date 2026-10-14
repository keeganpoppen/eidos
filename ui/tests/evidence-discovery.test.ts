import { describe, expect, test } from 'bun:test';
import { EvidenceDiscoveryClient, EVIDENCE_SCOPE, evidenceFieldLabel, readEvidenceHit, readEvidenceSource } from '../src/lib/evidence-discovery';
import type { EvidenceHit, EvidenceHitSource } from '../src/lib/types';

const hit: EvidenceHit = { id: 'field-one', version: 'v1', threadId: 't', turnId: 'turn', itemId: 'message', field: 'agentMessage.text', anchorSeq: 1, recordSeqs: [1, 3], excerpt: 'Remembered decision' };
const page = (hits = [hit], nextCursor: string | null = null) => ({ scope: EVIDENCE_SCOPE, version: 'index-v1', unchanged: false, hits, nextCursor });
const response = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));
const deferred = () => { let resolve!: (response: Response) => void; const promise = new Promise<Response>(r => resolve = r); return { promise, resolve }; };
async function source(expected = hit): Promise<EvidenceHitSource> {
  const records = await Promise.all(expected.recordSeqs.map(async seq => {
    const rawText = JSON.stringify({ method: 'item/agentMessage/delta', params: { delta: seq === 1 ? 'Remembered ' : 'decision', unknown: '<script>inert raw text</script>' } });
    const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(rawText)))].map(n => n.toString(16).padStart(2, '0')).join('');
    return { seq, threadId: expected.threadId, source: 'authored', direction: 'appserver_to_client', method: 'item/agentMessage/delta', rawText, sha256 };
  }));
  return { scope: EVIDENCE_SCOPE, hit: expected, records };
}

describe('bounded evidence discovery reads', () => {
  test('manual normalized literal query and exact filter use GET; no automatic reads or storage', async () => {
    const calls: string[] = [];
    const client = new EvidenceDiscoveryClient(() => {}, path => { calls.push(path); return response(page()); });
    expect(calls).toHaveLength(0);
    await client.search('  10%_Straße  ', 't');
    const url = new URL(calls[0], 'http://fixture');
    expect(url.pathname).toBe('/api/evidence/search');
    expect(url.searchParams.get('q')).toBe('10%_Straße');
    expect(url.searchParams.get('threadId')).toBe('t');
    expect(url.searchParams.get('limit')).toBe('20');
    expect(client.state.page?.hits).toEqual([hit]);
  });
  test('inspection preserves exact raw records and validates identity, members and hashes', async () => {
    const value = await source();
    expect(await readEvidenceSource(value, hit)).toEqual(value);
    expect(value.records[0].rawText).toContain('<script>');
    for (const bad of [
      { ...value, hit: { ...hit, version: 'v2' } },
      { ...value, hit: { ...hit, threadId: 'other' } },
      { ...value, hit: { ...hit, excerpt: 'substituted' } },
      { ...value, records: [...value.records].reverse() },
      { ...value, records: value.records.map(r => ({ ...r, threadId: 'other' })) },
      { ...value, records: value.records.map(r => ({ ...r, rawText: r.rawText + ' ' })) },
    ]) await expect(readEvidenceSource(bad, hit)).rejects.toThrow();
  });
  test('rejects oversized inspection and malformed membership/unknown field pages', async () => {
    const value = await source();
    value.records[0].rawText = 'x'.repeat(131073);
    await expect(readEvidenceSource(value, hit)).rejects.toThrow('128 KiB');
    for (const bad of [{ ...hit, recordSeqs: [1, 1] }, { ...hit, recordSeqs: [3, 1] }, { ...hit, anchorSeq: 2 }, { ...hit, field: 'unknown.control' }, { ...hit, excerpt: 'x'.repeat(241) }]) expect(() => readEvidenceHit(bad)).toThrow();
    const client = new EvidenceDiscoveryClient(() => {}, () => response(page([{ ...hit, threadId: 'wrong' }])));
    await client.search('decision', 't');
    expect(client.state.page).toBeNull();
    expect(client.state.error).toContain('mismatched');
  });
  test('old search success cannot replace a newer query or filter', async () => {
    const held = deferred(); let count = 0;
    const client = new EvidenceDiscoveryClient(() => {}, () => ++count === 1 ? held.promise : response(page([{ ...hit, id: 'new', threadId: 'new-thread' }])));
    const old = client.search('old');
    await client.search('new', 'new-thread');
    held.resolve(new Response(JSON.stringify(page()))); await old;
    expect(client.state.q).toBe('new');
    expect(client.state.page?.hits[0].id).toBe('new');
  });
  test('edited query invalidates a held source reply without fetching or adding', async () => {
    const held = deferred(), value = await source(); const calls: string[] = [];
    const client = new EvidenceDiscoveryClient(() => {}, path => { calls.push(path); return path.includes('/hits/') ? held.promise : response(page()); });
    await client.search('decision');
    const pending = client.inspect(hit);
    client.clearSearch();
    held.resolve(new Response(JSON.stringify(value))); await pending;
    expect(client.inspected()).toBeNull(); expect(client.state.source).toBeNull(); expect(calls).toHaveLength(2);
  });
  for (const navigation of ['source', 'hidden-returned', 'disposed'] as const) test(`${navigation} invalidates a held source read`, async () => {
    const held = deferred(), value = await source();
    const client = new EvidenceDiscoveryClient(() => {}, path => path.includes('/hits/') ? held.promise : response(page()));
    await client.search('decision'); const pending = client.inspect(hit);
    if (navigation === 'source') client.navigate();
    else if (navigation === 'hidden-returned') { client.navigate(false); client.navigate(true); }
    else client.dispose();
    held.resolve(new Response(JSON.stringify(value))); await pending;
    expect(client.inspected()).toBeNull(); expect(client.state.source).toBeNull();
  });
  test('successful inspection uses encoded identity/query/version and is available only in active view', async () => {
    const value = await source(); const calls: string[] = [];
    const client = new EvidenceDiscoveryClient(() => {}, path => { calls.push(path); return response(path.includes('/hits/') ? value : page()); });
    await client.search('decision'); await client.inspect(hit);
    expect(new URL(calls[1], 'http://fixture').searchParams.get('version')).toBe('v1');
    expect(new URL(calls[1], 'http://fixture').searchParams.get('q')).toBe('decision');
    expect(client.inspected()?.records.map(r => r.seq)).toEqual([1, 3]);
    client.navigate(false); expect(client.inspected()).toBeNull();
    client.navigate(true); expect(client.inspected()?.hit.id).toBe(hit.id);
  });
  test('changed-source 409 requires deliberate refresh without automatic retry', async () => {
    let calls = 0;
    const client = new EvidenceDiscoveryClient(() => {}, path => { calls++; return path.includes('/hits/') ? response({ error: 'Source changed' }, 409) : response(page()); });
    await client.search('decision'); await client.inspect(hit);
    expect(client.state.refreshRequired).toBe(true); expect(client.inspected()).toBeNull();
    await client.inspect(hit); await client.move(true); expect(calls).toBe(2);
    await client.refresh(); expect(calls).toBe(3); expect(client.state.refreshRequired).toBe(false);
  });
  test('pagination is explicit and invalidates prior source before fetching', async () => {
    const value = await source(); const calls: string[] = [];
    const client = new EvidenceDiscoveryClient(() => {}, path => { calls.push(path); return response(path.includes('/hits/') ? value : page([hit], 'cursor+one')); });
    await client.search('decision'); await client.inspect(hit); await client.move(true);
    expect(new URL(calls[2], 'http://fixture').searchParams.get('cursor')).toBe('cursor+one');
    expect(client.state.previous).toEqual(['']); expect(client.inspected()).toBeNull();
    await client.move(false); expect(new URL(calls[3], 'http://fixture').searchParams.has('cursor')).toBe(false);
  });
  test('unsupported or empty search never fetches and field labels do not call raw text native output', async () => {
    let calls = 0; const client = new EvidenceDiscoveryClient(() => {}, () => { calls++; return response(page()); });
    await client.search('  '); await client.search('x'.repeat(201)); expect(calls).toBe(0);
    expect(evidenceFieldLabel('reasoning.summary/2')).toBe('Exposed reasoning summary');
    expect(readEvidenceHit({ ...hit, field: 'reasoning.summary/-2' }).field).toBe('reasoning.summary/-2');
    expect(evidenceFieldLabel('turn.input/3/text')).toBe('Turn input');
    expect(evidenceFieldLabel('commandExecution.output')).toBe('Recorded command output');
    expect(evidenceFieldLabel('fileChange.changes/1/path')).toBe('Changed file path');
  });
});
