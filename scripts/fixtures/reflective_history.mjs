// Coordinates of the authored history persisted by investigation_demo.py.
// Acceptance resolves actual record identities from HTTP responses; this file
// never manufactures a history or intercepts a server response.
export const persistedHistory = Object.freeze({
  threadId: 'fixture-long-history',
  title: 'Synthetic long history:',
  totalTurns: 1200,
  semanticNodeId: 'recovery-decision',
  rejectionItemId: 'fixture-long-history-turn-20-answer',
  decisionItemId: 'fixture-long-history-turn-1100-answer',
  lastItemId: 'fixture-long-history-turn-1199-answer',
  toolItemId: 'fixture-long-history-turn-600-command',
  neighborThreadId: 'fixture-history-neighbor',
  neighborItemId: 'fixture-history-neighbor-answer'
});
