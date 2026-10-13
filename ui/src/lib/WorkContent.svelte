<script lang="ts">
  import Markdown from './Markdown.svelte';
  import { contentBlocks, patchLines } from './semantic';

  let { source, onFocus, focusedBlockId = '' }: {
    source: string;
    onFocus?: (block: { id: string; text: string; citations: number[] }) => void;
    focusedBlockId?: string;
  } = $props();

  let page = $state(0);
  const blocks = $derived(contentBlocks(source));
  const pages = $derived(Math.max(1, Math.ceil(blocks.length / 32)));
  const currentPage = $derived(Math.min(page, pages - 1));
  const visible = $derived(blocks.slice(currentPage * 32, (currentPage + 1) * 32));
  let expandedPatches = $state<Set<string>>(new Set());

  $effect(() => {
    const index = blocks.findIndex((block) => block.id === focusedBlockId);
    if (index >= 0) page = Math.floor(index / 32);
  });
</script>

<div class="work-content">
  {#each visible as block (block.id)}
    <section class="work-block" class:focused={block.id === focusedBlockId} data-block-id={block.id}>
      {#if block.diff !== undefined}
        {@const lines = patchLines(block.diff)}
        <div class="native-patch" aria-label="Returned patch; presentation only">
          <div class="patch-label">Returned diff · not applied</div>
          <pre>{#each expandedPatches.has(block.id) ? lines : lines.slice(0, 120) as line}<span class={line.kind}>{line.text || ' '}</span>{/each}</pre>
          {#if lines.length > 120}
            <button class="content-control" onclick={() => {
              const next = new Set(expandedPatches);
              next.has(block.id) ? next.delete(block.id) : next.add(block.id);
              expandedPatches = next;
            }}>{expandedPatches.has(block.id) ? 'Collapse diff' : `Show all ${lines.length} diff lines`}</button>
          {/if}
        </div>
      {:else}
        <Markdown source={block.text} />
      {/if}
      {#if onFocus && !['heading', 'hr'].includes(block.kind)}
        <div class="block-support">
          <button class="support-action" aria-pressed={block.id === focusedBlockId} onclick={() => onFocus?.(block)}>Inspect support</button>
          {#if block.citations.length}
            <span>{block.citations.map((seq) => `[evidence:${seq}]`).join(' · ')}</span>
          {:else if block.id === focusedBlockId}
            <span class="support-unknown">No evidence citations in this block. Support is unverified.</span>
          {/if}
        </div>
      {/if}
    </section>
  {/each}
  {#if pages > 1}
    <nav class="content-pages" aria-label="Artifact content pages">
      <button class="content-control" disabled={currentPage === 0} onclick={() => page = currentPage - 1}>Previous blocks</button>
      <span>Page {currentPage + 1} / {pages}</span>
      <button class="content-control" disabled={currentPage === pages - 1} onclick={() => page = currentPage + 1}>Next blocks</button>
    </nav>
  {/if}
</div>

<style>
  .work-content { min-width: 0; font-size: 15px; line-height: 1.6; overflow-wrap: anywhere; }
  .work-block { padding: 5px 10px 9px; margin: 0 0 7px -10px; border-left: 2px solid transparent; }
  .work-block.focused { border-left-color: var(--accent); background: var(--selection); }
  .block-support { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; font-size: 13px; line-height: 1.5; color: #595e54; }
  .support-action, .content-control { cursor: pointer; font: inherit; font-size: 13px; color: var(--accent); border: 1px solid var(--line-dark); border-radius: 3px; padding: 4px 7px; background: transparent; }
  .support-action:hover, .content-control:hover { background: var(--accent-soft); }
  .support-action:focus-visible, .content-control:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .support-unknown { color: #77561c; }
  .content-pages { display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; align-items: center; font-size: 13px; }
  .content-control:disabled { opacity: .45; cursor: default; }
  .native-patch { border: 1px solid var(--line-dark); background: var(--code); color: var(--ink); }
  .patch-label { padding: 6px 9px; font-size: 13px; color: #51574e; border-bottom: 1px solid var(--line); }
  .native-patch pre { margin: 0; max-height: 440px; overflow: auto; font: 13px/1.55 monospace; tab-size: 2; }
  .native-patch pre span { display: block; padding: 0 8px; min-height: 1.55em; white-space: pre-wrap; overflow-wrap: anywhere; }
  .native-patch .added { background: #e0eddc; color: #234d2a; }
  .native-patch .removed { background: #f1e1db; color: #73362b; }
  .native-patch .hunk { color: #365067; background: #e1e9ed; }
  .native-patch .content-control { margin: 8px; }
</style>
