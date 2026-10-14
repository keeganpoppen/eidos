<script lang="ts">
  import { onMount } from 'svelte';
  import { SuppliedTextClient, emptyTextState, type TextReceipt } from './supplied-text';
  let { open, navigation, onClose, onOpen, onFind }: { open: boolean; navigation: string; onClose: () => void; onOpen: (receipt: TextReceipt) => void; onFind: () => void } = $props();
  let dialog: HTMLDialogElement;
  let client = $state<SuppliedTextClient | null>(null);
  let view = $state(emptyTextState());
  const busy = $derived(view.sending || view.checking || view.downloading);
  onMount(() => {
    client = new SuppliedTextClient({ getItem: key => localStorage.getItem(key), setItem: (key, value) => localStorage.setItem(key, value), removeItem: key => localStorage.removeItem(key) }, value => view = value);
    client.restore();
    return () => client?.dispose();
  });
  $effect(() => { void navigation; client?.navigate(open); if (dialog) { if (open && !dialog.open) dialog.showModal(); else if (!open && dialog.open) dialog.close(); } });
  function close() { client?.navigate(false); onClose(); }
  function openSource() { const receipt = view.receipt; if (receipt && client?.canUse(receipt)) onOpen(receipt); }
  function find() { const receipt = view.receipt; if (receipt && client?.canUse(receipt)) onFind(); }
  async function download() {
    const original = await client?.original();
    if (!original || !client?.canUse(original.receipt) || !dialog.open) return;
    const url = URL.createObjectURL(new Blob([original.bytes], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = original.receipt.fileName;
    link.click(); URL.revokeObjectURL(url);
  }
</script>

<dialog bind:this={dialog} oncancel={event => { event.preventDefault(); close(); }} aria-labelledby="supplied-text-title">
  <section class="supplied-text-evidence" aria-label="Add text evidence">
    <header><h2 id="supplied-text-title">Add text evidence</h2><button class="work-secondary" onclick={close}>Close text evidence</button></header>
    <p>Choose a local UTF-8 file, such as test output or a code excerpt. It will be saved as supplied text. Your investigation draft stays separate.</p>
    <p class="muted">Up to 64 KiB before encoding; escaped text must also fit the saved-record limit. File contents are not run or interpreted as messages.</p>
    {#if view.unavailable}
      <p class="notice">The existing recovery entry was retained. Reload after resolving unavailable or changed metadata.</p>
    {:else if view.receipt}
      {@const receipt = view.receipt}
      <section class="receipt" data-supplied-text-receipt={receipt.id}>
        <h3>Text evidence saved</h3><p role="status">{receipt.fileName} · {receipt.byteLength} bytes</p>
        <p>Local file; contents supplied by the owner.</p>
        {#if !receipt.discoverableFieldCount}<p>This file has no searchable text. Open it to select its exact source record.</p>{/if}
        <details><summary>File identity and receipt</summary><p class="object-ref" data-text-request-id={receipt.requestId}>Request {receipt.requestId}<br />Admission {receipt.id}<br />File SHA-256 {receipt.fileSha256}<br />Saved record {receipt.seq} · SHA-256 {receipt.hostRecordSha256}<br />Source {receipt.threadId}<br />{receipt.parserVersion}</p></details>
        <div class="actions">
          <button class="work-primary" onclick={openSource}>Open supplied text</button>
          <button class="work-secondary" onclick={find}>Find supplied evidence</button>
          <button class="work-secondary" disabled={busy} onclick={download}>{view.downloading ? 'Checking original bytes…' : 'Download original file'}</button>
          <button class="work-secondary" disabled={busy} onclick={() => client?.checkReceipt()}>Check text receipt</button>
          <button class="work-secondary" disabled={busy} onclick={() => client?.startAnother()}>Add another text file</button>
        </div>
      </section>
    {:else}
      {#if view.pending}
        <section class="notice" aria-label="Pending text recovery">
          <h3>Text admission not confirmed</h3>
          <p>The exact request is retained. Reload never sends it automatically. Check its receipt, or reselect the same file bytes to retry.</p>
          <details><summary>Pending file identity</summary><p class="object-ref" data-text-request-id={view.pending.requestId}>Request {view.pending.requestId}<br />{view.pending.fileName} · {view.pending.byteLength} bytes<br />SHA-256 {view.pending.fileSha256}</p></details>
          <button class="work-secondary" disabled={busy} onclick={() => client?.checkReceipt()}>{view.checking ? 'Checking text receipt…' : 'Check text receipt'}</button>
        </section>
      {/if}
      <label for="supplied-text-file">{view.pending ? 'Reselect the same file' : 'UTF-8 text file'}</label>
      <input id="supplied-text-file" type="file" disabled={busy} onchange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (file) void client?.choose(file); }} />
      {#if view.reading}<p role="status">Reading file identity…</p>{:else if view.hasFile}<p>Selected {view.fileName} · {view.byteLength} bytes{view.pending ? ' · exact bytes match' : ''}</p>{/if}
      {#if view.pending}
        <button class="work-primary" disabled={busy || !view.hasFile || view.reading} onclick={() => client?.commit()}>{view.sending ? 'Adding text…' : 'Retry adding this file'}</button>
      {:else}
        <button class="work-secondary" disabled={view.previewing || !view.hasFile || view.reading} onclick={() => client?.preview()}>{view.previewing ? 'Reviewing text…' : 'Preview text evidence'}</button>
      {/if}
      {#if view.preview && !view.pending}
        {@const preview = view.preview}
        <section class="preview" data-supplied-text-preview={preview.previewFingerprint} aria-label="Supplied text preview">
          <h3>Supplied text · {preview.fileName}</h3>
          <pre>{preview.textExcerpt}</pre>
          {#if preview.truncated}<p>Preview excerpt; the complete file will be retained.</p>{/if}
          {#if !preview.discoverableFieldCount}<p>No searchable text was found. The saved file will still be selectable as one source record.</p>{/if}
          <details><summary>Reviewed file identity</summary><p class="object-ref">{preview.byteLength} bytes<br />SHA-256 {preview.fileSha256}<br />{preview.parserVersion}</p></details>
          <button class="work-primary" disabled={busy} onclick={() => client?.commit()}>Add reviewed text</button>
        </section>
      {/if}
      {#if view.refusal}
        <section class="notice" aria-label="Refused text request"><p role="alert">Server refused this request: {view.refusal}</p><p>Check its receipt first. Dismissing discards local recovery; an earlier save may still exist.</p><button class="work-secondary" disabled={busy} onclick={() => client?.startAnother(true)}>Dismiss refused text request</button></section>
      {/if}
    {/if}
    {#if view.error}<p class="work-error" role="alert">{view.error}</p>{/if}
  </section>
</dialog>

<style>
  dialog { width:min(760px,calc(100vw - 28px)); max-height:calc(100dvh - 36px); box-sizing:border-box; border:1px solid var(--line-dark); padding:0; color:var(--ink); background:var(--paper); overflow:auto; }
  dialog::backdrop { background:rgb(25 30 25 / .45); }
  .supplied-text-evidence { padding:24px; overflow-wrap:anywhere; }
  header { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:12px; }
  h2 { margin:0; font-size:24px; font-weight:500; }
  h3 { font-size:18px; font-weight:500; }
  p { font-size:14px; line-height:1.55; }
  label { display:block; font-size:14px; margin:16px 0 8px; }
  input { box-sizing:border-box; width:100%; padding:10px; border:1px solid var(--line-dark); background:var(--paper); color:var(--ink); font:inherit; font-size:14px; }
  button { margin:6px 8px 6px 0; max-width:100%; white-space:normal; }
  .actions { display:flex; flex-wrap:wrap; }
  .notice,.preview,.receipt { padding:16px; border:1px solid var(--line); margin:16px 0; }
  .muted { color:var(--muted); }
  .object-ref { font:12px/1.6 monospace; }
  details { margin:14px 0; font-size:13px; }
  summary { cursor:pointer; }
  summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  pre { max-height:360px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; padding:12px; background:var(--code); font:13px/1.55 monospace; }
  @media(max-width:520px) { .supplied-text-evidence { padding:16px; } .notice,.preview,.receipt { padding:12px; } }
</style>
