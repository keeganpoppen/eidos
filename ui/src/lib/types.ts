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
  eventCount: number;
};

export type ThreadPayload = {
  id: string;
  preview: string;
  turns: Turn[];
  outline: SemanticRevision | null;
  revisions: SemanticRevision[];
  recordCount: number;
  lastSeq: number;
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
  projectedPrompt: string;
  coverage: unknown;
  createdAtMs: number;
};

export type Investigation = {
  schemaVersion: number;
  id: string;
  title: string;
  createdAtMs: number;
  contexts: InvestigationContext[];
  currentContextId: string;
  status: 'draft' | 'dispatching' | 'running' | 'completed' | 'failed' | 'unknown';
  attempt: null | {
    id: string;
    contextId: string;
    status: string;
    source: string | null;
    threadId: string | null;
    turnId: string | null;
    startedAtMs: number;
    timeoutSeconds: number;
    error: string | null;
  };
  artifact: null | {
    id: string;
    text: string;
    outputSeqs: number[];
    contextId: string;
    attemptId: string;
    citations: number[];
    unsupportedCitations: number[];
  };
  adoption: null | {
    artifactId: string;
    decision: 'adopt' | 'reject';
    note: string;
    createdAtMs: number;
  };
};
