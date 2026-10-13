export type ThreadSummary = {
  thread_id: string;
  first_seq: number;
  last_seq: number;
  record_count: number;
  turn_count: number;
  preview: string;
  hasSemanticMap: boolean;
};

export type SupportSpan = {
  start: number;
  end: number;
  weight: number;
  label?: string | null;
};

export type SemanticNode = {
  node_id: string;
  parent_node_id?: string | null;
  ordinal: number;
  title: string;
  summary: string;
  confidence: number;
  support: SupportSpan[];
};

export type SemanticRevision = {
  revision_id: string;
  thread_id: string;
  lens: string;
  observer: string;
  horizon_seq: number;
  confidence: number;
  reliability: number;
  score: number;
  created_at_ms: number;
  note?: string | null;
  nodes?: SemanticNode[];
};

export type ThreadItem = {
  id: string;
  type: string;
  startSeq: number;
  endSeq: number;
  recordSeqs?: number[];
  complete: boolean;
  raw: Record<string, unknown>;
  text?: string;
  phase?: string | null;
  summary?: string[];
  content?: unknown[];
  command?: string;
  output?: string;
  status?: string | null;
  exitCode?: number | null;
  changes?: Array<Record<string, unknown>>;
  detail?: Record<string, unknown>;
};

export type Turn = {
  id: string;
  inputs: Array<Record<string, unknown>>;
  items: ThreadItem[];
  startSeq: number;
  endSeq: number;
  recordSeqs?: number[];
  eventCount: number;
};

export type ThreadWindow = {
  anchorSeq: number | null;
  startSeq: number | null;
  endSeq: number | null;
  startIndex: number;
  totalTurns: number;
  hasEarlier: boolean;
  hasLater: boolean;
  nextAnchorSeq: number | null;
  previousAnchorSeq: number | null;
};

export type ThreadPayload = {
  id: string;
  version: string;
  window: ThreadWindow;
  preview: string;
  turns: Turn[];
  outline: SemanticRevision | null;
  revisions: SemanticRevision[];
  recordCount: number;
  lastSeq: number;
};

export type ThreadResponse = ThreadPayload | {
  id: string;
  unchanged: true;
  version: string;
  window: ThreadWindow;
};

export type ObserverJobEvent = {
  seq: number;
  atMs: number;
  elapsedMs: number;
  stage: string;
  current: number;
  total: number;
  detail: string;
};

export type ObserverJob = {
  id: string;
  threadId: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  createdAtMs: number;
  startedAtMs: number | null;
  completedAtMs: number | null;
  lastProgressAtMs: number;
  phase: string;
  current: number;
  total: number;
  currentWindow: number;
  totalWindows: number;
  horizonSeq: number | null;
  detail: string;
  model: string | null;
  effort: string;
  revisions: string[];
  events: ObserverJobEvent[];
  error: string | null;
};

export type EvidenceSelection = {
  threadId: string;
  startSeq: number;
  endSeq: number;
  rationale: string;
};

export type ContextRecord = {
  seq: number;
  threadId: string;
  source: string;
  direction: string;
  method: string | null;
  rawText: string;
  sha256: string;
};

export type InvestigationContext = {
  id: string;
  parentContextId: string | null;
  question: string;
  selections: EvidenceSelection[];
  records: ContextRecord[];
  artifactInputs?: FrozenArtifactInput[];
  projectedPrompt: string;
  coverage: unknown;
  manifestId?: string | null;
  createdAtMs: number;
};

export type ArtifactInputSelection = {
  investigationId: string;
  artifactId: string;
  rationale: string;
};

export type FrozenArtifactInput = ArtifactInputSelection & {
  artifact: InvestigationArtifact;
  sourceContextId: string;
  sourceManifestId: string | null;
  sourceAttemptManifestId: string | null;
  sourceAdoption: Investigation['adoption'];
};

export type Investigation = {
  schemaVersion: number;
  id: string;
  title: string;
  createdAtMs: number;
  contexts: InvestigationContext[];
  currentContextId: string;
  status: 'draft' | 'dispatching' | 'running' | 'completed' | 'failed' | 'unknown' | 'pending' | 'resuming' | 'needs-evidence' | 'cancelled';
  continuation?: InvestigationContinuation | null;
  nativeArtifact?: InvestigationArtifact | null;
  attemptHistory?: InvestigationAttempt[];
  artifactHistory?: InvestigationArtifact[];
  inquiryAdmissionError?: string;
  attempt: InvestigationAttempt | null;
  artifact: InvestigationArtifact | null;
  adoption: null | {
    artifactId: string;
    decision: 'adopt' | 'reject';
    note: string;
    createdAtMs: number;
  };
};

