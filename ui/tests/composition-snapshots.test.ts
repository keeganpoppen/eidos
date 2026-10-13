import { describe, expect, test } from 'bun:test';
import { version as installedMarkdownVersion } from 'marked/package.json';
import { evidenceChain, emptyComposition, readComposition, resolveTarget, type Composition } from '../src/lib/comparison';
import { captureSnapshot, CompositionClient, openSnapshot, readSnapshotDraft, sameSnapshotView, supportsBlockFocus, type CompositionSnapshot } from '../src/lib/composition-snapshots';
import { contentBlocks, rendererVersion } from '../src/lib/semantic';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function state(): Composition {
  const work = makeReflectionFixture('supplied').investigations[0];
  const artifact = work.nativeArtifact!;
  const block = contentBlocks(artifact.text).find((block) => block.citations.includes(12))!;
  return { ...emptyComposition(), open: true, arrangement: evidenceChain(work), focusRendererVersion: rendererVersion,
    focus: { investigationId: work.id, contextId: artifact.contextId, artifactId: artifact.id, blockId: block.id, seq: 12, threadId: 'fixture:design' } };
}
function envelope(composition = state()): CompositionSnapshot {
  const body = captureSnapshot('Return to the original', composition, 'request-fixed');
  const { requestId, ...fields } = body;
  return { ...fields, schemaVersion: 1, id: 'composition-original', contentId: 'sha256:original', createdAtMs: 1, copiedFrom: body.copiedFrom ?? null };
}
function reordered<T>(value: T): T {
  if (value && typeof value === 'object' && !Array.isArray(value)) return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, reordered(child)])) as T;
  return value;
}

