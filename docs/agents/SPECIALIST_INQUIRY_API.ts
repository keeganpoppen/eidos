/** Additive owner-service contract for Codecy D / integrator. No UI implementation.
 * Names identify records; none of these objects is a responder or execution token.
 * Existing schemaVersion:1 Investigation/Context/Attempt/Artifact types remain valid.
 */
export interface NativeInquiryEvent {
  seq: number;
  source: string;
  threadId: string;
  turnId: string;
  method: 'item/completed' | 'turn/completed';
  sha256: string;
}
export interface NativeInquiryCause {
  schemaVersion: 1;
  origin: 'native-specialist';
  mode: 'terminal-needs-evidence';
  investigationId: string;
  attemptId: string;
  contextId: string;
  nativeArtifactId: string;
  requestSeq: number;
  nativeEvent: NativeInquiryEvent;
  question: string;
  cause: string;
}
export interface EvidenceSelection {
  threadId: string;
  startSeq: number;
  endSeq: number;
  rationale?: string;
}
export type InquiryResponseRequest = {
  requestId: string;
  note?: string;
} & ({decision: 'offer'; selections: EvidenceSelection[]} | {decision: 'defer' | 'refuse'});
export interface InquiryCancelRequest { requestId: string; note?: string }
export interface SpecialistContinueRequest {
  requestId: string;
  continuationId: string;
  contextId: string;
}
export interface InquiryResponse<ContextPacket> {
  id: string;
  requestId: string;
  decision: 'offer' | 'refuse' | 'defer';
  note: string;
  status: 'admitted' | 'committed';
  evidenceContext: ContextPacket | null;
  occurrenceId: string | null;
  disclosureCutId: string | null;
  responseValueId: string | null;
}
export interface SpecialistInquiry<ContextPacket> {
  id: string;
  question: string;
  cause: NativeInquiryCause;
  // offer/refuse: source committed; answered/refused: recipient incorporated.
  status: 'pending' | 'deferred' | 'offer' | 'refuse' | 'answered' | 'refused' | 'cancelled';
  openedOccurrenceId: string;
  responses: InquiryResponse<ContextPacket>[];
}
export interface NativeNext {
  status: 'awaiting-admission' | 'dispatched';
  // Null until preview preparation finishes. An error prevents admission.
  contextId: string | null;
  attemptId: string | null;
  error?: string;
}
export interface SpecialistContinuation<ContextPacket> {
  schemaVersion: 1;
  id: string;
  attemptId: string;
  origin: 'native-specialist';
  question: string;
  cause: NativeInquiryCause;
  status: 'preparing' | 'pending' | 'resuming' | 'completed' | 'cancelled';
  realizationStatus: 'ready' | 'failed' | 'completed' | 'cancelled';
  error: string | null;
  processId: string | null;
  protocolId: string | null;
  modelId: string | null;
  checkpointId: string | null;
  initialCheckpointId: string | null;
  outcomeId: string | null;
  contextName: string | null;
  inquiry: SpecialistInquiry<ContextPacket> | null;
  nativeNext?: NativeNext;
  cancellation?: {requestId: string; note: string; inquiryId: string};
}
export interface InquiryLineage {
  investigationId: string;
  attemptId: string;
  continuationId: string;
  inquiryId: string;
  responseId: string;
  decision: 'offer' | 'refuse';
  decisionOccurrenceId: string;
  outcomeId: string;
  contextName: string;
  nativeArtifactId: string;
  evidenceContextId: string | null;
}
export interface InvestigationInquiryAdditions<Attempt, Artifact> {
  attemptHistory?: Attempt[];
  artifactHistory?: Artifact[];
  nativeArtifact?: Artifact;
  inquiryAdmissionError?: string;
}
// Context packets optionally gain inquiryLineage; A2 attempts and artifacts gain
// continuedFrom: InquiryLineage. Native attempt status remains dispatching/running/
// completed/failed/unknown, distinct from continuation and inquiry state.
// Outer status additionally accepts needs-evidence and cancelled.
// Artifact kinds add native-needs-evidence, native-inquiry-invalid, native-specialist-result.
// Responses to all mutations are the current saved Investigation, not a new inner process.
export type InvestigationStatus = 'draft' | 'dispatching' | 'running' | 'completed'
  | 'failed' | 'unknown' | 'pending' | 'resuming' | 'needs-evidence' | 'cancelled';
export type NativeAttemptStatus = 'dispatching' | 'running' | 'completed' | 'failed' | 'unknown';
export type SpecialistArtifactKind = 'native-needs-evidence' | 'native-inquiry-invalid'
  | 'native-specialist-result' | 'eidos-evidence-review';
export interface FollowupContextAdditions { inquiryLineage: InquiryLineage }
export interface FollowupAttemptAdditions { continuedFrom: InquiryLineage }
