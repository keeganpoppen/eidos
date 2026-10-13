import { describe, expect, test } from 'bun:test';
import { artifacts, changeComparisonLens, compileAttentionRequest, contextText, createTargetRequests, emptyComposition, matchesExperiment, readComposition, resolveTarget, validateRecordedExperiment } from '../src/lib/comparison';
import { captureSnapshot, openSnapshot, type CompositionSnapshot } from '../src/lib/composition-snapshots';
import { SavedWorkClient } from '../src/lib/saved-work';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import type { WorkbenchExperiment } from '../src/lib/types';

function fixture() {
  const example = makeReflectionFixture('supplied');
  const owner = structuredClone(example.investigations[0]);
  owner.id = 'recorded-owner';
  const baseline = owner.nativeArtifact!;
  const originalAttempt = owner.attempt!;
  const alternative = { ...structuredClone(example.investigations[1].contexts[0]), id: 'C1' };
  const later = { ...structuredClone(alternative), id: 'C2' };
  owner.contexts.push(alternative, later);
  owner.currentContextId = later.id;
  owner.artifactHistory = [baseline, { ...baseline, id: 'later-C1-result', contextId: 'C1', attemptId: 'later-C1-attempt' }];
  owner.artifact = { ...baseline, id: 'A2', contextId: 'C2', attemptId: 'A2-attempt' };
  owner.attemptHistory = [originalAttempt, { ...originalAttempt, id: 'later-C1-attempt', contextId: 'C1' }];
  owner.attempt = { ...originalAttempt, id: 'A2-attempt', contextId: 'C2' };
  const experiment: WorkbenchExperiment = {
    id: 'recorded-E1', investigationId: owner.id, proposalId: 'proposal-E1', mode: 'reinterpretation', evidenceClass: 'synthetic',
    baseline: { investigationId: owner.id, contextId: baseline.contextId, artifactId: baseline.id, attemptId: baseline.attemptId },
    alternative: { investigationId: owner.id, contextId: alternative.id }, rationale: 'Retain the original decision and inspect added evidence.',
    evaluation: { id: 'evaluation-E1', method: 'context-selection-comparison/v1', baseline: { recordIds: [12, 38], recordCount: 2, promptBytes: 100 }, alternative: { recordIds: [12, 38, 72], recordCount: 3, promptBytes: 150 }, addedRecordIds: [72], removedRecordIds: [], additionalPromptBytes: 50, checks: { sameQuestion: true, baselineEvidenceRetained: true, withinContextBound: true }, passes: true, modelCalls: 0, measuredModelReasoningImprovement: false, limitations: ['Selection measurement only.'] },
    review: null, adoption: null, rollback: null, status: 'evaluated'
  };
  return { owner, experiment };
}
const request = (experiment: WorkbenchExperiment) => ({ version: 1, intent: 'alternative-review', investigationId: experiment.investigationId, experimentId: experiment.id });
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe('recorded context experiment composition', () => {
  test('compiles exact historical baseline and context-only alternative despite newer results, lens changes and snapshot recovery', () => {
    const { owner, experiment } = fixture();
    const before = JSON.stringify(owner);
    expect(artifacts(owner).some((artifact) => artifact.contextId === 'C1')).toBe(true);
    const arrangement = compileAttentionRequest(request(experiment), [owner], [experiment]);
    expect(arrangement.lens).toBe('context');
    expect(arrangement.left).toEqual({ investigationId: owner.id, contextId: experiment.baseline.contextId, artifactId: experiment.baseline.artifactId });
    expect(arrangement.right).toEqual(experiment.alternative);
    const resultLens = changeComparisonLens(arrangement, 'result', [owner]);
    expect(resultLens.right.artifactId).toBeUndefined();
    expect(resolveTarget([owner], resultLens.right).artifact).toBeUndefined();
    expect(matchesExperiment(resultLens, experiment)).toBe(true);
    const body = captureSnapshot('Evaluated inputs', { ...emptyComposition(), arrangement });
    const saved: CompositionSnapshot = { ...body, schemaVersion: 1, id: 'saved-E1', contentId: 'content-E1', createdAtMs: 1, copiedFrom: null };
    const restored = readComposition(JSON.stringify(openSnapshot(emptyComposition(), saved)));
    expect(restored.arrangement).toEqual(arrangement);
    expect(resolveTarget([owner], restored.arrangement!.left).artifact!.id).toBe(experiment.baseline.artifactId);
    expect(JSON.stringify(owner)).toBe(before);
  });

  test('requires explicit owner and exact baseline artifact, context and attempt; malformed alternative never becomes a result', () => {
    const { owner, experiment } = fixture();
    expect(validateRecordedExperiment([owner], experiment)).toBeNull();
    expect(() => compileAttentionRequest({ ...request(experiment), investigationId: 'other-owner' }, [owner], [experiment])).toThrow('owning investigation');
    expect(() => compileAttentionRequest({ version: 1, intent: 'alternative-review', experimentId: experiment.id }, [owner], [experiment])).toThrow('owning investigation');
    for (const baseline of [
      { ...experiment.baseline, artifactId: 'missing' },
      { ...experiment.baseline, contextId: 'C1' },
      { ...experiment.baseline, attemptId: 'A2-attempt' }
    ]) expect(validateRecordedExperiment([owner], { ...experiment, baseline })).toContain('exact baseline');
    expect(validateRecordedExperiment([owner], { ...experiment, alternative: { ...experiment.alternative, contextId: 'missing' } })).toContain('context-only');
    expect(validateRecordedExperiment([owner], { ...experiment, alternative: { ...experiment.alternative, artifactId: 'later-C1-result' } } as WorkbenchExperiment)).toContain('context-only');
    expect(validateRecordedExperiment([], experiment)).toContain('owning investigation');
    expect(matchesExperiment({ ...compileAttentionRequest(request(experiment), [owner], [experiment]), right: { ...experiment.alternative, artifactId: 'later-C1-result' } }, experiment)).toBe(false);
    // A malformed import can retain artifact/context IDs while replacing the
    // attempt with another otherwise valid attempt in that same context.
    owner.attemptHistory!.push({ ...owner.attemptHistory![0], id: 'same-context-other-attempt' });
    owner.nativeArtifact!.attemptId = 'same-context-other-attempt';
    expect(validateRecordedExperiment([owner], experiment)).toContain('exact baseline');
  });

  test('a changed current review does not change compiled or saved targets, and frozen source-review differences remain visible', () => {
    const { owner, experiment } = fixture();
    const input = { investigationId: 'source-owner', artifactId: 'same-source-result', rationale: 'Original support', artifact: { ...owner.nativeArtifact!, id: 'same-source-result' }, sourceContextId: 'source-context', sourceManifestId: 'manifest', sourceAttemptManifestId: null, sourceAdoption: null };
    owner.contexts[0].artifactInputs = [input];
    owner.contexts[1].artifactInputs = [{ ...input, sourceAdoption: { artifactId: input.artifactId, decision: 'reject', note: 'Contradicting evidence', createdAtMs: 2 } }];
    const compiled = compileAttentionRequest(request(experiment), [owner], [experiment]);
    const saved = captureSnapshot('Before review', { ...emptyComposition(), arrangement: compiled }, 'save-original');
    experiment.review = { id: 'review', decision: 'reject', rationale: 'Retain contradictory review.', actor: 'local-owner', kind: 'human' };
    experiment.status = 'rejected';
    expect(compileAttentionRequest(request(experiment), [owner], [experiment])).toEqual(compiled);
    expect(saved).not.toHaveProperty('review');
    expect(JSON.stringify(saved)).not.toContain('Retain contradictory review.');
    expect(contextText(owner.contexts[0])).toContain('Source review when selected: (none recorded)');
    expect(contextText(owner.contexts[1])).toContain('reject at 2 · Contradicting evidence');
  });

  test('exact experiment reads deduplicate simultaneous consumers, refresh current review, and never fetch whole owners', async () => {
    const { experiment } = fixture();
    const paths: string[] = [];
    let resolve!: (value: Response) => void;
    const waiting = new Promise<Response>((done) => resolve = done);
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      return paths.length === 1 ? waiting : json({ ...experiment, status: 'rejected', review: { id: 'r', decision: 'reject', rationale: 'Later review', actor: 'local-owner', kind: 'human' } });
    });
    const first = client.experiment(experiment.investigationId, experiment.id);
    const second = client.experiment(experiment.investigationId, experiment.id);
    expect(paths).toHaveLength(1);
    resolve(json(experiment));
    expect(await first).toEqual(await second);
    const refreshed = await client.experiment(experiment.investigationId, experiment.id);
    expect(refreshed.status).toBe('rejected');
    expect(refreshed.baseline).toEqual(experiment.baseline);
    expect(paths).toEqual(Array(2).fill('/api/investigations/recorded-owner/experiments/recorded-E1'));
  });

  test('wrong-owner/experiment responses fail without substituting another experiment, and failed reads remain retryable', async () => {
    const { experiment } = fixture();
    let count = 0;
    const client = new SavedWorkClient(async () => {
      count++;
      return count === 1 ? json({ error: 'Temporarily unavailable' }, 503) : count === 2 ? json({ ...experiment, id: 'E2' }) : count === 3 ? json({ ...experiment, investigationId: 'other-owner' }) : json(experiment);
    });
    await expect(client.experiment(experiment.investigationId, experiment.id)).rejects.toThrow('Temporarily');
    await expect(client.experiment(experiment.investigationId, experiment.id)).rejects.toThrow('does not match');
    await expect(client.experiment(experiment.investigationId, experiment.id)).rejects.toThrow('does not match');
    expect(await client.experiment(experiment.investigationId, experiment.id)).toEqual(experiment);
  });

  test('a late free-comparison bind from an older cache generation cannot overwrite a reviewed historical experiment', async () => {
    const { owner, experiment } = fixture();
    let finishOld!: (response: Response) => void;
    const oldResponse = new Promise<Response>((resolve) => finishOld = resolve);
    let calls = 0;
    const client = new SavedWorkClient(async () => ++calls === 1 ? oldResponse : json({ version: 'new', unchanged: false, investigation: owner }));
    const targets = createTargetRequests();
    const bindCurrent = targets.begin('left');
    let draft = compileAttentionRequest(request(experiment), [owner], [experiment]);
    let staleBindRan = false;
    const oldBind = client.view(owner.id).then((value) => {
      if (bindCurrent() && draft.left.investigationId === value.id) {
        staleBindRan = true;
        draft = { ...draft, left: { investigationId: value.id, contextId: value.currentContextId, artifactId: value.artifact!.id } };
      }
      return value;
    });
    // Successful draft mutation creates generation G+1; this newer view can
    // finish while generation G's transport is still pending.
    client.remember(owner);
    targets.cancel(); // The exact experiment proposal replaces the free draft.
    const currentOwner = await client.view(owner.id);
    draft = compileAttentionRequest(request(experiment), [currentOwner], [experiment]);
    finishOld(json({ version: 'old', unchanged: false, investigation: { ...owner, title: 'Earlier read' } }));
    expect((await oldBind).currentContextId).toBe('C2');
    expect(calls).toBe(2);
    expect(staleBindRan).toBe(false);
    expect(draft.left.contextId).toBe(experiment.baseline.contextId);
    expect(draft.left.artifactId).toBe(experiment.baseline.artifactId);
    expect(matchesExperiment(draft, experiment)).toBe(true);
  });
});
