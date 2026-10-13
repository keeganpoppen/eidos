<script lang="ts">
  import ArtifactContent from './ArtifactContent.svelte';
  import ArtifactLineage from './ArtifactLineage.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import Markdown from './Markdown.svelte';
  import { artifactKind, type ArtifactSourceTarget } from './artifact-inputs';
  import { resolveTarget } from './comparison';
  import type { CompositionSnapshot } from './composition-snapshots';
  import { savedQuestionFocus } from './saved-question';
  import type { FrozenArtifactInput, Investigation, WorkbenchExperiment } from './types';

  let { snapshot, owners, experiment, experimentError, onRetry }: {
    snapshot: CompositionSnapshot; owners: Investigation[]; experiment?: WorkbenchExperiment;
    experimentError: string; onRetry: () => void;
  } = $props();
  let lineageTarget = $state<(ArtifactSourceTarget & { snapshot?: FrozenArtifactInput }) | null>(null);
  let openRecords = $state<Record<string, boolean>>({});
  const sides = $derived((['left', 'right'] as const).map((side) => ({ side,
    target: snapshot.arrangement[side], ...resolveTarget(owners, snapshot.arrangement[side]) })));
  const focused = $derived(savedQuestionFocus(snapshot, owners));

  function inspectInput(input: FrozenArtifactInput) {
    lineageTarget = { investigationId: input.investigationId, artifactId: input.artifactId,
      contextId: input.sourceContextId, snapshot: input };
  }
</script>

