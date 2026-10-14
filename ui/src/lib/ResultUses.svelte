<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import ArtifactContent from './ArtifactContent.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import { ResultUsesClient, resultUseKey, type ResultUse, type ResultUseTarget, type ResultUsesState } from './result-uses';

  let { target }: { target: ResultUseTarget } = $props();
  let uses = $state<ResultUsesState>({ target: null, expanded: false, page: null, cursor: '', previous: [], loading: false, inspecting: null, detail: null, error: '', refreshRequired: false });
  const client = new ResultUsesClient(value => uses = value);
  let previewHeading = $state<HTMLHeadingElement>();
  $effect(() => { client.target(target); });
  onDestroy(() => client.dispose());
  // The dialog calls this synchronously before its parent clears the target.
  export function cancel() { client.target(null); }
  export function hasInteracted() { return client.state.expanded; }
  async function inspect(row: ResultUse) {
    const detail = await client.inspect(row);
    if (!detail) return;
    await tick();
    if (client.isCurrentDetail(detail) && previewHeading?.isConnected && previewHeading.closest('dialog')?.open) {
      previewHeading.focus({ preventScroll: true });
      previewHeading.scrollIntoView({ block: 'start' });
    }
  }
</script>

<section class="result-uses" aria-label="Questions supplied this result">
  {#if !uses.expanded}
    <button class="work-secondary" onclick={() => client.refresh()}>Questions supplied this result</button>
  {:else}
    <h3>Questions supplied this result</h3>
    <p>These saved contexts directly included this exact result. This shows supplied inputs, not whether a claim relied on them. Indirect uses through other results are not listed.</p>
    <button class="work-secondary" onclick={() => client.refresh()}>Refresh saved uses</button>
    {#if uses.loading}<p role="status">Loading saved uses…</p>{/if}
    {#if uses.error}<p class="work-error" role="alert">{uses.error}</p>{/if}
    {#if uses.refreshRequired}<p class="work-notice">Saved uses changed. Refresh saved uses before inspecting another context.</p>{/if}
    {#if uses.page}
      <p role="status">Page {uses.previous.length + 1} · {uses.page.uses.length} saved {uses.page.uses.length === 1 ? 'context' : 'contexts'}{uses.page.nextCursor ? ' · more available' : ''}</p>
      {#if !uses.page.uses.length}<p class="empty-uses">No saved contexts directly supplied this exact result.</p>{/if}
      <ol class="use-list">
        {#each uses.page.uses as row (resultUseKey(row))}
          <li data-result-use-owner={row.investigationId} data-result-use-context={row.contextId}>
            <h4>{row.investigationTitle}</h4>
            <p class="context-status">{row.isCurrent ? 'Current saved context' : 'Historical saved context'}</p>
            <p class="saved-question">{row.questionExcerpt}</p>
            <p class="inclusion-rationale">Inclusion rationale: {row.rationaleExcerpt || 'No inclusion rationale recorded.'}</p>
            <details><summary>Saved context references</summary><p class="object-ref">Investigation {row.investigationId}<br />Context {row.contextId}</p></details>
            {#if row.matchingInputCount > 1}<p>{row.matchingInputCount} matching frozen inputs</p>{/if}
            <button class="work-secondary" disabled={uses.refreshRequired || uses.inspecting === resultUseKey(row)} onclick={() => inspect(row)}>{uses.inspecting === resultUseKey(row) ? 'Loading saved context…' : 'Inspect saved context'}</button>
          </li>
        {/each}
      </ol>
      <nav aria-label="Saved uses pages">
        <button class="work-secondary" disabled={uses.loading || uses.refreshRequired || !uses.previous.length} onclick={() => client.move(false)}>Previous saved uses</button>
        <button class="work-secondary" disabled={uses.loading || uses.refreshRequired || !uses.page.nextCursor} onclick={() => client.move(true)}>Next saved uses</button>
      </nav>
    {/if}
    {#if uses.detail}
      {@const detail = uses.detail}
      {@const context = detail.context}
      <section class="use-preview" aria-label="Exact saved consumer context" data-result-use-preview={context.id} data-consumer-owner={detail.investigationId} data-consumer-context={context.id}>
        <h3 bind:this={previewHeading} tabindex="-1">Saved context · {detail.investigationTitle}</h3>
        <p class="context-status">{detail.isCurrent ? 'Current saved context' : 'Historical saved context'}</p>
        <h4>Saved question</h4>
        <p class="saved-question" data-consumer-question>{context.question}</p>
        <p>This preview retains the inputs saved with this question. Your working draft is unchanged.</p>
        <details><summary>Saved context references</summary><p class="object-ref">Investigation {detail.investigationId}<br />Context {context.id}<br />Owner version {detail.ownerVersion}</p></details>
        {#if context.inputOrigin}
          <section class="input-origin" aria-label="Saved input origin">
            <h4>Input origin</h4>
            <p>Inputs copied from a saved context.</p>
            <details><summary>Exact input origin</summary><p class="object-ref">Investigation {context.inputOrigin.investigationId}<br />Context {context.inputOrigin.contextId}<br />Manifest {context.inputOrigin.manifestId ?? 'not recorded'}</p><pre>{JSON.stringify(context.inputOrigin, null, 2)}</pre></details>
          </section>
        {/if}
        <h4>Matching frozen result</h4>
        {#each detail.matchingInputIndexes as index (index)}
          {@const input = context.artifactInputs![index]}
          <article class="frozen-input matching-input" data-matching-input-index={index}>
            <p class="inclusion-rationale">Inclusion rationale: {input.rationale || 'No inclusion rationale recorded.'}</p>
            <ArtifactContent artifact={input.artifact} />
            <details><summary>Frozen result references</summary><p class="object-ref">Source investigation {input.investigationId}<br />Result {input.artifactId}<br />Source context {input.sourceContextId}</p></details>
            {#if input.sourceAdoption}<p class="source-review">Source review when this input was saved: {input.sourceAdoption.decision === 'adopt' ? 'adopted' : 'rejected'}. {input.sourceAdoption.note || 'No review note recorded.'}</p>{/if}
          </article>
        {/each}
        <h4>Other supplied results</h4>
        {#if (context.artifactInputs?.length ?? 0) === detail.matchingInputIndexes.length}<p>No other results were supplied.</p>{/if}
        {#each context.artifactInputs ?? [] as input, index}
          {#if !detail.matchingInputIndexes.includes(index)}
            <details class="frozen-input" data-other-input-index={index}>
              <summary>Supplied result {index + 1}</summary>
              <p class="inclusion-rationale">Inclusion rationale: {input.rationale || 'No inclusion rationale recorded.'}</p>
              <ArtifactContent artifact={input.artifact} />
              <details><summary>Frozen result references</summary><p class="object-ref">Source investigation {input.investigationId}<br />Result {input.artifactId}<br />Source context {input.sourceContextId}</p></details>
              {#if input.sourceAdoption}<p class="source-review">Source review when this input was saved: {input.sourceAdoption.decision === 'adopt' ? 'adopted' : 'rejected'}. {input.sourceAdoption.note || 'No review note recorded.'}</p>{/if}
            </details>
          {/if}
        {/each}
        <h4>Supplied evidence</h4>
        {#each context.selections as selection}
          <p class="inclusion-rationale"><span class="object-ref">{selection.threadId} · records {selection.startSeq}–{selection.endSeq}</span><br />{selection.rationale || 'No inclusion rationale recorded.'}</p>
        {/each}
        {#if !context.records.length}<p>No raw records were supplied.</p>{/if}
        {#each context.records as record, index (index)}
          <details class="supplied-record"><summary>[evidence:{record.seq}] · {record.threadId}</summary><EvidenceRecord {record} /></details>
        {/each}
        {#if typeof context.coverage === 'string'}<p class="coverage">{context.coverage}</p>{/if}
        <details class="projected-input"><summary>Exact projected input</summary><pre>{context.projectedPrompt}</pre></details>
        <details><summary>Exact saved context</summary><pre>{JSON.stringify(context, null, 2)}</pre></details>
      </section>
    {/if}
  {/if}
</section>

<style>
  .result-uses { margin-block:20px; border-top:1px solid var(--line); padding-top:14px; min-width:0; overflow-wrap:anywhere; }
  h3 { font-size:19px; font-weight:500; margin:12px 0; }
  h4 { font-size:16px; font-weight:600; margin:16px 0 7px; }
  p { font-size:14px; line-height:1.55; margin:9px 0; }
  button { max-width:100%; margin:5px 8px 5px 0; white-space:normal; }
  .use-list { list-style:none; padding:0; }
  .use-list li { border-left:2px solid var(--line-dark); padding-left:14px; margin-block:22px; }
  .use-list h4 { margin-top:0; }
  .saved-question,.inclusion-rationale { white-space:pre-wrap; }
  .context-status { color:var(--accent); font-size:13px; }
  .object-ref { font:12px/1.55 monospace; color:var(--muted); overflow-wrap:anywhere; }
  .use-preview { margin-top:20px; padding:16px; border:1px solid var(--line-dark); }
  .frozen-input { margin-block:14px; border-block:1px solid var(--line); padding:12px 0; }
  .source-review { border-left:2px solid var(--accent); padding-left:10px; }
  details { margin-block:12px; font-size:13px; }
  summary { cursor:pointer; }
  summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  pre { max-height:390px; max-width:100%; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; padding:12px; background:var(--code); font:12px/1.55 monospace; }
  nav { display:flex; flex-wrap:wrap; }
  @media(max-width:600px) { .use-preview { padding:12px; } }
</style>
