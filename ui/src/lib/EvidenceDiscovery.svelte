<script lang="ts">
  import { onDestroy } from 'svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import { EvidenceDiscoveryClient, evidenceFieldLabel, type EvidenceDiscoveryState } from './evidence-discovery';
  import type { EvidenceHit, ThreadSummary } from './types';
  import type { EvidenceAddition } from './evidence-selection';

  let { active, navigationKey, threads, addDisabled, addReason, onAdd, onShow }: {
    active: boolean; navigationKey: string; threads: ThreadSummary[]; addDisabled: boolean; addReason: string;
    onAdd: (addition: EvidenceAddition) => boolean; onShow: (hit: EvidenceHit) => void;
  } = $props();
  let query = $state('');
  let threadId = $state('');
  let notice = $state('');
  let discovery = $state<EvidenceDiscoveryState>({ q: '', threadId: '', page: null, previous: [], cursor: '', loading: false, inspecting: null, source: null, error: '', refreshRequired: false });
  const client = new EvidenceDiscoveryClient(value => discovery = value);
  $effect(() => { void navigationKey; client.navigate(active); });
  onDestroy(() => client.dispose());

  function edited() { notice = ''; client.clearSearch(); }
  function add() {
    const source = client.inspected();
    if (!active || addDisabled || !source) return;
    if (onAdd({ threadId: source.hit.threadId, recordSeqs: source.records.map(record => record.seq) })) notice = 'Exact source references added. Save the working draft to freeze its source bytes.';
  }
  function show() { const source = client.inspected(); if (active && source) onShow(source.hit); }
</script>

