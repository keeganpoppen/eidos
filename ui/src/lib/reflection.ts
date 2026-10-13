import { artifacts, attempts } from './comparison';
import type { ApertureTarget } from './comparison';
import type { Investigation, InvestigationContext, InvestigationContinuation, InquiryResponse } from './types';

/** References into one admitted review, not a request to create or resume authority. */
export type InquiryBinding = {
  continuationId: string;
  inquiryId: string;
  responseId?: string;
  evidenceContextId?: string;
};

export type Experiment = {
  id: string;
  name: string;
  origin: 'synthetic-fixture';
  baseline: ApertureTarget;
  alternative: ApertureTarget;
  change: string;
  evaluation: {
    id: string;
    method: string;
    cases: Array<{ name: string; baseline: string; alternative: string; result: string }>;
    established: string[];
    limitations: string[];
    cost: string;
  };
};

/** An authored presentation experiment. It is never a production agent proposal. */
export type Improvement = {
  id: string;
  version: number;
  title: string;
  evidence: ApertureTarget[];
  experimentId: string;
  expectedBenefit: string;
  patch: string;
  beforeVersion: string;
  afterVersion: string;
  rollback: string;
  origin: 'synthetic-fixture';
};

export type ReflectionInquiry = {
  id: string;
  continuationId: string;
  question: string;
  requester: string;
  origin: 'synthetic-fixture';
  status: 'pending' | 'offered';
  baseline: ApertureTarget;
  result: ApertureTarget | null;
  evidenceContextId?: string;
  responseId?: string;
};

export type ReflectionFixture = {
  investigations: Investigation[];
  inquiry: ReflectionInquiry;
  experiment: Experiment;
  improvement: Improvement;
};

export type ResolvedInquiryBinding = {
  investigation?: Investigation;
  continuation?: InvestigationContinuation;
  inquiry?: NonNullable<InvestigationContinuation['inquiry']>;
  response?: InquiryResponse;
  evidenceContext?: InvestigationContext;
  error: string | null;
};

/** Resolve through the owning investigation and response; never follow "current". */
export function resolveInquiryBinding(
  investigations: Investigation[], target: ApertureTarget, binding: InquiryBinding
): ResolvedInquiryBinding {
  const investigation = investigations.find((item) => item.id === target.investigationId);
  if (!investigation) return { error: 'The bound investigation is unavailable.' };
  const continuation = investigation.continuation;
  if (!continuation || continuation.id !== binding.continuationId) {
    return { investigation, error: 'The continuation does not belong to this investigation.' };
  }
  const inquiry = continuation.inquiry;
  if (!inquiry || inquiry.id !== binding.inquiryId) {
    return { investigation, continuation, error: 'The inquiry does not belong to this continuation.' };
  }
  const found = { investigation, continuation, inquiry };
  const attempt = attempts(investigation).find((item) => item.id === continuation.attemptId);
  if (!attempt) {
    return { ...found, error: 'The inquiry has no matching investigation attempt.' };
  }
  if (binding.evidenceContextId && !binding.responseId) {
    return { ...found, error: 'An offered packet requires its exact response identity.' };
  }
  const response = binding.responseId ? inquiry.responses.find((item) => item.id === binding.responseId) : undefined;
  if (binding.responseId && !response) return { ...found, error: 'The response does not belong to this inquiry.' };
  const evidenceContext = response?.evidenceContext ?? undefined;
  if (evidenceContext && evidenceContext.id !== binding.evidenceContextId) {
    return { ...found, response, error: 'The offered packet needs its exact context binding.' };
  }
  if (binding.evidenceContextId && (response?.decision !== 'offer' || evidenceContext?.id !== binding.evidenceContextId)) {
    return { ...found, response, error: 'The offered context does not match this response.' };
  }
  // The native packet and the separately offered packet are both legal views of
  // this inquiry. Another draft/revision in the same work is not interchangeable.
  const isOriginal = target.contextId === attempt.contextId &&
    investigation.contexts.some((context) => context.id === target.contextId);
  const isOffered = !!binding.evidenceContextId && target.contextId === binding.evidenceContextId &&
    evidenceContext?.id === target.contextId;
  if (!isOriginal && !isOffered) return { ...found, response, error: 'The context is outside this inquiry binding.' };
  if (target.artifactId && !artifacts(investigation).some((artifact) =>
    artifact?.id === target.artifactId && artifact?.contextId === target.contextId)) {
    return { ...found, response, error: 'The artifact does not match the bound context.' };
  }
  return { ...found, response, evidenceContext, error: null };
}

export function validateInquiryBinding(investigations: Investigation[], target: ApertureTarget, binding: InquiryBinding): string | null {
  return resolveInquiryBinding(investigations, target, binding).error;
}
