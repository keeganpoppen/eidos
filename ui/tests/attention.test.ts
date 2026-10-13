import { expect, test } from 'bun:test';
import { compileAttentionRequest, evidenceChain, matchesExperiment, validateEvidenceChain, applyArrangement, emptyComposition, readComposition, resolveTarget, undoArrangement } from '../src/lib/comparison';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';

test('semantic attention requests pin original, response, offered context and result without changing work', () => {
  const fixture = makeReflectionFixture('supplied');
  const before = JSON.stringify(fixture);
  const arrangement = compileAttentionRequest({ version: 1, intent: 'evidence-chain', investigationId: fixture.inquiry.baseline.investigationId }, fixture.investigations, [fixture.experiment]);
  expect(validateEvidenceChain(fixture.investigations, arrangement)).toBeNull();
  expect(arrangement.left).toEqual(fixture.inquiry.baseline);
  expect(arrangement.right).toEqual(fixture.inquiry.result!);
  expect(arrangement.inquiry?.evidenceContextId).toBe(fixture.inquiry.evidenceContextId!);
  expect(JSON.stringify(fixture)).toBe(before);
});

test('an old pending arrangement never follows a newly supplied receipt', () => {
  const pending = makeReflectionFixture('pending');
  const supplied = makeReflectionFixture('supplied');
  const arrangement = evidenceChain(pending.investigations[0])!;
  expect(validateEvidenceChain(supplied.investigations, arrangement)).toBeNull();
  expect(resolveTarget(supplied.investigations, arrangement.right).artifact).toBeUndefined();
  expect(arrangement.inquiry?.evidenceContextId).toBeUndefined();
  expect(evidenceChain(supplied.investigations[0])!.right.artifactId).toBe(supplied.inquiry.result!.artifactId!);
});

test('a copied receipt, wrong original, wrong response or packet cannot form an evidence chain', () => {
  const fixture = makeReflectionFixture('supplied');
  const arrangement = evidenceChain(fixture.investigations[0])!;
  expect(validateEvidenceChain(fixture.investigations, { ...arrangement, right: fixture.experiment.alternative })).not.toBeNull();
  expect(validateEvidenceChain(fixture.investigations, { ...arrangement, left: arrangement.right })).not.toBeNull();
  expect(validateEvidenceChain(fixture.investigations, { ...arrangement, inquiry: { ...arrangement.inquiry!, evidenceContextId: arrangement.left.contextId } })).not.toBeNull();
  expect(validateEvidenceChain(fixture.investigations, { ...arrangement, inquiry: { ...arrangement.inquiry!, responseId: 'guessed' } })).not.toBeNull();
  expect(validateEvidenceChain(fixture.investigations, { ...arrangement, inquiry: { continuationId: arrangement.inquiry!.continuationId, inquiryId: arrangement.inquiry!.inquiryId, responseId: arrangement.inquiry!.responseId } })).not.toBeNull();
  const missing = structuredClone(fixture.investigations);
  missing[0].continuation!.inquiry!.responses[0].evidenceContext = null;
  expect(validateEvidenceChain(missing, arrangement)).not.toBeNull();
});

test('arrangement apply/reload/undo retains exact offered focus and strips copied evidence', () => {
  const fixture = makeReflectionFixture('supplied');
  const chain = evidenceChain(fixture.investigations[0])!;
  const alternative = compileAttentionRequest({ version: 1, intent: 'alternative-review', experimentId: fixture.experiment.id }, fixture.investigations, [fixture.experiment]);
  const focus = { investigationId: fixture.inquiry.baseline.investigationId, contextId: fixture.inquiry.evidenceContextId!, seq: 72, threadId: 'fixture:recovery' };
  const state = applyArrangement(applyArrangement({ ...emptyComposition(), focus }, chain), alternative);
  const restored = readComposition(JSON.stringify({ ...state, artifact: 'copied content' }));
  expect(restored.arrangement).toEqual(alternative);
  expect(undoArrangement(restored).arrangement).toEqual(chain);
  expect(restored.focus).toEqual(focus);
  expect(resolveTarget(fixture.investigations, focus).context?.id).toBe(fixture.inquiry.evidenceContextId!);
  expect(JSON.stringify(restored)).not.toContain('copied content');
  expect(JSON.stringify(restored)).not.toContain('rawText');
});

