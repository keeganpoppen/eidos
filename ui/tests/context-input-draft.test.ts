import { describe, expect, test } from 'bun:test';
import { CONTEXT_INPUT_DRAFT_KEY, ContextInputDraftClient, createdInputContext, inputDraftOpenDecision, readInputDraft } from '../src/lib/context-input-draft';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import type { Investigation } from '../src/lib/types';

const old = () => makeReflectionFixture('supplied').investigations[0];
function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}
function setup(fetcher?: (path: string, init?: RequestInit) => Promise<Response>, store = memory()) {
  const owner = old(), context = owner.contexts[0];
  const client = new ContextInputDraftClient(store, () => {}, fetcher, () => 'new-request-1');
  client.restore(); client.stage(owner, context); client.edit('question', 'A genuinely new question');
  return { owner, context, client, store };
}
function created(body: string): Investigation {
  const request = JSON.parse(body), work = old();
  work.id = 'new-work'; work.title = request.title;
  work.contexts = [{ ...work.contexts[0], id: 'created-context', question: request.question, parentContextId: null,
    inputOrigin: { version: 1, kind: 'historical-context-inputs', ...request.inputSource, manifestId: 'source-manifest' } }];
  work.currentContextId = 'created-context'; work.attempt = null; work.artifact = null; work.status = 'draft';
  return work;
}
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => resolve = yes);
  return { promise, resolve };
};

