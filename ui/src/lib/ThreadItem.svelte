<script lang="ts">
  import Markdown from './Markdown.svelte';
  import type { ThreadItem } from './types';

  let {
    item,
    dimmed = false,
    highlighted = false
  }: {
    item: ThreadItem;
    dimmed?: boolean;
    highlighted?: boolean;
  } = $props();

  const textContent = $derived(
    Array.isArray(item.content)
      ? item.content
          .filter((part): part is Record<string, unknown> => typeof part === 'object' && part !== null)
          .filter((part) => part.type === 'text')
          .map((part) => String(part.text ?? ''))
      : []
  );
</script>

<article
  class:dimmed
  class:highlighted
  class:assistant={item.type === 'agentMessage'}
  class:user={item.type === 'userMessage'}
  class:reasoning={item.type === 'reasoning'}
  class:tool={['commandExecution', 'mcpToolCall', 'dynamicToolCall', 'collabAgentToolCall', 'functionCallOutput', 'webSearch'].includes(item.type)}
  class="item-card"
  data-start={item.startSeq}
  data-end={item.endSeq}
>
  <header>
    <span>{item.type}</span>
    <code>{item.id}</code>
    {#if !item.complete}<b>LIVE</b>{/if}
  </header>

  {#if item.type === 'agentMessage'}
    <Markdown source={item.text ?? ''} />
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
    <div class="command-line">$ {item.command}</div>
    {#if item.output}
      <pre>{item.output}</pre>
    {/if}
    <footer>
      <span>{item.status ?? (item.complete ? 'completed' : 'running')}</span>
      {#if item.exitCode !== null && item.exitCode !== undefined}
        <span>exit {item.exitCode}</span>
      {/if}
    </footer>
  {:else if item.type === 'fileChange'}
    <ul class="changes">
      {#each item.changes ?? [] as change}
        <li>{String(change.path ?? JSON.stringify(change))}</li>
      {/each}
    </ul>
  {:else}
    <details open={item.type === 'plan'}>
      <summary>{item.type === 'plan' ? 'plan' : 'inspect'}</summary>
      <pre>{JSON.stringify(item.detail ?? item.raw, null, 2)}</pre>
    </details>
  {/if}
</article>
