import { describe, expect, test } from 'bun:test';
import { RESULT_USES_SCOPE, ResultUsesClient, readResultUses, readResultUseDetail, type ResultUse, type ResultUseDetail } from '../src/lib/result-uses';
import { authoredFindingId } from '../src/lib/authored-finding';

const target = { investigationId: 'source-owner', artifactId: 'F0' };
const row: ResultUse = { investigationId: 'consumer-B', investigationTitle: 'Later question', contextId: 'B0', ownerVersion: 'owner-v2', isCurrent: false, questionExcerpt: 'Original question?', rationaleExcerpt: 'Compare against the earlier result.', matchingInputCount: 1 };
const copied: ResultUse = { ...row, investigationId: 'consumer-D', contextId: 'D0', ownerVersion: 'owner-D', isCurrent: true };
const page = (rows = [row], nextCursor: string | null = null, source = target) => ({ scope: RESULT_USES_SCOPE, source, version: 'page-version', unchanged: false, uses: rows, nextCursor });
const response = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));
const deferred = () => { let resolve!: (response: Response) => void; const promise = new Promise<Response>(r => resolve = r); return { promise, resolve }; };
function detail(selected = row, source = target): ResultUseDetail {
  return {
    scope: RESULT_USES_SCOPE, source, investigationId: selected.investigationId, investigationTitle: selected.investigationTitle,
    contextId: selected.contextId, ownerVersion: selected.ownerVersion, isCurrent: selected.isCurrent, matchingInputIndexes: [0],
    context: {
      id: selected.contextId, parentContextId: null, question: 'Original question?', createdAtMs: 1,
      selections: [{ threadId: 'raw-thread', startSeq: 5, endSeq: 5, rationale: 'Original source rationale' }],
      records: [{ seq: 5, threadId: 'raw-thread', source: 'fixture', direction: 'appserver_to_client', method: 'item/completed', rawText: '{"unknown":"retained"}', sha256: 'a'.repeat(64) }],
      artifactInputs: [{ ...source, rationale: 'Compare against the earlier result.', sourceContextId: 'source-C0', sourceManifestId: 'manifest-original', sourceAttemptManifestId: 'manifest-attempt',
        sourceAdoption: { artifactId: source.artifactId, decision: 'adopt', note: 'Original review only', createdAtMs: 1 },
        artifact: { id: source.artifactId, contextId: 'source-C0', attemptId: 'source-A0', text: 'Original F0 text', citations: [1], unsupportedCitations: [], outputSeqs: [2], createdAtMs: 1 } }],
      projectedPrompt: 'Exact original projected input.', coverage: 'Only selected source records.',
      inputOrigin: { version: 1, kind: 'historical-context-inputs', investigationId: 'original-owner', contextId: 'original-C0', manifestId: 'manifest-origin' },
    },
  };
}

