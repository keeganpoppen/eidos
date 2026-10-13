import { describe, expect, test } from 'bun:test';
import { applyImprovementPreview, emptyImprovementPreview, readImprovementPreview, undoImprovementPreview } from '../src/lib/improvement-preview';
import type { Experiment, Improvement } from '../src/lib/reflection';

const experiment: Experiment = {
  id: 'experiment-1', name: 'Evidence first', origin: 'synthetic-fixture',
  baseline: { investigationId: 'inquiry-1', contextId: 'original', artifactId: 'original-answer' },
  alternative: { investigationId: 'inquiry-1', contextId: 'extended', artifactId: 'review-receipt' },
  change: 'Keep the source chain visible.',
  evaluation: { id: 'evaluation-1', method: 'Deterministic synthetic check', cases: [], established: [], limitations: ['No user study'], cost: 'Not measured' }
};
const improvement: Improvement = {
  id: 'proposal-1', version: 1, title: 'Evidence first', evidence: [experiment.baseline], experimentId: experiment.id,
  expectedBenefit: 'Reduce source navigation', patch: '- result first\n+ source first', beforeVersion: 'recipe-1', afterVersion: 'recipe-2',
  rollback: 'Restore the previous preview', origin: 'synthetic-fixture'
};

describe('reference-only presentation preview', () => {
  test('apply, reload and undo restore the prior presentation without an adoption receipt', () => {
    const initial = emptyImprovementPreview(experiment, improvement);
    const applied = applyImprovementPreview(initial);
    const restored = readImprovementPreview(JSON.stringify(applied), experiment, improvement);
    expect(restored.activeVersion).toBe('recipe-2');
    expect(restored.canUndo).toBe(true);
    expect(undoImprovementPreview(restored)).toEqual(initial);
    expect(JSON.stringify(restored)).not.toContain('adopted');
    expect(JSON.stringify(restored)).not.toContain('Reduce source navigation');
    expect(JSON.stringify(restored)).not.toContain('original-answer');
    expect(applyImprovementPreview(restored)).toEqual(restored);
  });

  test('an explicitly pinned original version survives reload and undo', () => {
    const initial = { ...emptyImprovementPreview(experiment, improvement), activeVersion: 'recipe-1' };
    const applied = applyImprovementPreview(initial);
    expect(undoImprovementPreview(readImprovementPreview(JSON.stringify(applied), experiment, improvement))).toEqual(initial);
  });

  test('unknown, changed, or mismatched references cannot activate a preview', () => {
    const applied = applyImprovementPreview(emptyImprovementPreview(experiment, improvement));
    for (const changed of [
      { schemaVersion: 2 }, { scope: 'durable-adoption' }, { experimentId: 'missing' },
      { proposalId: 'missing' }, { proposalVersion: 2 }, { beforeVersion: 'unreviewed' },
      { afterVersion: 'unreviewed' }, { activeVersion: 'unreviewed' },
      { previousVersion: 'unreviewed' }, { canUndo: false }, { canUndo: 'true' }
    ]) {
      const restored = readImprovementPreview(JSON.stringify({ ...applied, ...changed }), experiment, improvement);
      expect(restored).toEqual(emptyImprovementPreview(experiment, improvement));
    }
    const mismatched = { ...improvement, experimentId: 'other-experiment' };
    expect(readImprovementPreview(JSON.stringify(applied), experiment, mismatched).activeVersion).toBeNull();
  });

  test('untrusted stored content and authority claims are discarded', () => {
    const applied = applyImprovementPreview(emptyImprovementPreview(experiment, improvement));
    const forged = { ...applied, adopted: true, evidence: [{ text: 'Forged source' }], expectedBenefit: 'Forged benefit', authority: 'execute' };
    const restored = readImprovementPreview(JSON.stringify(forged), experiment, improvement);
    expect(restored).toEqual(applied);
    expect(JSON.stringify(restored)).not.toContain('Forged');
    expect(JSON.stringify(restored)).not.toContain('execute');
    expect(JSON.stringify(restored)).not.toContain('adopted');
  });

  test('malformed and oversized preferences do not create an active state', () => {
    for (const raw of [null, '{', 'null', '[]', 'false', 'x'.repeat(4097)]) {
      expect(readImprovementPreview(raw, experiment, improvement)).toEqual(emptyImprovementPreview(experiment, improvement));
    }
  });
});
