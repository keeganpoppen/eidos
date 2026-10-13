import { describe, expect, test } from 'bun:test';
import { createHistoryRequests, hasSourceEvidence, historyQuery, readSourceFocus, retainThread, sourceTarget } from '../src/lib/history';
import type { ThreadPayload } from '../src/lib/types';

function sourcePage(): ThreadPayload {
  return {
    id: 'design', version: 'history-1200:revision-a:anchor-1100', preview: 'Design history',
    recordCount: 4800, lastSeq: 5000, outline: null, revisions: [],
    window: { anchorSeq: 4400, startSeq: 4400, endSeq: 4559, startIndex: 1100, totalTurns: 1200,
      hasEarlier: true, hasLater: true, nextAnchorSeq: 4560, previousAnchorSeq: 4240 },
    turns: [{ id: 'decision', startSeq: 4400, endSeq: 4403, eventCount: 4, inputs: [],
      items: [{ id: 'rationale', type: 'agentMessage', startSeq: 4401, endSeq: 4403,
        complete: true, raw: { preserved: 'unknown native field' }, text: 'Keep the original acknowledgement.' }] }]
  };
}

describe('source history recovery', () => {
  test('interleaved item and turn extents do not impersonate constituent source records', () => {
    const tool = { startSeq: 1, endSeq: 5, recordSeqs: [1, 5] };
    const support = { start: 3, end: 3, weight: 1 };
    expect(hasSourceEvidence(tool, support)).toBe(false);
    expect(hasSourceEvidence({ startSeq: 3, endSeq: 3, recordSeqs: [3] }, support)).toBe(true);
    // Old fixtures do not establish membership in the unobserved interval.
    expect(hasSourceEvidence({ startSeq: 1, endSeq: 5 }, support)).toBe(false);
    expect(hasSourceEvidence(tool, { start: 5, end: 8, weight: 1 })).toBe(true);
  });

  test('source navigation selects the exact item or its turn for a turn-only record', () => {
    const turn = sourcePage().turns[0];
    const turns = [
      { ...turn, id: 'old-turn', startSeq: 1, endSeq: 20, recordSeqs: [1, 5, 20],
        items: [{ ...turn.items[0], id: 'old-tool', startSeq: 5, endSeq: 20, recordSeqs: [5, 20] }] },
      { ...turn, id: 'target-turn', startSeq: 8, endSeq: 9, recordSeqs: [8, 9],
        items: [{ ...turn.items[0], id: 'target-item', startSeq: 9, endSeq: 9, recordSeqs: [9] }] }
    ];
    expect(sourceTarget(turns, { start: 9, end: 9, weight: 1 })).toEqual({ turnId: 'target-turn', itemId: 'target-item' });
    expect(sourceTarget(turns, { start: 8, end: 8, weight: 1 })).toEqual({ turnId: 'target-turn' });
    expect(sourceTarget(turns, { start: 7, end: 7, weight: 1 })).toBeNull();
  });

  test('new source navigation discards an in-flight poll and a delayed navigation failure', async () => {
    const requests = createHistoryRequests();
    const pendingPoll = requests.request();
    const oldNavigation = requests.navigate();
    const oldRequest = requests.request();
    let release!: () => void;
    let notice = '';
    const delayedFailure = new Promise<void>((resolve) => release = resolve).then(() => {
      if (oldRequest()) notice = 'old request error';
      if (oldNavigation()) notice = 'old source unavailable';
    });
    const currentNavigation = requests.navigate();
    const currentRequest = requests.request();
    notice = 'new source loaded';
    release();
    await delayedFailure;
    expect(pendingPoll()).toBe(false);
    expect(currentRequest()).toBe(true);
    expect(currentNavigation()).toBe(true);
    expect(notice).toBe('new source loaded');
  });

  test('clearing focus cancels pending source work while an ordinary poll preserves focus', () => {
    const requests = createHistoryRequests();
    const navigation = requests.navigate();
    const sourceRequest = requests.request();
    const poll = requests.request();
    expect(sourceRequest()).toBe(false);
    expect(navigation()).toBe(true);
    expect(poll()).toBe(true);
    requests.navigate(); // A local clear or aggregate selection need not fetch a page.
    expect(navigation()).toBe(false);
    expect(poll()).toBe(false);
  });

  test('remembers stable evidence and interpretation identity without storing history prose', () => {
    const saved = { threadId: 'design', revision: 'revision-a', anchorSeq: 4400,
      selectedNodeId: 'decision', workMode: false,
      spans: [{ start: 80, end: 82, weight: 1, label: 'Earlier rejection' }, { start: 4401, end: 4403, weight: 1 }] };
    expect(readSourceFocus(JSON.stringify(saved))).toEqual(saved);
    // An old array offset cannot be mistaken for a durable source coordinate.
    expect(readSourceFocus(JSON.stringify({ threadId: 'design', historyStart: 1100 }))?.anchorSeq).toBeNull();
  });

  test('malformed saved source ranges cannot become navigation or context selections', () => {
    const saved = readSourceFocus(JSON.stringify({ threadId: 'design', anchorSeq: -1,
      spans: [null, { start: 40, end: 20 }, { start: 0, end: 3 }, { start: 2.5, end: 3 }, { start: 5, end: 6 }] }));
    expect(saved?.anchorSeq).toBeNull();
    expect(saved?.spans).toEqual([{ start: 5, end: 6, weight: 1 }]);
  });

  test('an unchanged poll retains the exact source page object and native fields', () => {
    const current = sourcePage();
    const response = { id: current.id, unchanged: true as const, version: current.version, window: current.window };
    expect(retainThread(current, response)).toBe(current);
    expect(current.turns[0].items[0].raw.preserved).toBe('unknown native field');
    expect(() => retainThread(null, response)).toThrow();
    expect(() => retainThread({ ...current, id: 'other-thread' }, response)).toThrow();
    expect(() => retainThread({ ...current, version: 'another-page' }, response)).toThrow();
    expect(() => retainThread({ ...current, window: { ...current.window, anchorSeq: 80 } }, response)).toThrow();
  });

  test('exact source navigation does not retain a conflicting page anchor or polling token', () => {
    const source = new URLSearchParams(historyQuery('revision-a', 4400, 82));
    expect(source.get('aroundSeq')).toBe('82');
    expect(source.has('anchorSeq')).toBe(false);
    expect(source.has('knownVersion')).toBe(false);
    expect(source.get('revision')).toBe('revision-a');
    const poll = new URLSearchParams(historyQuery('revision-a', 4400, undefined, 'saved-version'));
    expect(poll.get('anchorSeq')).toBe('4400');
    expect(poll.get('knownVersion')).toBe('saved-version');
  });
});
