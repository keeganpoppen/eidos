import type { Investigation, InvestigationContext } from './types';

export const CONTEXT_INPUT_DRAFT_KEY = 'nema.context-input-draft.v1';
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;
export type InputSource = { investigationId: string; contextId: string };
export type StagedInputDraft = {
  version: 1;
  source: InputSource & { title: string; recordCount: number; artifactCount: number };
  title: string;
  question: string;
  request: string | null;
  saved: { investigationId: string; contextId: string } | null;
  refusal: { status: 400 | 404 | 409; message: string } | null;
};
export type InputDraftState = { draft: StagedInputDraft | null; sending: boolean; error: string };
const empty = (): InputDraftState => ({ draft: null, sending: false, error: '' });
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const shape = (value: unknown, keys: string[]): value is Record<string, unknown> => object(value) && Object.keys(value).sort().join('|') === keys.sort().join('|');
const text = (value: unknown, maximum: number, blank = false): value is string => typeof value === 'string' && value.length <= maximum && (blank || !!value.trim());
const source = (value: unknown): value is InputSource => shape(value, ['investigationId', 'contextId']) && text(value.investigationId, 200) && text(value.contextId, 200);

/** Local storage contains references and authored form text, never copied source
 * payloads. Restoring an entry never sends it or promotes it into authority. */
export function readInputDraft(raw: string): StagedInputDraft {
  if (raw.length > 65536) throw Error('Saved staged creation exceeds its limit.');
  const value = JSON.parse(raw);
  if (!shape(value, ['version', 'source', 'title', 'question', 'request', 'saved', 'refusal']) || value.version !== 1
      || !shape(value.source, ['investigationId', 'contextId', 'title', 'recordCount', 'artifactCount'])
      || !source({ investigationId: value.source.investigationId, contextId: value.source.contextId })
      || !text(value.source.title, 200) || !Number.isInteger(value.source.recordCount) || (value.source.recordCount as number) < 0 || (value.source.recordCount as number) > 256
      || !Number.isInteger(value.source.artifactCount) || (value.source.artifactCount as number) < 0 || (value.source.artifactCount as number) > 32
      || !text(value.title, 200, true) || !text(value.question, 16000, true)) throw Error('Saved staged creation is unavailable. Its recovery entry was retained.');
  if (value.request !== null) {
    if (!text(value.request, 40000)) throw Error('Invalid saved creation request.');
    const request = JSON.parse(value.request);
    if (!shape(request, ['requestId', 'title', 'question', 'inputSource']) || !text(request.requestId, 200)
        || !text(request.title, 200) || !text(request.question, 16000) || !source(request.inputSource)
        || request.title !== value.title || request.question !== value.question
        || request.inputSource.investigationId !== value.source.investigationId || request.inputSource.contextId !== value.source.contextId) throw Error('Saved creation request does not match its staged inputs.');
  }
  if (value.saved !== null && (!value.request || !source(value.saved))) throw Error('Invalid saved draft reference.');
  if (value.refusal !== null && (!value.request || value.saved || !shape(value.refusal, ['status', 'message'])
      || ![400, 404, 409].includes(value.refusal.status as number) || !text(value.refusal.message, 4000))) throw Error('Invalid saved refusal.');
  return value as StagedInputDraft;
}

export function createdInputContext(work: Investigation, draft: StagedInputDraft): InvestigationContext {
  if (!work || !text(work.id, 200) || work.title !== draft.title || !Array.isArray(work.contexts)) throw Error('Created draft receipt is unavailable. Retry this exact creation.');
  const matches = work.contexts.filter(context => context.parentContextId === null && context.question === draft.question
    && context.inputOrigin?.version === 1 && context.inputOrigin.kind === 'historical-context-inputs'
    && context.inputOrigin.investigationId === draft.source.investigationId && context.inputOrigin.contextId === draft.source.contextId);
  if (matches.length !== 1 || !text(matches[0].id, 200)) throw Error('Created draft receipt does not identify one exact initial context. Retry this exact creation.');
  if (draft.saved && (draft.saved.investigationId !== work.id || draft.saved.contextId !== matches[0].id)) throw Error('The saved draft no longer matches its exact created context.');
  return matches[0];
}

export function inputDraftOpenDecision(busy: boolean, pendingSave: boolean, unsaved: boolean, confirmed: boolean): 'blocked' | 'confirm' | 'open' {
  return busy || pendingSave ? 'blocked' : unsaved && !confirmed ? 'confirm' : 'open';
}

