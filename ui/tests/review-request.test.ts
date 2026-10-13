import { expect, test } from 'bun:test';
import { readReviewRequest, responseBody } from '../src/lib/review-request';

test('reviewed offer retains exact ranges when the live tray changes', () => {
  const tray = [{ threadId: 'source-a', startSeq: 12, endSeq: 14, rationale: 'Counterexample' }];
  const body = responseBody('request-a', 'offer', 'Owner reviewed', tray);
  tray[0].startSeq = 70;
  tray[0].rationale = 'Changed draft';
  expect(body.selections).toEqual([{ threadId: 'source-a', startSeq: 12, endSeq: 14, rationale: 'Counterexample' }]);
  const pending = { version: 1, investigationId: 'a', path: 'inquiries/inquiry-a/responses', body };
  expect(readReviewRequest(JSON.stringify(pending), 'a')?.body).toEqual(body);
  expect(readReviewRequest(JSON.stringify(pending), 'b')).toBeNull();
});

test('refusal and deferral never carry the selected evidence, and storage cannot route another action', () => {
  const tray = [{ threadId: 'secret', startSeq: 1, endSeq: 4, rationale: '' }];
  expect(responseBody('r', 'refuse', '', tray)).not.toHaveProperty('selections');
  expect(responseBody('d', 'defer', '', tray)).not.toHaveProperty('selections');
  expect(readReviewRequest('{', 'a')).toBeNull();
  expect(readReviewRequest(JSON.stringify({ version: 1, investigationId: 'a', path: 'dispatch', body: { requestId: 'r' } }), 'a')).toBeNull();
});
