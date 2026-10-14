import { expect, test } from 'bun:test';
import { AuthoredFindingClient, FINDING_KEY, authoredFindingId, checkAuthoredFinding, findingDraftText, findingSupport, isAuthoredFinding, readFindingDraft, type FindingDraft } from '../src/lib/authored-finding';
import { artifactKind, experimentBaselines, resolveArtifactSource } from '../src/lib/artifact-inputs';
import { artifacts, outputEvidence, resolveTarget } from '../src/lib/comparison';
import { SavedWorkClient } from '../src/lib/saved-work';
import type { AuthoredFinding, Investigation, InvestigationContext, NativeInvestigationArtifact } from '../src/lib/types';

const context: InvestigationContext = { id: 'C0', parentContextId: null, question: 'What should survive restart?', records: [{ seq: 1, threadId: 'public', source: 'authored', direction: 'internal', method: null, rawText: 'public source', sha256: 'hash' }],
  selections: [{ threadId: 'public', startSeq: 1, endSeq: 1, rationale: 'Recovery evidence' }], projectedPrompt: 'frozen C0 prompt', coverage: 'selected evidence', createdAtMs: 1 };
const owner = (): Investigation => ({ schemaVersion: 1, id: 'owner', title: 'Recovery finding', contexts: [structuredClone(context)], currentContextId: 'C0', createdAtMs: 1, status: 'draft', attempt: null, artifact: null, adoption: null });
const prose = 'Keep the stopped reservation. [evidence:1]\nOpen question: when should it expire?';
function store() { const values = new Map<string, string>(); return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } }; }
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function held<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => resolve = yes); return { resolve, promise }; }
async function finding(changes: Partial<AuthoredFinding> = {}, investigationId = 'owner'): Promise<AuthoredFinding> {
  const value: AuthoredFinding = { id: '', kind: 'owner-authored-finding', contextId: 'C0', text: prose, citations: [1], unsupportedCitations: [], artifactCitations: [], unsupportedArtifactCitations: [], authorship: { kind: 'local-owner', createdAtMs: 123 }, ...changes };
  value.id = await authoredFindingId(investigationId, value); return value;
}
async function ready(send?: (url: string, init?: RequestInit) => Promise<Response>) {
  const storage = store(), calls: { url: string; init?: RequestInit }[] = [], value = await finding();
  const client = new AuthoredFindingClient(storage, () => {}, async (url, init) => { calls.push({ url, init }); return send ? send(url, init) : response({ finding: value }, 201); }, () => 'request-F0');
  client.restore(); client.stage(owner(), context); client.edit(prose);
  return { client, storage, calls, value };
}

test('staged finding stays on exact saved C0 despite current context/owner changes', async () => {
  const work = owner(), storage = store(), client = new AuthoredFindingClient(storage, () => {});
  client.restore(); expect(client.stage(work, { ...context, question: 'caller override' })).toBe(true);
  work.contexts.push({ ...context, id: 'C1', question: 'Newer question' }); work.currentContextId = 'C1';
  expect(client.stage({ ...work, id: 'other-owner' }, work.contexts[1])).toBe(false);
  expect(client.state.draft?.source).toEqual({ investigationId: 'owner', contextId: 'C0', title: 'Recovery finding', question: context.question });
  expect(work.attempt).toBeNull(); expect(work.artifact).toBeNull(); expect(work.status).toBe('draft');
});

