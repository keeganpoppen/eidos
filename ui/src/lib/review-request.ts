import type { EvidenceSelection } from './types';

export type ReviewDecision = 'offer' | 'refuse' | 'defer';
export type ReviewRequest = {
  version: 1;
  investigationId: string;
  path: 'continuation' | 'continue' | `inquiries/${string}/responses` | `inquiries/${string}/cancel`;
  body: { requestId: string; [key: string]: unknown };
};

export function responseBody(requestId: string, decision: ReviewDecision, note: string, selections: EvidenceSelection[]) {
  return {
    requestId, decision, note,
    ...(decision === 'offer' ? { selections: selections.map((selection) => ({ ...selection })) } : {})
  };
}

export function readReviewRequest(raw: string | null, investigationId: string): ReviewRequest | null {
  try {
    const value = JSON.parse(raw ?? 'null');
    if (!value || value.version !== 1 || value.investigationId !== investigationId ||
      typeof value.path !== 'string' || !(value.path === 'continuation' || value.path === 'continue' || /^inquiries\/[A-Za-z0-9_.%:-]+\/(responses|cancel)$/.test(value.path)) ||
      !value.body || typeof value.body !== 'object' || Array.isArray(value.body) || typeof value.body.requestId !== 'string') return null;
    return { version: 1, investigationId, path: value.path, body: value.body };
  } catch { return null; }
}
