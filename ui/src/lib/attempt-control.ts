import type { AttemptSignIn, Investigation, OwnedAttemptControl } from './types';

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
type Clock = { now: () => number; later: (callback: () => void, delay: number) => () => void };
const clock: Clock = { now: () => Date.now(), later: (callback, delay) => {
  const timer = setTimeout(callback, delay);
  return () => clearTimeout(timer);
} };
const key = (target: AttemptTarget) => `nema.attempt-stop.v1.${JSON.stringify([target.investigationId, target.attemptId])}`;
const path = (target: AttemptTarget) => `/api/investigations/${encodeURIComponent(target.investigationId)}/attempts/${encodeURIComponent(target.attemptId)}/control`;
const same = (a: AttemptTarget | null, b: AttemptTarget | null) => a?.investigationId === b?.investigationId && a?.attemptId === b?.attemptId;
const empty = (target: AttemptTarget | null = null): AttemptControlState => ({ target, control: null, reading: false, sending: false, pending: false, error: '', notice: '' });

function signIn(value: unknown, now: number): AttemptSignIn | undefined {
  const result = value as AttemptSignIn | null;
  if (!result || result.verificationUrl !== 'https://auth.openai.com/codex/device'
      || typeof result.userCode !== 'string' || !/^[\x20-\x7e]{1,128}$/.test(result.userCode) || !result.userCode.trim()
      || !Number.isSafeInteger(result.expiresAtMs) || result.expiresAtMs <= now || result.expiresAtMs > 8.64e15) return;
  return { verificationUrl: result.verificationUrl, userCode: result.userCode, expiresAtMs: result.expiresAtMs };
}

function control(value: unknown, target: AttemptTarget, now: number): OwnedAttemptControl {
  const result = value as OwnedAttemptControl | null;
  if (!result || result.attemptId !== target.attemptId || typeof result.owned !== 'boolean' || typeof result.canCancel !== 'boolean' || (result.canCancel && !result.owned)) {
    throw new Error('Attempt control does not match this exact attempt. Refresh its control status.');
  }
  const challenge = result.owned && result.canCancel ? signIn(result.signIn, now) : undefined;
  return { attemptId: result.attemptId, owned: result.owned, canCancel: result.canCancel, ...(challenge ? { signIn: challenge } : {}) };
}

/** Control reads are advisory. Only the server's live reservation can stop work.
 * A saved request is an exact retry intent; selecting or reloading never sends it. */
export class AttemptControlClient {
  state: AttemptControlState = empty();
  private generation = 0;
  private readSequence = 0;
  private disposed = false;
  private stops = new Map<string, Promise<StopResult | null>>();
  private observedChallenges = new Set<string>();
  private retiredChallenges = new Set<string>();
  private clearExpiry?: () => void;
  constructor(private storage: Storage, private changed: (state: AttemptControlState) => void,
    private fetcher: Fetcher = (url, init) => fetch(url, init), private time: Clock = clock) {}

  /** A completed, expired or stopped sign-in cannot return through a late read. */
  retireSignIn(): void {
    const target = this.state.target;
    if (this.disposed || !target) return;
    this.retiredChallenges.add(key(target));
    this.clearExpiry?.();
    this.clearExpiry = undefined;
    if (this.state.control?.signIn) {
      const { signIn: _challenge, ...value } = this.state.control;
      this.update({ control: value });
    }
  }

  private acceptControl(value: OwnedAttemptControl, target: AttemptTarget): OwnedAttemptControl {
    const identity = key(target);
    if (!value.owned || !value.canCancel || this.state.pending || (this.observedChallenges.has(identity) && !value.signIn)) {
      this.retiredChallenges.add(identity);
    }
    if (this.retiredChallenges.has(identity)) {
      const { signIn: _challenge, ...plain } = value;
      value = plain;
    }
    this.clearExpiry?.();
    this.clearExpiry = undefined;
    if (value.signIn) {
      this.observedChallenges.add(identity);
      const expires = value.signIn.expiresAtMs;
      const expire = () => {
        if (this.disposed || !same(this.state.target, target) || this.state.control?.signIn?.expiresAtMs !== expires) return;
        if (expires > this.time.now()) {
          this.clearExpiry = this.time.later(expire, Math.min(expires - this.time.now(), 2_147_483_647));
          return;
        }
        this.retireSignIn();
        this.update({ notice: 'The sign-in time limit has passed. This code is no longer available.' });
      };
      this.clearExpiry = this.time.later(expire, Math.min(expires - this.time.now(), 2_147_483_647));
    }
    return value;
  }

  private update(patch: Partial<AttemptControlState>) {
    this.state = { ...this.state, ...patch };
    if (!this.disposed) this.changed(this.state);
  }

  select(target: AttemptTarget | null): void {
    if (this.disposed || same(this.state.target, target)) return;
    this.clearExpiry?.();
    this.clearExpiry = undefined;
    this.generation++;
    this.readSequence++;
    this.state = empty(target ? { ...target } : null);
    if (target) {
      try {
        const saved = JSON.parse(this.storage.getItem(key(target)) ?? 'null');
        this.state.pending = !!saved && Object.keys(saved).length === 4 && saved.version === 1 && saved.action === 'cancel' && same(saved, target);
      } catch { /* Invalid retry descriptions never become a request. */ }
      this.state.sending = this.stops.has(key(target));
      if (this.state.pending) this.retiredChallenges.add(key(target));
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
      const value = control(await response.json(), target, this.time.now());
      if (current()) this.update({ control: this.acceptControl(value, target), error: this.state.pending ? this.state.error : '' });
    } catch (cause) {
      if (current()) {
        this.clearExpiry?.();
        this.clearExpiry = undefined;
        this.update({ control: null, error: cause instanceof Error ? cause.message : String(cause) });
      }
    } finally { if (current()) this.update({ reading: false }); }
  }

  cancel(): Promise<StopResult | null> {
    const target = this.state.target;
    if (this.disposed || !target) return Promise.resolve(null);
    const existing = this.stops.get(key(target));
    if (existing) return existing;
    if (!this.state.pending && !this.state.control?.canCancel) return Promise.resolve(null);
    this.retireSignIn();
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
      value.control = control(value.control, target, this.time.now());
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

  dispose(): void {
    this.clearExpiry?.();
    this.clearExpiry = undefined;
    this.state = empty();
    this.observedChallenges.clear();
    this.retiredChallenges.clear();
    this.disposed = true; this.generation++; this.readSequence++;
  }
}
