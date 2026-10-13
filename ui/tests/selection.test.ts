import { expect, test } from 'bun:test';
import { sameSelections } from '../src/lib/semantic';

test('polling key order cannot make a saved context dirty; actual evidence edits can', () => {
  const local = [{ threadId: 'a', startSeq: 12, endSeq: 12, rationale: 'decision' }];
  const polled = [{ endSeq: 12, rationale: 'decision', startSeq: 12, threadId: 'a' }];
  expect(sameSelections(local, polled)).toBe(true);
  expect(sameSelections(local, [{ ...polled[0], rationale: 'changed reason' }])).toBe(false);
  expect(sameSelections(local, [{ ...polled[0], threadId: 'another source' }])).toBe(false);
  expect(sameSelections(local, [{ ...polled[0], endSeq: 13 }])).toBe(false);
  expect(sameSelections(local, [...polled, ...polled])).toBe(false);
});
