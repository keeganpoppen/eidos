import type { Investigation, OwnedAttemptControl } from './types';

export type AttemptTarget = { investigationId: string; attemptId: string };
export type AttemptControlState = {
  target: AttemptTarget | null;
  control: OwnedAttemptControl | null;
  reading: boolean;
  sending: boolean;
  pending: boolean;
  error: string;
  notice: string;
};
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;
type StopResult = { investigation: Investigation; control: OwnedAttemptControl };
const key = (target: AttemptTarget) => `nema.attempt-stop.v1.${JSON.stringify([target.investigationId, target.attemptId])}`;
const path = (target: AttemptTarget) => `/api/investigations/${encodeURIComponent(target.investigationId)}/attempts/${encodeURIComponent(target.attemptId)}/control`;
const same = (a: AttemptTarget | null, b: AttemptTarget | null) => a?.investigationId === b?.investigationId && a?.attemptId === b?.attemptId;
const empty = (target: AttemptTarget | null = null): AttemptControlState => ({ target, control: null, reading: false, sending: false, pending: false, error: '', notice: '' });

function control(value: unknown, target: AttemptTarget): OwnedAttemptControl {
  const result = value as OwnedAttemptControl | null;
  if (!result || result.attemptId !== target.attemptId || typeof result.owned !== 'boolean' || typeof result.canCancel !== 'boolean' || (result.canCancel && !result.owned)) {
    throw new Error('Attempt control does not match this exact attempt. Refresh its control status.');
  }
  return { attemptId: result.attemptId, owned: result.owned, canCancel: result.canCancel };
}

/** Control reads are advisory. Only the server's live reservation can stop work.
 * A saved request is an exact retry intent; selecting or reloading never sends it. */
export class AttemptControlClient {
  state: AttemptControlState = empty();
  private generation = 0;
  private readSequence = 0;
  private disposed = false;
  private stops = new Map<string, Promise<StopResult | null>>();
  constructor(private storage: Storage, private changed: (state: AttemptControlState) => void, private fetcher: Fetcher = (url, init) => fetch(url, init)) {}

  private update(patch: Partial<AttemptControlState>) {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.changed(this.state);
  }

  select(target: AttemptTarget | null): void {
    if (this.disposed || same(this.state.target, target)) return;
    this.generation++;
    this.readSequence++;
    this.state = empty(target ? { ...target } : null);
    if (target) {
      try {
        const saved = JSON.parse(this.storage.getItem(key(target)) ?? 'null');
        this.state.pending = !!saved && Object.keys(saved).length === 4 && saved.version === 1 && saved.action === 'cancel' && same(saved, target);
      } catch { /* Invalid retry descriptions never become a request. */ }
      this.state.sending = this.stops.has(key(target));
    }
    this.update({});
  }

  async inspect(): Promise<void> {
    const target = this.state.target;
    if (this.disposed || !target || this.state.sending || this.state.reading) return;
    const generation = this.generation, sequence = ++this.readSequence;
    const current = () => !this.disposed && generation === this.generation && sequence === this.readSequence;
    this.update({ reading: true });
    try {
      const response = await this.fetcher(path(target));
      if (!response.ok) throw new Error('Live control is unavailable. Retry the control check.');
      const value = control(await response.json(), target);
      if (current()) this.update({ control: value, error: this.state.pending ? this.state.error : '' });
    } catch (cause) {
      if (current()) this.update({ control: null, error: cause instanceof Error ? cause.message : String(cause) });
    } finally { if (current()) this.update({ reading: false }); }
  }

  cancel(): Promise<StopResult | null> {
    const target = this.state.target;
    if (this.disposed || !target) return Promise.resolve(null);
    const existing = this.stops.get(key(target));
    if (existing) return existing;
    if (!this.state.pending && !this.state.control?.canCancel) return Promise.resolve(null);
    try {
      this.storage.setItem(key(target), JSON.stringify({ version: 1, ...target, action: 'cancel' }));
    } catch {
      this.update({ error: 'Could not preserve the stop request. No cancellation was sent.' });
      return Promise.resolve(null);
    }
    this.readSequence++; // A read started before cancellation cannot revive its control.
    this.update({ sending: true, pending: true, reading: false, control: null, error: '', notice: '' });
    const request = this.send(target).finally(() => {
      this.stops.delete(key(target));
      if (!this.disposed && same(this.state.target, target)) this.update({ sending: false });
    });
    this.stops.set(key(target), request);
    return request;
  }

  private async send(target: AttemptTarget): Promise<StopResult | null> {
    const current = () => !this.disposed && same(this.state.target, target);
    try {
      const response = await this.fetcher(path(target), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action: 'cancel' }) });
      if (!response.ok) {
        if ([404, 409].includes(response.status)) {
          this.storage.removeItem(key(target));
          if (current()) this.update({ pending: false });
          throw new Error('This exact attempt is no longer available for control. No different attempt was selected.');
        }
        throw new Error('The stop reply was not confirmed. Retry this same attempt.');
      }
      const value: StopResult = await response.json();
      value.control = control(value.control, target);
      if (value.investigation?.id !== target.investigationId || value.investigation.attempt?.id !== target.attemptId || value.control.canCancel) {
        throw new Error('The stop reply does not confirm this exact attempt. Retry this same attempt.');
      }
      this.storage.removeItem(key(target));
      if (current()) this.update({ control: value.control, pending: false, notice: value.control.owned ? 'Local stop acknowledged. The recorded outcome remains separate.' : 'No live owner is available in this app. Recorded evidence is still inspectable.' });
      return value;
    } catch (cause) {
      if (current()) this.update({ error: cause instanceof Error ? cause.message : String(cause) });
      return null;
    }
  }

  dispose(): void { this.disposed = true; this.generation++; this.readSequence++; }
}
