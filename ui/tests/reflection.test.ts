import { describe, expect, test } from 'bun:test';
import { resolveTarget } from '../src/lib/comparison';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import { resolveInquiryBinding, validateInquiryBinding } from '../src/lib/reflection';
import type { InquiryBinding } from '../src/lib/reflection';

function binding(stage: 'pending' | 'supplied' = 'supplied'): InquiryBinding {
  const { inquiry } = makeReflectionFixture(stage);
  return { continuationId: inquiry.continuationId, inquiryId: inquiry.id,
    ...(inquiry.responseId ? { responseId: inquiry.responseId, evidenceContextId: inquiry.evidenceContextId } : {}) };
}

describe('synthetic reflective investigation', () => {
  test('reload regenerates exact references without pretending fixture output was observed', () => {
    const first = makeReflectionFixture('supplied');
    expect(makeReflectionFixture('supplied')).toEqual(first);
    expect(first.inquiry.origin).toBe('synthetic-fixture');
    expect(first.experiment.origin).toBe('synthetic-fixture');
    expect(first.improvement.origin).toBe('synthetic-fixture');
    for (const investigation of first.investigations) {
      expect(investigation.id.startsWith('fixture:')).toBe(true);
      expect(investigation.attempt?.threadId).toBeNull();
      expect(investigation.attempt?.turnId).toBeNull();
      for (const artifact of [investigation.artifact, investigation.nativeArtifact].filter(Boolean)) {
        expect(artifact!.outputSeqs).toEqual([]);
        expect(artifact!.text).toContain('Synthetic');
      }
    }
    expect(first.experiment.evaluation.limitations.join(' ')).toContain('not model-generated');
    expect(first.experiment.evaluation.cost).toContain('No model calls');
  });

  test('supply preserves original packet/output and adds a separate disclosure receipt', () => {
    const pending = makeReflectionFixture('pending');
    const supplied = makeReflectionFixture('supplied');
    expect(supplied.inquiry.id).toBe(pending.inquiry.id);
    expect(supplied.inquiry.continuationId).toBe(pending.inquiry.continuationId);
    expect(pending.inquiry.status).toBe('pending');
    expect(pending.inquiry.result).toBeNull();
    expect(supplied.investigations[0].contexts).toEqual(pending.investigations[0].contexts);
    expect(supplied.investigations[0].nativeArtifact).toEqual(pending.investigations[0].nativeArtifact);
    const original = resolveTarget(supplied.investigations, supplied.inquiry.baseline);
    const result = resolveTarget(supplied.investigations, supplied.inquiry.result);
    expect(result.artifact?.kind).toBe('eidos-evidence-review');
    expect(result.artifact?.id).not.toBe(original.artifact?.id);
    expect(result.context?.id).toBe(original.context?.id);
    expect(result.artifact?.text).toStartWith(original.artifact!.text);
    expect(result.artifact?.text).toContain('not a new model conclusion');
    expect(result.artifact?.citations).toEqual([12, 38]);
  });

  test('counterfactual exposes exactly what changed and retains the original evidence bytes', () => {
    const fixture = makeReflectionFixture('supplied');
    const original = resolveTarget(fixture.investigations, fixture.experiment.baseline);
    const alternative = resolveTarget(fixture.investigations, fixture.experiment.alternative);
    expect(original.context?.records.map((record) => record.seq)).toEqual([12, 38]);
    expect(alternative.context?.records.map((record) => record.seq)).toEqual([12, 38, 72]);
    expect(alternative.context?.records.slice(0, 2)).toEqual(original.context?.records);
    expect(alternative.artifact?.contextId).not.toBe(original.artifact?.contextId);
    expect(alternative.artifact?.kind).toBe('synthetic-counterfactual');
    expect(alternative.artifact?.text).toContain('later evidence');
    expect(fixture.improvement.experimentId).toBe(fixture.experiment.id);
    expect(fixture.improvement.beforeVersion).not.toBe(fixture.improvement.afterVersion);
    expect(fixture.improvement.expectedBenefit).toContain('Hypothesis');
  });

  test('source digests identify exact original bytes, including unknown fields', async () => {
    const fixture = makeReflectionFixture('supplied');
    const allRecords = fixture.investigations.flatMap((investigation) => investigation.contexts.flatMap((context) => context.records));
    for (const record of allRecords) {
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(record.rawText));
      const digest = [...new Uint8Array(bytes)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
      expect(record.sha256).toBe(digest);
    }
    expect(JSON.parse(allRecords[0].rawText).unrecognizedFutureField).toEqual({ retain: 'original bytes' });
  });
});

