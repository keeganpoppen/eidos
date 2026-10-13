import { describe, expect, test } from 'bun:test';
import { applyArrangement, contextText, emptyComposition, readComposition, resolveAttention, resolveTarget, undoArrangement } from '../src/lib/comparison';
import type { Arrangement } from '../src/lib/comparison';
import type { Investigation } from '../src/lib/types';

const record = { seq: 12, threadId: 'design', rawText: '{"future":true}', source: 'fixture', direction: 'internal', method: null, sha256: 'first' };
const context = { id: 'c1', parentContextId: null, question: 'Does uncertainty justify a retry?', records: [record], selections: [{ threadId: 'design', startSeq: 12, endSeq: 12, rationale: 'Original decision' }], projectedPrompt: 'Exact immutable input', coverage: 'partial', createdAtMs: 1 };
const work: Investigation = {
  schemaVersion: 1, id: 'a', title: 'Original work', createdAtMs: 1, status: 'completed', currentContextId: 'c2',
  contexts: [context, { ...context, id: 'c2', parentContextId: 'c1', question: 'What remained unknown?', records: [{ ...record, sha256: 'changed' }] }],
  attempt: null, adoption: null,
  artifact: { id: 'artifact-a', contextId: 'c1', attemptId: 'attempt-a', text: 'Retain uncertainty. [evidence:12]', citations: [12], unsupportedCitations: [99], outputSeqs: [50] }
};
const arrangement: Arrangement = { left: { investigationId: 'a', contextId: 'c1' }, right: { investigationId: 'a', contextId: 'c2' }, lens: 'context', layout: 'beside' };

describe('reference-only composition recovery', () => {
  test('unknown versions and corrupt storage cannot replace API objects', () => {
    expect(readComposition('{')).toEqual(emptyComposition());
    expect(readComposition('{"version":2,"open":true}')).toEqual(emptyComposition());
    const recovered = readComposition(JSON.stringify({ ...emptyComposition(), arrangement, title: 'Forged', artifact: work.artifact }));
    expect(JSON.stringify(recovered)).not.toContain('Retain uncertainty');
    expect(JSON.stringify(recovered)).not.toContain('Forged');
    expect(resolveTarget([work], recovered.arrangement?.left).investigation?.title).toBe('Original work');
    expect(resolveTarget([work], { investigationId: 'missing', contextId: 'c1' }).context).toBeUndefined();
  });

  test('historical context remains exact when current context differs', () => {
    const resolved = resolveTarget([work], arrangement.left);
    expect(resolved.context?.id).toBe('c1');
    expect(resolved.context?.records[0].sha256).toBe('first');
    expect(contextText(work.contexts[1])).toContain('SHA-256 changed');
  });

  test('artifact focus refuses wrong revision, uncited block support, and wrong thread', () => {
    const focus = { ...arrangement.left, artifactId: 'artifact-a', blockId: 'block-0', seq: 12, threadId: 'design' };
    expect(resolveAttention([work], focus, [12]).record?.rawText).toBe(record.rawText);
    expect(resolveAttention([work], { ...focus, contextId: 'c2' }, [12]).artifact).toBeNull();
    expect(resolveAttention([work], { ...focus, contextId: 'c2' }, [12]).record).toBeUndefined();
    expect(resolveAttention([work], focus, []).record).toBeUndefined();
    expect(resolveAttention([work], { ...focus, threadId: 'other' }, [12]).record).toBeUndefined();
    expect(resolveAttention([work], { ...focus, seq: 99 }, [99]).record).toBeUndefined();
  });

  test('apply and reload undo preserve focus independently of arrangement', () => {
    const focus = { ...arrangement.left, artifactId: 'artifact-a', blockId: 'block-0', seq: 12, threadId: 'design' };
    const first = applyArrangement({ ...emptyComposition(), focus }, arrangement);
    const second = applyArrangement(first, { ...arrangement, layout: 'stacked' });
    const recovered = readComposition(JSON.stringify(second));
    expect(undoArrangement(recovered).arrangement).toEqual(arrangement);
    expect(undoArrangement(recovered).focus).toEqual(focus);
    expect(undoArrangement(undoArrangement(recovered)).arrangement).toBeNull();
    expect(first.arrangement?.layout).toBe('beside');
  });

  test('result pins retain the native artifact through local review and reintegration', () => {
    const native = work.artifact!;
    const ref = { ...arrangement.left, artifactId: native.id };
    const waiting: Investigation = { ...work, status: 'pending', nativeArtifact: native, artifact: null };
    const reviewed: Investigation = { ...waiting, status: 'completed', artifact: { ...native, id: 'reviewed', kind: 'eidos-evidence-review', text: native.text + '\nLocal receipt' } };
    expect(resolveTarget([waiting], ref).artifact?.id).toBe(native.id);
    expect(resolveTarget([reviewed], ref).artifact?.text).toBe(native.text);
    expect(resolveTarget([reviewed], { ...ref, artifactId: 'reviewed' }).artifact?.kind).toBe('eidos-evidence-review');
    expect(resolveTarget([reviewed], arrangement.left).artifact).toBeUndefined();
    expect(resolveTarget([reviewed], { ...ref, contextId: 'c2' }).artifact).toBeUndefined();
    const persisted = readComposition(JSON.stringify({ ...emptyComposition(), arrangement: { ...arrangement, left: ref } }));
    expect(persisted.arrangement?.left.artifactId).toBe(native.id);
    expect(resolveAttention([reviewed], { ...ref, blockId: 'block-0', seq: 12, threadId: 'design' }, [12]).record?.rawText).toBe(record.rawText);
  });
});