<section class="evidence-discovery" aria-label="Find recorded evidence">
  <h3>Find recorded evidence</h3>
  <p>Search supplied text, recorded messages, exposed reasoning, commands, output and file paths. Raw fields, control records and private evidence are outside this search.</p>
  <form onsubmit={event => { event.preventDefault(); notice = ''; void client.search(query, threadId); }}>
    <label for="evidence-search-query">Remembered words or phrase</label>
    <input id="evidence-search-query" type="search" maxlength="200" bind:value={query} oninput={edited} placeholder="Find a decision or counterexample" />
    <label for="evidence-search-thread">Recorded history</label>
    <select id="evidence-search-thread" bind:value={threadId} onchange={edited}>
      <option value="">All recorded sources</option>
      {#each threads as thread (thread.thread_id)}<option value={thread.thread_id}>{thread.preview || thread.thread_id}</option>{/each}
    </select>
    <button class="work-secondary" type="submit" disabled={!active || !query.trim() || discovery.loading}>Search history</button>
  </form>
  {#if discovery.q}<p class="search-query">Results for “{discovery.q}”{discovery.threadId ? ` in ${discovery.threadId}` : ' across recorded threads'}.</p>{/if}
  {#if discovery.loading}<p role="status">Searching recorded evidence…</p>{/if}
  {#if discovery.error}<p class="work-error" role="alert">{discovery.error}</p>{/if}
  {#if discovery.refreshRequired}<p class="work-notice">The recorded source changed. Refresh this search before inspecting or adding a match.</p>{/if}
  {#if discovery.q && !discovery.loading}<button class="work-secondary" onclick={() => { notice = ''; void client.refresh(); }}>Refresh search</button>{/if}
  {#if discovery.page}
    <p class="search-count" role="status">Page {discovery.previous.length + 1} · {discovery.page.hits.length} {discovery.page.hits.length === 1 ? 'match' : 'matches'}{discovery.page.nextCursor ? ' · more available' : ''}</p>
    {#if !discovery.page.hits.length}<p>No matching text in the eligible recorded fields.</p>{/if}
    <ol class="evidence-hits">
      {#each discovery.page.hits as hit (hit.id)}
        <li data-evidence-hit-id={hit.id} data-evidence-field={hit.field}>
          <strong>{evidenceFieldLabel(hit.field)}</strong>
          <p class="evidence-excerpt">{hit.excerpt}</p>
          <p class="object-ref">{hit.threadId}<br />Turn {hit.turnId}{hit.itemId ? ` · item ${hit.itemId}` : ''}<br />Records {hit.recordSeqs.join(', ')}</p>
          <button class="work-secondary" disabled={!active || !!discovery.inspecting || discovery.refreshRequired} onclick={() => { notice = ''; void client.inspect(hit); }}>{discovery.inspecting === hit.id ? 'Inspecting source…' : 'Inspect source'}</button>
        </li>
      {/each}
    </ol>
    <nav aria-label="Evidence matches pages">
      <button class="work-secondary" disabled={!active || discovery.loading || discovery.refreshRequired || !discovery.previous.length} onclick={() => { notice = ''; void client.move(false); }}>Previous matches</button>
      <button class="work-secondary" disabled={!active || discovery.loading || discovery.refreshRequired || !discovery.page.nextCursor} onclick={() => { notice = ''; void client.move(true); }}>Next matches</button>
    </nav>
  {/if}
  {#if discovery.source}
    <section class="evidence-source" aria-label="Exact matched source" data-inspected-evidence-hit={discovery.source.hit.id}>
      <h4>Exact matched source</h4>
      <p>{evidenceFieldLabel(discovery.source.hit.field)} · {discovery.source.records.length} source {discovery.source.records.length === 1 ? 'record' : 'records'}</p>
      <p class="object-ref">{discovery.source.hit.threadId}<br />Hit version {discovery.source.hit.version}</p>
      <p>These are the record bytes read for this hit version. Add stages their exact references; saving the working draft freezes source bytes then. Surrounding history may show later updates.</p>
      {#each discovery.source.records as record (record.seq)}
        <article data-evidence-record-seq={record.seq}>
          {#if record.localEvidence}
            <EvidenceRecord {record} />
          {:else}
          <p class="object-ref">Record {record.seq} · {record.method ?? record.direction}<br />{record.source} · {record.direction}<br />SHA-256 {record.sha256}</p>
          <details><summary>Original record · seq {record.seq}</summary><pre>{record.rawText}</pre></details>
          {/if}
        </article>
      {/each}
      <button class="work-secondary" disabled={!active || discovery.refreshRequired} onclick={show}>Show in history</button>
      <button class="work-primary" disabled={!active || addDisabled || discovery.refreshRequired} onclick={add}>Add these source records</button>
      {#if addReason}<p class="work-notice">{addReason}</p>{/if}
    </section>
  {/if}
  {#if notice}<p class="work-notice" role="status">{notice}</p>{/if}
</section>

<style>
  .evidence-discovery { min-width:0; overflow-wrap:anywhere; }
  h3 { margin:0 0 12px; font-size:18px; }
  p { font-size:13px; line-height:1.5; }
  label { display:block; margin:12px 0 6px; font-size:13px; }
  input,select { box-sizing:border-box; width:100%; min-width:0; max-width:100%; padding:9px; border:1px solid var(--line-dark); border-radius:2px; font:inherit; font-size:14px; color:var(--ink); background:var(--paper); }
  button { margin:10px 8px 0 0; max-width:100%; white-space:normal; }
  .object-ref { font:11px/1.5 monospace; color:var(--muted); overflow-wrap:anywhere; }
  .evidence-hits { padding:0; list-style:none; }
  .evidence-hits li { margin:16px 0; border-left:2px solid var(--line-dark); padding-left:10px; }
  .evidence-excerpt { white-space:pre-wrap; }
  .evidence-source { padding:12px; border:1px solid var(--line); }
  .evidence-source article { margin-block:14px; }
  summary { cursor:pointer; font-size:13px; }
  pre { max-height:390px; max-width:100%; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; padding:10px; background:var(--code); font:12px/1.5 monospace; }
  nav { display:flex; flex-wrap:wrap; }
</style>