<div class="saved-question-preview">
  <p class="preview-readonly">Review this saved work and its original support before opening it. Your working comparison and investigation draft stay in place.</p>
  {#if experiment}
    <section class="preview-experiment-rationale"><h5>Why this comparison was recorded</h5><p>{experiment.rationale}</p></section>
  {:else if snapshot.arrangement.experimentId}
    <p class="work-notice">The named experiment is unavailable for this preview. Its rationale and review have not been substituted. {experimentError} <button class="retry-preview-experiment" onclick={onRetry}>Retry experiment preview</button></p>
  {/if}
  <div class="preview-content-sides">
    {#each sides as item (item.side)}
      <section data-preview-side={item.side}>
        <h5>{item.side === 'left' ? 'A / Baseline' : 'B / Competing reading'} · {item.investigation?.title ?? 'Unavailable investigation'}</h5>
        {#if item.context}
          <div class="preview-question"><h6>Saved question</h6><p class="saved-question">{item.context.question}</p></div>
          {#if item.target.artifactId}
            {#if item.artifact}
              <div class="preview-result"><ArtifactContent artifact={item.artifact} context={item.context} onArtifact={inspectInput} /></div>
              <button class="preview-inspect-result" data-side={item.side} onclick={() => lineageTarget = {
                investigationId: item.target.investigationId, contextId: item.target.contextId, artifactId: item.target.artifactId!
              }}>Inspect original result and support</button>
              <p class="preview-note">Provenance inspection shows the exact result. Its currently recorded source review is labelled separately; it is not a review frozen by this arrangement.</p>
            {:else}<p class="work-notice">The exact saved result is unavailable. No newer result has been substituted.</p>{/if}
          {:else}<p class="preview-context-only">Context only · no result was saved in this aperture.</p>{/if}
          <details class="preview-selected-inputs"><summary>Selected inputs · {item.context.records.length} records · {item.context.artifactInputs?.length ?? 0} results</summary>
            {#each item.context.selections as selection}
              <p>{selection.rationale || 'No inclusion rationale recorded.'}<small>{selection.threadId} · {selection.startSeq}–{selection.endSeq}</small></p>
            {/each}
            {#each item.context.records as record}
              {@const key = JSON.stringify([item.side, record.threadId, record.seq])}
              <details class="preview-selected-record" data-record-seq={record.seq} ontoggle={(event) => openRecords[key] = event.currentTarget.open}>
                <summary>Inspect [evidence:{record.seq}] · {record.method ?? record.direction}<small>{record.threadId}</small></summary>
                {#if openRecords[key]}<EvidenceRecord {record} />{/if}
              </details>
            {/each}
            {#each item.context.artifactInputs ?? [] as input}
              <button class="preview-input-result" data-artifact-id={input.artifactId} onclick={() => inspectInput(input)}>{input.rationale || 'Inspect supplied result'}<small>{artifactKind(input.artifact)} · frozen input and source review</small></button>
            {/each}
            <p class="preview-note">These are the inputs of this saved context. Inspecting them does not add them to your draft.</p>
          </details>
        {:else}<p class="work-notice">This exact saved context is unavailable. Open retains its reference for explicit repair; the current context has not been substituted.</p>{/if}
      </section>
    {/each}
  </div>
  {#if snapshot.focus}
    <section class="preview-saved-focus">
      <h5>Saved evidence focus</h5>
      {#if focused.block}<div class="preview-saved-passage" data-saved-block-id={focused.block.id}><h6>Saved passage</h6><Markdown source={focused.block.text} /></div>{/if}
      {#if !focused.supported}<p class="work-notice" data-unresolved-selector>Passage selector unavailable for renderer {snapshot.rendererVersion}. Exact result and record references remain; no passage is highlighted under the installed parser.</p>{/if}
      {#if focused.record}<EvidenceRecord record={focused.record} />
      {:else if snapshot.focus.seq}<p class="work-notice">The saved record is unavailable or does not match this exact context, thread and cited support. No other record has been substituted.</p>
      {:else if !focused.block}<p class="preview-note">No resolvable passage or record was saved with this focus. Inspect the exact result using its provenance references.</p>{/if}
    </section>
  {:else}<p class="preview-note">No evidence focus was saved in this comparison. Inspect either result to recover its original support.</p>{/if}
  {#if experiment}
    <section class="preview-current-review" data-review-status={experiment.status}>
      <h5>Current review of this saved experiment</h5>
      {#if experiment.review}<p>{experiment.review.kind === 'human' ? 'Owner decision' : 'Synthetic review decision'}: {experiment.review.decision} · {experiment.review.rationale}</p>
      {:else}<p>No review decision is currently recorded.</p>{/if}
      {#if experiment.rollback}<p>Rollback recorded: {experiment.rollback.rationale}</p>{/if}
      <p class="preview-note">Read at preview time, separately from the frozen comparison. This does not change its question, result, or context pins. Configuration activation: not performed.</p>
    </section>
  {/if}
</div>
<ArtifactLineage target={lineageTarget} onClose={() => lineageTarget = null} />

<style>
  .saved-question-preview { min-width:0; overflow-wrap:anywhere; }
  .preview-content-sides { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:24px; }
  .preview-content-sides > section { min-width:0; border-top:1px solid var(--line-dark); padding-top:16px; }
  h5 { font-size:17px; font-weight:500; margin:0 0 12px; } h6 { font-size:13px; font-weight:500; margin:0 0 6px; }
  p { line-height:1.6; margin:8px 0; white-space:pre-wrap; }
  .preview-question { border-left:2px solid var(--accent); padding:10px 14px; background:var(--paper); margin-bottom:16px; }
  .saved-question { margin:0; font-size:16px; }
  .preview-result { max-height:440px; overflow:auto; padding:0 8px; scrollbar-gutter:stable; }
  .preview-context-only { color:var(--accent); }
  .preview-note,.preview-readonly { color:var(--muted); font-size:13px; }
  .preview-experiment-rationale,.preview-current-review,.preview-saved-focus { border-top:1px solid var(--line); padding:16px 0; margin-top:12px; }
  .preview-saved-passage { border-left:2px solid var(--accent); padding-left:14px; margin-bottom:16px; }
  details { margin-top:16px; } summary { cursor:pointer; font-size:13px; }
  .preview-selected-record { border-top:1px solid var(--line); padding-top:10px; }
  .preview-selected-record > summary { margin-bottom:12px; }
  small { display:block; font-size:12px; color:var(--muted); margin-top:4px; }
  button { cursor:pointer; max-width:100%; text-align:left; font:inherit; font-size:13px; padding:8px; border:1px solid var(--line-dark); color:var(--accent); background:var(--paper); overflow-wrap:anywhere; }
  .preview-input-result { display:block; width:100%; margin:8px 0; }
  button:focus-visible,summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  @media(max-width:760px) { .preview-content-sides { grid-template-columns:minmax(0,1fr); gap:18px; } }
</style>
