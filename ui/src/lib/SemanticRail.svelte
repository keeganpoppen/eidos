<script lang="ts">
  import type { SemanticNode, SemanticRevision } from './types';

  let {
    outline,
    revisions,
    selectedRevision = '',
    onSelectNode,
    onSelectRevision,
    onObserve,
    observerBusy = false
  }: {
    outline: SemanticRevision | null;
    revisions: SemanticRevision[];
    selectedRevision?: string;
    onSelectNode: (node: SemanticNode | null) => void;
    onSelectRevision: (revision: string) => void;
    onObserve: (pool: boolean) => void;
    observerBusy?: boolean;
  } = $props();

  let activeNode = $state<string | null>(null);

  const nodes = $derived(outline?.nodes ?? []);
  const byId = $derived(new Map(nodes.map((node) => [node.node_id, node])));

  function depth(node: SemanticNode): number {
    let parent = node.parent_node_id ?? null;
    let d = 0;
    const seen = new Set<string>();
    while (parent && byId.has(parent) && !seen.has(parent) && d < 8) {
      seen.add(parent);
      d += 1;
      parent = byId.get(parent)?.parent_node_id ?? null;
    }
    return d;
  }

  function select(node: SemanticNode) {
    if (activeNode === node.node_id) {
      activeNode = null;
      onSelectNode(null);
      return;
    }
    activeNode = node.node_id;
    onSelectNode(node);
  }
</script>

<aside class="semantic-rail">
  <div class="rail-head">
    <div>
      <span class="eyebrow">semantic map</span>
      {#if outline}
        <strong>{outline.observer}</strong>
      {/if}
    </div>
    <button class="tiny" onclick={() => { activeNode = null; onSelectNode(null); }}>ALL</button>
  </div>

  <div class="observer-actions">
    <button class="observe" disabled={observerBusy} onclick={() => onObserve(false)}>
      {observerBusy ? 'OBSERVING…' : 'OBSERVE'}
    </button>
    <button class="observe alt" disabled={observerBusy} onclick={() => onObserve(true)}>POOL ×3</button>
  </div>

  {#if revisions.length}
    <select
      aria-label="semantic revision"
      value={selectedRevision}
      onchange={(event) => onSelectRevision((event.currentTarget as HTMLSelectElement).value)}
    >
      <option value="">auto-select</option>
      {#each revisions as revision}
        <option value={revision.revision_id}>
          {revision.observer} · h{revision.horizon_seq} · {revision.score.toFixed(2)}
        </option>
      {/each}
    </select>
  {/if}

  {#if outline}
    <div class="provenance">
      horizon {outline.horizon_seq} · score {outline.score.toFixed(2)}
    </div>

    <div class="nodes">
      {#each nodes as node}
        <button
          class:active={activeNode === node.node_id}
          class="semantic-node"
          style:--depth={depth(node)}
          onclick={() => select(node)}
        >
          <strong>{node.title}</strong>
          <span>{node.summary}</span>
          <small>
            {node.support.length} region{node.support.length === 1 ? '' : 's'} · {node.confidence.toFixed(2)}
          </small>
        </button>
      {/each}
    </div>
  {:else}
    <div class="empty-map">
      <strong>NO MAP YET</strong>
      <p>Run an observer. Its map will appear here without replacing the underlying trace.</p>
    </div>
  {/if}
</aside>
