import { marked } from 'marked';
import type { EvidenceSelection } from './types';

export function sameSelections(left: EvidenceSelection[], right: EvidenceSelection[]): boolean {
  return left.length === right.length && left.every((item, index) => {
    const other = right[index];
    return item.threadId === other.threadId && item.startSeq === other.startSeq && item.endSeq === other.endSeq && item.rationale === other.rationale;
  });
}

export type ContentBlock = {
  id: string;
  text: string;
  citations: number[];
  artifactCitations: string[];
  kind: string;
  diff?: string;
};

/** Offsets are local to an immutable artifact, not global claim identities. */
export function contentBlocks(source: string): ContentBlock[] {
  let offset = 0;
  return marked.lexer(source).flatMap((token) => {
    const start = offset;
    offset += token.raw.length;
    if (token.type === 'space') return [];
    const citations = [...new Set([...token.raw.matchAll(/\[evidence:(\d+)\]/g)]
      .map((match) => Number(match[1])).filter(Number.isSafeInteger))];
    return [{
      id: `block-${start}`,
      text: token.raw,
      citations,
      artifactCitations: [...new Set([...token.raw.matchAll(/\[artifact:([A-Za-z0-9_:-]+)\]/g)].map((match) => match[1]))],
      kind: token.type,
      ...(token.type === 'code' && /^(diff|patch)$/i.test(token.lang ?? '')
        ? { diff: token.text } : {})
    }];
  });
}

export type DiffLine = {
  kind: 'unchanged' | 'added' | 'removed';
  text: string;
  beforeLine: number | null;
  afterLine: number | null;
};

/** Bounded LCS; large unmatched regions use an explicit replacement, never an NxM allocation. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const left = before === '' ? [] : before.split('\n');
  const right = after === '' ? [] : after.split('\n');
  const rows: DiffLine[] = [];
  let prefix = 0;
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) {
    rows.push({ kind: 'unchanged', text: left[prefix], beforeLine: prefix + 1, afterLine: prefix + 1 });
    prefix++;
  }
  let suffix = 0;
  while (suffix < left.length - prefix && suffix < right.length - prefix
    && left[left.length - suffix - 1] === right[right.length - suffix - 1]) suffix++;
  const a = left.slice(prefix, left.length - suffix);
  const b = right.slice(prefix, right.length - suffix);
  let i = 0;
  let j = 0;
  const add = () => rows.push({ kind: 'added', text: b[j], beforeLine: null, afterLine: prefix + ++j });
  const remove = () => rows.push({ kind: 'removed', text: a[i], beforeLine: prefix + ++i, afterLine: null });
  if ((a.length + 1) * (b.length + 1) <= 200_000) {
    const width = b.length + 1;
    const table = new Uint32Array((a.length + 1) * width);
    for (let x = a.length - 1; x >= 0; x--) {
      for (let y = b.length - 1; y >= 0; y--) {
        table[x * width + y] = a[x] === b[y]
          ? 1 + table[(x + 1) * width + y + 1]
          : Math.max(table[(x + 1) * width + y], table[x * width + y + 1]);
      }
    }
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        rows.push({ kind: 'unchanged', text: a[i], beforeLine: prefix + ++i, afterLine: prefix + ++j });
      } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) remove();
      else add();
    }
  }
  while (i < a.length) remove();
  while (j < b.length) add();
  for (let n = suffix; n > 0; n--) {
    rows.push({ kind: 'unchanged', text: left[left.length - n], beforeLine: left.length - n + 1, afterLine: right.length - n + 1 });
  }
  return rows;
}

export type DiffEntry = DiffLine | { kind: 'gap'; id: number; count: number };

export function diffEntries(rows: DiffLine[], expanded: ReadonlySet<number> = new Set()): DiffEntry[] {
  const entries: DiffEntry[] = [];
  for (let start = 0; start < rows.length;) {
    if (rows[start].kind !== 'unchanged') {
      entries.push(rows[start++]);
      continue;
    }
    let end = start;
    while (end < rows.length && rows[end].kind === 'unchanged') end++;
    if (end - start > 8 && !expanded.has(start)) {
      entries.push(...rows.slice(start, start + 3));
      entries.push({ kind: 'gap', id: start, count: end - start - 6 });
      entries.push(...rows.slice(end - 3, end));
    } else for (let index = start; index < end; index++) entries.push(rows[index]);
    start = end;
  }
  return entries;
}

export function patchLines(source: string): Array<{ text: string; kind: 'added' | 'removed' | 'hunk' | 'context' }> {
  return source.split('\n').map((text) => ({
    text,
    kind: text.startsWith('@@') ? 'hunk'
      : text.startsWith('+') && !text.startsWith('+++') ? 'added'
      : text.startsWith('-') && !text.startsWith('---') ? 'removed' : 'context'
  }));
}

type ObjectValue = Record<string, unknown>;
function object(value: unknown): ObjectValue | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as ObjectValue : null;
}

export type EvidenceProjection = {
  kind: 'message' | 'command' | 'changes' | 'unknown';
  type: string;
  text: string;
  command: string;
  output: string;
  changes: Array<{ path: string; diff: string }>;
};

/** A replaceable projection; the untouched record remains the evidence. */
export function projectEvidence(rawText: string): EvidenceProjection {
  const unknown: EvidenceProjection = { kind: 'unknown', type: 'unrecognized record', text: '', command: '', output: '', changes: [] };
  let root: ObjectValue | null;
  try { root = object(JSON.parse(rawText)); } catch { return unknown; }
  if (!root) return unknown;
  const params = object(root.params);
  const item = object(params?.item) ?? object(root.item) ?? (typeof root.type === 'string' ? root : null);
  if (!item) return unknown;
  const type = typeof item.type === 'string' ? item.type : 'unrecognized item';
  if (['agentMessage', 'userMessage', 'reasoning'].includes(type)) {
    const parts = Array.isArray(item.content) ? item.content : [];
    const text = typeof item.text === 'string' ? item.text : parts.flatMap((part) => {
      const value = object(part);
      return value?.type === 'text' && typeof value.text === 'string' ? [value.text] : [];
    }).join('\n\n');
    const summaries = Array.isArray(item.summary) ? item.summary.filter((part): part is string => typeof part === 'string').join('\n\n') : '';
    return text || summaries ? { ...unknown, kind: 'message', type, text: text || summaries } : { ...unknown, type };
  }
  if (type === 'commandExecution') {
    return { ...unknown, kind: 'command', type,
      command: typeof item.command === 'string' ? item.command : '',
      output: typeof item.aggregatedOutput === 'string' ? item.aggregatedOutput : typeof item.output === 'string' ? item.output : '' };
  }
  if (type === 'fileChange') {
    const changes = (Array.isArray(item.changes) ? item.changes : []).flatMap((change) => {
      const value = object(change);
      return value && typeof value.path === 'string' ? [{ path: value.path, diff: typeof value.diff === 'string' ? value.diff : '' }] : [];
    });
    return { ...unknown, kind: 'changes', type, changes };
  }
  return { ...unknown, type };
}
