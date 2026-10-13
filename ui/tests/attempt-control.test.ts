import { describe, expect, test } from 'bun:test';
import { AttemptControlClient, type AttemptControlState } from '../src/lib/attempt-control';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';

const a = { investigationId: 'owner-a', attemptId: 'attempt-a' };
const b = { investigationId: 'owner-b', attemptId: 'attempt-b' };
const live = (target = a) => ({ attemptId: target.attemptId, owned: true, canCancel: true });
const stopped = (target = a, owned = true) => ({ attemptId: target.attemptId, owned, canCancel: false });
const reply = (target = a, owned = true) => {
  const investigation = makeReflectionFixture('supplied').investigations[0];
  investigation.id = target.investigationId;
  investigation.attempt!.id = target.attemptId;
  return { investigation, control: stopped(target, owned) };
};
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}

describe('exact owned-attempt control', () => {
  test('a late ownership read cannot enable controls on another selection', async () => {
    const old = deferred<Response>();
    const client = new AttemptControlClient(memory(), () => {}, path => path.includes('owner-a') ? old.promise : Promise.resolve(response(live(b))));
    client.select(a); const reading = client.inspect();
    client.select(b); await client.inspect();
    old.resolve(response(live(a))); await reading;
    expect(client.state.target).toEqual(b);
    expect(client.state.control).toEqual(live(b));
    expect(client.state.error).toBe('');
  });

  test('polling cannot accumulate control reads while the current request is unresolved', async () => {
    const read = deferred<Response>(); let requests = 0;
    const client = new AttemptControlClient(memory(), () => {}, () => { requests++; return read.promise; });
    client.select(a); const pending = client.inspect();
    await client.inspect(); await client.inspect();
    expect(requests).toBe(1);
    read.resolve(response(live())); await pending;
    expect(client.state.control).toEqual(live());
  });

  test('persisted history cannot authorize a stop', async () => {
    const requests: RequestInit[] = [];
    const client = new AttemptControlClient(memory(), () => {}, async (_path, init) => {
      requests.push(init ?? {}); return response(stopped(a, false));
    });
    client.select(a); await client.inspect();
    expect(await client.cancel()).toBeNull();
    expect(client.state.control).toEqual(stopped(a, false));
    expect(requests).toEqual([{}]);
  });

  test('a failed refresh withdraws previously observed control', async () => {
    let reads = 0, posts = 0;
    const client = new AttemptControlClient(memory(), () => {}, async (_path, init) => {
      if (init) posts++;
      return ++reads === 1 ? response(live()) : response({}, 503);
    });
    client.select(a); await client.inspect(); expect(client.state.control).toEqual(live());
    await client.inspect(); await client.cancel();
    expect(client.state.control).toBeNull(); expect(posts).toBe(0);
  });

  test('lost cancel reply persists only its exact retry and reload performs no POST', async () => {
    const store = memory();
    const calls: Array<{ path: string; init?: RequestInit }> = [];
    const first = new AttemptControlClient(store, () => {}, async (path, init) => {
      calls.push({ path, init });
      if (init?.method === 'POST') throw Error('Authored lost reply');
      return response(live());
    });
    first.select(a); await first.inspect(); await first.cancel();
    expect(first.state.pending).toBe(true);
    expect([...store.values.values()].map(value => JSON.parse(value))).toEqual([{ version: 1, ...a, action: 'cancel' }]);
    first.dispose();
    const reopened = new AttemptControlClient(store, () => {}, async (path, init) => {
      calls.push({ path, init }); return response(init?.method === 'POST' ? reply(a, false) : stopped(a, false));
    });
    reopened.select(a); await reopened.inspect();
    expect(calls.filter(call => call.init?.method === 'POST')).toHaveLength(1);
    expect(reopened.state.pending).toBe(true);
    await reopened.cancel();
    const posts = calls.filter(call => call.init?.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(posts.map(call => call.path)).toEqual(Array(2).fill('/api/investigations/owner-a/attempts/attempt-a/control'));
    expect(posts.map(call => call.init?.body)).toEqual(Array(2).fill('{"action":"cancel"}'));
    expect(reopened.state.pending).toBe(false);
    expect(store.values.size).toBe(0);
  });

  test('an old GET cannot revive control after an acknowledged cancellation', async () => {
    const old = deferred<Response>(); let reads = 0;
    const client = new AttemptControlClient(memory(), () => {}, async (_path, init) => {
      if (init?.method === 'POST') return response(reply());
      return ++reads === 1 ? response(live()) : old.promise;
    });
    client.select(a); await client.inspect();
    const reading = client.inspect(); await client.cancel();
    old.resolve(response(live())); await reading;
    expect(client.state.control).toEqual(stopped());
    expect(client.state.pending).toBe(false);
    expect(client.state.reading).toBe(false);
  });

  test('a failed close retains exact retry even after the owned cancellation latch is set', async () => {
    const store = memory(); const posts: Array<{ path: string; body: BodyInit | null | undefined }> = [];
    const client = new AttemptControlClient(store, () => {}, async (path, init) => {
      if (init?.method === 'POST') {
        posts.push({ path, body: init.body });
        return posts.length === 1 ? response({ error: 'Attempt stop was not confirmed; retry this same attempt.' }, 503) : response(reply());
      }
      return response(posts.length ? stopped() : live());
    });
    client.select(a); await client.inspect(); await client.cancel();
    expect(client.state.pending).toBe(true);
    expect(client.state.error).toBe('The stop reply was not confirmed. Retry this same attempt.');
    await client.inspect();
    expect(client.state.control).toEqual(stopped());
    expect(posts).toHaveLength(1);
    await client.cancel();
    expect(posts).toEqual(Array(2).fill({ path: '/api/investigations/owner-a/attempts/attempt-a/control', body: '{"action":"cancel"}' }));
    expect(client.state.pending).toBe(false);
    expect(store.values.size).toBe(0);
  });

  test('navigation while stopping preserves the original target and independent new controls', async () => {
    const stop = deferred<Response>(); const store = memory(); const calls: string[] = [];
    const client = new AttemptControlClient(store, () => {}, async (path, init) => {
      if (init?.method === 'POST') { calls.push(path); return stop.promise; }
      return response(path.includes('owner-a') ? live(a) : live(b));
    });
    client.select(a); await client.inspect(); const pending = client.cancel();
    expect(client.cancel()).toBe(pending);
    client.select(b); await client.inspect();
    stop.resolve(response(reply(a))); await pending;
    expect(calls).toEqual(['/api/investigations/owner-a/attempts/attempt-a/control']);
    expect(client.state.target).toEqual(b); expect(client.state.control).toEqual(live(b));
    expect(client.state.notice).toBe(''); expect(client.state.sending).toBe(false);
    expect(store.values.size).toBe(0);
  });

  test('returning to an in-flight stop cannot start a duplicate request', async () => {
    const stop = deferred<Response>(); let posts = 0;
    const client = new AttemptControlClient(memory(), () => {}, async (_path, init) => {
      if (init?.method === 'POST') { posts++; return stop.promise; }
      return response(live());
    });
    client.select(a); await client.inspect(); const pending = client.cancel();
    client.select(b); client.select(a);
    expect(client.state.sending).toBe(true); expect(client.state.pending).toBe(true);
    await client.inspect(); expect(client.cancel()).toBe(pending);
    stop.resolve(response(reply())); await pending;
    expect(posts).toBe(1); expect(client.state.control).toEqual(stopped());
  });

  for (const value of [{ ...live(), attemptId: 'another-attempt' }, { ...live(), owned: false }, { ...live(), canCancel: 'yes' }]) {
    test(`rejects a mismatched or contradictory control response ${JSON.stringify(value)}`, async () => {
      let posts = 0;
      const client = new AttemptControlClient(memory(), () => {}, async (_path, init) => { if (init) posts++; return response(value); });
      client.select(a); await client.inspect(); await client.cancel();
      expect(client.state.control).toBeNull(); expect(client.state.error).not.toBe(''); expect(posts).toBe(0);
    });
  }

  test('wrong-owner stop reply keeps the original retry and never returns its investigation', async () => {
    const store = memory();
    const client = new AttemptControlClient(store, () => {}, async (_path, init) => response(init ? { ...reply(b), control: stopped(a) } : live()));
    client.select(a); await client.inspect();
    expect(await client.cancel()).toBeNull(); expect(client.state.pending).toBe(true);
    expect([...store.values.values()].map(value => JSON.parse(value))).toEqual([{ version: 1, ...a, action: 'cancel' }]);
    client.select(b); expect(client.state.pending).toBe(false);
  });

  for (const status of [404, 409]) {
    test(`an unavailable exact attempt clears its retry without selecting a replacement (${status})`, async () => {
      const store = memory();
      const client = new AttemptControlClient(store, () => {}, async (_path, init) => init ? response({}, status) : response(live()));
      client.select(a); await client.inspect(); await client.cancel();
      expect(client.state.target).toEqual(a); expect(client.state.pending).toBe(false);
      expect(client.state.control).toBeNull(); expect(store.values.size).toBe(0);
    });
  }

  test('storage failure sends nothing and leaves unrelated pending-save data untouched', async () => {
    const store = memory(); store.values.set('nema.investigation-draft.v1', '{"pendingRequest":{"id":"save-id","body":"original"}}');
    let posts = 0;
    const client = new AttemptControlClient({ ...store, setItem: () => { throw Error('Storage unavailable'); } }, () => {}, async (_path, init) => {
      if (init) posts++; return response(live());
    });
    client.select(a); await client.inspect(); await client.cancel();
    expect(posts).toBe(0); expect(client.state.pending).toBe(false);
    expect(store.values.get('nema.investigation-draft.v1')).toBe('{"pendingRequest":{"id":"save-id","body":"original"}}');
  });

  test('copied unknown retry fields never create pending control or an automatic request', async () => {
    const store = memory(); store.values.set(`nema.attempt-stop.v1.${JSON.stringify([a.investigationId, a.attemptId])}`, JSON.stringify({ version: 1, ...a, action: 'cancel', authority: 'copied' }));
    let requests = 0;
    const client = new AttemptControlClient(store, () => {}, async () => { requests++; return response(live()); });
    client.select(a); expect(client.state.pending).toBe(false); expect(requests).toBe(0);
  });

  test('disposal prevents late reads from publishing UI state', async () => {
    const read = deferred<Response>(); const states: AttemptControlState[] = [];
    const client = new AttemptControlClient(memory(), state => states.push(state), () => read.promise);
    client.select(a); const pending = client.inspect(); client.dispose(); const count = states.length;
    read.resolve(response(live())); await pending;
    expect(states).toHaveLength(count); expect(await client.cancel()).toBeNull();
  });
});
