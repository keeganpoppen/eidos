<script lang="ts">
  import { diffEntries, lineDiff } from './semantic';

  let { before, after }: { before: string; after: string } = $props();
  let expanded = $state<Set<number>>(new Set());
  let page = $state(0);
  const rows = $derived(lineDiff(before, after));
  const entries = $derived(diffEntries(rows, expanded));
  const pages = $derived(Math.max(1, Math.ceil(entries.length / 120)));
  const currentPage = $derived(Math.min(page, pages - 1));
  const visible = $derived(entries.slice(currentPage * 120, (currentPage + 1) * 120));
  const added = $derived(rows.filter((row) => row.kind === 'added').length);
  const removed = $derived(rows.filter((row) => row.kind === 'removed').length);
</script>

<section class="line-diff" aria-label="Text changes from baseline to alternative">
  <header><span>− {removed} removed</span><span>+ {added} added</span>{#if !added && !removed}<span>Text unchanged</span>{/if}</header>
  <div class="diff-lines">
    {#each visible as row}
      {#if row.kind === 'gap'}
        <button class="diff-gap" onclick={() => expanded = new Set([...expanded, row.id])}>Show {row.count.toLocaleString()} unchanged lines</button>
      {:else}
        <div class="diff-row" class:added={row.kind === 'added'} class:removed={row.kind === 'removed'}>
          <span class="line-number" aria-label="Baseline line">{row.beforeLine ?? ''}</span>
          <span class="line-number" aria-label="Alternative line">{row.afterLine ?? ''}</span>
          <span class="diff-marker" aria-hidden="true">{row.kind === 'added' ? '+' : row.kind === 'removed' ? '−' : ' '}</span>
          <span class="line-text"><span class="sr-only">{row.kind}: </span>{row.text || ' '}</span>
        </div>
      {/if}
    {/each}
  </div>
  {#if pages > 1}
    <nav class="diff-pages" aria-label="Diff pages">
      <button disabled={currentPage === 0} onclick={() => page = currentPage - 1}>Previous lines</button>
      <span>Page {currentPage + 1} / {pages}</span>
      <button disabled={currentPage === pages - 1} onclick={() => page = currentPage + 1}>Next lines</button>
    </nav>
  {/if}
  {#if expanded.size}<button class="collapse-unchanged" onclick={() => { expanded = new Set(); page = 0; }}>Collapse unchanged lines</button>{/if}
</section>

<style>
  .line-diff { min-width: 0; border: 1px solid var(--line-dark); background: var(--paper); font-size: 13px; }
  header { display: flex; flex-wrap: wrap; gap: 14px; padding: 8px 10px; border-bottom: 1px solid var(--line); color: #51574d; }
  .diff-lines { max-height: 560px; overflow: auto; }
  .diff-row { display: grid; grid-template-columns: 4ch 4ch 2ch minmax(0, 1fr); min-height: 1.65em; font: 13px/1.65 monospace; }
  .line-number { padding-right: 5px; color: #65695f; text-align: right; user-select: none; }
  .diff-marker { text-align: center; }
  .line-text { white-space: pre-wrap; overflow-wrap: anywhere; padding-right: 8px; }
  .added { background: #e0eddc; color: #234d2a; }
  .removed { background: #f1e1db; color: #73362b; }
  .diff-gap { width: 100%; text-align: left; background: var(--paper-3); }
  button { cursor: pointer; font: inherit; font-size: 13px; border: 1px solid var(--line-dark); padding: 7px 9px; color: var(--accent); background: transparent; }
  button:disabled { opacity: .45; cursor: default; }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .diff-pages { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 9px; padding: 9px; color: #51574d; }
  .collapse-unchanged { margin: 8px; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
