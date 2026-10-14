<script lang="ts">
  import { tick } from 'svelte';
  import ArtifactContent from './ArtifactContent.svelte';
  import ContextProvenance from './ContextProvenance.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import ResultUses from './ResultUses.svelte';
  import type { ArtifactSourceTarget } from './artifact-inputs';
  import { savedWork, type ArtifactSource } from './saved-work';
  import type { FrozenArtifactInput } from './types';

  type Target = ArtifactSourceTarget & { snapshot?: FrozenArtifactInput; scrollTop?: number };
  let { target, onClose }: { target: Target | null; onClose: () => void } = $props();
  const headingId = $props.id();
  let dialog: HTMLDialogElement;
  let heading: HTMLHeadingElement;
  let resultUses = $state<{ cancel: () => void; hasInteracted: () => boolean }>();
  let trail = $state<Target[]>([]);
  let source = $state<ArtifactSource | null>(null);
  let loading = $state(false);
  let error = $state('');
  const active = $derived(trail.at(-1));
  const resolved = $derived(source);
  const artifact = $derived(active?.snapshot?.artifact ?? resolved?.artifact);
  const context = $derived(resolved?.context);
  const adoption = $derived(active?.snapshot ? active.snapshot.sourceAdoption : source?.adoption ?? null);

  $effect(() => {
    if (target) {
      trail = [target];
      if (dialog && !dialog.open) dialog.showModal();
    } else {
      trail = [];
      if (dialog?.open) dialog.close();
    }
  });

  $effect(() => {
    const ref = active;
    source = null;
    error = '';
    if (!ref) return;
    let cancelled = false;
    loading = true;
    void (async () => {
      try {
        const value = await savedWork.source(ref);
        if (cancelled || !dialog.open) return;
        source = value;
        await tick();
        if (!cancelled && dialog.open && !resultUses?.hasInteracted()) {
          dialog.scrollTop = ref.scrollTop ?? 0;
          heading?.focus({ preventScroll: true });
        }
      } catch (cause) {
        if (!cancelled) error = cause instanceof Error ? cause.message : String(cause);
      } finally { if (!cancelled) loading = false; }
    })();
    return () => { cancelled = true; };
  });

  function follow(input: FrozenArtifactInput) {
    resultUses?.cancel();
    const previous = active ? [...trail.slice(0, -1), { ...active, scrollTop: dialog.scrollTop }] : trail;
    trail = [...previous, { investigationId: input.investigationId, artifactId: input.artifactId, contextId: input.sourceContextId, snapshot: input }];
  }

  function close() { resultUses?.cancel(); onClose(); }
  function back() { resultUses?.cancel(); trail = trail.slice(0, -1); }
</script>