test('save persists exact request first, deduplicates concurrent clicks, and does not touch editor keys', async () => {
  const wait = held<Response>();
  const { client, storage, calls, value } = await ready(async (_url, init) => {
    expect(readFindingDraft(storage.getItem(FINDING_KEY)!).request).toBe(init!.body as string); return wait.promise;
  });
  storage.values.set('nema.investigation-draft.v1', 'INDEPENDENT_PENDING_EDITOR');
  storage.values.set('nema.context-input-draft.v1', 'INDEPENDENT_CREATION');
  const first = client.save(), second = client.save(); expect(first).toBe(second);
  client.edit('Do not replace the pending text.');
  wait.resolve(response({ finding: value }, 201)); await first;
  expect(calls).toHaveLength(1); expect(client.state.finding).toEqual(value);
  expect(client.state.draft?.text).toBeNull(); expect(client.state.draft?.savedId).toBe(value.id);
  expect(findingDraftText(client.state.draft!)).toBe(prose);
  expect(storage.getItem('nema.investigation-draft.v1')).toBe('INDEPENDENT_PENDING_EDITOR');
  expect(storage.getItem('nema.context-input-draft.v1')).toBe('INDEPENDENT_CREATION');
  expect(storage.getItem(FINDING_KEY)).not.toContain('public source');
});

test('lost save reply restores without POST; receipt GET recovers original F0 after owner advances', async () => {
  const { client, storage, value } = await ready(async () => { throw Error('lost reply'); }); await client.save();
  const requests: [string, RequestInit | undefined][] = [];
  const restored = new AuthoredFindingClient(storage, () => {}, async (url, init) => { requests.push([url, init]); return response({ finding: value }); });
  restored.restore(); expect(requests).toEqual([]); expect(restored.state.finding).toBeNull();
  await restored.checkReceipt();
  expect(requests).toEqual([['/api/investigations/owner/findings/requests/request-F0', undefined]]);
  expect(restored.state.finding?.contextId).toBe('C0'); expect(restored.state.finding?.text).toBe(prose);
});

test('unknown receipt stays pending and exact retry reuses bytes and request ID', async () => {
  const { client, storage, calls, value } = await ready(async () => { throw Error('lost'); }); await client.save();
  const originalRequest = calls[0].init!.body;
  const retried: RequestInit[] = [];
  const restored = new AuthoredFindingClient(storage, () => {}, async (_url, init) => {
    if (!init) return response({ error: 'missing' }, 404);
    retried.push(init); return response({ finding: value });
  }, () => { throw Error('must retain old request ID'); });
  restored.restore(); await restored.checkReceipt();
  expect(restored.state.error).toContain('outcome remains unknown'); restored.dismiss();
  expect(restored.state.draft).not.toBeNull(); await restored.save();
  expect(retried).toHaveLength(1); expect(retried[0].body).toBe(originalRequest);
});

test('savedId after restart still requires receipt matching exact ID, context and prose', async () => {
  const { client, storage } = await ready(); await client.save();
  const wrong = await finding({ text: 'Later finding', contextId: 'C1' });
  const restored = new AuthoredFindingClient(storage, () => {}, async () => response({ finding: wrong }));
  restored.restore(); const raw = storage.getItem(FINDING_KEY); await restored.checkReceipt();
  expect(restored.state.finding).toBeNull(); expect(restored.state.error).toContain('exact saved finding'); expect(storage.getItem(FINDING_KEY)).toBe(raw);
});

test('storage failure blocks sending, complete slot/outbound request limits checked before POST', async () => {
  const { client, storage, calls } = await ready();
  storage.setItem = () => { throw Error('storage unavailable'); }; await client.save(); expect(calls).toHaveLength(0);
  const another = await ready(); another.client.edit('\u0000'.repeat(50000));
  await another.client.save(); expect(another.calls).toHaveLength(0); expect(another.client.state.error).toContain('256 KiB');
  expect(another.client.state.draft?.request).toBeNull();
  expect(() => readFindingDraft(' '.repeat(512 * 1024 + 1))).toThrow('512 KiB');
});

test('finding text enforces UTF-8 bytes and rejects invalid scalars while retaining previous text', async () => {
  const { client } = await ready(); client.edit('語'.repeat(50000)); expect(findingDraftText(client.state.draft!)).toBe(prose);
  client.edit('\ud800'); expect(findingDraftText(client.state.draft!)).toBe(prose);
});

