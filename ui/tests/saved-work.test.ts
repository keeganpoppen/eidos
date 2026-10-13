import { describe, expect, test } from 'bun:test';
import { SavedWorkClient, catalogChoices, catalogKey, catalogSelection, type ArtifactSource, type ResultSummary, type WorkSummary } from '../src/lib/saved-work';
import { makeReflectionFixture } from '../src/lib/reflection-fixture';
import { resolveTarget, artifacts } from '../src/lib/comparison';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => resolve = done);
  return { promise, resolve };
}
const owner = () => structuredClone(makeReflectionFixture('supplied').investigations[0]);
const summary = (id: string): WorkSummary => ({ id, title: id, status: 'completed', createdAtMs: 1, currentContextId: 'c', contextCount: 1, artifactCount: 1, attemptStatus: 'completed', hasInquiry: false, version: 'v1' });

describe('bounded saved-work reads', () => {
  test('deduplicates simultaneous catalog consumers and scopes conditional versions to exact query and cursor', async () => {
    const initial = deferred<Response>();
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      if (paths.length === 1) return initial.promise;
      if (path.includes('knownVersion')) return json({ version: 'v1', unchanged: true });
      return json({ version: 'v2', unchanged: false, investigations: [summary('older')], nextCursor: null });
    });
    const left = client.catalog('catalog', 'Mixed title');
    const right = client.catalog('catalog', 'Mixed title');
    expect(paths).toHaveLength(1);
    initial.resolve(json({ version: 'v1', unchanged: false, investigations: [summary('first')], nextCursor: 'older/+' }));
    const first = await left;
    expect(await right).toBe(first);
    expect(await client.catalog('catalog', 'Mixed title')).toBe(first);
    await client.catalog('catalog', 'Mixed title', 'older/+');
    await client.catalog('catalog', 'another title');
    expect(paths[1]).toContain('knownVersion=v1');
    expect(paths[2]).toContain('cursor=older%2F%2B');
    expect(paths[2]).not.toContain('knownVersion');
    expect(paths[3]).not.toContain('knownVersion');
    expect(paths.every((path) => path.includes('limit=20'))).toBe(true);
  });

  test('exact selected results remain in choices outside search pages without becoming newer versions', () => {
    const result: ResultSummary = { investigationId: 'old-owner', investigationTitle: 'Old result', artifactId: 'A1', contextId: 'C1', attemptId: 'T1', createdAtMs: 1 };
    const newer = { ...result, artifactId: 'A2', contextId: 'C2' };
    expect(catalogChoices([newer], result)).toEqual([result, newer]);
    expect(catalogChoices([result, newer], result)).toEqual([result, newer]);
    expect(catalogKey(result)).toBe(JSON.stringify(['old-owner', 'A1']));
    expect(catalogChoices([summary('recent')], summary('older'))[0].id).toBe('older');
  });

  test('retained result selection cannot turn an earlier excerpt into a current search match', () => {
    const old: ResultSummary = { investigationId: 'owner', investigationTitle: 'Review', artifactId: 'A1', contextId: 'C0', attemptId: 'T0', createdAtMs: 1,
      match: { field: 'question', excerpt: 'Why did cancelled preparation resume?' } };
    const newer: ResultSummary = { ...old, artifactId: 'A2', contextId: 'C1', attemptId: 'T1', match: { field: 'result', excerpt: 'A different result.' } };
    expect(catalogSelection([newer], catalogKey(old), old)).toEqual({ item: old, onPage: false });
    expect(catalogSelection([], catalogKey(old), old)).toEqual({ item: old, onPage: false });
    const currentMatch: ResultSummary = { ...old, match: { field: 'result', excerpt: 'The stopped claim must survive.' } };
    expect(catalogSelection([currentMatch], catalogKey(old), old)).toEqual({ item: currentMatch, onPage: true });
    expect(old.match?.field).toBe('question');
  });

  test('a reused result key cannot silently change a retained context or attempt pin', () => {
    const old: ResultSummary = { investigationId: 'owner', investigationTitle: 'Review', artifactId: 'A1', contextId: 'C0', attemptId: 'T0', createdAtMs: 1 };
    for (const changed of [{ ...old, contextId: 'C1' }, { ...old, attemptId: 'T1' }]) {
      expect(catalogSelection([changed], catalogKey(old), old)).toEqual({ item: old, onPage: false });
    }
    expect(catalogSelection([old], '', old)).toEqual({ item: undefined, onPage: false });
  });

  test('artifact search preserves exact match envelopes and scopes cached excerpts to the query', async () => {
    const historical: ResultSummary = { investigationId: 'owner', investigationTitle: 'Review', artifactId: 'A1', contextId: 'C0', attemptId: 'T0', createdAtMs: 1,
      match: { field: 'result', excerpt: '<img src=x onerror=alert(1)> Straße %_ claim' } };
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      if (path.includes('knownVersion')) return json({ version: 'matched-v1', unchanged: true });
      if (path.includes('different')) return json({ version: 'empty-v1', unchanged: false, artifacts: [], nextCursor: null });
      return json({ version: 'matched-v1', unchanged: false, artifacts: [historical], nextCursor: null });
    });
    const hit = await client.catalog('artifacts', 'STRASSE %_');
    expect(hit.items).toEqual([historical]);
    expect(await client.catalog('artifacts', 'STRASSE %_')).toBe(hit);
    expect((await client.catalog('artifacts', 'different')).items).toEqual([]);
    expect(paths[0]).toContain('q=STRASSE+%25_');
    expect(paths[1]).toContain('knownVersion=matched-v1');
    expect(paths[2]).not.toContain('knownVersion');
  });

  test('remembered owner is loaded directly and unchanged polls preserve object and historical pins', async () => {
    const work = owner();
    const pin = { investigationId: work.id, contextId: work.nativeArtifact!.contextId, artifactId: work.nativeArtifact!.id };
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      return paths.length === 1 ? json({ version: 'old-v1', unchanged: false, investigation: work }) : json({ version: 'old-v1', unchanged: true });
    });
    const first = await client.view(work.id);
    const second = await client.view(work.id);
    expect(paths[0]).toBe(`/api/investigations/${encodeURIComponent(work.id)}/view`);
    expect(paths[1]).toContain('knownVersion=old-v1');
    expect(second).toBe(first);
    expect(resolveTarget([second], pin).artifact?.id).toBe(pin.artifactId);
    expect(paths.some((path) => path.includes('/catalog'))).toBe(false);
  });

  test('a save supersedes an older in-flight poll, including its stale conditional version', async () => {
    const old = owner();
    const saved = { ...old, title: 'Saved while poll was pending' };
    const late = deferred<Response>();
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => {
      paths.push(path);
      return paths.length === 1 ? late.promise : json({ version: 'v2', unchanged: false, investigation: saved });
    });
    const poll = client.view(old.id);
    client.remember(saved);
    late.resolve(json({ version: 'v1', unchanged: false, investigation: old }));
    expect(await poll).toBe(saved);
    expect((await client.view(old.id)).title).toBe(saved.title);
    expect(paths[1]).not.toContain('knownVersion');
  });

  test('stale poll errors cannot replace a successful mutation, and failed requests remain retryable', async () => {
    const old = owner();
    const late = deferred<Response>();
    let count = 0;
    const client = new SavedWorkClient(async () => ++count === 1 ? late.promise : json({ version: 'v2', unchanged: false, investigation: old }));
    const poll = client.view(old.id);
    client.remember(old);
    late.resolve(json({ error: 'old poll failed' }, 503));
    expect(await poll).toBe(old);
    await client.view(old.id);
    expect(count).toBe(2);
  });

  test('loads only the pinned source endpoint, preserves unknown fields, and rejects mismatched ownership/context/attempt', async () => {
    const work = owner();
    const artifact = artifacts(work)[0];
    const context = work.contexts.find((item) => item.id === artifact.contextId)!;
    const source: ArtifactSource = { version: 'v1', investigationId: work.id, investigationTitle: work.title, artifact, context, attempt: work.attempt!, adoption: null };
    const paths: string[] = [];
    const client = new SavedWorkClient(async (path) => { paths.push(path); return json(source); });
    const pin = { investigationId: work.id, artifactId: artifact.id, contextId: artifact.contextId };
    expect(await client.source(pin)).toEqual(source);
    expect(paths[0]).toBe(`/api/investigations/${encodeURIComponent(work.id)}/artifacts/${encodeURIComponent(artifact.id)}/source?contextId=${encodeURIComponent(artifact.contextId)}`);
    for (const wrong of [ { ...source, investigationId: 'another-owner' }, { ...source, context: { ...context, id: 'new-context' } }, { ...source, attempt: { ...source.attempt, id: 'new-attempt' } } ]) {
      await expect(new SavedWorkClient(async () => json(wrong)).source(pin)).rejects.toThrow('No newer result has been substituted');
    }
    await expect(new SavedWorkClient(async () => json({ error: 'Exact source missing' }, 404)).source(pin)).rejects.toThrow('Exact source missing');
  });
});
