<script lang="ts">
  import type { SemanticNode, SemanticRevision } from './types';

  let {
    outline,
    revisions,
    selectedRevision = '',
    selectedNodeId = null,
    onSelectNode,
    onSelectRevision,
    onObserve,
    observerBusy = false
  }: {
    outline: SemanticRevision | null;
    revisions: SemanticRevision[];
    selectedRevision?: string;
    selectedNodeId?: string | null;
    onSelectNode: (node: SemanticNode | null) => void;
    onSelectRevision: (revision: string) => void;
    onObserve: (pool: boolean) => void;
    observerBusy?: boolean;
  } = $props();

  const nodes = $derived(outline?.nodes ?? []);
  const byId = $derived(new Map(nodes.map((node) => [node.node_id, node])));

  const displayNodes = $derived.by(() => {
    const top = nodes.filter((node) => !node.parent_node_id);
    return top.length ? top : nodes;
  });

  function childCount(node: SemanticNode): number {
    return nodes.filter((candidate) => candidate.parent_node_id === node.node_id).length;
  }

  function selectedRootId(): string | null {
    if (!selectedNodeId) return null;
    let current = byId.get(selectedNodeId);
    const seen = new Set<string>();
    while (current?.parent_node_id && byId.has(current.parent_node_id) && !seen.has(current.parent_node_id)) {
      seen.add(current.parent_node_id);
      current = byId.get(current.parent_node_id);
    }
    return current?.node_id ?? selectedNodeId;
  }

  function select(node: SemanticNode) {
    if (selectedNodeId === node.node_id) {
      onSelectNode(null);
      return;
    }
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
    <button class="tiny" onclick={() => onSelectNode(null)}>ALL</button>
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
      {#each displayNodes as node}
        <button
          class:active={selectedRootId() === node.node_id}
          class="semantic-node"
          onclick={() => select(node)}
        >
          <strong>{node.title}</strong>
          {#if node.summary}<span>{node.summary}</span>{/if}
          <small>
            {childCount(node) ? `${childCount(node)} topics · ` : ''}
            {node.support.length} region{node.support.length === 1 ? '' : 's'}
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
