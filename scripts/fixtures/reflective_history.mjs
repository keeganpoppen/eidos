// A browser-only stress projection of the explicitly synthetic demo history.
// It is served only by CDP request interception in the rendered acceptance;
// none of these additional records are admitted to an investigation or store.
export function extendSyntheticHistory(original, totalTurns = 1200) {
  if (original.id !== 'fixture-design') throw Error('Only synthetic design history may be extended');
  const turns = structuredClone(original.turns);
  for (let index = turns.length; index < totalTurns; index++) {
    const seq = 10000 + index * 2;
    const id = `browser-fixture-turn-${index}`;
    const text = `Synthetic browser-only history ${index + 1}. This routine note adds no evidence to the recovery decision.`;
    turns.push({
      id, inputs: [], startSeq: seq, endSeq: seq + 1, eventCount: 2,
      items: [{
        id: `${id}-answer`, type: 'agentMessage', startSeq: seq, endSeq: seq + 1,
        complete: true, text, raw: { fixture: 'browser-only', ordinal: index }
      }]
    });
  }
  return {
    ...structuredClone(original), turns,
    preview: 'Synthetic browser-only stress history — 1,200 turns',
    recordCount: turns.length * 2, lastSeq: turns.at(-1).endSeq
  };
}