describe('direct saved result uses', () => {
  test('explicit GET reads the exact pair without resolving its source or touching editor/storage', async () => {
    const calls: { path: string; init: unknown }[] = [];
    const source = { investigationId: 'owner / x', artifactId: 'F0/é' };
    const client = new ResultUsesClient(() => {}, (path, init) => { calls.push({ path, init }); return response(page([row], null, source)); });
    client.target(source);
    expect(calls).toHaveLength(0);
    expect(client.state.expanded).toBe(false);
    await client.refresh();
    expect(client.state.expanded).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe('/api/investigations/owner%20%2F%20x/artifacts/F0%2F%C3%A9/uses?limit=20');
    expect(Object.keys(calls[0].init as object)).toEqual(['signal']);
    expect(client.state.page?.source).toEqual(source);
    expect(client.state.page?.uses[0].contextId).toBe('B0');
  });

  test('keeps historical and copied current contexts distinct; no current owner substitution', async () => {
    const calls: string[] = [];
    const value = detail();
    const client = new ResultUsesClient(() => {}, path => { calls.push(path); return response(path.includes('/contexts/') ? value : page([row, copied])); });
    client.target(target); await client.refresh();
    // Svelte presents proxy objects, so callers need not retain object reference equality.
    await client.inspect({ ...row });
    expect(calls[1]).toBe('/api/investigations/source-owner/artifacts/F0/uses/consumer-B/contexts/B0?expectedVersion=owner-v2');
    expect(client.state.detail).toEqual(value);
    expect(client.state.detail?.context.id).toBe('B0');
    expect(client.state.detail?.isCurrent).toBe(false);
    expect(client.state.page?.uses.map(item => [item.contextId, item.isCurrent])).toEqual([['B0', false], ['D0', true]]);
  });

  test('preserves frozen text, review, raw bytes and unknown fields without upstream re-resolution', async () => {
    const value = detail();
    Object.assign(value.context, { unknownFutureContext: { preserve: 'original' } });
    Object.assign(value.context.artifactInputs![0], { unknownFutureInput: ['original'] });
    Object.assign(value.context.inputOrigin!, { unknownFutureOrigin: 'original' });
    expect(await readResultUseDetail(value, target, row)).toBe(value);
    expect(value.context.artifactInputs![0].artifact.text).toBe('Original F0 text');
    expect(value.context.artifactInputs![0].sourceAdoption?.note).toBe('Original review only');
    expect(value.context.records[0].rawText).toBe('{"unknown":"retained"}');
    value.context.records[0].source = 'metadata'.repeat(100);
    value.context.records[0].rawText = 'x'.repeat(131073);
    expect((await readResultUseDetail(value, target, row)).context.records[0].rawText.length).toBe(131073);
  });

  test('detail rejects newer context, wrong owner/pair/version/current label and false membership', async () => {
    const value = detail();
    const bad: unknown[] = [
      { ...value, scope: 'transitive-uses' }, { ...value, source: { ...target, artifactId: 'F1' } },
      { ...value, investigationId: 'consumer-C' }, { ...value, contextId: 'B1' },
      { ...value, context: { ...value.context, id: 'B1' } }, { ...value, ownerVersion: 'newer-v3' },
      { ...value, isCurrent: true }, { ...value, matchingInputIndexes: [] }, { ...value, matchingInputIndexes: [1] },
      { ...value, matchingInputIndexes: [0, 0] }, { ...value, matchingInputIndexes: ['0'] },
      { ...value, context: { ...value.context, artifactInputs: [] } },
      { ...value, context: { ...value.context, artifactInputs: [{ ...value.context.artifactInputs![0], investigationId: 'different-source' }] } },
      { ...value, context: { ...value.context, artifactInputs: [{ ...value.context.artifactInputs![0], artifact: { ...value.context.artifactInputs![0].artifact, id: 'F1' } }] } },
    ];
    for (const item of bad) await expect(readResultUseDetail(item, target, row)).rejects.toThrow();
  });

  test('all matching inputs must be identified in original order; unrelated input stays visible', async () => {
    const value = detail(), selected = { ...row, matchingInputCount: 2 };
    const input = value.context.artifactInputs![0];
    value.context.artifactInputs = [input, { ...input, artifactId: 'other', artifact: { ...input.artifact, id: 'other' } }, { ...input, rationale: 'Second reason' }];
    value.matchingInputIndexes = [0, 2];
    expect((await readResultUseDetail(value, target, selected)).context.artifactInputs).toHaveLength(3);
    await expect(readResultUseDetail({ ...value, matchingInputIndexes: [2, 0] }, target, selected)).rejects.toThrow();
    await expect(readResultUseDetail(value, target, row)).rejects.toThrow();
  });

  test('authored snapshots bind saved content to their original owner without requiring original context availability', async () => {
    const value = detail();
    const body = { kind: 'owner-authored-finding' as const, contextId: 'deleted-source-context', text: 'Original finding [evidence:1].', citations: [1], unsupportedCitations: [], artifactCitations: [], unsupportedArtifactCitations: [] };
    const artifact = { ...body, id: await authoredFindingId(target.investigationId, body), authorship: { kind: 'local-owner' as const, createdAtMs: 1 } };
    const source = { ...target, artifactId: artifact.id };
    value.source = source;
    value.context.artifactInputs![0] = { ...value.context.artifactInputs![0], ...source, artifact, sourceContextId: body.contextId, sourceAdoption: null };
    expect((await readResultUseDetail(value, source, row)).context.artifactInputs![0].artifact).toEqual(artifact);
    const changed = structuredClone(value);
    changed.context.artifactInputs![0].artifact.text = 'Replacement finding under the original ID.';
    await expect(readResultUseDetail(changed, source, row)).rejects.toThrow('owner and content');
    const wrongOwner = { ...source, investigationId: 'other-owner' };
    const moved = structuredClone(value); moved.source = wrongOwner; moved.context.artifactInputs![0].investigationId = wrongOwner.investigationId;
    await expect(readResultUseDetail(moved, wrongOwner, row)).rejects.toThrow('owner and content');
    // Other supplied findings are also frozen evidence, not exempt because they are not the match.
    value.context.artifactInputs!.push({ ...changed.context.artifactInputs![0], investigationId: 'other-owner' });
    await expect(readResultUseDetail(value, source, row)).rejects.toThrow('owner and content');
  });

  test('list metadata validates Unicode code points and rejects mismatches/duplicates/unchanged without a cached page', () => {
    expect(readResultUses(page([{ ...row, questionExcerpt: '🧭'.repeat(240) }]), target).uses).toHaveLength(1);
    expect(readResultUses(page([{ ...row, investigationId: '🧭'.repeat(183), contextId: '🧭'.repeat(200) }]), target).uses).toHaveLength(1);
    for (const value of [page([{ ...row, questionExcerpt: '🧭'.repeat(241) }]), page([row, row]), page([row], null, { ...target, artifactId: 'F1' }),
      { ...page(), unchanged: true }, { ...page(), uses: new Array(21).fill(row) }, { ...page(), nextCursor: '' },
      page([{ ...row, matchingInputCount: 0 }]), page([{ ...row, isCurrent: 'false' } as unknown as ResultUse])]) {
      expect(() => readResultUses(value, target)).toThrow();
    }
  });

  test('an explicit empty page is distinct from failed/malformed list reads', async () => {
    for (const failure of [response({ error: 'Unavailable' }, 404), response({ unexpected: true }), Promise.resolve(new Response('not JSON'))]) {
      const client = new ResultUsesClient(() => {}, () => failure);
      client.target(target); await client.refresh();
      expect(client.state.page).toBeNull(); expect(client.state.error).not.toBe('');
    }
    const client = new ResultUsesClient(() => {}, () => response(page([])));
    client.target(target); await client.refresh();
    expect(client.state.page?.uses).toEqual([]); expect(client.state.error).toBe('');
  });

  test('404 detail never erases list membership or substitutes an empty context', async () => {
    const client = new ResultUsesClient(() => {}, path => path.includes('/contexts/') ? response({ error: 'Exact context no longer exists' }, 404) : response(page()));
    client.target(target); await client.refresh(); await client.inspect(row);
    expect(client.state.error).toContain('no longer exists'); expect(client.state.detail).toBeNull();
    expect(client.state.page?.uses).toHaveLength(1);
  });

  for (const change of ['close', 'new-target', 'disposed'] as const) test(`${change} cancels a late list response and its error`, async () => {
    for (const status of [200, 409]) {
      const held = deferred(); let signal: AbortSignal | undefined;
      const client = new ResultUsesClient(() => {}, (_path, init) => { signal = init.signal; return held.promise; });
      client.target(target); const pending = client.refresh();
      if (change === 'disposed') client.dispose(); else client.target(change === 'close' ? null : { ...target, artifactId: 'F1' });
      expect(signal?.aborted).toBe(true);
      held.resolve(new Response(JSON.stringify(status === 200 ? page() : { error: 'stale old target' }), { status })); await pending;
      expect(client.state.page).toBeNull(); expect(client.state.error).toBe(''); expect(client.state.refreshRequired).toBe(false);
    }
  });

  for (const change of ['close', 'new-target', 'disposed', 'page', 'consumer', 'refresh'] as const) test(`${change} cancels a late exact-context reply`, async () => {
    const held = deferred(); const signals: AbortSignal[] = [];
    const client = new ResultUsesClient(() => {}, (path, init) => {
      if (path.includes('/contexts/B0')) { signals.push(init.signal); return held.promise; }
      return response(path.includes('/contexts/D0') ? detail(copied) : page([row, copied], 'next+page'));
    });
    client.target(target); await client.refresh(); const pending = client.inspect(row);
    if (change === 'close') client.target(null);
    if (change === 'new-target') client.target({ ...target, artifactId: 'F1' });
    if (change === 'disposed') client.dispose();
    if (change === 'page') await client.move(true);
    if (change === 'consumer') await client.inspect(copied);
    if (change === 'refresh') await client.refresh();
    expect(signals[0].aborted).toBe(true);
    held.resolve(new Response(JSON.stringify(detail()))); await pending;
    expect(client.state.detail?.context.id ?? null).toBe(change === 'consumer' ? 'D0' : null);
    expect(client.state.error).toBe('');
  });

  test('pagination uses opaque cursor and refresh starts at first page with no retained context', async () => {
    const calls: string[] = [];
    const client = new ResultUsesClient(() => {}, path => { calls.push(path); return response(path.includes('/contexts/') ? detail() : page([row], 'next+/=')); });
    client.target(target); await client.refresh(); await client.inspect(row); await client.move(true);
    expect(client.state.detail).toBeNull(); expect(client.state.previous).toEqual(['']);
    expect(new URL(calls.at(-1)!, 'http://fixture').searchParams.get('cursor')).toBe('next+/=');
    await client.move(false); expect(client.state.previous).toEqual([]);
    expect(new URL(calls.at(-1)!, 'http://fixture').searchParams.has('cursor')).toBe(false);
    await client.move(true); await client.refresh();
    expect(client.state.cursor).toBe(''); expect(client.state.previous).toEqual([]); expect(client.state.detail).toBeNull();
  });

  test('409 cursor or detail requires explicit refresh and never automatically retries', async () => {
    for (const failingRead of ['cursor', 'detail']) {
      let calls = 0;
      const client = new ResultUsesClient(() => {}, path => {
        calls++; return path.includes(failingRead === 'cursor' ? 'cursor=' : '/contexts/') ? response({ error: 'Saved owner changed' }, 409) : response(page([row], 'cursor'));
      });
      client.target(target); await client.refresh();
      if (failingRead === 'cursor') await client.move(true); else await client.inspect(row);
      expect(calls).toBe(2); expect(client.state.refreshRequired).toBe(true); expect(client.state.detail).toBeNull();
      await client.inspect(row); await client.move(true); expect(calls).toBe(2);
      await client.refresh(); expect(calls).toBe(3); expect(client.state.refreshRequired).toBe(false);
      expect(client.state.cursor).toBe('');
    }
  });

  test('unlisted consumer and wrong version cannot trigger detail reads', async () => {
    let calls = 0;
    const client = new ResultUsesClient(() => {}, () => { calls++; return response(page()); });
    client.target(target); await client.refresh();
    await client.inspect(copied); await client.inspect({ ...row, ownerVersion: 'newer' });
    expect(calls).toBe(1); expect(client.state.detail).toBeNull();
  });

  test('preview focus eligibility disappears synchronously on target cancellation and disposal', async () => {
    for (const action of ['close', 'target', 'dispose'] as const) {
      const client = new ResultUsesClient(() => {}, path => response(path.includes('/contexts/') ? detail() : page()));
      client.target(target); await client.refresh(); const inspected = await client.inspect(row);
      expect(inspected).not.toBeNull(); expect(client.isCurrentDetail(inspected!)).toBe(true);
      if (action === 'dispose') client.dispose(); else client.target(action === 'close' ? null : { ...target, artifactId: 'F1' });
      expect(client.isCurrentDetail(inspected!)).toBe(false);
    }
  });
});
