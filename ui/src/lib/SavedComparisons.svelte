<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { resolveTarget, validateEvidenceChain, type Composition } from './comparison';
  import { captureSnapshot, compositionSnapshots, CompositionRequestError, readSnapshotDraft, snapshotDraftKey, supportsBlockFocus, type CompositionSnapshot, type SnapshotSave, type SnapshotSummary } from './composition-snapshots';
  import { savedWork } from './saved-work';
  import type { Investigation } from './types';

  let { composition, active, editing, onOpen, onSaved }: {
    composition: Composition; active: boolean; editing: boolean;
    onOpen: (snapshot: CompositionSnapshot, owners: Investigation[]) => void;
    onSaved: (snapshot: CompositionSnapshot) => void;
  } = $props();
  let title = $state('');
  let pending = $state<SnapshotSave | null>(null);
  let saving = $state(false);
  let saveError = $state('');
  let rejected = $state(false);
  let saved = $state<CompositionSnapshot | null>(null);
  let ready = $state(false);
  let storageError = $state('');
  let browse = $state(false);
  let search = $state('');
  let query = $state('');
  let cursor = $state('');
  let previous = $state<string[]>([]);
  let next = $state<string | null>(null);
  let items = $state<SnapshotSummary[]>([]);
  let selected = $state('');
  let selectedTitle = $state('');
  let loading = $state(false);
  let listError = $state('');
  let loaded = false;
  let listGeneration = 0;
  let previewGeneration = 0;
  let previewing = $state(false);
  let previewError = $state('');
  let preview = $state<CompositionSnapshot | null>(null);
  let owners = $state<Investigation[]>([]);
  let resolutionErrors = $state<string[]>([]);
  let reviewBase = $state('');
  const currentView = $derived(JSON.stringify({ arrangement: composition.arrangement, focus: composition.focus, renderer: composition.focusRendererVersion }));
  const changedAfterReview = $derived(!!preview && reviewBase !== currentView);

  function persist(nextTitle = title, nextPending = pending): boolean {
    try {
      localStorage.setItem(snapshotDraftKey, JSON.stringify({ version: 1, title: nextTitle, pending: nextPending }));
      storageError = ''; return true;
    } catch { storageError = 'Browser storage is unavailable. Save is paused so a lost response can still be retried with its original request.'; return false; }
  }

  async function save() {
    if (saving || !ready) return;
    saveError = ''; rejected = false;
    try {
      if (!pending) {
        const body = captureSnapshot(title, $state.snapshot(composition));
        if (!persist(title, body)) return;
        pending = body;
      }
      // Persist before every send, including a recovered request. Never recapture
      // current arrangement/focus under an earlier request ID.
      if (!persist()) return;
      saving = true;
      const result = await compositionSnapshots.save($state.snapshot(pending));
      saved = result;
      onSaved(result);
      // If clearing local recovery fails, retain the exact request: retry is safe.
      if (persist(title, null)) pending = null;
      if (browse) { cursor = ''; previous = []; await load(); }
    } catch (cause) {
      saveError = cause instanceof Error ? cause.message : String(cause);
      rejected = cause instanceof CompositionRequestError && cause.status >= 400 && cause.status < 500;
    }
    finally { saving = false; }
  }

  async function load() {
    const request = ++listGeneration;
    loading = true; listError = '';
    try {
      const page = await compositionSnapshots.list(query, cursor);
      if (request !== listGeneration) return;
      items = page.compositions; next = page.nextCursor; loaded = true;
    } catch (cause) { if (request === listGeneration) listError = cause instanceof Error ? cause.message : String(cause); }
    finally { if (request === listGeneration) loading = false; }
  }
  function find() { query = search.trim(); cursor = ''; previous = []; next = null; void load(); }
  function move(forward: boolean) {
    if (forward && next) { previous = [...previous, cursor]; cursor = next; }
    else if (!forward && previous.length) { cursor = previous.at(-1)!; previous = previous.slice(0, -1); }
    else return;
    void load();
  }
  function select(id: string) {
    previewGeneration++;
    selected = id; selectedTitle = items.find((item) => item.id === id)?.title ?? id;
    preview = null; previewing = false; previewError = '';
  }
  async function inspect(id = selected) {
    if (!id) return;
    const request = ++previewGeneration;
    browse = true; previewing = true; preview = null; previewError = ''; resolutionErrors = [];
    selected = id;
    const base = currentView;
    try {
      const value = await compositionSnapshots.get(id);
      const ids = [...new Set([value.arrangement.left.investigationId, value.arrangement.right.investigationId, value.focus?.investigationId].filter((item): item is string => !!item))];
      const results = await Promise.allSettled(ids.map((owner) => savedWork.view(owner)));
      if (request !== previewGeneration) return;
      owners = results.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []);
      resolutionErrors = results.flatMap((result, index) => result.status === 'rejected' ? [`${ids[index]}: ${String(result.reason instanceof Error ? result.reason.message : result.reason)}`] : []);
      const chainError = validateEvidenceChain(owners, value.arrangement);
      if (chainError) resolutionErrors = [...resolutionErrors, chainError];
      preview = value; selectedTitle = value.title; reviewBase = base;
    } catch (cause) { if (request === previewGeneration) previewError = cause instanceof Error ? cause.message : String(cause); }
    finally { if (request === previewGeneration) previewing = false; }
  }
  function openPreview() {
    if (!preview || changedAfterReview) return;
    onOpen($state.snapshot(preview), $state.snapshot(owners));
    if (!pending) { title = `${preview.title.slice(0, 155)} copy`; persist(); }
    preview = null;
  }
  onMount(() => {
    try {
      const recovered = readSnapshotDraft(localStorage.getItem(snapshotDraftKey));
      title = recovered.title; pending = recovered.pending; ready = true;
    } catch (cause) { storageError = cause instanceof Error ? cause.message : String(cause); }
    return () => { listGeneration++; previewGeneration++; };
  });
  $effect(() => { if (ready && active && browse) untrack(() => { if (!loaded && !loading) void load(); }); });
