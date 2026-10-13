<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import Markdown from './Markdown.svelte';
  import WorkContent from './WorkContent.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import LineDiff from './LineDiff.svelte';
  import InquirySurface from './InquirySurface.svelte';
  import ArtifactLineage from './ArtifactLineage.svelte';
  import CatalogPicker from './CatalogPicker.svelte';
  import SavedComparisons from './SavedComparisons.svelte';
  import { openSnapshot, sameSnapshotView, snapshotRenderer, supportsBlockFocus, type CompositionSnapshot } from './composition-snapshots';
  import { savedWork, type WorkSummary } from './saved-work';
  import type { ArtifactSourceTarget } from './artifact-inputs';
  import ImprovementReview from './ImprovementReview.svelte';
  import ExperimentEvaluation from './ExperimentEvaluation.svelte';
  import { makeReflectionFixture } from './reflection-fixture';
  import { contentBlocks, rendererVersion } from './semantic';
  import { applyArrangement, changeComparisonLens, compositionKey, compileAttentionRequest, contextText, createTargetRequests, emptyComposition, evidenceChain, matchesExperiment, readComposition, resolveAttention, resolveTarget, artifacts, outputEvidence, sameArrangement, undoArrangement, validateEvidenceChain, validateRecordedExperiment } from './comparison';
  import type { ApertureTarget, Arrangement } from './comparison';
  import type { FrozenArtifactInput, Investigation, InvestigationContext, ContextRecord, InvestigationArtifact, EvidenceSelection, WorkbenchExperiment } from './types';

  let { open = $bindable(false), initialId = '', requestId = 0, requestIntent = 'comparison', requestExperimentId = '', selections = [] }: { open: boolean; initialId?: string; requestId?: number; requestIntent?: 'comparison' | 'evidence-chain' | 'alternative-review'; requestExperimentId?: string; selections?: EvidenceSelection[] } = $props();
  let composition = $state(emptyComposition());
  let savedInvestigations = $state<Investigation[]>([]);
  let fixtureStage = $state<'pending' | 'supplied' | null>(null);
  const fixture = $derived(fixtureStage ? makeReflectionFixture(fixtureStage) : null);
  const investigations = $derived([...savedInvestigations, ...(fixture?.investigations ?? [])]);
  const fixtureChoices = $derived((fixture?.investigations ?? []).map((item): WorkSummary => ({
    id: item.id, title: item.title, status: item.status, createdAtMs: item.createdAtMs, currentContextId: item.currentContextId,
    contextCount: item.contexts.length, artifactCount: artifacts(item).length, attemptStatus: item.attempt?.status ?? null, hasInquiry: !!item.continuation?.inquiry, version: 'fixture'
  })));
  let attentionRequest = $state('');
  let intentError = $state('');
  let intentLoading = $state(false);
  let proposalGeneration = 0;
  let experimentGeneration = 0;
  let experimentViews = $state<Record<string, WorkbenchExperiment>>({});
  let experimentLoading = $state(false);
  let experimentError = $state('');
  let reviewBase = $state('');
  let previewVersion = $state<string | null>(null);
  let draft = $state<Arrangement>({ left: { investigationId: '', contextId: '' }, right: { investigationId: '', contextId: '' }, lens: 'result', layout: 'beside' });
  let editing = $state(false);
  let reviewing = $state(false);
  let ready = $state(false);
  let loading = $state(true);
  let error = $state('');
  let storageError = $state(false);
  let receipt = $state('');
  let seenRequest = -1;
  let inFlight = false;
  let refreshAgain = false;
  const targetRequests = createTargetRequests();
  let disposed = false;
  let editButton: HTMLButtonElement;
  let evidenceHeading: HTMLHeadingElement;
  let recordPage = $state({ left: 0, right: 0 });
  let lineageTarget = $state<(ArtifactSourceTarget & { snapshot?: FrozenArtifactInput }) | null>(null);

  function inspectArtifact(input: FrozenArtifactInput) {
    lineageTarget = { investigationId: input.investigationId, artifactId: input.artifactId, contextId: input.sourceContextId, snapshot: input };
  }

  const arranged = $derived(composition.arrangement);
  const left = $derived(resolveTarget(investigations, arranged?.left));
  const right = $derived(resolveTarget(investigations, arranged?.right));
  const focused = $derived(resolveTarget(investigations, composition.focus));
  const focusedArtifact = $derived(resolveAttention(investigations, composition.focus).artifact);
  const focusSupported = $derived(supportsBlockFocus(composition.focus, snapshotRenderer(composition)));
  const presentationFocus = $derived(focusSupported ? composition.focus : composition.focus ? { ...composition.focus, blockId: undefined } : null);
  const focusedBlock = $derived(focusSupported && focusedArtifact ? contentBlocks(focusedArtifact.text).find((block) => block.id === composition.focus?.blockId) : null);
  const support = $derived(focusedBlock?.citations ?? (composition.focus?.seq ? [composition.focus.seq] : []));
  const focusedRecord = $derived(resolveAttention(investigations, composition.focus, focusedBlock?.citations).record);
  const fallbackRecord = $derived(!focusSupported && focusedArtifact ? focused.context?.records.find((record) => record.seq === composition.focus?.seq && record.threadId === composition.focus.threadId && focusedArtifact.citations.includes(record.seq)) : undefined);
  const canReview = $derived(!!resolveTarget(investigations, draft.left).context && !!resolveTarget(investigations, draft.right).context && !sameArrangement(arranged, draft));
  const inquirySubjects = $derived(investigations.filter((item) => item.continuation?.inquiry));
  const activeSubject = $derived(investigations.find((item) => item.id === draft.left.investigationId && item.continuation?.inquiry) ?? inquirySubjects[0]);
  const activeFixtureExperiment = $derived(arranged && fixture && matchesExperiment(arranged, fixture.experiment) ? fixture.experiment : null);
  const recordedKey = (owner: string, id: string) => JSON.stringify([owner, id]);
  const recordedTarget = $derived(arranged?.experimentId && !arranged.experimentId.startsWith('fixture:') ? { owner: arranged.left.investigationId, id: arranged.experimentId } : null);
  const recordedView = $derived(recordedTarget ? experimentViews[recordedKey(recordedTarget.owner, recordedTarget.id)] : undefined);
  const recordedFailure = $derived(recordedView && arranged ? validateRecordedExperiment(investigations, recordedView) ?? (!matchesExperiment(arranged, recordedView) ? 'The saved experiment does not match these exact comparison targets. No evaluation has been substituted.' : '') : '');
  const activeRecordedExperiment = $derived(recordedView && !recordedFailure ? recordedView : null);
  const sides = $derived([
    { side: 'left' as const, label: 'A / Baseline', ...left },
    { side: 'right' as const, label: 'B / Competing reading', ...right }
  ]);

  function label(ref: ApertureTarget | null | undefined): string {
    if (!ref) return 'No aperture';
    const { investigation, context, artifact } = resolveTarget(investigations, ref);
    if (!investigation || !context) return `Unavailable · ${ref.investigationId}`;
    const version = ref.artifactId ? ` · ${artifactLabel(investigation, artifact)} ${ref.artifactId.slice(-12)}` : '';
    const revision = investigation.contexts.indexOf(context);
    return `${investigation.title} · ${revision < 0 ? 'separately offered context' : `revision ${revision + 1}`}${version}`;
  }

  function artifactLabel(investigation: Investigation | undefined, artifact: InvestigationArtifact | undefined): string {
    if (investigation?.id.startsWith('fixture:')) return artifact?.kind === 'eidos-evidence-review' ? 'synthetic Eidos receipt' : artifact?.kind === 'synthetic-counterfactual' ? 'synthetic counterfactual' : 'synthetic model-output example';
    return outputEvidence(artifact);
  }

  function contextFor(item: Investigation): string {
    return draft.lens === 'result' && item.artifact ? item.artifact.contextId : item.currentContextId;
  }

  function cancelProposalLoad() { proposalGeneration++; intentLoading = false; }

  function editBindings() {
    cancelProposalLoad();
    if (draft.experimentId) freeComparison();
    reviewing = false;
  }

  function bindTarget(side: 'left' | 'right', id: string) {
    const isCurrent = targetRequests.begin(side);
    const item = investigations.find((i) => i.id === id);
    const bind = (value: Investigation) => {
      const contextId = contextFor(value);
      const artifact = artifacts(value).find((candidate) => candidate.contextId === contextId);
      draft = { ...draft, [side]: { investigationId: id, contextId, ...(artifact ? { artifactId: artifact.id } : {}) } };
    };
    if (item) { bind(item); return; }
    draft = { ...draft, [side]: { investigationId: id, contextId: '' } };
    if (!id) return;
    void savedWork.view(id).then((value) => {
      if (disposed || !isCurrent() || draft[side].investigationId !== id) return;
      receiveInvestigation(value);
      bind(value);
    }).catch((cause) => { if (!disposed && isCurrent()) error = cause instanceof Error ? cause.message : String(cause); });
  }

  function bindContext(side: 'left' | 'right', contextId: string) {
    targetRequests.begin(side);
    const item = investigations.find((candidate) => candidate.id === draft[side].investigationId);
    const artifact = artifacts(item).find((candidate) => candidate.contextId === contextId);
    draft = { ...draft, [side]: { investigationId: draft[side].investigationId, contextId, ...(artifact ? { artifactId: artifact.id } : {}) } };
  }

  function setLens(lens: Arrangement['lens']) {
    cancelProposalLoad(); reviewing = false;
    draft = changeComparisonLens($state.snapshot(draft), lens, investigations);
  }

  function beginEdit(seed = '') {
    cancelProposalLoad(); targetRequests.cancel();
    if (arranged) draft = structuredClone($state.snapshot(arranged));
    if (seed) { freeComparison(); bindTarget('left', seed); }
    if (!draft.left.investigationId && investigations[0]) bindTarget('left', investigations[0].id);
    if (!draft.right.investigationId) {
      const other = investigations.find((i) => i.id !== draft.left.investigationId) ?? investigations[0];
      if (other) bindTarget('right', other.id);
    }
    editing = true; reviewing = false; receipt = '';
  }

  function freeComparison() {
    cancelProposalLoad(); targetRequests.cancel();
    draft = { left: draft.left, right: draft.right, lens: draft.lens, layout: draft.layout };
    reviewing = false; intentError = '';
  }

  function reviewDraft() {
    targetRequests.cancel();
    reviewBase = JSON.stringify(arranged);
    reviewing = true;
  }

  function stageIntent(intent: 'evidence-chain' | 'alternative-review', investigationId = activeSubject?.id, experimentId?: string) {
    attentionRequest = JSON.stringify({ version: 1, intent, ...(intent === 'evidence-chain' ? { investigationId } : experimentId ? { investigationId, experimentId } : { origin: 'authored-fixture', experimentId: fixture?.experiment.id }) }, null, 2);
    void previewRequest();
  }

  async function previewRequest() {
    targetRequests.cancel();
    const generation = ++proposalGeneration;
    const requested = attentionRequest;
    const incomingRequest = requestId;
    intentLoading = true; intentError = ''; reviewing = false;
    const isCurrent = () => !disposed && generation === proposalGeneration && requested === attentionRequest && incomingRequest === requestId;
    try {
      const request = JSON.parse(requested);
      let recorded: WorkbenchExperiment | undefined;
      const authoredFixture = fixture && request.experimentId === fixture.experiment.id && (!request.investigationId || request.investigationId === fixture.experiment.baseline.investigationId);
      if (request.intent === 'alternative-review' && !authoredFixture) {
        if (typeof request.investigationId !== 'string' || !request.investigationId || typeof request.experimentId !== 'string' || !request.experimentId) throw new Error('A recorded alternative requires both investigationId and experimentId.');
        const [owner, experiment] = await Promise.all([savedWork.view(request.investigationId), savedWork.experiment(request.investigationId, request.experimentId)]);
        if (!isCurrent()) return;
        receiveInvestigation(owner);
        recorded = experiment;
        experimentViews = { ...experimentViews, [recordedKey(owner.id, experiment.id)]: experiment };
      } else if (typeof request.investigationId === 'string' && !investigations.some((item) => item.id === request.investigationId)) {
        const value = await savedWork.view(request.investigationId);
        if (!isCurrent()) return;
        receiveInvestigation(value);
      }
      if (!isCurrent()) return;
      draft = compileAttentionRequest(request, investigations, recorded ? [recorded] : fixture ? [fixture.experiment] : []);
      intentError = ''; editing = true; reviewDraft(); receipt = '';
    } catch (cause) { if (isCurrent()) intentError = cause instanceof Error ? cause.message : String(cause); }
    finally { if (!disposed && generation === proposalGeneration) intentLoading = false; }
  }

  async function refreshExperiment() {
    const target = recordedTarget;
    const generation = ++experimentGeneration;
    experimentError = ''; experimentLoading = !!target;
    if (!target) return;
    try {
      const value = await savedWork.experiment(target.owner, target.id);
      if (disposed || generation !== experimentGeneration || recordedTarget?.owner !== target.owner || recordedTarget.id !== target.id) return;
      experimentViews = { ...experimentViews, [recordedKey(target.owner, target.id)]: value };
    } catch (cause) {
      if (!disposed && generation === experimentGeneration) experimentError = cause instanceof Error ? cause.message : String(cause);
    } finally { if (generation === experimentGeneration) experimentLoading = false; }
  }

  async function openFixture(stage: 'pending' | 'supplied' = 'pending') {
    fixtureStage = stage;
    await tick();
    stageIntent('evidence-chain', fixture!.inquiry.baseline.investigationId);
  }

  function receiveInvestigation(value: Investigation) {
    savedInvestigations = [...savedInvestigations.filter((item) => item.id !== value.id), value];
  }

  function updateInvestigation(value: Investigation) {
    savedWork.remember(value);
    receiveInvestigation(value);
  }

  function openSavedComparison(snapshot: CompositionSnapshot, owners: Investigation[]) {
    cancelProposalLoad();
    for (const owner of owners) receiveInvestigation(owner);
    // Cancel pending target selections and semantic proposals; a saved snapshot
    // opens its compiled references without consulting current/latest bindings.
    targetRequests.cancel(); seenRequest = requestId;
    composition = openSnapshot($state.snapshot(composition), snapshot);
    draft = structuredClone(snapshot.arrangement);
    editing = false; reviewing = false; intentError = ''; recordPage = { left: 0, right: 0 };
    receipt = `Opened “${snapshot.title}” with its exact saved references and focus.`;
    void refreshExperiment();
  }

  function savedComparison(snapshot: CompositionSnapshot) {
    if (sameSnapshotView(composition, snapshot)) composition = { ...composition, snapshotId: snapshot.id };
  }

  function referencedOwners(): string[] {
    return [...new Set([arranged?.left.investigationId, arranged?.right.investigationId,
      draft.left.investigationId, draft.right.investigationId, composition.focus?.investigationId, initialId]
      .filter((id): id is string => !!id && !id.startsWith('fixture:')))];
  }

  async function refresh() {
    if (disposed || !open) return;
    if (inFlight) { refreshAgain = true; return; }
    inFlight = true;
    try {
      let ids = referencedOwners();
      if (!ids.length && !investigations.length) {
        const page = await savedWork.catalog('catalog');
        ids = page.items.slice(0, 2).map((item) => (item as WorkSummary).id);
      }
      const results = await Promise.allSettled(ids.map((id) => savedWork.view(id)));
      if (disposed) return;
      error = '';
      for (const result of results) {
        if (result.status === 'fulfilled') receiveInvestigation(result.value);
        else error = result.reason instanceof Error ? result.reason.message : String(result.reason);
      }
      // A failed initial selection has no context pin yet. Retrying may finish
      // that explicit selection; existing historical pins are never rebound.
      for (const side of ['left', 'right'] as const) {
        if (draft[side].investigationId && !draft[side].contextId && investigations.some((item) => item.id === draft[side].investigationId)) bindTarget(side, draft[side].investigationId);
      }
      if (!arranged && !draft.left.investigationId && !intentLoading) beginEdit(initialId);
    } catch (cause) {
      if (!disposed) error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      inFlight = false; loading = false;
      if (refreshAgain) { refreshAgain = false; void refresh(); }
    }
  }

  async function apply() {
    if (!canReview) return;
    if (!reviewing || reviewBase !== JSON.stringify(arranged)) { intentError = 'The arrangement changed after review. Review this proposal again.'; reviewing = false; return; }
    const failure = validateEvidenceChain(investigations, draft);
    if (failure) { intentError = failure; return; }
    if (draft.experimentId) {
      const recorded = experimentViews[recordedKey(draft.left.investigationId, draft.experimentId)];
      const fixtureMatches = fixture && matchesExperiment(draft, fixture.experiment);
      const failure = recorded ? validateRecordedExperiment(investigations, recorded) : '';
      if (!fixtureMatches && (!recorded || !matchesExperiment(draft, recorded) || failure)) { intentError = failure || 'The experiment requires its exact baseline and alternative. Preview the named alternative again.'; return; }
    }
    cancelProposalLoad(); targetRequests.cancel();
    composition = applyArrangement($state.snapshot(composition), $state.snapshot(draft));
    editing = false; reviewing = false;
    recordPage = { left: 0, right: 0 };
    receipt = 'Arrangement applied in this browser. Investigation and focus identities retained.';
    await tick(); editButton?.focus();
  }

  async function undo() {
    cancelProposalLoad(); targetRequests.cancel();
    composition = undoArrangement($state.snapshot(composition));
    recordPage = { left: 0, right: 0 };
    reviewing = false; editing = !composition.arrangement;
    receipt = 'Previous arrangement restored. Current evidence focus retained.';
    await tick(); editButton?.focus();
  }

  async function cancelEdit() {
    cancelProposalLoad(); targetRequests.cancel();
    reviewing = false; editing = !arranged;
    if (arranged) draft = structuredClone($state.snapshot(arranged));
    await tick(); editButton?.focus();
  }

  function focusBlock(investigation: Investigation, artifact: InvestigationArtifact, block: { id: string; citations: number[] }) {
    const context = investigation.contexts.find((c) => c.id === artifact.contextId);
    const first = context?.records.find((r) => block.citations.includes(r.seq) && artifact.citations.includes(r.seq));
    composition = { ...composition, focusRendererVersion: rendererVersion, focus: {
      investigationId: investigation.id, contextId: artifact.contextId, artifactId: artifact.id, blockId: block.id,
      ...(first ? { seq: first.seq, threadId: first.threadId } : {})
    } };
  }

  function focusRecord(investigation: Investigation, context: InvestigationContext, record: ContextRecord) {
    composition = { ...composition, focusRendererVersion: rendererVersion, focus: { investigationId: investigation.id, contextId: context.id, seq: record.seq, threadId: record.threadId } };
  }

  function chooseEvidence(seq: number) {
    const record = focused.context?.records.find((r) => r.seq === seq);
    if (!record || !composition.focus || (focusedArtifact && !focusedArtifact.citations.includes(seq))) return;
    composition = { ...composition, focus: { ...composition.focus, seq, threadId: record.threadId } };
  }

  function comparable(item: typeof left): string {
    if (arranged?.lens === 'context') return contextText(item.context);
    return item.artifact?.text ?? '';
  }

  function keydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape' && (editing || reviewing)) { event.preventDefault(); void cancelEdit(); }
    if (event.altKey && event.key.toLowerCase() === 'e' && composition.focus) { event.preventDefault(); evidenceHeading?.focus(); }
  }

  onMount(() => {
    try {
      composition = readComposition(localStorage.getItem(compositionKey));
      const stage = localStorage.getItem('nema.reflection-fixture.v1');
      fixtureStage = stage === 'pending' || stage === 'supplied' ? stage : null;
      open = open || composition.open;
    } catch { storageError = true; }
    editing = !composition.arrangement;
    ready = true;
    void refresh();
    const timer = setInterval(() => { if (open) void refresh(); }, 5000);
    return () => { disposed = true; proposalGeneration++; experimentGeneration++; clearInterval(timer); };
  });

  const experimentKey = $derived(recordedTarget ? recordedKey(recordedTarget.owner, recordedTarget.id) : '');
  $effect(() => {
    void experimentKey;
    if (ready && open) untrack(() => void refreshExperiment());
    else untrack(() => { experimentGeneration++; experimentLoading = false; cancelProposalLoad(); targetRequests.cancel(); });
  });

  const ownerKey = $derived(JSON.stringify(referencedOwners()));
  $effect(() => {
    void ownerKey; void requestId;
    if (ready && open) untrack(() => void refresh());
  });

  $effect(() => {
    if (!ready) return;
    try { localStorage.setItem(compositionKey, JSON.stringify({ ...composition, open })); storageError = false; }
    catch { storageError = true; }
    try { if (fixtureStage) localStorage.setItem('nema.reflection-fixture.v1', fixtureStage); else localStorage.removeItem('nema.reflection-fixture.v1'); } catch { storageError = true; }
  });
  $effect(() => {
    if (ready && initialId && requestId !== seenRequest && (requestIntent !== 'comparison' || investigations.some((i) => i.id === initialId))) {
      seenRequest = requestId;
      if (requestIntent === 'alternative-review') stageIntent('alternative-review', initialId, requestExperimentId);
      else if (requestIntent === 'evidence-chain') stageIntent('evidence-chain', initialId); else beginEdit(initialId);
    }
  });
