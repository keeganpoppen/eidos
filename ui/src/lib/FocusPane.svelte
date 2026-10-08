<script lang="ts">
  import ThreadItemCard from './ThreadItem.svelte';
  import type { SemanticNode, SemanticRevision, SupportSpan, ThreadItem } from './types';

  let {
    node,
    outline,
    items,
    onSelectNode,
    onJump
  }: {
    node: SemanticNode;
    outline: SemanticRevision | null;
    items: ThreadItem[];
    onSelectNode: (node: SemanticNode) => void;
    onJump: (item: ThreadItem) => void;
  } = $props();

  const nodes = $derived(outline?.nodes ?? []);
  const horizon = $derived(Math.max(1, outline?.horizon_seq ?? 1));

  const directChildren = $derived(
    nodes.filter((candidate) => candidate.parent_node_id === node.node_id)
  );

  const conversationItems = $derived(
    items.filter((item) =>
      item.type === 'userMessage' ||
      (item.type === 'agentMessage' && (!item.phase || item.phase === 'final' || item.phase === 'final_answer'))
    )
  );

  const implementationItems = $derived(
    items.filter((item) => !conversationItems.includes(item))
  );

  const related = $derived.by(() => {
    if (directChildren.length) {
      return { label: 'parts', nodes: directChildren };
    }
    if (node.parent_node_id) {
      return {
        label: 'nearby',
        nodes: nodes.filter(
          (candidate) =>
            candidate.parent_node_id === node.parent_node_id &&
            candidate.node_id !== node.node_id
        )
      };
    }
    return { label: 'parts', nodes: [] as SemanticNode[] };
  });

  function supportStyle(span: SupportSpan): string {
    const left = Math.max(0, Math.min(100, (span.start / horizon) * 100));
    const right = Math.max(left, Math.min(100, (span.end / horizon) * 100));
    return `left:${left}%;width:${Math.max(0.8, right - left)}%`;
  }
</script>

<aside class="focus-pane">
  <div class="focus-head">
    <span class="eyebrow">topic</span>
    <h2>{node.title}</h2>
    {#if node.summary}
      <p>{node.summary}</p>
    {/if}
    <div class="support-track focus-support" aria-hidden="true">
      {#each node.support as span}
        <i style={supportStyle(span)}></i>
      {/each}
    </div>
    <small>
      {#if directChildren.length}
        {directChildren.length} part{directChildren.length === 1 ? '' : 's'}
      {:else}
        {items.length} matching item{items.length === 1 ? '' : 's'}
      {/if}
    </small>
  </div>

  {#if related.nodes.length}
    <section class="focus-outline">
      <span class="eyebrow">{related.label}</span>
      <div class="focus-topics">
        {#each related.nodes as child}
          <button onclick={() => onSelectNode(child)}>
            <strong>{child.title}</strong>
            {#if child.summary}<span>{child.summary}</span>{/if}
            <div class="support-track" aria-hidden="true">
              {#each child.support as span}
                <i style={supportStyle(span)}></i>
              {/each}
            </div>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <section class="focus-evidence">
    {#if directChildren.length}
      <span class="eyebrow">next</span>
      <div class="empty-focus">
        Choose a child to get closer to the conversation.
      </div>
    {:else}
      <span class="eyebrow">conversation</span>
      {#if conversationItems.length}
        {#each conversationItems as item (item.id)}
          <div class="focus-item-wrap human-evidence">
            <button class="jump-button" onclick={() => onJump(item)}>jump</button>
            <ThreadItemCard {item} compact />
          </div>
        {/each}
      {:else}
        <div class="empty-focus">
          This memory is supported mostly by implementation evidence.
        </div>
      {/if}

      {#if implementationItems.length}
        <details class="implementation-evidence">
          <summary>
            implementation evidence · {implementationItems.length}
          </summary>
          <div class="implementation-evidence-list">
            {#each implementationItems as item (item.id)}
              <div class="focus-item-wrap">
                <button class="jump-button" onclick={() => onJump(item)}>jump</button>
                <ThreadItemCard {item} compact semanticFocus />
              </div>
            {/each}
          </div>
        </details>
      {/if}
    {/if}
  </section>
</aside>