</script>

<section class="saved-comparisons" aria-label="Saved comparisons">
  <div class="snapshot-save">
    <div><h3>Save this comparison</h3><p>A named snapshot keeps exact result, context, and focus references for another browser on this server.</p></div>
    <div class="save-controls">
      <label for="composition-title">Comparison name</label>
      <div class="input-row"><input id="composition-title" maxlength="160" value={title} oninput={(event) => { title = event.currentTarget.value; if (ready) persist(); }} disabled={!!pending || saving} placeholder="A question to return to" /><button id="save-comparison" disabled={!ready || !composition.arrangement || !title.trim() || !!pending || saving} onclick={save}>{composition.snapshotId ? 'Save a copy' : 'Save comparison'}</button></div>
      {#if editing}<p class="muted">Saves the applied comparison. Apply your arrangement edits first to include them.</p>{/if}
      {#if composition.snapshotId}<p class="snapshot-ref">Copy source: <button onclick={() => inspect(composition.snapshotId!)}>{composition.snapshotId}</button></p>{/if}
    </div>
  </div>
  {#if pending}<div class="pending-snapshot" role="status"><p>Save awaiting confirmation: <strong>{pending.title}</strong>. Retry uses the same captured comparison, focus, and request, even if this view has changed.</p><button id="retry-comparison-save" disabled={saving || !ready} onclick={save}>{saving ? 'Confirming save…' : 'Retry saved comparison'}</button><details><summary>Captured save references</summary><pre>{JSON.stringify(pending, null, 2)}</pre></details></div>{/if}
  {#if saved}<p class="snapshot-receipt" data-saved-composition-id={saved.id} role="status">Saved “{saved.title}”. <button onclick={() => inspect(saved!.id)}>Preview saved comparison</button></p>{/if}
  {#if saveError}<p class="work-error" role="alert">{saveError} The captured request is retained for retry.</p>{/if}
  {#if rejected && pending}<p>The server rejected this request. Correct the applied arrangement, then <button onclick={() => { if (persist(title, null)) { pending = null; rejected = false; saveError = ''; } }}>Clear rejected save</button> to capture a new request.</p>{/if}
  {#if storageError}<p class="work-error" role="alert">{storageError}</p>{/if}

  <details id="saved-comparisons-browser" bind:open={browse}>
    <summary>Find saved comparisons</summary>
    <form onsubmit={(event) => { event.preventDefault(); find(); }}>
      <label for="composition-search">Search comparison names</label>
      <div class="input-row"><input id="composition-search" type="search" bind:value={search} placeholder="All names" /><button type="submit">Search</button></div>
    </form>
    <label for="saved-composition">Saved comparison</label>
    <select id="saved-composition" value={selected} disabled={loading} onchange={(event) => select(event.currentTarget.value)}>
      <option value="">Choose a saved comparison</option>
      {#if selected && !items.some((item) => item.id === selected)}<option value={selected}>{selectedTitle} · selected outside this page</option>{/if}
      {#each items as item (item.id)}<option value={item.id}>{item.title} · {new Date(item.createdAtMs).toLocaleString()} · {item.id.slice(-8)}</option>{/each}
    </select>
    <nav aria-label="Saved comparison pages"><button disabled={loading || !previous.length} onclick={() => move(false)}>Previous page</button><span role="status">{loading ? 'Loading…' : `Page ${previous.length + 1} · ${items.length} comparisons`}</span><button disabled={loading || !next} onclick={() => move(true)}>Next page</button></nav>
    <button id="preview-comparison" disabled={!selected || previewing} onclick={() => inspect()}>{previewing ? 'Loading exact references…' : 'Preview comparison'}</button>
    {#if listError}<p class="work-error" role="alert">{listError} <button onclick={() => void load()}>Retry list</button></p>{/if}
    {#if previewError}<p class="work-error" role="alert">{previewError} <button onclick={() => inspect()}>Retry preview</button></p>{/if}
    {#if preview}
      <section class="snapshot-preview" data-composition-id={preview.id} aria-label="Saved comparison preview">
        <h4>{preview.title}</h4><p>{preview.arrangement.lens === 'context' ? 'Context and evidence' : 'Returned results'} · {preview.arrangement.layout === 'beside' ? 'side by side' : 'stacked'}{preview.arrangement.intent ? ` · ${preview.arrangement.intent}` : ''}</p>
        <div class="preview-targets">
          {#each ['left', 'right'] as side}
            {@const target = preview.arrangement[side as 'left' | 'right']}
            {@const resolved = resolveTarget(owners, target)}
            <div data-snapshot-side={side}><strong>{side === 'left' ? 'A / Baseline' : 'B / Competing reading'} · {resolved.investigation?.title ?? 'Unavailable investigation'}</strong><p class="snapshot-ref">{target.investigationId}<br />{target.contextId}<br />{target.artifactId ?? 'No result pinned'}</p>
              {#if !resolved.context || (target.artifactId && !resolved.artifact)}<p class="work-notice">This exact source is unavailable. Open retains its reference; edit the arrangement to repair it and save a copy.</p>{/if}
            </div>
          {/each}
        </div>
        {#if preview.focus}<p class="snapshot-ref">Focus: {preview.focus.investigationId}<br />{preview.focus.contextId}<br />{preview.focus.artifactId ?? 'Context record'}{preview.focus.blockId ? ` · ${preview.focus.blockId}` : ''}{preview.focus.seq ? ` · [evidence:${preview.focus.seq}] · ${preview.focus.threadId}` : ''}</p>{:else}<p>No saved evidence focus.</p>{/if}
        {#if !supportsBlockFocus(preview.focus, preview.rendererVersion)}<p class="work-notice" data-unresolved-selector>Passage selector unavailable for renderer {preview.rendererVersion}. Exact result and record references remain; opening will not highlight a passage under the installed parser.</p>{/if}
        {#each resolutionErrors as failure}<p class="work-notice">{failure}</p>{/each}
        {#if preview.copiedFrom}<p class="snapshot-ref">Copied from <button onclick={() => inspect(preview!.copiedFrom!)}>{preview.copiedFrom}</button></p>{/if}
        <details><summary>Exact saved references</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details>
        <p>Open replaces this browser’s applied comparison and focus. Investigation drafts and pending saves stay in place. {editing ? 'Unapplied arrangement edits will be replaced.' : ''}</p>
        {#if changedAfterReview}<p class="work-notice">Your comparison or focus changed after this preview. Preview it again before opening.</p>{/if}
        <button id="open-comparison" disabled={changedAfterReview} onclick={openPreview}>Open this comparison</button>
      </section>
    {/if}
  </details>
</section>

<style>
  .saved-comparisons { min-width:0; border-block:1px solid var(--line); padding:16px 0; margin-bottom:18px; font-size:14px; overflow-wrap:anywhere; }
  .snapshot-save { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  h3 { margin:0; font-size:18px; font-weight:500; } h4 { font-size:20px; margin:0; }
  p { line-height:1.5; margin:8px 0; overflow-wrap:anywhere; }
  label { display:block; font-size:13px; margin:8px 0 4px; }
  .input-row { display:flex; gap:8px; }
  input,select,button { box-sizing:border-box; min-width:0; font:inherit; color:var(--ink); background:var(--paper); border:1px solid var(--line-dark); padding:8px; }
  input { flex:1; width:0; } select { width:100%; max-width:100%; }
  button { cursor:pointer; overflow-wrap:anywhere; } button:disabled { opacity:.5; cursor:default; }
  :is(input,select,button,summary):focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .muted,nav span { color:var(--muted); font-size:13px; }
  nav { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:8px 0; } nav span { flex:1; }
  details { margin-top:12px; } summary { cursor:pointer; } form { max-width:760px; }
  .snapshot-preview,.pending-snapshot { background:var(--selection); border-left:3px solid var(--accent); margin-top:16px; padding:16px; min-width:0; }
  .preview-targets { display:grid; grid-template-columns:1fr 1fr; gap:20px; } .preview-targets > div { min-width:0; }
  .snapshot-ref { font-size:12px; overflow-wrap:anywhere; } .snapshot-ref button { max-width:100%; text-align:left; }
  pre { white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; line-height:1.5; }
  @media(max-width:760px) { .snapshot-save,.preview-targets { grid-template-columns:1fr; gap:8px; } .input-row { flex-wrap:wrap; } .input-row input { flex-basis:160px; } }
</style>