</script>

<svelte:window onkeydown={keydown} />

<section class="comparison-surface" class:hidden-aperture={!open} data-layout={arranged?.layout ?? 'beside'} aria-label="Reflective comparison">
  <header class="composition-heading">
    <div><div class="eyebrow">Nema / reflective surface</div><h2>Keep the question in view.</h2><p>Arrange the evidence, the alternatives, and what could change your mind.</p></div>
    <div class="composition-actions">
      <button bind:this={editButton} onclick={() => beginEdit()}>Edit arrangement</button>
      <button disabled={!composition.undo.length} onclick={undo}>Undo arrangement</button>
      <button onclick={() => open = false}>Return to investigation</button>
    </div>
  </header>

  {#if error}<p class="work-error" role="alert">{error} {investigations.length ? 'Showing last fetched state; it may be stale.' : 'Saved references are retained.'} <button onclick={() => void refresh()}>Retry</button></p>{/if}
  {#if storageError}<p class="work-notice" role="status">Browser storage is unavailable. This arrangement will not survive reload.</p>{/if}
  {#if receipt}<p class="composition-receipt" role="status">{receipt}</p>{/if}

  <SavedComparisons {composition} active={open} {editing} onOpen={openSavedComparison} onSaved={savedComparison} />

  <section class="attention-intents" aria-label="Organize this investigation">
    <div class="intent-copy"><span class="eyebrow">Arrange attention</span><p>{previewVersion && activeFixtureExperiment ? 'Presentation preview · evidence before interpretation' : 'Choose a relation to bring into view.'}</p></div>
    <div class="intent-actions">
      <button id="arrange-evidence-chain" disabled={!activeSubject} onclick={() => stageIntent('evidence-chain')}>Original evidence → request → result</button>
      <button id="arrange-alternative" disabled={!fixture} onclick={() => stageIntent('alternative-review')}>Compare the named alternative</button>
    </div>
    <details class="structured-attention"><summary>Structured attention request</summary><p>Versioned presentation intent. Preview resolves exact saved bindings; it grants no execution authority.</p><label for="arrangement-request">Request JSON</label><textarea id="arrangement-request" bind:value={attentionRequest} oninput={cancelProposalLoad} rows="5" placeholder={'{"version":1,"intent":"evidence-chain","investigationId":"…"}'}></textarea><button onclick={previewRequest}>Preview attention request</button></details>
    {#if !fixture}
      <div class="fixture-entry"><button onclick={() => openFixture()}>Open synthetic inquiry & experiment</button><span>Authored example · no model or live investigation is created.</span></div>
    {:else}
      <div class="fixture-entry" data-fixture-stage={fixtureStage}><strong>Synthetic inquiry & experiment</strong><span>Explicit fixture · {fixtureStage} stage · no native model run.</span><button onclick={() => { fixtureStage = null; receipt = 'Fixture closed. Saved fixture bindings remain unresolved until it is reopened.'; }}>Close synthetic example</button></div>
    {/if}
    {#if intentLoading}<p role="status">Loading the exact saved experiment and source references…</p>{/if}
    {#if intentError}<p class="work-error" role="alert">{intentError} <button onclick={previewRequest}>Retry attention preview</button></p>{/if}
  </section>

  {#if editing}
    <section class="arrangement-editor" aria-label="Arrange this surface">
      {#if !investigations.length}
        <p>{loading ? 'Loading saved investigations…' : 'No selected investigation is available. Search saved work to choose a target; existing references remain unchanged.'}</p>
      {/if}
        <div class="target-editors">
          {#each ['left', 'right'] as side}
            {@const position = side as 'left' | 'right'}
            {@const item = investigations.find((i) => i.id === draft[position].investigationId)}
            <div>
              <CatalogPicker id={`compare-${side}`} label={side === 'left' ? 'A / Retain a baseline' : 'B / Bring another reading'} value={draft[position].investigationId} selectedLabel={item?.title} active={open} extra={fixtureChoices} onChoose={(id) => { editBindings(); bindTarget(position, id); }} />
              <label class="small-label" for={`compare-${side}-context`}>Context aperture</label>
              <select id={`compare-${side}-context`} value={draft[position].contextId} onchange={(event) => { editBindings(); bindContext(position, event.currentTarget.value); }}>
                {#if draft[position].contextId && !item?.contexts.some((context) => context.id === draft[position].contextId)}<option value={draft[position].contextId}>Unavailable saved context · {draft[position].contextId}</option>{/if}
                {#each item?.contexts ?? [] as context, index (context.id)}
                  <option value={context.id}>Revision {index + 1}{context.id === item?.artifact?.contextId ? ' · returned artifact input' : context.id === item?.currentContextId ? ' · current' : ' · historical'}</option>
                {/each}
              </select>
              {#if draft.lens === 'result'}
                <label class="small-label" for={`compare-${side}-artifact`}>Exact returned artifact</label>
                <select id={`compare-${side}-artifact`} value={draft[position].artifactId ?? ''} onchange={(event) => { editBindings(); targetRequests.begin(position); draft = { ...draft, [position]: { ...draft[position], artifactId: event.currentTarget.value || undefined } }; }}>
                  <option value="">No result version bound</option>
                  {#if draft[position].artifactId && !artifacts(item).some((artifact) => artifact.id === draft[position].artifactId)}<option value={draft[position].artifactId}>Unavailable saved artifact</option>{/if}
                  {#each artifacts(item).filter((artifact) => artifact.contextId === draft[position].contextId) as artifact (artifact.id)}
                    <option value={artifact.id}>{artifactLabel(item, artifact)} · {artifact.id.slice(-12)}</option>
                  {/each}
                </select>
              {/if}
            </div>
          {/each}
        </div>
        <div class="arrangement-options">
          {#if draft.intent}<button onclick={freeComparison}>Use a free comparison</button>{/if}
          <label>Lens <select id="compare-lens" disabled={draft.intent === 'evidence-chain'} value={draft.lens} onchange={(event) => setLens(event.currentTarget.value as Arrangement['lens'])}><option value="result">{draft.intent === 'evidence-chain' ? 'Evidence, question & receipt' : 'Returned work'}</option><option value="context">Context & evidence</option></select></label>
          <label>Placement <select id="compare-layout" value={draft.layout} onchange={(event) => { cancelProposalLoad(); reviewing = false; draft = { ...draft, layout: event.currentTarget.value as Arrangement['layout'] }; }}><option value="beside">Side by side</option><option value="stacked">Stacked</option></select></label>
          <button class="composition-primary" disabled={!canReview} onclick={reviewDraft}>Review arrangement</button>
          {#if arranged}<button onclick={cancelEdit}>Cancel changes</button>{/if}
        </div>
        {#if reviewing}
          <div class="arrangement-review" aria-label="Review arrangement change">
            <h3>Presentation change</h3>
            {#if draft.intent}<p class="intent-rationale">{draft.intent === 'evidence-chain' ? 'Show the original evidence for this conclusion, the additional evidence requested, and the result after it was supplied.' : 'Compare this interpretation with the named alternative. Keep context changes, evidential support, and evaluation together.'}</p>{/if}
            <div class="proposal-lines"><p><span>−</span> {arranged ? `${label(arranged.left)} / ${label(arranged.right)} · ${arranged.lens} · ${arranged.layout}` : 'No comparison on this surface'}</p><p><span>+</span> {label(draft.left)} / {label(draft.right)} · {draft.lens} · {draft.layout}</p></div>
            <p>Retain {composition.focus ? `focus on ${label(composition.focus)}` : 'the current investigation and source focus'}. Applies only to this browser’s arrangement; no task is launched or conclusion adopted.</p>
            {#if draft.inquiry}<p class="object-ref">Inquiry {draft.inquiry.inquiryId}<br />Offered input {draft.inquiry.evidenceContextId ?? 'not yet bound'}<br />Response {draft.inquiry.responseId ?? 'pending'}</p>{/if}
            <button class="composition-primary" onclick={apply}>Apply arrangement</button>
            <button onclick={cancelEdit}>Cancel changes</button>
          </div>
        {/if}
    </section>
  {/if}

  {#if arranged}
    <div class="composition-meta"><span>Lens / {arranged.intent === 'evidence-chain' ? 'evidence, question & receipt' : arranged.lens === 'result' ? 'returned work' : 'context & evidence'} · v1</span><span>Saved references · browser arrangement · {arranged.layout === 'beside' ? 'side by side' : 'stacked'}</span></div>
    {#if arranged.intent === 'evidence-chain'}
      <InquirySurface arrangement={arranged} {investigations} {selections} fixtureInquiry={fixture?.inquiry} focus={presentationFocus} onBlock={focusBlock} onRecord={focusRecord} onUpdate={updateInvestigation} onRebind={() => stageIntent('evidence-chain', arranged.left.investigationId)} onPreview={() => openFixture('supplied')} />
    {:else}
    {#if arranged.experimentId && !activeFixtureExperiment && !recordedTarget}<p class="work-notice">The authored experiment cannot be resolved with these exact bindings. Reopen its synthetic example to inspect it.</p>{/if}
    {#if recordedTarget}
      <section class="recorded-comparison" data-experiment-id={recordedTarget.id} aria-label="Recorded context experiment">
        <header><div><span class="eyebrow">Recorded context experiment</span><h3>Compare the frozen inputs.</h3></div><button id="refresh-recorded-experiment" disabled={experimentLoading} onclick={refreshExperiment}>{experimentLoading ? 'Refreshing review…' : 'Refresh experiment review'}</button></header>
        <p class="object-ref">{recordedTarget.id}</p>
        {#if experimentError}<p class="work-error" role="alert">{experimentError} {recordedView ? 'Showing the last fetched review; it may be stale.' : 'The exact saved comparison targets remain in place.'}</p>{/if}
        {#if recordedFailure}<p class="work-notice">{recordedFailure}</p>{/if}
        {#if activeRecordedExperiment}
          <p>{activeRecordedExperiment.rationale}</p>
          <p class="work-muted">{activeRecordedExperiment.evidenceClass} evidence · baseline result retained · context-only alternative, with no alternative result selected.</p>
          <ExperimentEvaluation experiment={activeRecordedExperiment} />
          <p class="work-muted">Review and rollback remain in the investigation’s experiment panel.</p>
        {:else if experimentLoading}<p role="status">Loading the named experiment. Existing source references stay pinned.</p>{/if}
        {#if left.artifact && left.context && left.investigation}
          <button id="inspect-experiment-baseline" onclick={() => lineageTarget = { investigationId: left.investigation!.id, artifactId: left.artifact!.id, contextId: left.context!.id }}>Inspect retained baseline result</button>
          <details class="retained-baseline"><summary>Retained baseline passages and support</summary><WorkContent source={left.artifact.text} focusedBlockId={presentationFocus?.artifactId === left.artifact.id ? presentationFocus.blockId : undefined} onFocus={(block) => focusBlock(left.investigation!, left.artifact!, block)} /></details>
        {/if}
      </section>
    {/if}
    {#if activeFixtureExperiment}
      <header class="experiment-heading" data-experiment-id={activeFixtureExperiment.id}><span class="eyebrow">Named alternative / synthetic counterfactual</span><h3>{activeFixtureExperiment.name}</h3><p>{activeFixtureExperiment.change}</p><p class="work-muted">Original and counterfactual artifacts have separate identities. No native conversation or workspace fork was executed.</p></header>
    {/if}
    {#if activeFixtureExperiment && fixture && previewVersion === fixture.improvement.afterVersion}
      {@const chain = evidenceChain(fixture.investigations[0])}
      {#if chain}<section data-presentation-preview="evidence-first" aria-label="Evidence first presentation preview"><p class="preview-boundary">Presentation preview · bring the evidence chain before the competing interpretations</p><InquirySurface arrangement={chain} {investigations} {selections} fixtureInquiry={fixture.inquiry} focus={presentationFocus} onBlock={focusBlock} onRecord={focusRecord} onUpdate={updateInvestigation} onRebind={() => stageIntent('evidence-chain', chain.left.investigationId)} onPreview={() => openFixture('supplied')} /></section>{/if}
    {/if}
    <div class="comparison-apertures">
      {#each sides as item (item.side)}
        <article class="comparison-aperture" data-aperture={item.side} data-investigation-id={arranged[item.side].investigationId} data-context-id={arranged[item.side].contextId} data-artifact-id={arranged[item.side].artifactId ?? ''} aria-label={item.label}>
          <header class="aperture-heading"><span class="eyebrow">{item.label}</span><span class="state-label">{item.investigation?.status ?? 'unavailable'}</span><h3>{item.investigation?.title ?? 'Saved investigation unavailable'}</h3>
            {#if item.investigation && item.context}<p>Revision {item.investigation.contexts.indexOf(item.context) + 1} · {item.context.records.length} frozen records · {item.context.artifactInputs?.length ?? 0} result inputs · {new Set(item.context.records.map((r) => r.threadId)).size} threads</p>{/if}
          </header>
          {#if !item.investigation || !item.context}
            <p class="work-notice">This saved reference cannot be resolved by the current server. It has not been rebound. Edit the arrangement to choose an available target.</p>
            <p class="object-ref">{arranged[item.side].investigationId}<br />{arranged[item.side].contextId}</p>
          {:else if arranged.lens === 'context'}
            <div class="context-question"><span class="aperture-caption">Question supplied</span><Markdown source={item.context.question} /></div>
            <div class="context-ranges">
              {#each item.context.selections as selection}<p><strong>{selection.threadId} · {selection.startSeq}–{selection.endSeq}</strong><br />{selection.rationale || 'No inclusion rationale recorded.'}</p>{/each}
              {#each item.context.artifactInputs ?? [] as input}<p><button onclick={() => inspectArtifact(input)}>Inspect result input · {input.artifactId}</button><br />{input.rationale || 'No inclusion rationale recorded.'}</p>{/each}
            </div>
            <h4>Frozen evidence / inspect in place</h4>
            <div class="record-index">
              {#each item.context.records.slice(recordPage[item.side] * 20, (recordPage[item.side] + 1) * 20) as record (`${record.threadId}:${record.seq}`)}
                <button data-evidence-seq={record.seq} onclick={() => focusRecord(item.investigation!, item.context!, record)}>[evidence:{record.seq}] <span>{record.threadId}</span></button>
              {/each}
            </div>
            {#if item.context.records.length > 20}<div class="record-pagination"><button disabled={!recordPage[item.side]} onclick={() => recordPage[item.side]--}>Previous records</button><span>{recordPage[item.side] * 20 + 1}–{Math.min((recordPage[item.side] + 1) * 20, item.context.records.length)} of {item.context.records.length}</span><button disabled={(recordPage[item.side] + 1) * 20 >= item.context.records.length} onclick={() => recordPage[item.side]++}>Next records</button></div>{/if}
            <details class="aperture-details"><summary>Exact input & capture limits</summary><p>{String(item.context.coverage)}</p><pre>{item.context.projectedPrompt}</pre></details>
          {:else if item.artifact}
            {@const artifact = item.artifact}
            <p class="aperture-caption">{artifactLabel(item.investigation, artifact)} · citations establish supplied input, not proof</p>
            <WorkContent source={artifact.text} focusedBlockId={presentationFocus?.artifactId === artifact.id ? presentationFocus.blockId : undefined} onFocus={(block) => focusBlock(item.investigation!, artifact, block)} />
            <button onclick={() => lineageTarget = { investigationId: item.investigation!.id, artifactId: artifact.id, contextId: artifact.contextId }}>Inspect result provenance</button>
            {#if artifact.unsupportedCitations.length}<p class="work-notice">Outside the supplied packet: {artifact.unsupportedCitations.map((seq) => `[evidence:${seq}]`).join(', ')}. Support is unverified.</p>{/if}
            {#if artifact.unsupportedArtifactCitations?.length}<p class="work-notice">Results outside the supplied packet: {artifact.unsupportedArtifactCitations.map((id) => `[artifact:${id}]`).join(', ')}. Support is unverified.</p>{/if}
            {#if item.investigation.adoption?.artifactId === artifact.id}<p class="comparison-adoption">Conclusion {item.investigation.adoption.decision === 'adopt' ? 'adopted' : 'rejected'} · {item.investigation.adoption.note || 'No note recorded.'}</p>{/if}
            <details class="aperture-details"><summary>Inspect binding & provenance</summary><p class="object-ref">Artifact {artifact.id}<br />Context {artifact.contextId}<br />Attempt {artifact.attemptId}</p><p>Recorded output: {artifact.outputSeqs.join(', ') || 'No output sequence recorded'}</p><p>Provider context, native instructions, tools and configuration are not fully observed.</p></details>
          {:else}
            <div class="pending-question"><span class="aperture-caption">{['running', 'dispatching'].includes(item.investigation.status) ? 'Question awaiting a result' : item.investigation.status === 'unknown' ? 'Question / outcome unknown' : 'Question in this revision'}</span><Markdown source={item.context.question} /></div>
            <p class="work-muted">{arranged[item.side].artifactId ? 'This exact artifact version is unavailable. Its binding is retained; no other result has been substituted.' : artifacts(item.investigation).length ? 'This arrangement has no pinned result version. Edit the arrangement and select an exact artifact; it will not silently follow the latest result.' : item.investigation.status === 'unknown' ? 'The server has no confirmed outcome. Missing output does not establish that nothing ran.' : item.investigation.status === 'failed' ? 'This attempt failed. No completed artifact is available.' : 'No returned artifact version is bound. Review a result binding when work completes.'}</p>
            {#if item.investigation.attempt?.error}<p class="work-error">{item.investigation.attempt.error}</p>{/if}
            {#if item.investigation.status === 'unknown'}<p class="work-notice">Missing output does not establish that nothing ran. Recovery checks recorded evidence and never resends this attempt.</p>{/if}

          {/if}
          {#if item.investigation?.continuation && !item.investigation.id.startsWith('fixture:')}
            <div class="pending-question"><span class="aperture-caption">{item.investigation.continuation.origin === 'native-specialist' ? 'Specialist evidence inquiry' : 'Owner-started local evidence review'} · {item.investigation.continuation.status}</span><Markdown source={item.investigation.continuation.question} /><p class="work-muted">{item.investigation.continuation.origin === 'native-specialist' ? 'The specialist requested evidence in a completed native turn. A response does not resume a hidden native stack.' : 'This is an owner-started local disclosure decision.'} Open this saved investigation in the Investigation view to inspect its decisions or respond.</p></div>
          {/if}
        </article>
      {/each}
    </div>

    <details class="comparison-diff">
      <summary>Inspect what changed / {arranged.lens === 'context' ? 'question, ranges, rationale & evidence hashes' : 'returned text'} <span>A → B</span></summary>
      {#if left.context && right.context && (arranged.lens === 'context' || (comparable(left) && comparable(right)))}
        <LineDiff before={comparable(left)} after={comparable(right)} />
        <p class="work-muted">{arranged.lens === 'context' ? 'Hashes expose changed frozen records at the same address. Raw evidence remains in the evidence aperture.' : 'Text differences do not establish which interpretation is correct.'}</p>
      {:else}<p>Both saved targets need comparable {arranged.lens === 'result' ? 'returned artifacts in these revisions' : 'contexts'}.</p>{/if}
    </details>
    {#if activeFixtureExperiment}
      <details class="comparison-diff" open><summary>Context changed / exact inputs and evidence <span>A → B</span></summary><LineDiff before={contextText(left.context)} after={contextText(right.context)} /><p class="work-muted">This authored counterfactual uses later evidence. It is a retrospective test case, not a blinded replay.</p></details>
      <section class="experiment-evaluation" aria-label="What the evaluation established"><span class="eyebrow">Evaluation / {activeFixtureExperiment.evaluation.id}</span><h3>What the comparison establishes</h3><p>{activeFixtureExperiment.evaluation.method}</p><div class="evaluation-columns"><div><h4>Established in this fixture</h4><ul>{#each activeFixtureExperiment.evaluation.established as finding}<li>{finding}</li>{/each}</ul></div><div><h4>Still unknown</h4><ul>{#each activeFixtureExperiment.evaluation.limitations as limit}<li>{limit}</li>{/each}</ul></div></div></section>
      {#if fixture}<ImprovementReview experiment={activeFixtureExperiment} improvement={fixture.improvement} onchange={(version) => previewVersion = version} />{/if}
    {/if}
    {/if}
  {/if}

  <section class="focus-evidence" data-investigation-id={composition.focus?.investigationId} data-context-id={composition.focus?.contextId} aria-label="Focused original evidence">
    <header><div><span class="eyebrow">Focus / original evidence</span><h3 bind:this={evidenceHeading} tabindex="-1">{composition.focus ? 'The source stays with the claim.' : 'Inspect a claim. Keep both readings.'}</h3></div><span class="focus-shortcut">Alt E · evidence</span></header>
    {#if composition.focus}
      <div class="focus-binding"><span>{label(composition.focus)}</span><button onclick={() => composition = { ...composition, focus: null }}>Release focus</button></div>
      {#if !focusSupported}
        <p class="work-notice" data-unresolved-selector>Passage selector unavailable for renderer {composition.focusRendererVersion}. The exact result and record references are retained; no passage is highlighted. Select “Inspect support” again to choose a passage with the installed renderer.</p>
        {#if fallbackRecord}<p class="aperture-caption">Saved record · passage association unresolved</p><EvidenceRecord record={fallbackRecord} />{/if}
      {:else if !focused.context || (composition.focus.artifactId && !focusedArtifact) || (composition.focus.blockId && !focusedBlock)}
        <p class="work-notice">This focus cannot be resolved. Its saved reference is retained; no other claim has been substituted.</p>
      {:else}
        <div class="evidence-body">
          <div class="evidence-nav">
            <p class="aperture-caption">{focusedBlock ? 'Support cited by this passage' : focusedArtifact ? 'Saved record cited by this result · no passage selected' : 'Selected frozen context record'}</p>
            {#each support as seq}
              {@const valid = focused.context.records.some((r) => r.seq === seq) && (!focusedArtifact || focusedArtifact.citations.includes(seq))}
              <button data-evidence-seq={seq} disabled={!valid} aria-pressed={composition.focus.seq === seq} onclick={() => chooseEvidence(seq)}>[evidence:{seq}] {valid ? '' : '· outside packet'}</button>
            {/each}
            {#each focusedBlock?.artifactCitations ?? [] as id}
              {@const input = focusedArtifact?.artifactCitations?.includes(id) ? focused.context.artifactInputs?.find((value) => value.artifactId === id) : undefined}
              <button disabled={!input} onclick={() => input && inspectArtifact(input)}>[artifact:{id}] {input ? '· inspect source result' : '· outside packet'}</button>
            {/each}
            {#if !support.length && !focusedBlock?.artifactCitations.length}<p>{focusedBlock ? 'No evidence cited by this passage. Its support is unverified.' : 'No individual record selected. Inspect support beside a passage to choose one.'}</p>{/if}
            {#if focusedBlock}<details><summary>Focused passage</summary><Markdown source={focusedBlock.text} /></details>{/if}
          </div>
          <div class="evidence-record">
            {#if focusedRecord}<EvidenceRecord record={focusedRecord} />
            {:else if support.length}<p class="work-notice">No supplied record selected. References outside this packet cannot be resolved here.</p>
            {:else if focusedBlock?.artifactCitations.length}<p class="work-muted">Open a cited result to inspect its original input and evidence. Those records were not directly supplied to this packet.</p>
            {:else}<p class="work-muted">Uncited interpretation remains visible above. No source has been inferred for it.</p>{/if}
          </div>
        </div>
      {/if}
    {:else}<p>Select “Inspect support” beside a returned passage, or inspect a frozen context record. Evidence opens here without replacing either aperture.</p>{/if}
  </section>
  <ArtifactLineage target={lineageTarget} onClose={() => lineageTarget = null} />
</section>

<style>
  .recorded-comparison { min-width:0; overflow-wrap:anywhere; border-block:1px solid var(--line); padding:18px 0; margin-bottom:18px; }
  .recorded-comparison header { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
  .recorded-comparison h3 { font-size:23px; font-weight:500; margin:8px 0; }
  .recorded-comparison p { font-size:14px; line-height:1.6; }
  .recorded-comparison button { padding:8px 10px; margin:8px 0; border:1px solid var(--line-dark); background:var(--paper); color:var(--accent); font:inherit; cursor:pointer; }
  .recorded-comparison button:disabled { opacity:.5; cursor:default; }
  .recorded-comparison button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .retained-baseline { margin:10px 0; }
  .attention-intents { border-block:1px solid var(--line); padding:16px 0; margin-bottom:18px; }
  .intent-copy p { font-size:15px; margin:7px 0 12px; }
  .intent-actions { display:flex; gap:10px; flex-wrap:wrap; }
  .fixture-entry { display:flex; align-items:center; flex-wrap:wrap; gap:10px; font-size:13px; color:var(--muted); margin-top:14px; }
  .fixture-entry strong { color:var(--accent); font-weight:500; }
  .structured-attention { margin-top:12px; }
  .structured-attention p { font-size:14px; color:var(--muted); }
  .structured-attention label { display:block; font-size:13px; }
  textarea { display:block; width:100%; box-sizing:border-box; max-width:760px; font:13px/1.5 monospace; margin:8px 0; padding:10px; }
  .intent-rationale { font:20px/1.4 Georgia,serif; max-width:850px; }
  .experiment-heading { padding:20px 0; }
  .preview-boundary { padding:12px; border-left:3px solid var(--accent); background:var(--selection); font-size:14px; }
  .experiment-heading h3 { font-size:28px; font-weight:500; letter-spacing:-.035em; margin:10px 0; }
  .experiment-heading p { font-size:15px; line-height:1.5; max-width:850px; }
  .experiment-evaluation { padding:24px 0; border-bottom:1px solid var(--line); }
  .experiment-evaluation h3 { font-size:24px; font-weight:500; margin:10px 0; }
  .experiment-evaluation p,.experiment-evaluation li { font-size:15px; line-height:1.6; }
  .evaluation-columns { display:grid; grid-template-columns:1fr 1fr; gap:30px; }
  .evaluation-columns h4 { font-size:16px; font-weight:500; }
  .evaluation-columns ul { padding-left:20px; }
  @media(max-width:760px) { .evaluation-columns { grid-template-columns:1fr; gap:10px; } }
</style>
