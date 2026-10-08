<script lang="ts">
  import type { SemanticNode, SemanticRevision, SupportSpan } from './types';

  let {
    outline,
    revisions,
    selectedRevision = '',
    selectedNodeId = null,
    onSelectNode,
    onSelectRevision,
    onObserve,
    observerBusy = false,
    observerProgress = ''
  }: {
    outline: SemanticRevision | null;
    revisions: SemanticRevision[];
    selectedRevision?: string;
    selectedNodeId?: string | null;
    onSelectNode: (node: SemanticNode | null) => void;
    onSelectRevision: (revision: string) => void;
    onObserve: () => void;
    observerBusy?: boolean;
    observerProgress?: string;
  } = $props();

  const nodes = $derived(outline?.nodes ?? []);
  const byId = $derived(new Map(nodes.map((node) => [node.node_id, node])));
  const horizon = $derived(Math.max(1, outline?.horizon_seq ?? 1));

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

  function supportStyle(span: SupportSpan): string {
    const left = Math.max(0, Math.min(100, (span.start / horizon) * 100));
    const right = Math.max(left, Math.min(100, (span.end / horizon) * 100));
    const width = Math.max(0.8, right - left);
    return `left:${left}%;width:${width}%`;
  }
</script>

<aside class="semantic-rail">
  <div class="rail-head">
    <div>
      <span class="eyebrow">outline</span>
      {#if outline}
        <strong>retrospective map</strong>
      {/if}
    </div>
    <button class="tiny" onclick={() => onSelectNode(null)}>clear</button>
  </div>

  <div class="observer-actions single">
    <button class="observe" disabled={observerBusy} onclick={onObserve}>
      {observerBusy ? 'working…' : 'rebuild map'}
    </button>
  </div>

  {#if observerBusy && observerProgress}
    <div class="observer-progress">{observerProgress}</div>
  {/if}

  {#if revisions.length}
    <select
      aria-label="semantic revision"
      value={selectedRevision}
      onchange={(event) => onSelectRevision((event.currentTarget as HTMLSelectElement).value)}
    >
      <option value="">latest</option>
      {#each revisions as revision}
        <option value={revision.revision_id}>
          {revision.observer === 'retrospective-tree'
            ? 'tree'
            : revision.observer === 'retrospective'
              ? 'older retrospective'
              : 'older map'}
          · seq {revision.horizon_seq}
        </option>
      {/each}
    </select>
  {/if}

  {#if outline}
    <div class="provenance">through seq {outline.horizon_seq}</div>

    <div class="nodes">
      {#each displayNodes as node}
        <button
          class:active={selectedRootId() === node.node_id}
          class="semantic-node"
          onclick={() => select(node)}
        >
          <strong>{node.title}</strong>
          {#if node.summary}<span>{node.summary}</span>{/if}
          <div class="support-track" aria-hidden="true">
            {#each node.support as span}
              <i style={supportStyle(span)}></i>
            {/each}
          </div>
          <small>
            {childCount(node) ? `${childCount(node)} children` : `${node.support.length} regions`}
          </small>
        </button>
      {/each}
    </div>
  {:else}
    <div class="empty-map">
      <strong>No map yet.</strong>
      <p>Build one from the full conversation history.</p>
    </div>
  {/if}
</aside>
