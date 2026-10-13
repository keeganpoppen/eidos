import type { SupportSpan, ThreadPayload, ThreadResponse, Turn } from './types';

/** Ranges describe extent; only constituent records establish membership. */
export function hasSourceEvidence(source: { startSeq: number; endSeq: number; recordSeqs?: number[] }, span: SupportSpan): boolean {
  const records = source.recordSeqs ?? [source.startSeq, source.endSeq];
  return records.some((seq) => span.start <= seq && seq <= span.end);
}

export function sourceTarget(turns: Turn[], span: SupportSpan): { turnId: string; itemId?: string } | null {
  for (const turn of turns) {
    const item = turn.items.find((candidate) => hasSourceEvidence(candidate, span));
    if (item) return { turnId: turn.id, itemId: item.id };
  }
  const turn = turns.find((candidate) => hasSourceEvidence(candidate, span));
  return turn ? { turnId: turn.id } : null;
}

/** User navigation invalidates requests and deferred focus work; polling only supersedes requests. */
export function createHistoryRequests() {
  let navigation = 0;
  let request = 0;
  return {
    navigate() {
      const current = ++navigation;
      return () => current === navigation;
    },
    request() {
      const currentNavigation = navigation;
      const currentRequest = ++request;
      return () => currentNavigation === navigation && currentRequest === request;
    }
  };
}

export type SourceFocus = {
  threadId: string;
  revision: string;
  anchorSeq: number | null;
  selectedNodeId: string | null;
  spans: SupportSpan[];
  workMode: boolean;
};

const sequence = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

export function readSourceFocus(raw: string | null): SourceFocus | null {
  try {
    const saved = JSON.parse(raw ?? 'null');
    if (!saved || typeof saved.threadId !== 'string' || !saved.threadId) return null;
    return {
      threadId: saved.threadId,
      revision: typeof saved.revision === 'string' ? saved.revision : '',
      anchorSeq: sequence(saved.anchorSeq) ? saved.anchorSeq : null,
      selectedNodeId: typeof saved.selectedNodeId === 'string' ? saved.selectedNodeId : null,
      spans: Array.isArray(saved.spans) ? saved.spans.filter((span: SupportSpan) =>
        span && sequence(span.start) && sequence(span.end) && span.end >= span.start
      ).map((span: SupportSpan) => ({ start: span.start, end: span.end, weight: Number.isFinite(span.weight) ? span.weight : 1,
        ...(typeof span.label === 'string' ? { label: span.label } : {}) })) : [],
      workMode: saved.workMode !== false
    };
  } catch { return null; }
}

export function historyQuery(revision: string, anchorSeq: number | null, aroundSeq?: number, knownVersion?: string): string {
  const query = new URLSearchParams();
  if (revision) query.set('revision', revision);
  if (aroundSeq !== undefined) query.set('aroundSeq', String(aroundSeq));
  else if (anchorSeq !== null) query.set('anchorSeq', String(anchorSeq));
  if (knownVersion) query.set('knownVersion', knownVersion);
  const encoded = query.toString();
  return encoded ? `?${encoded}` : '';
}

/** A compact poll response cannot replace the evidence already being read. */
export function retainThread(current: ThreadPayload | null, response: ThreadResponse): ThreadPayload | null {
  if ('unchanged' in response) {
    if (!current || current.id !== response.id || current.version !== response.version || current.window.anchorSeq !== response.window.anchorSeq) {
      throw new Error('The history response no longer matches this source page. Reload the page.');
    }
    return current;
  }
  return response;
}
