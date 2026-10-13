<script lang="ts">
  import Markdown from './Markdown.svelte';
  import WorkContent from './WorkContent.svelte';
  import { projectEvidence } from './semantic';
  import type { ContextRecord } from './types';

  let { record }: { record: ContextRecord } = $props();
  let full = $state(false);
  let rawOpen = $state(false);
  let fullRaw = $state(false);
  const projected = $derived(projectEvidence(record.rawText));
  const displayText = $derived(full ? projected.text : projected.text.slice(0, 12000));
  const displayOutput = $derived(full ? projected.output : projected.output.slice(0, 12000));
</script>

<article class="frozen-record" data-evidence-seq={record.seq}>
  <header class="record-origin">
    <strong>[evidence:{record.seq}]</strong>
    <span>{record.threadId}</span>
    <small>{projected.type} · {record.method ?? record.direction}</small>
  </header>
  {#if projected.kind === 'message'}
    <Markdown source={displayText} />
    {#if projected.text.length > 12000}<button onclick={() => full = !full}>{full ? 'Collapse evidence text' : `Read full evidence · ${projected.text.length.toLocaleString()} characters`}</button>{/if}
  {:else if projected.kind === 'command'}
    {#if projected.command}<pre class="record-command">$ {projected.command}</pre>{/if}
    {#if projected.output}<pre class="record-output">{displayOutput}</pre>{:else}<p>No command output is exposed in this record.</p>{/if}
    {#if projected.output.length > 12000}<button onclick={() => full = !full}>{full ? 'Collapse command output' : 'Read full command output'}</button>{/if}
  {:else if projected.kind === 'changes'}
    {#each projected.changes as change}
      <p class="record-path">{change.path}</p>
      {#if change.diff}<WorkContent source={'```diff\n' + change.diff + '\n```'} />{:else}<p>No patch text is exposed for this path.</p>{/if}
    {/each}
    {#if !projected.changes.length}<p>No recognized file changes are exposed in this record.</p>{/if}
  {:else}
    <p class="record-unknown">This record has no recognized content projection. Inspect its original bytes below.</p>
  {/if}
  <details bind:open={rawOpen} class="raw-evidence">
    <summary>Original record · {record.rawText.length.toLocaleString()} characters</summary>
    {#if rawOpen}
      <pre>{fullRaw ? record.rawText : record.rawText.slice(0, 12000)}</pre>
      {#if record.rawText.length > 12000}<button onclick={() => fullRaw = !fullRaw}>{fullRaw ? 'Collapse original record' : 'Read complete original record'}</button>{/if}
    {/if}
  </details>
  <footer><span>Frozen from {record.source} · {record.direction}</span><span class="record-hash">SHA-256 {record.sha256}</span></footer>
</article>

<style>
  .frozen-record { min-width: 0; font-size: 15px; line-height: 1.6; overflow-wrap: anywhere; }
  .record-origin { display: flex; flex-wrap: wrap; gap: 5px 10px; align-items: baseline; margin-bottom: 13px; }
  .record-origin strong { font: 13px/1.5 monospace; color: var(--accent); }
  .record-origin span { color: var(--ink); font-size: 14px; }
  .record-origin small { color: #5c6157; font-size: 13px; width: 100%; }
  .record-command, .record-output, .raw-evidence pre { padding: 12px; background: var(--code); border: 1px solid var(--line); max-height: 390px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 13px/1.55 monospace; }
  .record-path { font: 14px/1.5 monospace; }
  .record-unknown { color: #795a22; }
  .raw-evidence { margin-top: 18px; padding-top: 10px; border-top: 1px solid var(--line); }
  .raw-evidence summary { cursor: pointer; font-size: 13px; color: #575e53; }
  footer { display: grid; gap: 4px; margin-top: 12px; font-size: 13px; color: #575e53; }
  .record-hash { font-family: monospace; overflow-wrap: anywhere; }
  button { cursor: pointer; color: var(--accent); font: inherit; font-size: 13px; padding: 5px 8px; border: 1px solid var(--line-dark); border-radius: 3px; background: transparent; }
  button:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
</style>
