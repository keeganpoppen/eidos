import type { EvidenceSelection, ThreadItem } from './types';

export type EvidenceAddition = { threadId: string; recordSeqs: number[]; rationale?: string } | { ranges: EvidenceSelection[] };
export type EvidenceEditor = { disabled: boolean; reason: string; add: (addition: EvidenceAddition) => boolean };
const validSeq = (n: number) => Number.isSafeInteger(n) && n > 0;

/** Only adjacent *observed* sequences form a range. Extent is not membership. */
export function recordSelections(threadId: string, records: number[], rationale = ''): EvidenceSelection[] {
  if (!threadId || !records.length || records.length > 256 || records.some(n => !validSeq(n))) throw Error('Exact source membership is unavailable or exceeds 256 records.');
  const result: EvidenceSelection[] = [];
  for (const seq of [...new Set(records)].sort((a, b) => a - b)) {
    const last = result.at(-1);
    if (last && last.endSeq + 1 === seq) last.endSeq = seq;
    else result.push({ threadId, startSeq: seq, endSeq: seq, rationale });
  }
  return result;
}

export function itemRecords(item: ThreadItem): number[] {
  // A legacy single-record item is exact; a legacy extent is not.
  return item.recordSeqs ?? (item.startSeq === item.endSeq ? [item.startSeq] : []);
}

export function recordsSelected(selections: EvidenceSelection[], threadId: string, records: number[]): boolean {
  return records.length > 0 && records.every(seq => selections.some(s => s.threadId === threadId && s.startSeq <= seq && s.endSeq >= seq));
}

/** Conservative union count, without enumerating wide semantic/manual ranges.
 * Gaps may belong to other threads; the server's actual record count is final. */
export function selectionRecordBound(selections: EvidenceSelection[]): number {
  const ordered = [...selections].sort((a, b) => a.threadId.localeCompare(b.threadId) || a.startSeq - b.startSeq);
  let thread = '', end = 0, count = 0;
  for (const s of ordered) {
    if (!s.threadId || !validSeq(s.startSeq) || !validSeq(s.endSeq) || s.endSeq < s.startSeq) throw Error('An evidence selection is invalid.');
    if (thread !== s.threadId) { thread = s.threadId; end = 0; }
    count += Math.max(0, s.endSeq - Math.max(end, s.startSeq - 1));
    end = Math.max(end, s.endSeq);
    if (count > 256) return count;
  }
  return count;
}

export function addEvidence(selections: EvidenceSelection[], artifactCount: number, addition: EvidenceAddition): EvidenceSelection[] {
  let added: EvidenceSelection[];
  if ('recordSeqs' in addition) {
    // Do not replace the rationale or split an existing intentional range.
    recordSelections(addition.threadId, addition.recordSeqs, addition.rationale);
    const missing = addition.recordSeqs.filter(seq => !recordsSelected(selections, addition.threadId, [seq]));
    if (!missing.length) return selections;
    added = recordSelections(addition.threadId, missing, addition.rationale);
  } else {
    added = addition.ranges.filter(s => !selections.some(old => old.threadId === s.threadId && old.startSeq === s.startSeq && old.endSeq === s.endSeq));
  }
  const result = [...selections, ...added];
  if (!Number.isSafeInteger(artifactCount) || artifactCount < 0 || result.length + artifactCount > 32) throw Error('These exact records do not fit the 32-input limit. Remove an input or select fewer records.');
  if (selectionRecordBound(result) > 256) throw Error('These selections may exceed 256 records. Narrow the source ranges before adding; the server checks actual record membership when saving.');
  return result;
}

export function evidenceEditReason(ready: boolean, busy: boolean, pending: boolean): string {
  return !ready ? 'Wait for the working draft to load.' : busy ? 'Wait for the current editor action to finish.'
    : pending ? 'Resolve the current draft’s pending save before changing its evidence. Its exact retry is retained.' : '';
}
