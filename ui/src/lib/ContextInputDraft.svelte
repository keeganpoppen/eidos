<script lang="ts">
  import type { InputDraftState } from './context-input-draft';
  import type { InvestigationContext } from './types';

  let { state, editorBusy, editorPending, confirmReplacement, inspection, inspecting, inspectionError, onInspect, onEdit, onCreate, onCancel, onOpen, onKeep }: {
    state: InputDraftState; editorBusy: boolean; editorPending: boolean; confirmReplacement: boolean;
    inspection: InvestigationContext | null; inspecting: boolean; inspectionError: string; onInspect: () => void;
    onEdit: (field: 'title' | 'question', value: string) => void; onCreate: () => void; onCancel: () => void;
    onOpen: (confirmed: boolean) => void; onKeep: () => void;
  } = $props();
  const draft = $derived(state.draft);
</script>

{#if draft || state.error}
  <section class="context-input-draft" aria-label="New question from historical inputs">
    <h3>New question from historical inputs</h3>
    {#if draft}
      <p>Inputs from <strong>{draft.source.title}</strong>: {draft.source.recordCount} frozen records and {draft.source.artifactCount} frozen results.</p>
      <p class="object-ref" data-input-source-context={draft.source.contextId}>Source {draft.source.investigationId}<br />Context {draft.source.contextId}</p>
      <p class="work-muted">The first saved context keeps these exact inputs and their inclusion rationales. It uses your new question. Your current working draft stays separate.</p>
      {#if draft.saved}
        <p class="work-notice" role="status">New draft saved. No specialist was started.</p>
        <p class="object-ref" data-created-context={draft.saved.contextId}>Investigation {draft.saved.investigationId}<br />Created context {draft.saved.contextId}</p>
        <p><strong>{draft.title}</strong></p>
        <p class="new-question">{draft.question}</p>
        <button class="work-secondary" disabled={inspecting} onclick={onInspect}>{inspecting ? 'Loading saved input…' : 'Inspect saved input'}</button>
        {#if inspectionError}<p class="work-error" role="alert">{inspectionError}</p>{/if}
        {#if inspection}
          <section class="created-input-preview" aria-label="Exact created input preview" data-inspected-context={inspection.id}>
            <h4>Saved input preview</h4>
            <p class="new-question">{inspection.question}</p>
            <p>{inspection.records.length} frozen records · {inspection.artifactInputs?.length ?? 0} frozen results</p>
            <p class="object-ref">Created context {inspection.id}<br />Input origin {inspection.inputOrigin?.investigationId}<br />Source context {inspection.inputOrigin?.contextId}<br />Source manifest {inspection.inputOrigin?.manifestId ?? 'not recorded'}</p>
            <p>{typeof inspection.coverage === 'string' ? inspection.coverage : 'Coverage description is unavailable.'}</p>
            <details><summary>Exact specialist input</summary><pre>{inspection.projectedPrompt}</pre></details>
          </section>
        {/if}
        <button class="work-primary" disabled={editorBusy || editorPending} onclick={() => onOpen(false)}>Open saved draft</button>
        {#if editorPending}<p class="work-notice">Your current draft has an unresolved save. Resolve that save before opening another draft; its retry identity is still retained.</p>{/if}
        {#if confirmReplacement && !editorPending}
          <div class="replacement-choice" role="group" aria-label="Replace unsaved draft">
            <p>Opening this saved draft replaces the unsaved question, selections and notes in your current editor.</p>
            <button class="work-primary" disabled={editorBusy} onclick={() => onOpen(true)}>Replace unsaved draft and open</button>
            <button class="work-secondary" disabled={editorBusy} onclick={onKeep}>Keep editing current draft</button>
          </div>
        {/if}
        <button class="work-secondary" disabled={editorBusy} onclick={onCancel}>Dismiss saved draft notice</button>
      {:else}
        <label for="context-input-title">New draft title</label>
        <input id="context-input-title" maxlength="200" value={draft.title} disabled={!!draft.request || state.sending} oninput={event => onEdit('title', event.currentTarget.value)} />
        <label for="context-input-question">New question</label>
        <textarea id="context-input-question" maxlength="16000" rows="4" value={draft.question} disabled={!!draft.request || state.sending} oninput={event => onEdit('question', event.currentTarget.value)} placeholder="Ask a new question using these historical inputs."></textarea>
        <button class="work-primary" disabled={state.sending || !draft.title.trim() || !draft.question.trim()} onclick={onCreate}>{state.sending ? 'Saving new draft…' : draft.request ? 'Retry creating this draft' : 'Save new draft'}</button>
        {#if draft.request}
          {#if draft.refusal}
            <p class="work-error" role="alert">Server refused this request ({draft.refusal.status}): {draft.refusal.message}</p>
            <p class="work-muted">This response does not establish whether an earlier request took effect. The exact request is retained for retry until you dismiss it.</p>
            <button class="work-secondary" disabled={state.sending} onclick={onCancel}>Dismiss refused creation</button>
          {:else}<p class="work-muted">This exact creation request is retained. Retry uses the same source, question and request identity; reload never sends it automatically.</p>{/if}
        {:else}<button class="work-secondary" onclick={onCancel}>Cancel new draft</button>{/if}
      {/if}
    {/if}
    {#if state.error}<p class="work-error" role="alert">{state.error}</p>{/if}
  </section>
{/if}

<style>
  .context-input-draft { margin-block:20px; padding:16px 12px; border:1px solid var(--line); overflow-wrap:anywhere; }
  h3 { margin:0 0 12px; font-size:19px; }
  p { line-height:1.5; }
  label { display:block; margin:12px 0 6px; }
  input,textarea { box-sizing:border-box; width:100%; max-width:100%; font-family:inherit; color:var(--ink); }
  button { margin:10px 8px 0 0; max-width:100%; white-space:normal; }
  .object-ref { font:11px/1.5 var(--font-mono,monospace); overflow-wrap:anywhere; }
  .work-muted { color:var(--muted); font-size:13px; }
  .new-question { white-space:pre-wrap; }
  .replacement-choice { margin-block:12px; padding:12px; border:1px solid var(--accent); }
  .created-input-preview { margin-block:12px; padding:12px; border-left:2px solid var(--accent); }
  .created-input-preview pre { max-width:100%; overflow-wrap:anywhere; white-space:pre-wrap; font-size:12px; }
</style>
