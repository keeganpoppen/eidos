import { describe, expect, test } from 'bun:test';
import { addEvidence, evidenceEditReason, itemRecords, recordSelections, recordsSelected, selectionRecordBound } from '../src/lib/evidence-selection';
import type { EvidenceSelection, ThreadItem } from '../src/lib/types';

const range = (startSeq: number, endSeq = startSeq, rationale = '', threadId = 't'): EvidenceSelection => ({ threadId, startSeq, endSeq, rationale });
describe('exact evidence membership and editor gate', () => {
  test('interleaved item records never add their unrelated enclosing gap', () => {
    const item = { startSeq: 1, endSeq: 3, recordSeqs: [1, 3] } as ThreadItem;
    const result = addEvidence([], 0, { threadId: 't', recordSeqs: itemRecords(item) });
    expect(result).toEqual([range(1), range(3)]);
    expect(recordsSelected(result, 't', [1, 3])).toBe(true);
    expect(recordsSelected(result, 't', [2])).toBe(false);
    expect(recordsSelected(result, 'other', [1])).toBe(false);
  });
  test('only actual adjacent members merge and input membership remains unchanged', () => {
    const seqs = [9, 2, 4, 3, 9];
    expect(recordSelections('t', seqs, 'why')).toEqual([range(2, 4, 'why'), range(9, 9, 'why')]);
    expect(seqs).toEqual([9, 2, 4, 3, 9]);
  });
  test('existing rationale and intentional semantic intervals are retained', () => {
    const existing = [range(5, 8, 'owner rationale')];
    expect(addEvidence(existing, 0, { threadId: 't', recordSeqs: [4, 5, 8, 9] })).toEqual([...existing, range(4), range(9)]);
    expect(existing).toEqual([range(5, 8, 'owner rationale')]);
    expect(addEvidence(existing, 0, { ranges: [range(5, 8, 'new rationale'), range(20, 25, 'semantic support')] })).toEqual([...existing, range(20, 25, 'semantic support')]);
  });
  test('legacy extents do not invent membership; singleton legacy source remains exact', () => {
    expect(itemRecords({ startSeq: 1, endSeq: 3 } as ThreadItem)).toEqual([]);
    expect(itemRecords({ startSeq: 3, endSeq: 3 } as ThreadItem)).toEqual([3]);
    expect(() => addEvidence([], 0, { threadId: 't', recordSeqs: [] })).toThrow('membership');
    expect(() => recordSelections('t', [1, 1.5])).toThrow();
  });
  test('combined artifact/range and record bounds refuse instead of widening', () => {
    expect(addEvidence([], 30, { threadId: 't', recordSeqs: [1, 3] })).toHaveLength(2);
    expect(() => addEvidence([], 31, { threadId: 't', recordSeqs: [1, 3] })).toThrow('32-input');
    expect(() => addEvidence([], 0, { threadId: 't', recordSeqs: Array.from({ length: 33 }, (_, i) => 2 * i + 1) })).toThrow('32-input');
    expect(addEvidence([], 0, { threadId: 't', recordSeqs: Array.from({ length: 256 }, (_, i) => i + 1) })).toEqual([range(1, 256)]);
    expect(() => addEvidence([range(1, 256)], 0, { threadId: 'other', recordSeqs: [1] })).toThrow('256 records');
  });
  test('wide and overlapping ranges are counted arithmetically without allocating each record', () => {
    expect(selectionRecordBound([range(1, 128), range(64, 256)])).toBe(256);
    expect(selectionRecordBound([range(1), range(1, 1, '', 'other')])).toBe(2);
    expect(() => addEvidence([], 0, { ranges: [range(1, Number.MAX_SAFE_INTEGER)] })).toThrow('256 records');
  });
  test('already-covered members retain original selection object', () => {
    const selected = [range(1, 3, 'retain')];
    expect(addEvidence(selected, 0, { threadId: 't', recordSeqs: [1, 3] })).toBe(selected);
  });
  test('busy, unready and unresolved editor saves refuse evidence changes', () => {
    expect(evidenceEditReason(false, false, false)).toContain('load');
    expect(evidenceEditReason(true, true, false)).toContain('finish');
    expect(evidenceEditReason(true, false, true)).toContain('pending save');
    expect(evidenceEditReason(true, false, false)).toBe('');
  });
});