export type InvestigationAttempt = {
    id: string;
    contextId: string;
    status: string;
    source: string | null;
    threadId: string | null;
    turnId: string | null;
    startedAtMs: number;
    timeoutSeconds: number;
    manifestId?: string | null;
    contextRequestName?: string | null;
    error: string | null;
  continuedFrom?: InquiryLineage;
};

export type InvestigationArtifact = {
  id: string;
  text: string;
  outputSeqs: number[];
  contextId: string;
  attemptId: string;
  citations: number[];
  unsupportedCitations: number[];
  artifactCitations?: string[];
  unsupportedArtifactCitations?: string[];
  kind?: string;
  executionEvidence?: 'synthetic' | 'native-observed' | 'unverified';
  nativeArtifactId?: string;
  continuationId?: string;
  evidenceContextId?: string | null;
  continuedFrom?: InquiryLineage;
};

export type InquiryResponse = {
  id: string;
  requestId: string;
  decision: 'offer' | 'refuse' | 'defer';
  note: string;
  status: 'admitted' | 'committed';
  evidenceContext: InvestigationContext | null;
  occurrenceId: string | null;
};

export type InvestigationContinuation = {
  schemaVersion: number;
  id: string;
  attemptId: string;
  origin: 'synthetic-eidos' | 'native-specialist';
  question: string;
  status: 'preparing' | 'pending' | 'resuming' | 'completed' | 'cancelled';
  realizationStatus?: 'ready' | 'failed' | 'completed' | 'cancelled';
  nativeNext?: { status: 'awaiting-admission' | 'dispatched'; contextId: string | null; attemptId: string | null; error?: string };
  cause?: { mode: 'terminal-needs-evidence'; nativeArtifactId: string; nativeEvent: { seq: number; source: string; sha256: string } };
  error: string | null;
  processId: string | null;
  checkpointId: string | null;
  outcomeId: string | null;
  inquiry: null | {
    id: string;
    question: string;
    status: 'pending' | 'deferred' | 'offer' | 'refuse' | 'answered' | 'refused' | 'cancelled';
    responses: InquiryResponse[];
  };
};

export type ManifestObject = { id: string; kind: string; data: unknown; refs: unknown };
export type ContextManifestView = {
  contextId: string;
  manifestId: string | null;
  slots: Array<{
    path: string;
    claims: Array<{ id: string; state: string; boundary: string; facet: string; rationale: string; scope: unknown; content: ManifestObject; evidence: string[] }>;
    gaps: Array<{ id: string; boundary: string; reason: string }>;
    conflicts: unknown[];
  }>;
  changes: Array<{ path: string; before: unknown; after: unknown; operation: string }>;
};
export type ContextLineage = {
  schemaVersion: number;
  error?: string | null;
  contexts: Array<{ contextId: string; manifestId: string | null }>;
  attemptHistory?: Array<ContextLineageAttempt | null>;
  attempt: ContextLineageAttempt | null;
};
export type ContextLineageAttempt = { id: string; manifestId: string | null; requestName: string | null; pin: ManifestObject | null; events: ManifestObject[] };

export type InquiryLineage = { investigationId: string; attemptId: string; continuationId: string; inquiryId: string; responseId: string; decision: 'offer' | 'refuse'; nativeArtifactId: string; evidenceContextId: string | null };
export type InvestigationCapabilities = { nativeExecution: { available: boolean; reason: string; mode: string }; legacyLiveActions?: { available: boolean; reason: string }; specialistInquiry?: { mode: string; interactive: boolean } };

export type WorkbenchExperiment = {
  id: string; investigationId: string; proposalId: string; mode: 'reinterpretation'; evidenceClass: 'recorded' | 'synthetic' | 'unverified';
  baseline: { investigationId: string; contextId: string; artifactId: string; attemptId: string };
  alternative: { investigationId: string; contextId: string }; rationale: string;
  evaluation: { id: string; method: 'context-selection-comparison/v1' | 'context-selection-comparison/v2'; baseline: { recordIds: number[]; recordCount: number; promptBytes: number; artifactIds?: string[]; artifactCount?: number }; alternative: { recordIds: number[]; recordCount: number; promptBytes: number; artifactIds?: string[]; artifactCount?: number }; addedRecordIds: number[]; removedRecordIds: number[]; addedArtifactIds?: string[]; removedArtifactIds?: string[]; changedArtifactIds?: string[]; additionalPromptBytes: number; checks: { sameQuestion: boolean; baselineEvidenceRetained: boolean; baselineArtifactsRetained?: boolean; withinContextBound: boolean }; passes: boolean; modelCalls: 0; measuredModelReasoningImprovement: false; limitations: string[] };
  review: null | { id: string; decision: 'adopt' | 'reject'; rationale: string; actor: string; kind: 'human' | 'synthetic' };
  adoption: null | { id: string; activation: 'not-performed' }; rollback: null | { id: string; rationale: string };
  status: 'evaluated' | 'adopted' | 'rejected' | 'rolled-back';
};
