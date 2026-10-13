import { describe, expect, test } from 'bun:test';
import { contentBlocks, diffEntries, lineDiff, patchLines, projectEvidence } from '../src/lib/semantic';

describe('artifact-local content focus', () => {
  test('keeps citation scope next to claims, including unsupported references', () => {
    const source = '# Result\n\nSupported claim [evidence:12] and [evidence:12].\n\nUnverified [evidence:999].\n\nNo citation.';
    const blocks = contentBlocks(source);
    expect(blocks.map((block) => block.citations)).toEqual([[], [12], [999], []]);
    expect(blocks.map((block) => block.id)).toEqual(contentBlocks(source).map((block) => block.id));
    expect(new Set(blocks.map((block) => block.id)).size).toBe(blocks.length);
  });
  test('preserves fenced patches as one block instead of interpreting lines as claims', () => {
    const [block] = contentBlocks('```diff\n--- old\n+++ new\n@@ -1 +1 @@\n-old\n+new\n```');
    expect(block.diff).toContain('-old\n+new');
    expect(patchLines(block.diff!).map((line) => line.kind)).toEqual(['context', 'context', 'hunk', 'removed', 'added']);
  });
});

describe('bounded native text changes', () => {
  test('retains precise line numbers through inserted and removed text', () => {
    expect(lineDiff('same\nold\ntail', 'same\nnew\ntail')).toEqual([
      { kind: 'unchanged', text: 'same', beforeLine: 1, afterLine: 1 },
      { kind: 'removed', text: 'old', beforeLine: 2, afterLine: null },
      { kind: 'added', text: 'new', beforeLine: null, afterLine: 2 },
      { kind: 'unchanged', text: 'tail', beforeLine: 3, afterLine: 3 }
    ]);
    expect(lineDiff('', 'one')[0]).toEqual({ kind: 'added', text: 'one', beforeLine: null, afterLine: 1 });
  });
  test('collapses huge unchanged history without losing the replacement', () => {
    const prefix = Array.from({ length: 20000 }, (_, i) => `line ${i}`).join('\n');
    const rows = lineDiff(prefix + '\nold', prefix + '\nnew');
    const entries = diffEntries(rows);
    expect(entries.length).toBe(9);
    expect(entries.some((row) => row.kind === 'gap' && row.count === 19994)).toBe(true);
    expect(entries.at(-2)?.kind).toBe('removed');
    expect(entries.at(-1)?.kind).toBe('added');
    expect(diffEntries(rows, new Set([0]))).toHaveLength(rows.length);
  });
  test('large unrelated regions remain exact replacements without quadratic allocation', () => {
    const a = Array.from({ length: 2000 }, (_, i) => `old ${i}`);
    const b = Array.from({ length: 2000 }, (_, i) => `new ${i}`);
    const rows = lineDiff(a.join('\n'), b.join('\n'));
    expect(rows.filter((row) => row.kind === 'removed').map((row) => row.text)).toEqual(a);
    expect(rows.filter((row) => row.kind === 'added').map((row) => row.text)).toEqual(b);
  });
});

describe('frozen evidence projection', () => {
  test('renders known observed item text without discarding original unknown fields', () => {
    const raw = JSON.stringify({ method: 'item/completed', params: { item: { type: 'agentMessage', text: 'Decision.', future: { secretMeaning: true } } }, extra: 'retained' });
    expect(projectEvidence(raw)).toMatchObject({ kind: 'message', text: 'Decision.' });
    expect(JSON.parse(raw).extra).toBe('retained');
  });
  test('extracts only explicitly textual user content', () => {
    expect(projectEvidence(JSON.stringify({ params: { item: { type: 'userMessage', content: [{ type: 'image', text: 'do not treat as text' }, { type: 'text', text: 'Actual input' }] } } }))).toMatchObject({ kind: 'message', text: 'Actual input' });
  });
  test('unknown and invalid JSON stays unknown instead of inventing a message', () => {
    for (const raw of ['{broken', 'null', '[1,2]', '{"params":{"question":"approve unknown action?"}}']) {
      expect(projectEvidence(raw).kind).toBe('unknown');
    }
  });
  test('supports native command output and literal patch text', () => {
    expect(projectEvidence(JSON.stringify({ item: { type: 'commandExecution', command: 'test', aggregatedOutput: 'passed' } }))).toMatchObject({ kind: 'command', command: 'test', output: 'passed' });
    expect(projectEvidence(JSON.stringify({ item: { type: 'fileChange', changes: [{ path: 'x', diff: '+literal' }] } })).changes).toEqual([{ path: 'x', diff: '+literal' }]);
  });
});
