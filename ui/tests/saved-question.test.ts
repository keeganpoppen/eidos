import { describe, expect, test } from 'bun:test';
import { compileAttentionRequest, resolveTarget } from '../src/lib/comparison';
import type { CompositionSnapshot } from '../src/lib/composition-snapshots';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import { loadSavedQuestion, savedQuestionFocus } from '../src/lib/saved-question';
import { SavedWorkClient } from '../src/lib/saved-work';
import { contentBlocks, rendererVersion } from '../src/lib/semantic';
import type { WorkbenchExperiment } from '../src/lib/types';

function fixture() {
  const example = makeReflectionFixture('supplied');
  const owner = structuredClone(example.investigations[0]);
  owner.id = 'saved-owner';
  const baseline = owner.nativeArtifact!;
  const attempt = owner.attempt!;
  const alternative = { ...structuredClone(owner.contexts[0]), id: 'C1', question: 'Saved alternative question' };
  owner.contexts.push(alternative, { ...structuredClone(alternative), id: 'C2', question: 'Later unrelated question' });
  owner.currentContextId = 'C2';
  owner.artifactHistory = [baseline, { ...baseline, id: 'later-C1', contextId: 'C1', attemptId: 'later-attempt' }];
  owner.artifact = { ...baseline, id: 'A2', contextId: 'C2', attemptId: 'A2-attempt' };
  owner.attemptHistory = [attempt];
  owner.attempt = { ...attempt, id: 'A2-attempt', contextId: 'C2' };
  const experiment: WorkbenchExperiment = {
    id: 'E1', investigationId: owner.id, proposalId: 'proposal', mode: 'reinterpretation', evidenceClass: 'synthetic',
    baseline: { investigationId: owner.id, contextId: baseline.contextId, artifactId: baseline.id, attemptId: baseline.attemptId },
    alternative: { investigationId: owner.id, contextId: alternative.id }, rationale: 'Retain the rejected retry and its original support.',
    evaluation: { id: 'evaluation', method: 'context-selection-comparison/v1', baseline: { recordIds: [12], recordCount: 1, promptBytes: 10 }, alternative: { recordIds: [12], recordCount: 1, promptBytes: 10 }, addedRecordIds: [], removedRecordIds: [], additionalPromptBytes: 0, checks: { sameQuestion: true, baselineEvidenceRetained: true, withinContextBound: true }, passes: true, modelCalls: 0, measuredModelReasoningImprovement: false, limitations: [] },
    status: 'rejected', review: { id: 'review', actor: 'local-owner', kind: 'human', decision: 'reject', rationale: 'Later review, not the original question.' }, adoption: null, rollback: null
  };
  const block = contentBlocks(baseline.text).find((value) => value.citations.includes(12))!;
  const record = owner.contexts[0].records.find((value) => value.seq === 12)!;
  const snapshot: CompositionSnapshot = { schemaVersion: 1, id: 'snapshot', contentId: 'content', title: 'Saved decision', createdAtMs: 1, copiedFrom: null, rendererVersion,
    arrangement: compileAttentionRequest({ version: 1, intent: 'alternative-review', investigationId: owner.id, experimentId: experiment.id }, [owner], [experiment]),
    focus: { investigationId: owner.id, contextId: baseline.contextId, artifactId: baseline.id, blockId: block.id, seq: record.seq, threadId: record.threadId } };
  return { owner, experiment, snapshot, record, block };
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe('saved question preview', () => {
  test('fetches one exact owner and named experiment, retains historical question/result and context-only alternative without mutations', async () => {
    const { owner, experiment, snapshot, record } = fixture();
    const before = JSON.stringify({ owner, snapshot });
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      return path.includes('/experiments/') ? json(experiment) : json({ version: 'v1', unchanged: false, investigation: owner });
    });
    const result = await loadSavedQuestion(snapshot, client);
    expect(paths.sort()).toEqual(['/api/investigations/saved-owner/experiments/E1', '/api/investigations/saved-owner/view']);
    expect(result.errors).toEqual([]);
    expect(result.experiment?.rationale).toBe(experiment.rationale);
    expect(result.experiment?.review?.rationale).toBe(experiment.review!.rationale);
    expect(resolveTarget(result.owners, snapshot.arrangement.left).artifact!.id).toBe(experiment.baseline.artifactId);
    const right = resolveTarget(result.owners, snapshot.arrangement.right);
    expect(right.context!.question).toBe('Saved alternative question');
    expect(right.artifact).toBeUndefined();
    expect(savedQuestionFocus(snapshot, result.owners).record).toEqual(record);
    expect(JSON.stringify({ owner, snapshot })).toBe(before);
  });

  test('a failed experiment read leaves exact sources inspectable and can retry without another owner transfer', async () => {
    const { owner, experiment, snapshot } = fixture();
    let experimentCalls = 0;
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      if (path.includes('/experiments/')) return ++experimentCalls === 1 ? json({ error: 'Temporary experiment failure' }, 503) : json(experiment);
      return path.includes('?') ? json({ unchanged: true, version: 'v1' }) : json({ version: 'v1', unchanged: false, investigation: owner });
    });
    const failed = await loadSavedQuestion(snapshot, client);
    expect(failed.experiment).toBeUndefined();
    expect(failed.experimentError).toContain('Temporary experiment failure');
    expect(failed.owners[0].id).toBe(owner.id);
    const retried = await loadSavedQuestion(snapshot, client);
    expect(retried.experiment?.id).toBe('E1');
    expect(paths).toContain('/api/investigations/saved-owner/view?knownVersion=v1');
  });

  test('missing owner, wrong experiment bindings and mismatched attempt remain explicit rather than borrowing latest data', async () => {
    const { owner, experiment, snapshot } = fixture();
    const missing = await loadSavedQuestion(snapshot, { view: async () => { throw new Error('Missing exact owner'); }, experiment: async () => experiment });
    expect(missing.owners).toEqual([]);
    expect(missing.errors[0]).toContain('Missing exact owner');
    expect(missing.experiment).toBeUndefined();
    const wrong = await loadSavedQuestion(snapshot, { view: async () => owner, experiment: async () => ({ ...experiment, alternative: { ...experiment.alternative, contextId: 'C2' } }) });
    expect(wrong.experiment).toBeUndefined();
    expect(wrong.experimentError).toContain('exact saved comparison targets');
    owner.nativeArtifact!.attemptId = owner.attempt!.id;
    const invalid = await loadSavedQuestion(snapshot, { view: async () => owner, experiment: async () => experiment });
    expect(invalid.experiment).toBeUndefined();
    expect(invalid.experimentError).toContain('exact baseline');
  });

  test('unsupported renderer retains a correctly scoped record without interpreting its saved block selector', () => {
    const { owner, snapshot, record, block } = fixture();
    expect(savedQuestionFocus(snapshot, [owner]).block!.text).toBe(block.text);
    const unknown = { ...snapshot, rendererVersion: 'unknown-parser' };
    const resolved = savedQuestionFocus(unknown, [owner]);
    expect(resolved.supported).toBe(false);
    expect(resolved.block).toBeUndefined();
    expect(resolved.record).toEqual(record);
    const noBlock = { ...unknown, focus: { ...unknown.focus!, blockId: undefined } };
    expect(savedQuestionFocus(noBlock, [owner]).record).toEqual(record);
  });

  test('wrong thread/context, uncited records and missing supported block never resolve to a nearby record', () => {
    const { owner, snapshot } = fixture();
    for (const change of [{ threadId: 'wrong-thread' }, { contextId: 'C2' }, { blockId: 'absent-block' }]) {
      expect(savedQuestionFocus({ ...snapshot, focus: { ...snapshot.focus!, ...change } }, [owner]).record).toBeUndefined();
    }
    owner.nativeArtifact!.citations = [];
    expect(savedQuestionFocus({ ...snapshot, rendererVersion: 'unknown-parser' }, [owner]).record).toBeUndefined();
    expect(savedQuestionFocus({ ...snapshot, focus: { ...snapshot.focus!, blockId: undefined } }, [owner]).record).toBeUndefined();
  });
});
