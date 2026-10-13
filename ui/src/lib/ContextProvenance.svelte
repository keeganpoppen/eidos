<script lang="ts">
  import type { ContextLineage, ContextManifestView } from './types';

  let { investigationId, contextId, attemptId = '', attemptStatus = '' }: { investigationId: string; contextId: string; attemptId?: string; attemptStatus?: string } = $props();
  let opened = $state(false);
  let manifest = $state<ContextManifestView | null>(null);
  let lineage = $state<ContextLineage | null>(null);
  let error = $state('');
  let loading = $state(false);
  let retry = $state(0);
  const pinnedAttempt = $derived([lineage?.attempt, ...(lineage?.attemptHistory ?? [])].find((item) => item?.id === attemptId));

  $effect(() => {
    if (!opened) return;
    const id = investigationId;
    const context = contextId;
    void attemptId; void attemptStatus; void retry;
    const controller = new AbortController();
    manifest = null; lineage = null; error = ''; loading = true;
    async function read(path: string) {
      const response = await fetch(path, { signal: controller.signal });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error ?? 'Context provenance is unavailable.');
      return value;
    }
    void Promise.all([
      read(`/api/investigations/${encodeURIComponent(id)}/contexts/${encodeURIComponent(context)}/manifest`),
      read(`/api/investigations/${encodeURIComponent(id)}/context-lineage`)
    ]).then(([projection, history]) => {
      if (!controller.signal.aborted) { manifest = projection; lineage = history; }
    }).catch((cause) => {
      if (!controller.signal.aborted) error = cause instanceof Error ? cause.message : String(cause);
    }).finally(() => { if (!controller.signal.aborted) loading = false; });
    return () => controller.abort();
  });
</script>

<details class="context-provenance" bind:open={opened}>
  <summary>Context provenance / projection, request pin & capture gaps</summary>
  <p>A manifest describes selected input and observations at named boundaries. It grants no authority and does not reveal complete provider context.</p>
  {#if loading}<p>Loading this context’s provenance…</p>{/if}
  {#if error}<p class="work-error" role="alert">{error} <button onclick={() => retry++}>Retry provenance</button></p>{/if}
  {#if lineage?.error}<p class="work-error" role="alert">Context observation needs repair: {lineage.error}. Check the recorded outcome to retry this projection without sending native work.</p>{/if}
  {#if manifest}
    {#if manifest.manifestId}
      <p class="object-ref">Projection {manifest.manifestId}</p>
      {#each manifest.slots as slot (slot.path)}
        <details class="manifest-slot">
          <summary>{slot.path} · {slot.claims.map((claim) => `${claim.state} / ${claim.boundary}`).join(', ') || 'unobserved'}</summary>
          {#each slot.claims as claim (claim.id)}
            <p><strong>{claim.state} · {claim.boundary}</strong> / {claim.facet}<br />{claim.rationale}</p>
            <details><summary>Frozen ingredient & support</summary><pre>{JSON.stringify(claim.content.data, null, 2)}</pre><p class="object-ref">{claim.content.id}</p><p>Scope: {JSON.stringify(claim.scope)}</p><p>Evidence: {claim.evidence.join(', ') || 'No trace observation attached.'}</p></details>
          {/each}
          {#each slot.gaps as gap (gap.id)}<p class="work-notice">Unknown at {gap.boundary}: {gap.reason}</p>{/each}
          {#if slot.conflicts.length}<p class="work-notice">{slot.conflicts.length} unresolved provenance conflicts.</p>{/if}
        </details>
      {/each}
      {#if manifest.changes.length}<details><summary>Manifest changes from parent context</summary>{#each manifest.changes as change}<p>{change.operation} · {change.path}</p>{/each}</details>{/if}
    {:else}<p class="work-notice">This historical context has no recorded manifest. No request pin has been inferred.</p>{/if}
  {/if}
  {#if pinnedAttempt}
    <div class="request-pin">
      <h4>Native request pin</h4>
      <p class="object-ref">Attempt {pinnedAttempt.id}<br />Pinned manifest {pinnedAttempt.manifestId ?? 'not recorded'}<br />Request {pinnedAttempt.requestName ?? 'not recorded'}</p>
      <p>{pinnedAttempt.pin ? 'The attempt retains this recorded manifest; later observations do not rewrite its pin.' : 'No durable pin is available for this attempt.'}</p>
      {#each pinnedAttempt.events as event (event.id)}<details><summary>{event.kind} · recorded event</summary><pre>{JSON.stringify(event.data, null, 2)}</pre><p class="object-ref">{event.id}</p></details>{/each}
      {#if !pinnedAttempt.events.length}<p>No later request observations have been captured.</p>{/if}
    </div>
  {:else if lineage}<p>No native attempt is pinned to this selected context.</p>{/if}
</details>

<style>
  .context-provenance { margin-top: 16px; border-top: 1px solid var(--line); padding-top: 12px; font-size: 14px; overflow-wrap: anywhere; }
  summary { cursor: pointer; }
  .manifest-slot, .request-pin { margin-top: 12px; padding: 8px 0; border-top: 1px solid var(--line); }
  pre { max-height: 280px; overflow: auto; white-space: pre-wrap; font-size: 12px; }
  button { font: inherit; cursor: pointer; }
</style>
