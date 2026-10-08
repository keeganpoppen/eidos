<script lang="ts">
  import Markdown from './Markdown.svelte';
  import type { ThreadItem } from './types';

  let {
    item,
    dimmed = false,
    highlighted = false,
    compact = false,
    semanticFocus = false
  }: {
    item: ThreadItem;
    dimmed?: boolean;
    highlighted?: boolean;
    compact?: boolean;
    semanticFocus?: boolean;
  } = $props();

  let showFullOutput = $state(false);
  let showFullText = $state(false);
  let showFullRaw = $state(false);
  let inspectOpen = $state(false);

  const textContent = $derived(
    Array.isArray(item.content)
      ? item.content
          .filter((part): part is Record<string, unknown> => typeof part === 'object' && part !== null)
          .filter((part) => part.type === 'text')
          .map((part) => String(part.text ?? ''))
      : []
  );

  const outputText = $derived(item.output ?? '');
  const outputLines = $derived(outputText ? outputText.split('\n') : []);
  const largeOutput = $derived(outputText.length > 4200 || outputLines.length > 70);

  const outputPreview = $derived.by(() => {
    if (!largeOutput) return outputText;
    const headCount = compact ? 8 : 18;
    const tailCount = compact ? 4 : 8;
    const head = outputLines.slice(0, headCount);
    const tail = outputLines.slice(-tailCount);
    const hidden = Math.max(0, outputLines.length - head.length - tail.length);
    return [...head, `… ${hidden} lines hidden …`, ...tail].join('\n');
  });

  const agentText = $derived(item.text ?? '');
  const compactAgent = $derived(compact && agentText.length > 1100);
  const agentPreview = $derived(
    compactAgent ? agentText.slice(0, 1100).trimEnd() + '…' : agentText
  );

  const rawText = $derived(
    JSON.stringify(item.detail ?? item.raw, null, 2)
  );
  const largeRaw = $derived(rawText.length > 5000);
  const rawPreview = $derived(
    largeRaw ? rawText.slice(0, compact ? 1800 : 3200).trimEnd() + '\n…' : rawText
  );
</script>

<article
  class:dimmed
  class:highlighted
  class:compact
  class:semantic-focus={semanticFocus}
  class:assistant={item.type === 'agentMessage'}
  class:user={item.type === 'userMessage'}
  class:reasoning={item.type === 'reasoning'}
  class:tool={['commandExecution', 'fileChange', 'mcpToolCall', 'dynamicToolCall', 'collabAgentToolCall', 'functionCallOutput', 'webSearch'].includes(item.type)}
  class="item-card"
  data-start={item.startSeq}
  data-end={item.endSeq}
  data-item-id={item.id}
>
  <header>
    <span>{item.type}</span>
    <code>{item.id}</code>
    {#if !item.complete}<b>LIVE</b>{/if}
  </header>

  {#if item.type === 'agentMessage'}
    <Markdown source={showFullText ? agentText : agentPreview} />
    {#if compactAgent}
      <button class="inline-control" onclick={() => showFullText = !showFullText}>
        {showFullText ? 'COLLAPSE' : 'FULL MESSAGE'}
      </button>
    {/if}
  {:else if item.type === 'userMessage'}
    {#each textContent as text}
      <Markdown source={text} />
    {/each}
  {:else if item.type === 'reasoning'}
    {#if item.summary?.length}
      <div class="reasoning-summary">
        {#each item.summary as summary}
          <Markdown source={summary} />
        {/each}
      </div>
    {/if}
    {#if Array.isArray(item.content) && item.content.length}
      <details>
        <summary>reasoning content</summary>
        {#each item.content as content}
          <Markdown source={String(content)} />
        {/each}
      </details>
    {:else if !item.summary?.length}
      <p class="empty-note">reasoning activity recorded; no text exposed</p>
    {/if}
  {:else if item.type === 'commandExecution'}
    {#if semanticFocus}
      <details bind:open={inspectOpen} class="semantic-tool-detail">
        <summary>
          command · {item.status ?? (item.complete ? 'completed' : 'running')}
          {#if item.exitCode !== null && item.exitCode !== undefined}
            · exit {item.exitCode}
          {/if}
        </summary>
        <div class="command-line">$ {item.command}</div>
        {#if outputText}
          <pre>{showFullOutput ? outputText : outputPreview}</pre>
          {#if largeOutput}
            <button class="inline-control" onclick={() => showFullOutput = !showFullOutput}>
              {showFullOutput ? 'collapse output' : `full output · ${outputLines.length} lines`}
            </button>
          {/if}
        {/if}
      </details>
    {:else}
      <div class="command-line">$ {item.command}</div>
      {#if outputText}
        <pre>{showFullOutput ? outputText : outputPreview}</pre>
        {#if largeOutput}
          <button class="inline-control" onclick={() => showFullOutput = !showFullOutput}>
            {showFullOutput ? 'COLLAPSE OUTPUT' : `FULL OUTPUT · ${outputLines.length} LINES`}
          </button>
        {/if}
      {/if}
      <footer>
        <span>{item.status ?? (item.complete ? 'completed' : 'running')}</span>
        {#if item.exitCode !== null && item.exitCode !== undefined}
          <span>exit {item.exitCode}</span>
        {/if}
      </footer>
    {/if}
  {:else if item.type === 'fileChange'}
    {#if semanticFocus}
      <details bind:open={inspectOpen} class="semantic-tool-detail">
        <summary>file changes · {(item.changes ?? []).length}</summary>
        <ul class="changes">
          {#each item.changes ?? [] as change}
            <li>{String(change.path ?? JSON.stringify(change))}</li>
          {/each}
        </ul>
      </details>
    {:else}
      <ul class="changes">
        {#each item.changes ?? [] as change}
          <li>{String(change.path ?? JSON.stringify(change))}</li>
        {/each}
      </ul>
    {/if}
  {:else}
    <details bind:open={inspectOpen}>
      <summary>
        {item.type === 'plan'
          ? 'plan'
          : `inspect · ${Math.max(1, Math.round(rawText.length / 1024))} KB raw`}
      </summary>
      <pre>{showFullRaw ? rawText : rawPreview}</pre>
      {#if largeRaw}
        <button class="inline-control" onclick={() => showFullRaw = !showFullRaw}>
          {showFullRaw ? 'COLLAPSE RAW' : 'FULL RAW'}
        </button>
      {/if}
    </details>
  {/if}
</article>