test.each(['not-json', '{"foreign":"slot"}'])('malformed recovery is preserved and cannot send', async raw => {
  const storage = store(); storage.values.set(FINDING_KEY, raw); let calls = 0;
  const client = new AuthoredFindingClient(storage, () => {}, async () => { calls++; return response({}); });
  client.restore(); client.stage(owner(), context); client.edit(prose); await client.save(); await client.checkReceipt(); client.dismiss();
  expect(client.state.unavailable).toBe(true); expect(calls).toBe(0); expect(storage.getItem(FINDING_KEY)).toBe(raw);
});

test('different-tab slot cannot be overwritten or dismissed by a delayed refusal', async () => {
  const wait = held<Response>(), { client, storage } = await ready(async () => wait.promise);
  const task = client.save(); storage.values.set(FINDING_KEY, 'FOREIGN_RECOVERY');
  wait.resolve(response({ error: 'stale' }, 409)); await task;
  expect(client.state.unavailable).toBe(true); expect(client.state.refusal).toBe(''); client.dismiss();
  expect(storage.getItem(FINDING_KEY)).toBe('FOREIGN_RECOVERY');
});

test('disposed save cannot change recovery under a replacement client', async () => {
  const wait = held<Response>(), { client, storage, value } = await ready(async () => wait.promise);
  const task = client.save(), raw = storage.getItem(FINDING_KEY);
  client.dispose();
  const replacement = new AuthoredFindingClient(storage, () => {}, async () => response({ finding: value }));
  replacement.restore(); wait.resolve(response({ finding: value }, 201)); await task;
  expect(storage.getItem(FINDING_KEY)).toBe(raw);
  await replacement.checkReceipt();
  expect(replacement.state.unavailable).toBe(false); expect(replacement.state.finding).toEqual(value);
});

test.each([400, 404, 409, 413])('only explicit dismissal clears a well-formed POST refusal %i', async status => {
  const { client, storage } = await ready(async () => response({ error: 'refused' }, status)); await client.save();
  expect(client.state.refusal).toContain('refused'); expect(storage.getItem(FINDING_KEY)).not.toBeNull(); client.dismiss(); expect(storage.getItem(FINDING_KEY)).toBeNull();
});

test.each([response({ error: 'retry later' }, 500), response({ other: 'malformed' }, 409), new Response('invalid JSON'), response({ finding: {} })])('unknown responses remain pending without dismissal', async res => {
  const { client, storage } = await ready(async () => res); await client.save(); const raw = storage.getItem(FINDING_KEY);
  client.dismiss(); expect(storage.getItem(FINDING_KEY)).toBe(raw); expect(client.state.refusal).toBe('');
});

test('oversized receipt does not become confirmed', async () => {
  const { client } = await ready(async () => new Response(' '.repeat(256 * 1024 + 1))); await client.save();
  expect(client.state.finding).toBeNull(); expect(client.state.error).toContain('256 KiB');
});

test('independent canonical hash vector includes owner and exact Unicode content', async () => {
  const value = await finding({ text: 'Café: retain it. [evidence:1]', unsupportedCitations: [0] });
  expect(value.id).toBe('artifact_4d1f035f5dc238ee7e2e7a80651812794d08280cd21378f0b3cf1cd853f7bb35');
  expect(await checkAuthoredFinding(value, 'owner')).toEqual(value);
  await expect(checkAuthoredFinding(value, 'wrong-owner')).rejects.toThrow('recorded owner');
});

test('zero is permitted only as unsupported; unsafe numeric citations are refused', async () => {
  const value = await finding({ citations: [], unsupportedCitations: [0, 9007199254740991] });
  expect(isAuthoredFinding(value)).toBe(true);
  expect(isAuthoredFinding({ ...value, citations: [0] })).toBe(false);
  expect(isAuthoredFinding({ ...value, unsupportedCitations: [9007199254740992] })).toBe(false);
});