<dialog bind:this={dialog} class="artifact-lineage" aria-labelledby={headingId} onclose={close}>
  <header>
    <div><span class="eyebrow">Result / original support</span><h2 id={headingId} bind:this={heading} tabindex="-1">{source?.investigationTitle ?? 'Result provenance'}</h2></div>
    <button class="lineage-close" onclick={close}>Close result provenance</button>
  </header>
  <nav aria-label="Result lineage navigation">
    <button disabled={trail.length < 2} onclick={back}>Back to previous result</button>
    <span>{trail.length > 1 ? `${trail.length - 1} source link${trail.length > 2 ? 's' : ''} from the selected result` : 'Selected result'}</span>
  </nav>
  {#if active}
    <p class="object-ref">Investigation {active.investigationId}<br />Artifact {active.artifactId}<br />Context {active.contextId ?? artifact?.contextId ?? 'resolving'}</p>
    {#key active}<ResultUses target={active} bind:this={resultUses} />{/key}
    <div data-lineage-artifact-id={active.artifactId} data-lineage-context-id={context?.id}>
      {#if loading}<p role="status">Loading original source context…</p>{/if}
      {#if error}<p class="work-error" role="alert">{error}</p>{/if}
      {#if context}<section class="original-question" aria-label="Original question"><h3>Original question</h3><p>{context.question}</p></section>{/if}
      {#if artifact}
        <ArtifactContent {artifact} {context} onArtifact={follow} />
        {#if adoption}
          <p class="source-adoption">{active.snapshot ? 'Source review when this input was saved' : 'Recorded source review'}: {adoption.decision === 'adopt' ? 'adopted' : 'rejected'}. {adoption.note || 'No note recorded.'} This records a decision about the result, not proof of its claims.</p>
        {:else if artifact.kind !== 'owner-authored-finding'}<p class="work-muted">{active.snapshot ? 'No matching adoption decision was included in this frozen input.' : 'No adoption decision is recorded for this exact result.'}</p>{/if}
      {/if}
      {#if context && artifact && resolved}
        <section aria-label="Original result inputs">
          <h3>Inputs supplied to this result</h3>
          <p class="work-muted">These belong to the original context. Opening them does not add them to your draft.</p>
          {#each context.artifactInputs ?? [] as input}
            <button class="lineage-input" data-artifact-id={input.artifactId} onclick={() => follow(input)}>Inspect input result · {input.artifactId}<small>{input.rationale || 'No inclusion rationale recorded.'}</small></button>
          {/each}
          {#if !context.records.length && !context.artifactInputs?.length}<p>No selected inputs were recorded in this context.</p>{/if}
          {#each context.records as record (record.seq)}
            <details class="lineage-record"><summary>[evidence:{record.seq}] · {artifact.citations.includes(record.seq) ? 'cited by this result' : 'supplied input'} · {record.threadId}</summary><EvidenceRecord {record} /></details>
          {/each}
        </section>
        {#if artifact.evidenceContextId}<p class="work-muted">This receipt separately names offered packet {artifact.evidenceContextId}. It does not establish that a native analysis used that offer.</p>{/if}
        {#if artifact.kind === 'owner-authored-finding'}
          <p class="object-ref">Source context manifest {context.manifestId ?? 'not recorded'}</p>
        {:else}
          <ContextProvenance investigationId={active.investigationId} contextId={context.id} attemptId={resolved.attempt?.id} attemptStatus={resolved.attempt?.status} />
        {/if}
      {/if}
    </div>
  {/if}
</dialog>

<style>
  .artifact-lineage { width:min(900px,calc(100vw - 28px)); max-height:calc(100dvh - 36px); box-sizing:border-box; padding:24px; color:var(--ink); background:var(--paper); border:1px solid var(--line-dark); overflow:auto; font-size:15px; line-height:1.55; }
  .artifact-lineage::backdrop { background:rgb(25 30 25 / .45); }
  header { display:flex; gap:18px; align-items:flex-start; justify-content:space-between; }
  h2 { margin:5px 0 12px; font-size:24px; font-weight:500; }
  h3 { font-size:19px; font-weight:500; margin:22px 0 10px; }
  nav { display:flex; gap:12px; align-items:center; flex-wrap:wrap; border-block:1px solid var(--line); padding:10px 0; }
  nav span { font-size:13px; color:var(--muted); }
  button { cursor:pointer; padding:7px 10px; font:inherit; font-size:13px; border:1px solid var(--line-dark); color:var(--accent); background:transparent; overflow-wrap:anywhere; }
  button:disabled { opacity:.5; cursor:default; }
  button:focus-visible,summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  .lineage-input { display:block; text-align:left; width:100%; margin:8px 0; }
  .lineage-input small { display:block; color:var(--muted); margin-top:4px; }
  .lineage-record { padding:10px 0; border-bottom:1px solid var(--line); }
  summary { cursor:pointer; font-size:13px; margin-bottom:10px; }
  .object-ref { font:12px/1.6 monospace; overflow-wrap:anywhere; }
  .source-adoption { border-left:2px solid var(--accent); padding-left:12px; font-size:14px; }
  .original-question p { white-space:pre-wrap; overflow-wrap:anywhere; }
  @media(max-width:600px) { .artifact-lineage { padding:16px; } header { flex-wrap:wrap; gap:6px; } }
</style>
