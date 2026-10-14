<script lang="ts">
  import ArtifactContent from './ArtifactContent.svelte';
  import { findingDraftText, type FindingState } from './authored-finding';
  let { state, onEdit, onSave, onCheck, onDismiss, onInspect }: {
    state: FindingState; onEdit: (value: string) => void; onSave: () => void; onCheck: () => void;
    onDismiss: () => void; onInspect: () => void;
  } = $props();
  const draft = $derived(state.draft);
</script>

{#if draft || state.error}
  <section class="authored-finding-draft" aria-label="Write an authored finding">
    <h3>Authored finding</h3>
    {#if draft}
      <p>Saved context from <strong>{draft.source.title}</strong></p>
      <p class="object-ref" data-finding-source-owner={draft.source.investigationId} data-finding-source-context={draft.source.contextId}>Investigation {draft.source.investigationId}<br />Context {draft.source.contextId}</p>
      <p class="saved-question">{draft.source.question}</p>
      <p class="work-muted">This finding stays pinned to that saved context even when you change the working draft or select another investigation.</p>
      {#if state.finding}
        <div data-saved-finding-id={state.finding.id}>
          <p role="status">Finding saved.</p>
          <ArtifactContent artifact={state.finding} />
          <button class="work-primary" onclick={onInspect}>Inspect saved finding</button>
          <button class="work-secondary" disabled={state.busy || state.unavailable} onclick={onDismiss}>Dismiss saved finding</button>
        </div>
      {:else}
        <label for="authored-finding-text">Finding and open questions</label>
        <textarea id="authored-finding-text" rows="7" maxlength="131072" value={findingDraftText(draft)} disabled={!!draft.request || state.busy || state.unavailable}
          oninput={event => onEdit(event.currentTarget.value)} placeholder="Record your conclusion, uncertainty and remaining questions. Cite supplied records as [evidence:N] or supplied results as [artifact:ID]."></textarea>
        <p class="work-muted">Up to 128 KiB. Citations identify sources in this saved context; they do not establish that a claim is true. Uncited hypotheses are allowed.</p>
        {#if draft.request}
          <p class="work-notice">{draft.savedId ? 'The saved finding reference is retained. Check its exact receipt to display it again.' : 'The save outcome is not confirmed. The exact request is retained; reload never sends it automatically.'}</p>
          <button class="work-secondary" disabled={state.busy || state.unavailable} onclick={onCheck}>{state.busy ? 'Checking…' : 'Check finding receipt'}</button>
          {#if !draft.savedId}<button class="work-primary" disabled={state.busy || state.unavailable} onclick={onSave}>Retry saving this finding</button>{/if}
        {:else}
          <button class="work-primary" disabled={state.busy || state.unavailable || !findingDraftText(draft).trim()} onclick={onSave}>Save finding</button>
          <button class="work-secondary" disabled={state.busy || state.unavailable} onclick={onDismiss}>Discard finding draft</button>
        {/if}
        {#if state.refusal}
          <p class="work-error" role="alert">{state.refusal}</p>
          <p class="work-muted">This discards local recovery; an earlier save may still exist.</p>
          <button class="work-secondary" disabled={state.busy || state.unavailable} onclick={onDismiss}>Dismiss refused finding</button>
        {/if}
      {/if}
    {/if}
    {#if state.error}<p class="work-error" role="alert">{state.error}</p>{/if}
  </section>
{/if}

<style>
  .authored-finding-draft { margin-block:20px; padding:16px 12px; border:1px solid var(--line); overflow-wrap:anywhere; }
  h3 { margin:0 0 12px; font-size:19px; }
  p { font-size:14px; line-height:1.5; }
  label { display:block; margin:12px 0 6px; }
  textarea { box-sizing:border-box; width:100%; min-width:0; padding:9px; border:1px solid var(--line-dark); background:var(--paper); font:inherit; color:var(--ink); }
  button { margin:10px 8px 0 0; max-width:100%; white-space:normal; }
  .object-ref { font:11px/1.5 monospace; overflow-wrap:anywhere; }
  .saved-question { white-space:pre-wrap; border-left:2px solid var(--line-dark); padding-left:10px; }
  .work-muted { color:var(--muted); font-size:13px; }
  .work-error { color:var(--accent); }
</style>