describe('separate historical-input creation', () => {
  test('stages exact selected context with blank question and only bounded metadata', () => {
    const store = memory(), owner = old(), selected = owner.contexts[0];
    owner.currentContextId = 'newer-context';
    const client = new ContextInputDraftClient(store, () => {}); client.restore();
    expect(client.stage(owner, selected)).toBe(true);
    expect(client.state.draft?.source.contextId).toBe(selected.id);
    expect(client.state.draft?.question).toBe('');
    const stored = store.getItem(CONTEXT_INPUT_DRAFT_KEY)!;
    expect(stored).not.toContain(selected.projectedPrompt);
    expect(stored).not.toContain('records'); expect(stored).not.toContain('rawText');
    expect(client.stage({ ...owner, id: 'other-owner' }, selected)).toBe(false);
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(stored);
  });

  test('commit response loss, reload and exact retry never touch the original pending draft or send automatically', async () => {
    const store = memory(); const original = '{"question":"unsaved","pendingRequest":{"id":"old-request","body":"old-body"}}';
    store.setItem('nema.investigation-draft.v1', original);
    const bodies: string[] = [];
    const first = setup(async (_path, init) => { bodies.push(init!.body as string); throw Error('authored lost reply after commit'); }, store);
    await first.client.create();
    const pending = store.getItem(CONTEXT_INPUT_DRAFT_KEY)!;
    expect(first.client.state.draft?.request).toBe(bodies[0]);
    first.client.edit('question', 'changed'); first.client.cancel();
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(pending);
    first.client.dispose();
    const second = new ContextInputDraftClient(store, () => {}, async (_path, init) => {
      bodies.push(init!.body as string); return response(created(bodies.at(-1)!));
    }, () => { throw Error('retry must not generate another identity'); });
    second.restore();
    expect(bodies).toHaveLength(1);
    await second.create();
    expect(bodies).toEqual([bodies[0], bodies[0]]);
    expect(JSON.parse(bodies[0])).toEqual({ requestId: 'new-request-1', title: first.client.state.draft!.title,
      question: 'A genuinely new question', inputSource: { investigationId: first.owner.id, contextId: first.context.id } });
    expect(second.state.draft?.saved).toEqual({ investigationId: 'new-work', contextId: 'created-context' });
    expect(store.getItem('nema.investigation-draft.v1')).toBe(original);
    const third = new ContextInputDraftClient(store, () => {}, async () => { throw Error('reload must not send'); });
    third.restore(); expect(third.state.draft?.saved).toEqual(second.state.draft?.saved);
  });

  test('persistence failure before send refuses network and retains staged state', async () => {
    let calls = 0; const { client, store } = setup(async () => { calls++; return response({}); });
    const before = store.getItem(CONTEXT_INPUT_DRAFT_KEY);
    store.setItem = () => { throw Error('authored full storage'); };
    await client.create();
    expect(calls).toBe(0); expect(client.state.draft?.request).toBeNull();
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(before); expect(client.state.error).toContain('storage');
  });

  test('failure to retain successful receipt keeps the original exact retry', async () => {
    const store = memory(); let body = '';
    const { client } = setup(async (_path, init) => {
      body = init!.body as string; store.setItem = () => { throw Error('receipt storage failed'); };
      return response(created(body));
    }, store);
    await client.create();
    expect(client.state.draft?.saved).toBeNull(); expect(client.state.draft?.request).toBe(body);
    expect(readInputDraft(store.getItem(CONTEXT_INPUT_DRAFT_KEY)!).request).toBe(body);
  });

  test('pending creation cannot be edited, dismissed, retargeted or sent twice', async () => {
    const later = deferred<Response>(); let calls = 0;
    const { client, store, owner, context } = setup(async () => { calls++; return later.promise; });
    const sending = client.create(), pending = store.getItem(CONTEXT_INPUT_DRAFT_KEY)!;
    client.edit('title', 'changed'); client.edit('question', 'changed'); client.cancel();
    expect(client.stage({ ...owner, id: 'another-owner' }, context)).toBe(false);
    expect(client.create()).toBe(sending); expect(calls).toBe(1);
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(pending);
    later.resolve(response(created(client.state.draft!.request!))); await sending;
  });

  test('explicit missing-source refusal retains request through reload until deliberately dismissed', async () => {
    const { client, store } = setup(async () => response({ error: 'Exact source context is unavailable' }, 404));
    await client.create();
    const request = client.state.draft!.request;
    expect(client.state.draft?.refusal).toEqual({ status: 404, message: 'Exact source context is unavailable' });
    const restored = new ContextInputDraftClient(store, () => {}, async () => { throw Error('must not send automatically'); });
    restored.restore();
    expect(restored.state.draft?.request).toBe(request);
    restored.edit('question', 'replace refused body'); expect(restored.state.draft?.request).toBe(request);
    restored.cancel(); expect(restored.state.draft).toBeNull(); expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBeNull();
  });

  test('retry after refusal keeps identity and an uncertain failure becomes locked pending again', async () => {
    const bodies: string[] = [];
    const { client, store } = setup(async (_path, init) => {
      bodies.push(init!.body as string);
      return response({ error: 'authored refusal or uncertainty' }, bodies.length === 1 ? 409 : 503);
    });
    await client.create(); expect(client.state.draft?.refusal?.status).toBe(409);
    await client.create(); expect(bodies).toEqual([bodies[0], bodies[0]]);
    expect(client.state.draft?.refusal).toBeNull();
    const pending = store.getItem(CONTEXT_INPUT_DRAFT_KEY); client.cancel();
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(pending);
  });

  test('another view changing storage prevents a stale reply from replacing it', async () => {
    const later = deferred<Response>(); const { client, store } = setup(async () => later.promise);
    const sending = client.create(), request = client.state.draft!.request!;
    const other = '{"authoredLaterRecoveryEntry":true}'; store.setItem(CONTEXT_INPUT_DRAFT_KEY, other);
    later.resolve(response(created(request))); await sending;
    expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(other);
    expect(client.state.draft?.saved).toBeNull(); expect(client.state.error).toContain('later staged');
  });

  test('replay can return newer current context while the receipt pins the initial context', async () => {
    const { client } = setup(async (_path, init) => {
      const work = created(init!.body as string);
      work.contexts.push({ ...work.contexts[0], id: 'newer', parentContextId: 'created-context', question: 'Later question' });
      work.currentContextId = 'newer'; work.status = 'completed';
      return response(work);
    });
    await client.create();
    expect(client.state.draft?.saved?.contextId).toBe('created-context');
  });

  for (const mutation of ['title', 'question', 'owner', 'context', 'parent', 'ambiguous']) {
    test(`invalid ${mutation} receipt retains exact pending request`, async () => {
      const { client } = setup(async (_path, init) => {
        const work = created(init!.body as string), context = work.contexts[0];
        if (mutation === 'title') work.title = 'Different creation';
        if (mutation === 'question') context.question = 'Different question';
        if (mutation === 'owner') context.inputOrigin!.investigationId = 'different-owner';
        if (mutation === 'context') context.inputOrigin!.contextId = 'different-source-context';
        if (mutation === 'parent') context.parentContextId = 'other-context';
        if (mutation === 'ambiguous') work.contexts.push({ ...context, id: 'another-match' });
        return response(work);
      });
      await client.create();
      expect(client.state.draft?.saved).toBeNull(); expect(client.state.draft?.request).not.toBeNull();
      expect(client.state.error).toContain('receipt');
    });
  }

  test('saved reference must continue to identify the exact created context', async () => {
    const { client } = setup(async (_path, init) => response(created(init!.body as string)));
    await client.create(); const draft = client.state.draft!, work = created(draft.request!);
    expect(createdInputContext(work, draft).id).toBe('created-context');
    work.contexts[0].id = 'replacement'; expect(() => createdInputContext(work, draft)).toThrow('exact created context');
  });

  test('malformed, future-version and injected request storage never becomes a send', async () => {
    const { store } = setup();
    const valid = JSON.parse(store.getItem(CONTEXT_INPUT_DRAFT_KEY)!);
    for (const raw of ['{', JSON.stringify({ ...valid, version: 2 }), JSON.stringify({ ...valid, request: JSON.stringify({
      requestId: 'injected', title: valid.title, question: valid.question, inputSource: valid.source, selections: [] }) })]) {
      store.setItem(CONTEXT_INPUT_DRAFT_KEY, raw); let calls = 0;
      const client = new ContextInputDraftClient(store, () => {}, async () => { calls++; return response({}); });
      client.restore(); await client.create(); client.cancel();
      expect(calls).toBe(0); expect(store.getItem(CONTEXT_INPUT_DRAFT_KEY)).toBe(raw);
    }
  });

  test('open requires current pending save resolution even after replacement confirmation', () => {
    expect(inputDraftOpenDecision(false, true, false, true)).toBe('blocked');
    expect(inputDraftOpenDecision(true, false, false, true)).toBe('blocked');
    expect(inputDraftOpenDecision(false, false, true, false)).toBe('confirm');
    expect(inputDraftOpenDecision(false, false, true, true)).toBe('open');
    expect(inputDraftOpenDecision(false, false, false, false)).toBe('open');
  });
});