describe('scoped inquiry references', () => {
  test('pending and offered inquiry bind without changing the original context', () => {
    const pending = makeReflectionFixture('pending');
    expect(validateInquiryBinding(pending.investigations, pending.inquiry.baseline, binding('pending'))).toBeNull();
    const supplied = makeReflectionFixture('supplied');
    const resolved = resolveInquiryBinding(supplied.investigations, supplied.inquiry.baseline, binding());
    expect(resolved.error).toBeNull();
    expect(resolved.response?.id).toBe(supplied.inquiry.responseId);
    expect(resolved.evidenceContext?.id).toBe(supplied.inquiry.evidenceContextId);
    expect(resolved.evidenceContext?.records.map((record) => record.seq)).toEqual([72]);
    expect(resolved.evidenceContext?.id).not.toBe(supplied.inquiry.baseline.contextId);
    expect(validateInquiryBinding(supplied.investigations, {
      investigationId: supplied.inquiry.baseline.investigationId, contextId: supplied.inquiry.evidenceContextId!
    }, binding())).toBeNull();
  });

  test('copied inquiry/response identifiers cannot cross investigation or context boundaries', () => {
    const fixture = makeReflectionFixture('supplied');
    const { baseline } = fixture.inquiry;
    expect(validateInquiryBinding(fixture.investigations, fixture.experiment.alternative, binding())).not.toBeNull();
    expect(validateInquiryBinding(fixture.investigations, baseline, { ...binding(), continuationId: 'other' })).not.toBeNull();
    expect(validateInquiryBinding(fixture.investigations, baseline, { ...binding(), inquiryId: 'other' })).not.toBeNull();
    expect(validateInquiryBinding(fixture.investigations, baseline, { ...binding(), responseId: 'other' })).not.toBeNull();
    expect(validateInquiryBinding(fixture.investigations, baseline, { ...binding(), evidenceContextId: baseline.contextId })).not.toBeNull();
    expect(validateInquiryBinding(fixture.investigations, { ...baseline, artifactId: fixture.experiment.alternative.artifactId }, binding())).not.toBeNull();
    const unscoped = { ...binding() };
    delete unscoped.responseId;
    expect(validateInquiryBinding(fixture.investigations, baseline, unscoped)).toContain('exact response');
  });

  test('missing response never falls back to a packet in the same investigation', () => {
    const fixture = makeReflectionFixture('supplied');
    fixture.investigations[0].continuation!.inquiry!.responses = [];
    expect(resolveInquiryBinding(fixture.investigations, fixture.inquiry.baseline, binding()).error).toContain('response');
    const restored = makeReflectionFixture('supplied');
    restored.investigations[0].currentContextId = restored.inquiry.evidenceContextId!;
    expect(resolveInquiryBinding(restored.investigations, restored.inquiry.baseline, binding()).error).toBeNull();
  });

  test('a terminal refusal cannot be treated as supplied evidence', () => {
    const fixture = makeReflectionFixture('supplied');
    const inquiry = fixture.investigations[0].continuation!.inquiry!;
    inquiry.status = 'refuse';
    inquiry.responses[0].decision = 'refuse';
    inquiry.responses[0].evidenceContext = null;
    expect(resolveInquiryBinding(fixture.investigations, fixture.inquiry.baseline, binding()).error).toContain('offered context');
  });
});