test('uncited hypotheses and directly supplied artifact citations have distinct labels', async () => {
  const hypothesis = await finding({ citations: [], unsupportedCitations: [99] });
  expect(findingSupport(hypothesis)).toBe('No cited support');
  expect(findingSupport(await finding({ citations: [], artifactCitations: ['artifact_supplied'] }))).toBe('Cited sources supplied; claims not verified');
  expect(artifactKind(hypothesis)).toBe('Authored finding'); expect(outputEvidence(hypothesis)).toBe('Saved in this workbench');
});

test('canonical findings enumerate for exact source/reuse/comparison without attempts', async () => {
  const work = owner(), value = await finding(); work.findings = [value];
  expect(artifacts(work)).toEqual([value]); expect(experimentBaselines(work)).toEqual([]);
  const ref = { investigationId: work.id, contextId: 'C0', artifactId: value.id };
  expect(resolveArtifactSource(work, ref)).toEqual({ artifact: value, context: work.contexts[0], attempt: null });
  expect(resolveTarget([work], ref).artifact).toEqual(value);
  work.currentContextId = 'C1'; work.contexts.push({ ...context, id: 'C1' });
  expect(resolveTarget([work], ref).context?.id).toBe('C0');
  expect(resolveArtifactSource(work, { ...ref, contextId: 'C1' })).toBeNull();
});

test('forged authored kind in native slots and malformed findings never bypass attempt provenance', async () => {
  const work = owner(), value = await finding();
  work.artifact = value as unknown as NativeInvestigationArtifact;
  expect(artifacts(work)).toEqual([]); expect(resolveArtifactSource(work, { investigationId: work.id, artifactId: value.id })).toBeNull();
  work.findings = [value]; expect(artifacts(work)).toEqual([]);
  work.artifact = null; work.findings = [{ ...value, attemptId: 'fake-attempt' } as unknown as AuthoredFinding];
  expect(artifacts(work)).toEqual([]);
});

test('authored source endpoint validates exact hash/context and null native state', async () => {
  const value = await finding();
  const payload = { version: 'v1', investigationId: 'owner', investigationTitle: 'Recovery finding', artifact: value, context, attempt: null, adoption: null };
  const ref = { investigationId: 'owner', contextId: 'C0', artifactId: value.id };
  expect((await new SavedWorkClient(async () => response(payload)).source(ref)).attempt).toBeNull();
  for (const bad of [{ ...payload, investigationId: 'other' }, { ...payload, context: { ...context, id: 'C1' } }, { ...payload, attempt: { id: 'pretend-native', contextId: 'C0' } }, { ...payload, adoption: { artifactId: value.id } }, { ...payload, artifact: { ...value, outputSeqs: [1] } }]) {
    await expect(new SavedWorkClient(async () => response(bad)).source(ref)).rejects.toThrow();
  }
});

test('native source remains attempt-bound and authored findings do not grant experiment baselines', async () => {
  const work = owner(), value = await finding(); work.findings = [value];
  const native: NativeInvestigationArtifact = { id: 'native-A0', contextId: 'C0', attemptId: 'T0', text: 'Native result', citations: [1], unsupportedCitations: [], outputSeqs: [2] };
  work.artifact = native;
  expect(experimentBaselines(work)).toEqual([]); expect(resolveArtifactSource(work, { investigationId: 'owner', artifactId: native.id })).toBeNull();
  work.attempt = { id: 'T0', contextId: 'C0', status: 'completed', source: 'native', threadId: 'native', turnId: 'turn', startedAtMs: 1, timeoutSeconds: 120, error: null };
  expect(experimentBaselines(work)).toEqual([native]); expect(artifacts(work)).toEqual([native, value]);
  expect(resolveArtifactSource(work, { investigationId: 'owner', artifactId: value.id })?.attempt).toBeNull();
});

test('valid same-text receipt under another owner cannot confirm this save', async () => {
  const wrong = await finding({}, 'other-owner'); const { client } = await ready(async () => response({ finding: wrong }));
  await client.save(); expect(client.state.finding).toBeNull(); expect(client.state.draft?.savedId).toBeNull();
});
