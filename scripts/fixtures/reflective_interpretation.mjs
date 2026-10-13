// Browser-only presentation fixture. It does not replace the persisted API object,
// impersonate native output, or carry the real artifact's adoption/record mapping.
export function competingInterpretation(original) {
  if (!original.title.startsWith('Competing interpretation') || !original.artifact) {
    throw Error('Expected the completed synthetic acceptance investigation');
  }
  const value = structuredClone(original);
  value.title = 'Synthetic competing interpretation · inspect the outer seam';
  value.adoption = null;
  value.artifact = {
    ...value.artifact,
    id: `${value.artifact.id}-presentation-fixture`, outputSeqs: [],
    text: [
      '**Synthetic presentation fixture — no model or native work was called.**',
      'The inner checkpoint preserves a prepared response, but the outer investigation still has an uncertain delivery window. Keep its outcome unknown until matching recorded completion is recovered. The crash experiment identifies this separate seam. [evidence:72]',
      '```diff\n- on missing reply: launch another specialist\n+ on missing reply: retain the original attempt\n+ recover only from recorded completion\n```',
      'Open question: does recovery still work when the native completion was never recorded locally? This reference is deliberately outside the supplied packet. [evidence:9999]'
    ].join('\n\n'),
    citations: [72], unsupportedCitations: [9999]
  };
  return value;
}