export class ContextInputDraftClient {
  state: InputDraftState = empty();
  private raw: string | null = null;
  private disposed = false;
  private unavailable = false;
  private sending: Promise<void> | null = null;
  constructor(private storage: Storage, private changed: (state: InputDraftState) => void,
    private fetcher: Fetcher = (url, init) => fetch(url, init), private requestId: () => string = () => crypto.randomUUID()) {}

  private update(patch: Partial<InputDraftState>) {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.changed(this.state);
  }
  restore(): void {
    try {
      this.raw = this.storage.getItem(CONTEXT_INPUT_DRAFT_KEY);
      this.update({ draft: this.raw === null ? null : readInputDraft(this.raw), error: '' });
    } catch (error) {
      this.unavailable = true;
      this.update({ error: error instanceof Error ? error.message : 'Saved staged creation is unavailable.' });
    }
  }
  private persist(draft: StagedInputDraft | null): boolean {
    try {
      if (this.unavailable || this.storage.getItem(CONTEXT_INPUT_DRAFT_KEY) !== this.raw) throw Error('Staged creation changed in another view. Reload before continuing.');
      const raw = draft === null ? null : JSON.stringify(draft);
      if (raw !== null) { readInputDraft(raw); this.storage.setItem(CONTEXT_INPUT_DRAFT_KEY, raw); }
      else this.storage.removeItem(CONTEXT_INPUT_DRAFT_KEY);
      this.raw = raw;
      this.update({ draft, error: '' });
      return true;
    } catch (error) {
      this.update({ error: error instanceof Error ? error.message : 'Could not preserve the staged creation. No new request was sent.' });
      return false;
    }
  }
  stage(work: Investigation, context: InvestigationContext): boolean {
    if (this.disposed || this.state.draft || this.state.sending || !work.contexts.some(c => c.id === context.id)) return false;
    return this.persist({ version: 1, source: { investigationId: work.id, contextId: context.id, title: work.title,
      recordCount: context.records.length, artifactCount: context.artifactInputs?.length ?? 0 },
      title: `New question: ${work.title}`.slice(0, 200), question: '', request: null, saved: null, refusal: null });
  }
  edit(field: 'title' | 'question', value: string): void {
    const draft = this.state.draft;
    if (!this.disposed && draft && !draft.request && !this.state.sending) this.persist({ ...draft, [field]: value });
  }
  cancel(): void {
    const draft = this.state.draft;
    if (!this.disposed && !this.state.sending && (!draft?.request || draft.saved || draft.refusal)) this.persist(null);
  }
  create(): Promise<void> {
    if (this.sending) return this.sending;
    const draft = this.state.draft;
    if (this.disposed || !draft || draft.saved || !text(draft.title, 200) || !text(draft.question, 16000)) return Promise.resolve();
    const request = draft.request ?? JSON.stringify({ requestId: this.requestId(), title: draft.title, question: draft.question,
      inputSource: { investigationId: draft.source.investigationId, contextId: draft.source.contextId } });
    if (!this.persist({ ...draft, request, refusal: null })) return Promise.resolve();
    const sent = this.state.draft!, expected = this.raw;
    this.update({ sending: true });
    this.sending = this.send(sent, expected).finally(() => {
      this.sending = null;
      this.update({ sending: false });
    });
    return this.sending;
  }
  private async send(draft: StagedInputDraft, expected: string | null): Promise<void> {
    try {
      const response = await this.fetcher('/api/investigations', { method: 'POST', headers: { 'content-type': 'application/json' }, body: draft.request! });
      const work = await response.json();
      if (!response.ok) {
        const message = typeof work?.error === 'string' && work.error.trim() ? work.error.slice(0, 4000) : 'Draft creation was not confirmed. Retry this same creation.';
        if ([400, 404, 409].includes(response.status)) this.persist({ ...draft,
          refusal: { status: response.status as 400 | 404 | 409, message } });
        else throw Error(message);
        return;
      }
      const context = createdInputContext(work, draft);
      if (this.storage.getItem(CONTEXT_INPUT_DRAFT_KEY) !== expected) throw Error('A later staged creation is present. This reply did not replace it.');
      this.persist({ ...draft, saved: { investigationId: work.id, contextId: context.id } });
    } catch (error) {
      this.update({ error: error instanceof Error ? error.message : 'Draft creation was not confirmed. Retry this same creation.' });
    }
  }
  dispose(): void { this.disposed = true; }
}
