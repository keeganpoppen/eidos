<script lang="ts">
  import { onMount } from 'svelte';
  import { HistoryImportClient, emptyImportState } from './history-import';
  let { open, navigation, onClose, onFind }: {
    open: boolean; navigation: string; onClose: () => void; onFind: () => void;
  } = $props();
  let dialog: HTMLDialogElement;
  let client = $state<HistoryImportClient | null>(null);
  let view = $state(emptyImportState());
  const busy = $derived(view.sending || view.checking);
  onMount(() => {
    const storage = { getItem: (key: string) => localStorage.getItem(key), setItem: (key: string, value: string) => localStorage.setItem(key, value), removeItem: (key: string) => localStorage.removeItem(key) };
    client = new HistoryImportClient(storage, next => view = next);
    client.restore();
    return () => client?.dispose();
  });
  $effect(() => {
    // Existing source/aperture navigation invalidates unfinished file previews.
    void navigation;
    client?.navigate(open);
    if (dialog) {
      if (open && !dialog.open) dialog.showModal();
      else if (!open && dialog.open) dialog.close();
    }
  });
</script>

<dialog bind:this={dialog} oncancel={event => { event.preventDefault(); onClose(); }} aria-labelledby="history-import-title">
  <section class="history-import" aria-label="Import history">
    <header>
      <h2 id="history-import-title">Import history</h2>
      <button class="work-secondary" onclick={onClose}>Close import</button>
    </header>
    <p>Choose a recorded app-server JSONL file to review before adding it to this workbench. Your investigation draft stays separate.</p>
    <p class="muted">One JSON object per line, UTF-8, one direction for the whole file. Up to 8 MiB, 20,000 physical lines and 512 KiB per line. Other export formats are not converted.</p>

    {#if view.unavailable}
      <p class="notice">The existing recovery entry was retained. Reload after resolving its unavailable or changed metadata; no new import can replace it here.</p>
    {:else if view.receipt}
      {@const receipt = view.receipt}
      <section class="receipt" data-import-receipt={receipt.id} aria-label="Confirmed import receipt">
        <h3>Import confirmed</h3>
        <p role="status">{receipt.recordCount} {receipt.recordCount === 1 ? 'record was' : 'records were'} committed from <strong>{receipt.fileName}</strong>.</p>
        <p>{receipt.summary.threadCount} {receipt.summary.threadCount === 1 ? 'thread' : 'threads'} · {receipt.summary.discoverableFieldCount} searchable text {receipt.summary.discoverableFieldCount === 1 ? 'field' : 'fields'} in this file</p>
        <p class="muted">These are counts recorded at import. This receipt does not establish that every source record is still available.</p>
        <p class="object-ref" data-import-request-id={receipt.requestId}>Request {receipt.requestId}<br />Import {receipt.id}</p>
        <details><summary>File identity and receipt</summary>
          <dl>
            <dt>Original file</dt><dd>{receipt.byteLength} bytes · SHA-256 {receipt.fileSha256}</dd>
            <dt>Origin label</dt><dd>{receipt.source}</dd>
            <dt>Direction</dt><dd>{receipt.direction}</dd>
            <dt>Isolated capture</dt><dd>{receipt.captureSource}</dd>
            <dt>Review version</dt><dd>{receipt.parserVersion} · {receipt.discoveryScope}</dd>
            <dt>Physical lines</dt><dd>{receipt.physicalLineCount}, including {receipt.blankLineCount} blank lines</dd>
          </dl>
        </details>
        <div class="actions">
          <button class="work-primary" onclick={onFind}>Find imported evidence</button>
          <button class="work-secondary" disabled={busy} onclick={() => client?.checkReceipt()}>Check import receipt</button>
          <button class="work-secondary" disabled={busy} onclick={() => client?.startAnother()}>Start another import</button>
        </div>
      </section>
    {:else}
      {#if view.pending}
        <section class="notice" aria-label="Pending import recovery">
          <h3>Import outcome not confirmed</h3>
          <p>This request identity is retained. Reload never sends it automatically. Check for its receipt, or reselect the exact file bytes to retry the same request.</p>
          <p class="object-ref" data-import-request-id={view.pending.requestId}>Request {view.pending.requestId}<br />{view.pending.fileName} · {view.pending.byteLength} bytes<br />SHA-256 {view.pending.fileSha256}</p>
          <button class="work-secondary" disabled={busy} onclick={() => client?.checkReceipt()}>{view.checking ? 'Checking receipt…' : 'Check import receipt'}</button>
        </section>
      {/if}
      <label for="history-import-source">Origin label</label>
      <input id="history-import-source" maxlength="256" value={view.source} disabled={!!view.pending || busy} oninput={event => client?.edit('source', event.currentTarget.value)} />
      <label for="history-import-direction">Recorded direction</label>
      <select id="history-import-direction" value={view.direction} disabled={!!view.pending || busy} onchange={event => client?.edit('direction', event.currentTarget.value)}>
        <option value="appserver_to_client">App-server → client</option>
        <option value="client_to_appserver">Client → app-server</option>
      </select>
      <p class="muted">The origin label describes the file; each import receives its own capture identity. Files overlapping existing thread IDs are refused. No direction is inferred.</p>
      <label for="history-import-file">{view.pending ? 'Reselect the same file' : 'JSONL file'}</label>
      <input id="history-import-file" type="file" accept=".jsonl,.ndjson,application/x-ndjson" disabled={busy} onchange={event => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = '';
        if (file) void client?.choose(file);
      }} />
      {#if view.reading}<p role="status">Reading and checking file identity…</p>
      {:else if view.hasFile}<p class="chosen-file">Selected {view.fileName} · {view.byteLength} bytes{view.pending ? ' · exact bytes match' : ''}</p>{/if}
      {#if view.pending}
        <button class="work-primary" disabled={busy || !view.hasFile || view.reading} onclick={() => client?.commit()}>{view.sending ? 'Importing…' : 'Retry this import'}</button>
      {:else}
        <button class="work-secondary" disabled={view.previewing || !view.hasFile || view.reading} onclick={() => client?.preview()}>{view.previewing ? 'Reviewing file…' : 'Preview import'}</button>
      {/if}
      {#if view.preview && !view.pending}
        {@const preview = view.preview}
        <section class="preview" data-import-preview={preview.previewFingerprint} aria-label="File preview">
          <h3>File preview</h3>
          <p>{preview.recordCount} {preview.recordCount === 1 ? 'record' : 'records'} · {preview.summary.threadCount} {preview.summary.threadCount === 1 ? 'thread' : 'threads'} · {preview.summary.turnCount} {preview.summary.turnCount === 1 ? 'turn' : 'turns'}</p>
          <p>{preview.summary.discoverableFieldCount} searchable text {preview.summary.discoverableFieldCount === 1 ? 'field' : 'fields'} · {preview.summary.unscopedRecordCount} {preview.summary.unscopedRecordCount === 1 ? 'record' : 'records'} without a thread or turn</p>
          <p class="muted">Preview counts describe this file only. All valid records and unknown fields are retained on import, including records without searchable text. Repeated lines remain separate records.</p>
          <details><summary>Reviewed file identity</summary>
            <p class="object-ref">{preview.byteLength} bytes · {preview.physicalLineCount} physical lines, including {preview.blankLineCount} blank lines<br />SHA-256 {preview.fileSha256}<br />{preview.parserVersion}</p>
          </details>
          {#if !preview.committable}<p class="notice">No supported searchable history was found. This file cannot be imported through this view.</p>{/if}
          <button class="work-primary" disabled={!preview.committable || busy} onclick={() => client?.commit()}>Import reviewed file</button>
        </section>
      {/if}
      {#if view.refusal}
        <section class="notice" aria-label="Refused import">
          <p role="alert">Server refused this request ({view.refusal.status}): {view.refusal.message}</p>
          <p>This response does not establish whether an earlier request took effect. Check its receipt first; the exact request is retained until you deliberately dismiss it.</p>
          <button class="work-secondary" disabled={busy} onclick={() => client?.dismissRefusal()}>Dismiss refused import</button>
        </section>
      {/if}
    {/if}
    {#if view.error}<p class="error" role="alert">{view.error}</p>{/if}
  </section>
</dialog>

<style>
  dialog { width:min(680px,calc(100vw - 24px)); max-height:calc(100dvh - 32px); margin:auto; padding:0; color:var(--ink); background:var(--paper); border:1px solid var(--line-dark); }
  dialog::backdrop { background:rgb(34 34 31 / 35%); }
  .history-import { padding:24px; overflow-wrap:anywhere; }
  header { display:flex; align-items:start; justify-content:space-between; gap:16px; }
  h2 { margin:0; font-size:25px; } h3 { font-size:19px; margin:0 0 10px; }
  p { font-size:14px; line-height:1.5; }
  .muted { color:var(--muted); font-size:13px; }
  label { display:block; margin:16px 0 6px; font-size:14px; }
  input,select { width:100%; min-width:0; max-width:100%; border:1px solid var(--line-dark); padding:9px; background:var(--paper); }
  input[type=file] { font-size:13px; }
  button { white-space:normal; max-width:100%; margin:8px 8px 0 0; }
  header button { margin:0; flex-shrink:0; }
  .notice,.preview,.receipt { margin-block:18px; padding:16px; border:1px solid var(--line); }
  .notice { border-left:2px solid var(--accent); }
  .object-ref,dd { font:11px/1.6 monospace; overflow-wrap:anywhere; }
  dt { margin-top:10px; font-size:13px; } dd { margin:4px 0; }
  summary { cursor:pointer; font-size:13px; }
  .error { color:var(--accent); }
  .actions { display:flex; flex-wrap:wrap; }
  @media(max-width:520px) { .history-import { padding:16px; } .notice,.preview,.receipt { padding:12px; } }
</style>