test('unknown semantic actions and missing named results never compile to authority actions', () => {
  const fixture = makeReflectionFixture('pending');
  expect(() => compileAttentionRequest({ version: 1, intent: 'dispatch', investigationId: fixture.inquiry.baseline.investigationId }, fixture.investigations, [])).toThrow('Unsupported attention intent');
  expect(() => compileAttentionRequest({ version: 1, intent: 'alternative-review', experimentId: 'missing' }, fixture.investigations, [fixture.experiment])).toThrow('unavailable');
  expect(() => compileAttentionRequest({ version: 2, intent: 'evidence-chain' }, fixture.investigations, [])).toThrow('version 1');
});

test('changing a pane cannot retain an unrelated experiment evaluation', () => {
  const fixture = makeReflectionFixture('supplied');
  const arrangement = compileAttentionRequest({ version: 1, intent: 'alternative-review', experimentId: fixture.experiment.id }, fixture.investigations, [fixture.experiment]);
  expect(matchesExperiment(arrangement, fixture.experiment)).toBe(true);
  expect(matchesExperiment({ ...arrangement, layout: 'stacked', lens: 'context' }, fixture.experiment)).toBe(true);
  expect(matchesExperiment({ ...arrangement, right: fixture.inquiry.result! }, fixture.experiment)).toBe(false);
  expect(matchesExperiment({ ...arrangement, left: { ...arrangement.left, contextId: fixture.inquiry.evidenceContextId! } }, fixture.experiment)).toBe(false);
});

test('follow-up preserves A1, local receipt and A2 input identities through attempt rollover', () => {
  const fixture = makeReflectionFixture('supplied');
  const work = fixture.investigations[0];
  const oldChain = evidenceChain(work)!;
  const receipt = work.artifact!;
  const original = work.nativeArtifact!;
  const first = work.attempt!;
  const continuation = work.continuation!;
  const response = continuation.inquiry!.responses[0];
  const expanded = { ...work.contexts[0], id: 'expanded-follow-up', records: [...work.contexts[0].records, ...response.evidenceContext!.records] };
  const lineage = { investigationId: work.id, attemptId: first.id, continuationId: continuation.id, inquiryId: continuation.inquiry!.id, responseId: response.id, decision: 'offer' as const, nativeArtifactId: original.id, evidenceContextId: response.evidenceContext!.id };
  continuation.origin = 'native-specialist';
  work.contexts.push(expanded);
  work.currentContextId = expanded.id;
  work.attemptHistory = [first];
  work.artifactHistory = [receipt];
  work.attempt = { ...first, id: 'a2', contextId: expanded.id, continuedFrom: lineage };
  work.artifact = { ...original, id: 'a2-result', contextId: expanded.id, attemptId: 'a2', kind: 'native-specialist-result', continuedFrom: lineage };
  const next = evidenceChain(work)!;
  expect(validateEvidenceChain([work], oldChain)).toBeNull();
  expect(validateEvidenceChain([work], next)).toBeNull();
  expect(next.left).toEqual(oldChain.left);
  expect(next.right.contextId).toBe(expanded.id);
  expect(next.right.artifactId).toBe('a2-result');
  expect(resolveTarget([work], oldChain.right).artifact?.id).toBe(receipt.id);
  expect(work.nativeArtifact).toEqual(original);
  work.artifact.continuedFrom = { ...lineage, responseId: 'another-response' };
  expect(validateEvidenceChain([work], next)).toContain('separately admitted');
});
