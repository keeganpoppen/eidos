<script lang="ts">
  import { onMount } from 'svelte';
  import Markdown from './Markdown.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import { readReviewRequest, responseBody } from './review-request';
  import type { ReviewDecision, ReviewRequest } from './review-request';
  import type { EvidenceSelection, Investigation } from './types';

  let { investigation, selections, onUpdate }: {
    investigation: Investigation;
    selections: EvidenceSelection[];
    onUpdate: (value: Investigation) => void;
  } = $props();
  const continuation = $derived(investigation.continuation);
  const inquiry = $derived(continuation?.inquiry);
  const terminal = $derived(inquiry?.responses.some((response) => response.decision !== 'defer'));
  const storageKey = $derived(`nema.review-request.v1.${investigation.id}`);
  let question = $state('');
  let note = $state('');
  let busy = $state(false);
  let error = $state('');
  let pending = $state<ReviewRequest | null>(null);
  let review = $state<{ decision: ReviewDecision; note: string; selections: EvidenceSelection[] } | null>(null);

  onMount(() => {
    try { pending = readReviewRequest(localStorage.getItem(storageKey), investigation.id); }
    catch { error = 'Browser storage is unavailable. Restore storage before submitting a review decision so its retry identity can survive reload.'; }
  });

  async function send(request: ReviewRequest) {
    if (busy) return;
    error = '';
    try {
      // Persist synchronously before mutation, including its exact scope. A lost
      // HTTP reply can then retry the same admission without inventing a decision.
      localStorage.setItem(storageKey, JSON.stringify(request));
      pending = request;
    } catch {
      error = 'Could not persist this action’s retry identity. No request was sent.';
      return;
    }
    busy = true;
    try {
      const response = await fetch(`/api/investigations/${encodeURIComponent(investigation.id)}/${request.path}`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request.body)
      });
      const value = await response.json();
      if (!response.ok) {
        if ([400, 404, 409].includes(response.status)) {
          // A definitive admission rejection needs a corrected action, not an
          // endless replay of invalid scope. Ambiguous network/5xx keeps its ID.
          localStorage.removeItem(storageKey);
          pending = null; review = null;
        }
        throw new Error(value.error ?? 'Review action failed.');
      }
      onUpdate(value);
      localStorage.removeItem(storageKey);
      pending = null; review = null;
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }

  function openReview() {
    if (!question.trim() || !investigation.attempt || pending || busy) return;
    void send({ version: 1, investigationId: investigation.id, path: 'continuation', body: {
      requestId: crypto.randomUUID(), attemptId: investigation.attempt.id, question
    } });
  }

  function stage(decision: ReviewDecision) {
    review = { decision, note, selections: decision === 'offer' ? selections.map((selection) => ({ ...selection })) : [] };
  }

  function respond() {
    if (!review || !inquiry || pending || busy) return;
    void send({ version: 1, investigationId: investigation.id, path: `inquiries/${encodeURIComponent(inquiry.id)}/responses`,
      body: responseBody(crypto.randomUUID(), review.decision, review.note, review.selections) });
  }

  async function resume() {
    if (busy || pending) return;
    busy = true; error = '';
    try {
      const response = await fetch(`/api/investigations/${encodeURIComponent(investigation.id)}/resume`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}'
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error ?? 'Local review could not resume.');
      onUpdate(value);
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }
</script>

