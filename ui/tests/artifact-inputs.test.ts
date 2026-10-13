import { describe, expect, test } from 'bun:test';
import { artifactInputDiff, artifactInputKey, artifactKind, changedFrozenArtifactInputs, readArtifactInputs, resolveArtifactSource, sameArtifactInputs } from '../src/lib/artifact-inputs';
import { artifacts, contextText } from '../src/lib/comparison';
import { contentBlocks } from '../src/lib/semantic';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import type { FrozenArtifactInput } from '../src/lib/types';

describe('exact result inputs', () => {
  test('browser storage retains only references and rationale, never copied results or authority', () => {
    const ref = { investigationId: 'source', artifactId: 'artifact_a1', rationale: 'Earlier rejection' };
    expect(readArtifactInputs([{ ...ref, artifact: { text: 'forged result', kind: 'native-specialist-result' }, sourceManifestId: 'forged pin', authority: 'copied continuation' }])).toEqual([ref]);
    expect(readArtifactInputs([null, {}, { ...ref, artifactId: '' }, { ...ref, rationale: 'x'.repeat(2001) }, ref, ref])).toEqual([ref]);
    expect(readArtifactInputs({ artifactInputs: [ref] })).toEqual([]);
    expect(readArtifactInputs(Array.from({ length: 40 }, (_, index) => ({ ...ref, artifactId: `artifact_${index}` })))).toHaveLength(32);
  });

  test('dirty and revision comparison preserve exact source ownership, artifact version and rationale', () => {
    const before = [{ investigationId: 'a', artifactId: 'artifact_a1', rationale: 'reason' }];
    expect(sameArtifactInputs(before, [{ rationale: 'reason', artifactId: 'artifact_a1', investigationId: 'a' }])).toBe(true);
    expect(sameArtifactInputs(undefined, [])).toBe(true);
    expect(sameArtifactInputs(before, [{ ...before[0], artifactId: 'artifact_a2' }])).toBe(false);
    expect(sameArtifactInputs(before, [{ ...before[0], investigationId: 'wrong-owner' }])).toBe(false);
    const changed = [{ ...before[0], rationale: 'new reason' }];
    expect(artifactInputDiff(before, changed)).toEqual({ added: [], removed: [], updated: changed });
    expect(artifactInputDiff(before, [{ ...before[0], artifactId: 'artifact_a2' }])).toEqual({ removed: before, added: [{ ...before[0], artifactId: 'artifact_a2' }], updated: [] });
    expect(artifactInputKey({ investigationId: 'a:b', artifactId: 'c' })).not.toBe(artifactInputKey({ investigationId: 'a', artifactId: 'b:c' }));
  });

  test('a pinned A1 never follows the visible receipt or a later A2 result', () => {
    const investigation = makeReflectionFixture('supplied').investigations[0];
    const a1 = investigation.nativeArtifact!;
    const ref = { investigationId: investigation.id, artifactId: a1.id, contextId: a1.contextId };
    expect(resolveArtifactSource(investigation, ref)?.artifact).toEqual(a1);
    const previousAttempt = investigation.attempt!;
    investigation.attemptHistory = [previousAttempt];
    investigation.artifactHistory = artifacts(investigation);
    investigation.attempt = { ...previousAttempt, id: 'attempt_a2' };
    investigation.artifact = { ...a1, id: 'artifact_a2', attemptId: 'attempt_a2', text: 'A different result.' };
    expect(resolveArtifactSource(investigation, ref)?.artifact).toEqual(a1);
    expect(resolveArtifactSource(investigation, { ...ref, investigationId: 'wrong-owner' })).toBeNull();
    expect(resolveArtifactSource(investigation, { ...ref, contextId: 'other-context' })).toBeNull();
    expect(resolveArtifactSource(investigation, { ...ref, artifactId: 'missing-version' })).toBeNull();
    investigation.attemptHistory = [];
    expect(resolveArtifactSource(investigation, ref)).toBeNull();
  });

  test('inquiry and receipt artifacts retain their type and remain exact selectable descriptions', () => {
    const investigation = makeReflectionFixture('supplied').investigations[0];
    const receipt = investigation.artifact!;
    expect(resolveArtifactSource(investigation, { investigationId: investigation.id, artifactId: receipt.id })?.artifact).toEqual(receipt);
    expect(artifactKind(receipt)).toBe('Evidence decision receipt');
    expect(artifactKind({ ...receipt, kind: 'native-needs-evidence' })).toBe('Specialist evidence inquiry');
    expect(artifactKind({ ...receipt, kind: 'native-inquiry-invalid' })).toBe('Invalid evidence inquiry');
  });

  test('artifact references remain distinct from direct evidence in content and context comparison', () => {
    const [block] = contentBlocks('Use [artifact:artifact_a1] and [artifact:artifact_a1]; source claims [evidence:12].');
    expect(block.artifactCitations).toEqual(['artifact_a1']);
    expect(block.citations).toEqual([12]);
    const investigation = makeReflectionFixture('supplied').investigations[0];
    const artifact = investigation.nativeArtifact!;
    const input: FrozenArtifactInput = { investigationId: investigation.id, artifactId: artifact.id, rationale: 'Controlling result', artifact,
      sourceContextId: artifact.contextId, sourceManifestId: 'source-manifest', sourceAttemptManifestId: 'source-request-pin', sourceAdoption: null };
    const context = { ...investigation.contexts[0], selections: [], records: [], artifactInputs: [input] };
    const text = contextText(context);
    expect(text).toContain(`[artifact:${artifact.id}]`);
    expect(text).toContain('source-manifest');
    expect(text).toContain('source-request-pin');
    expect(text).not.toContain(artifact.text);
    expect(context.records).toEqual([]);
    expect(readArtifactInputs(context.artifactInputs)).toEqual([{ investigationId: investigation.id, artifactId: artifact.id, rationale: 'Controlling result' }]);
  });

  test('same-ID frozen review changes appear in comparison without changing draft reference identity', () => {
    const investigation = makeReflectionFixture('supplied').investigations[0];
    const artifact = investigation.nativeArtifact!;
    const before: FrozenArtifactInput = { investigationId: investigation.id, artifactId: artifact.id, rationale: '', artifact,
      sourceContextId: artifact.contextId, sourceManifestId: 'source', sourceAttemptManifestId: 'attempt', sourceAdoption: null };
    const after = { ...before, sourceAdoption: { artifactId: artifact.id, decision: 'reject' as const, note: 'Reconsider the claim.', createdAtMs: 100 } };
    expect(sameArtifactInputs([before], [after])).toBe(true);
    expect(changedFrozenArtifactInputs([before], [after])).toEqual([after]);
    expect(changedFrozenArtifactInputs([after], [{ ...after, rationale: 'New rationale' }])).toEqual([]);
    const reordered = Object.fromEntries(Object.entries(after).reverse()) as FrozenArtifactInput;
    expect(changedFrozenArtifactInputs([after], [reordered])).toEqual([]);
    expect(contextText({ ...investigation.contexts[0], artifactInputs: [after] })).toContain('reject at 100 · Reconsider the claim.');
  });
});
