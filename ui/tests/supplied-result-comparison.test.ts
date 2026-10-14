import { describe, expect, test } from 'bun:test';
import { createSuppliedComparisonLoader, suppliedComparisonRequest, validateSuppliedComparison } from '../src/lib/supplied-result-comparison';
import { applyArrangement, emptyComposition, readComposition, undoArrangement } from '../src/lib/comparison';
import { captureSnapshot, openSnapshot } from '../src/lib/composition-snapshots';
import type { ArtifactSource } from '../src/lib/saved-work';
import type { AuthoredFinding, FrozenArtifactInput, Investigation, InvestigationContext } from '../src/lib/types';
const id = (n: number) => 'artifact_' + n.toString(16).padStart(64, '0');
function finding(n: number, contextId: string, artifactCitations: string[] = []): AuthoredFinding {
  return { id: id(n), kind: 'owner-authored-finding', contextId, text: `Finding ${n}`, citations: [], unsupportedCitations: [], artifactCitations, unsupportedArtifactCitations: [], authorship: { kind: 'local-owner', createdAtMs: n } };
}
function context(id: string, inputs: FrozenArtifactInput[] = []): InvestigationContext {
  return { id, parentContextId: null, question: `Saved question ${id}`, selections: [], records: [], artifactInputs: inputs, projectedPrompt: `Saved packet ${id}`, coverage: 'selected', manifestId: 'manifest-' + id, createdAtMs: 1 };
}
function owner(id: string, contexts: InvestigationContext[], findings: AuthoredFinding[]): Investigation {
  return { schemaVersion: 1, id, title: id, createdAtMs: 1, contexts, currentContextId: contexts.at(-1)!.id, status: 'draft', findings, artifact: null, attempt: null, adoption: null };
}
function source(owner: Investigation, artifact: AuthoredFinding): ArtifactSource {
  return { version: 'version', investigationId: owner.id, investigationTitle: owner.title, artifact, context: owner.contexts.find(c => c.id === artifact.contextId)!, attempt: null, adoption: null };
}
function fixture(sameOwner = false) {
  const c0 = context('c0'), c1 = context('c1'), f0 = finding(1, c0.id), f1 = finding(2, c1.id);
  const before = owner('source', [c0, c1], [f0, f1]);
  const input: FrozenArtifactInput = { investigationId: before.id, artifactId: f0.id, artifact: structuredClone(f0), sourceContextId: c0.id, sourceManifestId: c0.manifestId!, sourceAttemptManifestId: null, sourceAdoption: null, rationale: 'Retain the exact original basis.' };
  const r0 = context('r0', [input]), r1 = context('r1'), a0 = finding(3, r0.id, [f0.id]), a1 = finding(4, r1.id);
  const after = sameOwner ? before : owner('consumer', [r0, r1], [a0, a1]);
  if (sameOwner) { before.contexts.push(r0, r1); before.findings!.push(a0, a1); before.currentContextId = r1.id; }
  return { before, after, input, f0, f1, a0, a1, c0, c1, r0, r1, request: suppliedComparisonRequest(after.id, a0, r0, input), supplied: source(before, f0), consumer: source(after, a0), owners: sameOwner ? [before] : [before, after] };
}
const deferred = <T>() => { let resolve!: (value: T) => void, reject!: (cause: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
function reads(f: ReturnType<typeof fixture>) {
  return { view: async (id: string) => f.owners.find(o => o.id === id)!, source: async (target: { artifactId: string }) => target.artifactId === f.a0.id ? f.consumer : f.supplied };
}
describe('exact supplied-result comparison', () => {
  test('historical R0 supplied F0 while both owners now have newer contexts and results', () => {
    const f = fixture(), result = validateSuppliedComparison(f.request, f.consumer, f.supplied, f.owners);
    expect(result).toEqual({ left: { investigationId: 'source', contextId: 'c0', artifactId: f.f0.id }, right: { investigationId: 'consumer', contextId: 'r0', artifactId: f.a0.id }, lens: 'result', layout: 'beside' });
    expect(result).not.toHaveProperty('intent'); expect(result).not.toHaveProperty('experimentId');
    expect(f.after.currentContextId).toBe('r1'); expect(f.before.currentContextId).toBe('c1');
  });
  test('request requires a cited input of the displayed result and captures independent bytes', () => {
    const f = fixture();
    expect(() => suppliedComparisonRequest(f.after.id, f.a0, f.r1, f.input)).toThrow();
    expect(() => suppliedComparisonRequest(f.after.id, { ...f.a0, artifactCitations: [] }, f.r0, f.input)).toThrow();
    expect(() => suppliedComparisonRequest(f.after.id, f.a0, f.r0, { ...f.input, rationale: 'edited browser input' })).toThrow();
    const captured = suppliedComparisonRequest(f.after.id, f.a0, f.r0, f.input); f.input.artifact.text = 'Changed after capture';
    expect(captured.input.artifact.text).toBe('Finding 1');
  });
  for (const change of ['source-owner', 'source-context', 'source-artifact', 'frozen-text', 'source-manifest', 'attempt-manifest', 'consumer-owner', 'consumer-context', 'consumer-text', 'consumer-manifest', 'consumer-input'] as const) {
    test(`refuses ${change} mismatch`, () => {
      const f = fixture(), supplied = structuredClone(f.supplied), consumer = structuredClone(f.consumer);
      switch (change) {
        case 'source-owner': supplied.investigationId = 'other'; break;
        case 'source-context': supplied.context.id = 'new'; break;
        case 'source-artifact': supplied.artifact.id = f.f1.id; break;
        case 'frozen-text': supplied.artifact.text = 'Same ID, substituted contents'; break;
        case 'source-manifest': supplied.context.manifestId = 'another-manifest'; break;
        case 'attempt-manifest': f.request.input.sourceAttemptManifestId = 'missing-attempt-manifest'; break;
        case 'consumer-owner': consumer.investigationId = 'other'; break;
        case 'consumer-context': consumer.context.id = f.r1.id; break;
        case 'consumer-text': consumer.artifact.text = 'Different displayed finding'; break;
        case 'consumer-manifest': consumer.context.manifestId = 'new'; break;
        case 'consumer-input': consumer.context.artifactInputs = []; break;
      }
      expect(() => validateSuppliedComparison(f.request, consumer, supplied, f.owners)).toThrow();
    });
  }
  test('JSON object key order is immaterial', () => {
    const f = fixture(); f.supplied.artifact = Object.fromEntries(Object.entries(f.supplied.artifact).reverse()) as AuthoredFinding;
    expect(validateSuppliedComparison(f.request, f.consumer, f.supplied, f.owners).left.artifactId).toBe(f.f0.id);
    expect(f.request.input.sourceAdoption).toBeNull();
  });
  test('native result unknown fields and attempt pins remain exact while later source review may differ', () => {
    const f = fixture();
    const native = { id: f.f0.id, contextId: 'c0', attemptId: 'attempt', text: 'Native recorded baseline', citations: [], unsupportedCitations: [], outputSeqs: [20], future: { retained: ['exact'] } };
    const attempt = { id: 'attempt', contextId: 'c0', status: 'completed', source: 'recorded', threadId: 'thread', turnId: 'turn', startedAtMs: 1, timeoutSeconds: 20, error: null, manifestId: 'attempt-manifest' };
    f.before.artifact = native; f.before.attempt = attempt; f.before.findings = [f.f1];
    f.input.artifact = structuredClone(native); f.input.sourceAttemptManifestId = attempt.manifestId;
    f.request = suppliedComparisonRequest(f.after.id, f.a0, f.r0, f.input);
    f.supplied = { ...f.supplied, artifact: native, attempt, adoption: { artifactId: native.id, decision: 'reject', note: 'Later separate source review', createdAtMs: 42 } };
    expect(validateSuppliedComparison(f.request, f.consumer, f.supplied, f.owners).left.artifactId).toBe(native.id);
    const altered = structuredClone(f.supplied); (altered.artifact as typeof native).future.retained = ['substituted'];
    expect(() => validateSuppliedComparison(f.request, f.consumer, altered, f.owners)).toThrow();
  });
  test('a later owner refresh invalidates removed or changed exact pins before Apply', async () => {
    const f = fixture(), proposal = (await createSuppliedComparisonLoader(reads(f)).load(f.request))!;
    for (const change of ['missing-owner', 'removed-result', 'changed-context']) {
      const owners = structuredClone(f.owners);
      if (change === 'missing-owner') owners.shift();
      if (change === 'removed-result') owners[0].findings = [f.f1];
      if (change === 'changed-context') owners[0].contexts[0].question = 'Changed under an old context ID';
      expect(() => validateSuppliedComparison(proposal.request, proposal.consumer, proposal.supplied, owners)).toThrow();
    }
  });
  test('same-owner targets retain both results with one owner-view fetch', async () => {
    const f = fixture(true), views: string[] = [], targets: string[] = [];
    const loader = createSuppliedComparisonLoader({ view: async id => { views.push(id); return f.before; }, source: async target => { targets.push(target.artifactId); return target.artifactId === f.a0.id ? f.consumer : f.supplied; } });
    const result = (await loader.load(f.request))!;
    expect(views).toEqual(['source']); expect(targets).toEqual([f.a0.id, f.f0.id]);
    expect(result.arrangement.left.contextId).toBe('c0'); expect(result.arrangement.right.contextId).toBe('r0');
  });
  test('read-only staging plus existing Apply/Undo/save/reopen preserves separate focus and exact pair', async () => {
    const f = fixture(), focus = { investigationId: 'outside', contextId: 'retained-focus' };
    const original = { ...emptyComposition(), focus, arrangement: { left: { investigationId: 'consumer', contextId: 'r1' }, right: { investigationId: 'consumer', contextId: 'r1' }, lens: 'context' as const, layout: 'stacked' as const } };
    const bytes = JSON.stringify(original), proposal = (await createSuppliedComparisonLoader(reads(f)).load(f.request))!;
    expect(JSON.stringify(original)).toBe(bytes);
    const applied = applyArrangement(original, proposal.arrangement), saved = captureSnapshot('Retained basis and decision', applied, 'exact-save');
    expect(saved.arrangement).toEqual(proposal.arrangement); expect(saved.focus).toEqual(focus);
    expect(undoArrangement(readComposition(JSON.stringify(applied)))).toMatchObject({ arrangement: original.arrangement, focus });
    const opened = openSnapshot(original, { ...saved, schemaVersion: 1, id: 'comparison', contentId: 'content', createdAtMs: 1, copiedFrom: null });
    expect(opened.arrangement.left.artifactId).toBe(f.f0.id); expect(opened.arrangement.right.artifactId).toBe(f.a0.id);
  });
  for (const reason of ['close', 'manual-edit', 'new-intent', 'snapshot-open', 'dispose']) {
    test(`${reason} discards late successful and failed reads`, async () => {
      for (const fails of [false, true]) {
        const f = fixture(), held = deferred<ArtifactSource>();
        const loader = createSuppliedComparisonLoader({ ...reads(f), source: target => target.artifactId === f.f0.id ? held.promise : Promise.resolve(f.consumer) });
        const pending = loader.load(f.request); if (reason === 'dispose') loader.dispose(); else loader.cancel();
        if (fails) held.reject(Error('Late failed read')); else held.resolve(f.supplied);
        expect(await pending).toBeNull();
      }
    });
  }
  test('new request wins; caller mutation cannot retarget an in-flight capture', async () => {
    const f = fixture(), first = deferred<ArtifactSource>(); let calls = 0;
    const loader = createSuppliedComparisonLoader({ ...reads(f), source: target => target.artifactId === f.a0.id ? Promise.resolve(f.consumer) : ++calls === 1 ? first.promise : Promise.resolve(f.supplied) });
    const pending = loader.load(f.request), current = (await loader.load(f.request))!;
    f.request.consumer.artifactId = f.a1.id; first.resolve(f.supplied);
    expect(await pending).toBeNull(); expect(current.arrangement.right.artifactId).toBe(f.a0.id);
  });
  test('failed original read never synthesizes an owner from the readable frozen copy', async () => {
    const f = fixture(), loader = createSuppliedComparisonLoader({ ...reads(f), source: async () => { throw Error('Original unavailable'); } });
    await expect(loader.load(f.request)).rejects.toThrow('Original unavailable'); expect(f.input.artifact.text).toBe('Finding 1');
  });
});