{#if continuation || (!investigation.adoption && investigation.status === 'completed' && investigation.artifact)}
  <section class="evidence-review" aria-label="Local evidence review">
    <h3>Local evidence review</h3>
    <p class="work-muted">An owner-started Eidos continuation records a disclosure decision beside the native answer. It asks no new model question and sends no second native turn.</p>
    {#if continuation}
      <p class="review-status">Review {continuation.status} · native attempt {investigation.attempt?.status ?? 'unrecorded'}</p>
      <div class="review-question"><Markdown source={inquiry?.question ?? continuation.question} /></div>
      {#if continuation.error}<p class="work-error" role="alert">{continuation.error}</p>{/if}
      {#if inquiry}
        <p class="work-muted">Disclosure {inquiry.status}. Offered evidence joins this local Eidos review; the original native input remains fixed.</p>
        {#if inquiry.responses.length}
          <ol class="response-history">
            {#each inquiry.responses as response (response.id)}
              <li><strong>{response.decision === 'defer' ? 'Deferred' : response.decision === 'offer' ? 'Evidence offered' : 'Evidence refused'}</strong> · {response.status}
                {#if response.note}<p>{response.note}</p>{/if}
                {#if response.evidenceContext}
                  <details><summary>Inspect offered packet · {response.evidenceContext.records.length} frozen records</summary>
                    <p class="object-ref">{response.evidenceContext.id}</p>
                    {#each response.evidenceContext.records as record (record.seq)}<details><summary>[evidence:{record.seq}] · {record.threadId}</summary><EvidenceRecord {record} /></details>{/each}
                  </details>
                {/if}
                <details><summary>Decision receipt</summary><p class="object-ref">Response {response.id}<br />Occurrence {response.occurrenceId ?? 'not yet committed'}</p></details>
              </li>
            {/each}
          </ol>
        {/if}
        {#if !terminal && !pending}
          <label for="review-note">Disclosure note</label><textarea id="review-note" bind:value={note} rows="2" disabled={busy} placeholder="Why offer, defer, or refuse this evidence?"></textarea>
          <div class="decision-actions">
            <button disabled={busy || !selections.length} onclick={() => stage('offer')}>Review offer from current tray</button>
            <button disabled={busy} onclick={() => stage('defer')}>Defer review</button>
            <button disabled={busy} onclick={() => stage('refuse')}>Refuse evidence</button>
          </div>
        {/if}
        {#if review && !pending}
          <section class="disclosure-preview" aria-label="Review disclosure decision">
            <h4>{review.decision === 'offer' ? 'Offer these exact ranges' : review.decision === 'defer' ? 'Keep this review pending' : 'Finish without additional evidence'}</h4>
            {#if review.decision === 'offer'}
              <p>{review.selections.length} ranges. The server will freeze the records at these addresses when this offer is admitted. Changes to the tray do not change this reviewed selection.</p>
              <ul>{#each review.selections as selection}<li>{selection.threadId} · {selection.startSeq}–{selection.endSeq}<br />{selection.rationale}</li>{/each}</ul>
            {:else if review.decision === 'defer'}<p>Records a deferral and leaves the same waiting continuation available.</p>
            {:else}<p>Records refusal, finishes this local review, and preserves the original native answer.</p>{/if}
            <p>{review.note || 'No note.'}</p>
            <button disabled={busy} onclick={respond}>Confirm {review.decision}</button>
            <button disabled={busy} onclick={() => review = null}>Cancel decision</button>
          </section>
        {/if}
      {/if}
      {#if continuation.status !== 'completed'}<button class="work-secondary" disabled={busy || !!pending} onclick={resume}>Resume local review</button><p class="work-muted">Checks the admitted local continuation. It never resends native work.</p>{/if}
      <details><summary>Review provenance</summary><p class="object-ref">Continuation {continuation.id}<br />Process {continuation.processId ?? 'preparing'}<br />Checkpoint {continuation.checkpointId ?? 'not yet saved'}<br />Outcome {continuation.outcomeId ?? 'pending'}</p></details>
    {:else}
      <details class="start-review"><summary>Record a follow-up disclosure decision</summary>
        <label for="review-question">Your evidence review question</label><textarea id="review-question" bind:value={question} rows="3" disabled={busy || !!pending} placeholder="Which additional evidence should be retained with this result?"></textarea>
        <p>Adoption waits for this local review to finish. The returned native answer stays available throughout.</p>
        <button disabled={busy || !!pending || !question.trim()} onclick={openReview}>Start local evidence review</button>
      </details>
    {/if}
    {#if pending}
      <div class="work-notice" role="status"><p>The recorded action still needs confirmation. Retrying keeps its request identity and exact scope.</p><details><summary>Inspect pending request</summary><pre>{JSON.stringify(pending.body, null, 2)}</pre></details><button disabled={busy} onclick={() => pending && send(pending)}>Retry recorded review action</button></div>
    {/if}
    {#if error}<p class="work-error" role="alert">{error}</p>{/if}
  </section>
{/if}

<style>
  .evidence-review { margin-top: 24px; border-top: 1px solid var(--line-dark); padding-top: 14px; font-size: 14px; overflow-wrap: anywhere; }
  .review-question, .disclosure-preview { border-left: 2px solid var(--accent); padding: 8px 12px; background: var(--selection); margin: 12px 0; }
  .response-history { padding-left: 22px; }
  .response-history li { padding: 8px 0; }
  summary, button { cursor: pointer; }
  button { font: inherit; padding: 6px 9px; border: 1px solid var(--line-dark); background: transparent; margin: 5px 5px 5px 0; color: var(--accent); }
  button:disabled { opacity: .45; cursor: default; }
  button:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  label { display: block; margin-top: 10px; }
  textarea { width: 100%; box-sizing: border-box; margin-top: 5px; }
  pre { max-height: 220px; white-space: pre-wrap; overflow: auto; }
</style>