describe('immutable saved comparison references', () => {
  test('capture excludes browser controls, drafts, histories, copied content and semantic requests', () => {
    const original = { ...state(), undo: [null], draft: { question: 'private unsaved question', pendingRequestId: 'local-only' }, attentionRequest: 'recompile later', arrangement: { ...state().arrangement!, records: ['copied evidence'] } };
    const captured = captureSnapshot('  Return later  ', original, 'same-request');
    expect(Object.keys(captured).sort()).toEqual(['arrangement', 'focus', 'rendererVersion', 'requestId', 'title']);
    expect(captured.title).toBe('Return later');
    expect(JSON.stringify(captured)).not.toMatch(/private|pendingRequest|records|undo|recompile|open/);
    original.arrangement.left.contextId = 'later-context';
    original.focus!.seq = 99;
    expect(captured.arrangement.left.contextId).not.toBe('later-context');
    expect(captured.focus!.seq).toBe(12);
  });

  test('lost committed response survives reload and retries exact captured body despite changed view', async () => {
    const original = state();
    const body = captureSnapshot('Return to the original', original, 'retry-identity');
    const receipt = envelope(original);
    const requests: string[] = [];
    const client = new CompositionClient(async (path, init) => {
      expect(path).toBe('/api/compositions');
      requests.push(init!.body as string);
      if (requests.length === 1) throw new Error('response lost after commit');
      return json({ composition: reordered(receipt) }, 201);
    });
    await expect(client.save(body)).rejects.toThrow('response lost');
    const raw = JSON.stringify({ version: 1, title: body.title, pending: body });
    original.arrangement!.layout = 'stacked'; original.focus = null;
    const recovered = readSnapshotDraft(raw);
    expect(await client.save(recovered.pending!)).toEqual(reordered(receipt));
    expect(requests[1]).toBe(requests[0]);
    expect(recovered.pending!.requestId).toBe('retry-identity');
    expect(recovered.pending!.arrangement.layout).toBe('beside');
    expect(sameSnapshotView(original, receipt)).toBe(false);
    expect(sameSnapshotView(state(), reordered(receipt))).toBe(true);
  });

  test('open copies historical compiled pins without rebinding a newly answered inquiry; save-copy preserves ancestry', () => {
    const pending = makeReflectionFixture('pending');
    const old = { ...emptyComposition(), arrangement: evidenceChain(pending.investigations[0]) };
    const saved = envelope(old);
    const before = JSON.stringify(saved);
    const answered = makeReflectionFixture('supplied');
    const newer = { ...state(), arrangement: evidenceChain(answered.investigations[0]) };
    const opened = openSnapshot(newer, saved);
    expect(opened.arrangement!.right.artifactId).toBeUndefined();
    expect(opened.arrangement!.inquiry!.responseId).toBeUndefined();
    expect(resolveTarget(answered.investigations, opened.arrangement!.right).artifact).toBeUndefined();
    expect(opened.undo.at(-1)).toEqual(newer.arrangement);
    opened.arrangement!.layout = 'stacked';
    const copy = captureSnapshot('An altered copy', opened, 'copy-request');
    expect(copy.copiedFrom).toBe(saved.id);
    expect(copy.arrangement.layout).toBe('stacked');
    expect(JSON.stringify(saved)).toBe(before);
    expect(resolveTarget([], opened.arrangement!.left).context).toBeUndefined();
    expect(opened.arrangement!.left).toEqual(saved.arrangement.left);
  });

  test('a recovered save from an older renderer confirms its original receipt after upgrade without block focus', async () => {
    const oldRenderer = 'nema-content-blocks/v0;marked@17.0.0';
    for (const focus of [null, { investigationId: 'owner', contextId: 'context', seq: 1, threadId: 'thread' }]) {
      const body = { ...captureSnapshot('Saved before upgrade', { ...state(), focus }, 'old-request'), rendererVersion: oldRenderer };
      const recovered = readSnapshotDraft(JSON.stringify({ version: 1, title: body.title, pending: body })).pending!;
      const receipt = { ...envelope(), ...body, copiedFrom: null };
      const client = new CompositionClient(async (_path, init) => {
        expect(JSON.parse(init!.body as string)).toEqual(body);
        return json({ composition: reordered(receipt) }, 201);
      });
      expect((await client.save(recovered)).rendererVersion).toBe(oldRenderer);
      const wrong = new CompositionClient(async () => json({ composition: { ...receipt, rendererVersion } }, 201));
      await expect(wrong.save(recovered)).rejects.toThrow('captured references');
    }
  });

  test('unsupported renderer cannot select an identically numbered block, including after local reload and another save', () => {
    expect(rendererVersion).toBe(`nema-content-blocks/v1;marked@${installedMarkdownVersion}`);
    const unknown = { ...envelope(), rendererVersion: 'nema-content-blocks/v99;marked@99.0.0' };
    const opened = readComposition(JSON.stringify(openSnapshot(emptyComposition(), unknown)));
    expect(opened.focus).toEqual(unknown.focus);
    expect(opened.snapshotId).toBe(unknown.id);
    expect(contentBlocks(makeReflectionFixture('supplied').investigations[0].nativeArtifact!.text).some((block) => block.id === opened.focus!.blockId)).toBe(true);
    expect(supportsBlockFocus(opened.focus, opened.focusRendererVersion!)).toBe(false);
    expect(captureSnapshot('Keep unresolved selector', opened).rendererVersion).toBe(unknown.rendererVersion);
    expect(supportsBlockFocus({ ...opened.focus!, blockId: undefined }, unknown.rendererVersion)).toBe(true);
  });

  test('metadata search/pages and exact preview reads never write or automatically apply browser state', async () => {
    const calls: Array<{ path: string; init?: RequestInit }> = [];
    const receipt = envelope();
    const client = new CompositionClient(async (path, init) => {
      calls.push({ path, init });
      return path.includes('?') ? json({ compositions: [], nextCursor: null }) : json({ composition: receipt });
    });
    const browser = state(); const before = JSON.stringify(browser);
    await client.list('Older / title', 'opaque/+');
    const preview = await client.get(receipt.id);
    expect(calls[0].path).toBe('/api/compositions?limit=20&q=Older+%2F+title&cursor=opaque%2F%2B');
    expect(calls[1].path).toBe(`/api/compositions/${receipt.id}`);
    expect(calls.every((call) => call.init === undefined)).toBe(true);
    expect(preview.arrangement).toEqual(receipt.arrangement);
    expect(JSON.stringify(browser)).toBe(before);
  });

  test('wrong identities/receipts and malformed recovery never silently adopt or normalize another snapshot', async () => {
    const receipt = envelope();
    const client = new CompositionClient(async () => json({ composition: { ...receipt, focus: null } }));
    await expect(client.get('different-id')).rejects.toThrow('identity');
    await expect(client.save(captureSnapshot(receipt.title, state()))).rejects.toThrow('captured references');
    expect(() => readSnapshotDraft('{broken')).toThrow('left unchanged');
    expect(() => readSnapshotDraft(JSON.stringify({ version: 1, pending: { requestId: 'same', arrangement: null } }))).toThrow('cannot be recovered');
  });
});
