<script lang="ts">
  import ThreadItemCard from './ThreadItem.svelte';
  import type { SemanticNode, SemanticRevision, ThreadItem } from './types';

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

  const directChildren = $derived(
    nodes.filter((candidate) => candidate.parent_node_id === node.node_id)
  );

  const related = $derived.by(() => {
    if (directChildren.length) {
      return { label: 'subtopics', nodes: directChildren };
    }
    if (node.parent_node_id) {
      return {
        label: 'nearby topics',
        nodes: nodes.filter(
          (candidate) =>
            candidate.parent_node_id === node.parent_node_id &&
            candidate.node_id !== node.node_id
        )
      };
    }
    return { label: 'subtopics', nodes: [] as SemanticNode[] };
  });
</script>

<aside class="focus-pane">
  <div class="focus-head">
    <span class="eyebrow">focused lens</span>
    <h2>{node.title}</h2>
    {#if node.summary}
      <p>{node.summary}</p>
    {/if}
    <small>
      {#if directChildren.length}
        {directChildren.length} child topic{directChildren.length === 1 ? '' : 's'}
        · {node.support.length} descendant support region{node.support.length === 1 ? '' : 's'}
      {:else}
        {node.support.length} support region{node.support.length === 1 ? '' : 's'}
        · {items.length} matching item{items.length === 1 ? '' : 's'}
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
            <small>{child.support.length} region{child.support.length === 1 ? '' : 's'}</small>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <section class="focus-evidence">
    {#if directChildren.length}
      <span class="eyebrow">evidence</span>
      <div class="empty-focus">
        This is an aggregate node. Pick a child topic above to narrow the lens;
        raw transcript matching begins at leaf nodes.
      </div>
    {:else}
      <span class="eyebrow">matching evidence</span>
      {#if items.length}
        {#each items as item (item.id)}
          <div class="focus-item-wrap">
            <button class="jump-button" onclick={() => onJump(item)}>JUMP ↗</button>
            <ThreadItemCard {item} compact />
          </div>
        {/each}
      {:else}
        <div class="empty-focus">No projected item overlaps this tight support yet.</div>
      {/if}
    {/if}
  </section>
</aside>
