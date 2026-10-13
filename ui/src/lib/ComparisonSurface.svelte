<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Markdown from './Markdown.svelte';
  import WorkContent from './WorkContent.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import LineDiff from './LineDiff.svelte';
  import { contentBlocks } from './semantic';
  import { applyArrangement, compositionKey, contextText, emptyComposition, readComposition, resolveAttention, resolveTarget, artifacts, sameArrangement, undoArrangement } from './comparison';
  import type { ApertureTarget, Arrangement } from './comparison';
  import type { Investigation, InvestigationContext, ContextRecord, InvestigationArtifact } from './types';

  let { open = $bindable(false), initialId = '', requestId = 0 }: { open: boolean; initialId?: string; requestId?: number } = $props();
  let composition = $state(emptyComposition());
  let investigations = $state<Investigation[]>([]);
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
  let disposed = false;
  let editButton: HTMLButtonElement;
  let evidenceHeading: HTMLHeadingElement;
  let recordPage = $state({ left: 0, right: 0 });

  const arranged = $derived(composition.arrangement);
  const left = $derived(resolveTarget(investigations, arranged?.left));
  const right = $derived(resolveTarget(investigations, arranged?.right));
  const focused = $derived(resolveTarget(investigations, composition.focus));
  const focusedArtifact = $derived(resolveAttention(investigations, composition.focus).artifact);
  const focusedBlock = $derived(focusedArtifact ? contentBlocks(focusedArtifact.text).find((block) => block.id === composition.focus?.blockId) : null);
  const support = $derived(focusedBlock?.citations ?? (composition.focus?.seq ? [composition.focus.seq] : []));
  const focusedRecord = $derived(resolveAttention(investigations, composition.focus, focusedBlock?.citations).record);
  const canReview = $derived(!!resolveTarget(investigations, draft.left).context && !!resolveTarget(investigations, draft.right).context && !sameArrangement(arranged, draft));
  const sides = $derived([
    { side: 'left' as const, label: 'A / Baseline', ...left },
    { side: 'right' as const, label: 'B / Competing reading', ...right }
  ]);

  function label(ref: ApertureTarget | null | undefined): string {
    if (!ref) return 'No aperture';
    const { investigation, context, artifact } = resolveTarget(investigations, ref);
    if (!investigation || !context) return `Unavailable · ${ref.investigationId}`;
    const version = ref.artifactId ? ` · ${artifact?.kind === 'eidos-evidence-review' ? 'answer + review receipt' : 'native answer'} ${ref.artifactId.slice(-12)}` : '';
    return `${investigation.title} · revision ${investigation.contexts.indexOf(context) + 1}${version}`;
  }

  function contextFor(item: Investigation): string {
    return draft.lens === 'result' && item.artifact ? item.artifact.contextId : item.currentContextId;
  }

  function bindTarget(side: 'left' | 'right', id: string) {
    const item = investigations.find((i) => i.id === id);
    const contextId = item ? contextFor(item) : '';
    const artifact = artifacts(item).find((candidate) => candidate.contextId === contextId);
    draft = { ...draft, [side]: { investigationId: id, contextId, ...(artifact ? { artifactId: artifact.id } : {}) } };
  }

  function bindContext(side: 'left' | 'right', contextId: string) {
    const item = investigations.find((candidate) => candidate.id === draft[side].investigationId);
    const artifact = artifacts(item).find((candidate) => candidate.contextId === contextId);
    draft = { ...draft, [side]: { investigationId: draft[side].investigationId, contextId, ...(artifact ? { artifactId: artifact.id } : {}) } };
  }

  function setLens(lens: Arrangement['lens']) {
    draft = { ...draft, lens };
    // Only an explicit edit may choose a result for an old context-only binding.
    if (lens === 'result') for (const side of ['left', 'right'] as const) {
      if (!draft[side].artifactId) bindContext(side, draft[side].contextId);
    }
  }

  function beginEdit(seed = '') {
    if (arranged) draft = structuredClone($state.snapshot(arranged));
    if (seed) bindTarget('left', seed);
    if (!draft.left.investigationId && investigations[0]) bindTarget('left', investigations[0].id);
    if (!draft.right.investigationId) {
      const other = investigations.find((i) => i.id !== draft.left.investigationId) ?? investigations[0];
      if (other) bindTarget('right', other.id);
    }
    editing = true; reviewing = false; receipt = '';
  }

  async function refresh() {
    if (inFlight || disposed) return;
    inFlight = true;
    try {
      const response = await fetch('/api/investigations');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Could not load saved investigations.');
      if (disposed) return;
      investigations = result.investigations;
      error = '';
      if (!arranged && !draft.left.investigationId) beginEdit(initialId);
    } catch (cause) {
      if (!disposed) error = cause instanceof Error ? cause.message : String(cause);
    } finally { inFlight = false; loading = false; }
  }

  async function apply() {
    if (!canReview) return;
    composition = applyArrangement($state.snapshot(composition), $state.snapshot(draft));
    editing = false; reviewing = false;
    recordPage = { left: 0, right: 0 };
    receipt = 'Arrangement applied in this browser. Investigation and focus identities retained.';
    await tick(); editButton?.focus();
  }

  async function undo() {
    composition = undoArrangement($state.snapshot(composition));
    recordPage = { left: 0, right: 0 };
    reviewing = false; editing = !composition.arrangement;
    receipt = 'Previous arrangement restored. Current evidence focus retained.';
    await tick(); editButton?.focus();
  }

  async function cancelEdit() {
    reviewing = false; editing = !arranged;
    if (arranged) draft = structuredClone($state.snapshot(arranged));
    await tick(); editButton?.focus();
  }

  function focusBlock(investigation: Investigation, artifact: InvestigationArtifact, block: { id: string; citations: number[] }) {
    const context = investigation.contexts.find((c) => c.id === artifact.contextId);
    const first = context?.records.find((r) => block.citations.includes(r.seq) && artifact.citations.includes(r.seq));
    composition = { ...composition, focus: {
      investigationId: investigation.id, contextId: artifact.contextId, artifactId: artifact.id, blockId: block.id,
      ...(first ? { seq: first.seq, threadId: first.threadId } : {})
    } };
  }

  function focusRecord(investigation: Investigation, context: InvestigationContext, record: ContextRecord) {
    composition = { ...composition, focus: { investigationId: investigation.id, contextId: context.id, seq: record.seq, threadId: record.threadId } };
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
      open = open || composition.open;
    } catch { storageError = true; }
    editing = !composition.arrangement;
    ready = true;
    void refresh();
    const timer = setInterval(() => { if (open) void refresh(); }, 5000);
    return () => { disposed = true; clearInterval(timer); };
  });

  $effect(() => {
    if (!ready) return;
    try { localStorage.setItem(compositionKey, JSON.stringify({ ...composition, open })); storageError = false; }
    catch { storageError = true; }
  });
  $effect(() => {
    if (ready && initialId && requestId !== seenRequest && investigations.some((i) => i.id === initialId)) {
      seenRequest = requestId; beginEdit(initialId);
    }
  });
</script>

<svelte:window onkeydown={keydown} />

<section class="comparison-surface" class:hidden-aperture={!open} data-layout={arranged?.layout ?? 'beside'} aria-label="Reflective comparison">
  <header class="composition-heading">
    <div><div class="eyebrow">Nema / reflective surface</div><h2>Hold two interpretations together.</h2><p>Keep the evidence close. Change the arrangement without losing the inquiry.</p></div>
    <div class="composition-actions">
      <button bind:this={editButton} onclick={() => beginEdit()}>Edit arrangement</button>
      <button disabled={!composition.undo.length} onclick={undo}>Undo arrangement</button>
      <button onclick={() => open = false}>Return to investigation</button>
    </div>
  </header>

  {#if error}<p class="work-error" role="alert">{error} {investigations.length ? 'Showing last fetched state; it may be stale.' : 'Saved references are retained.'} <button onclick={() => void refresh()}>Retry</button></p>{/if}
  {#if storageError}<p class="work-notice" role="status">Browser storage is unavailable. This arrangement will not survive reload.</p>{/if}
  {#if receipt}<p class="composition-receipt" role="status">{receipt}</p>{/if}

  {#if editing}
    <section class="arrangement-editor" aria-label="Arrange this surface">
      {#if !investigations.length}
        <p>{loading ? 'Loading saved investigations…' : 'Save an investigation first. Two saved investigations, or two revisions of one, can share this surface.'}</p>
      {:else}
        <div class="target-editors">
          {#each ['left', 'right'] as side}
            {@const position = side as 'left' | 'right'}
            {@const item = investigations.find((i) => i.id === draft[position].investigationId)}
            <div>
              <label for={`compare-${side}`}>{side === 'left' ? 'A / Retain a baseline' : 'B / Bring another reading'}</label>
              <select id={`compare-${side}`} value={draft[position].investigationId} onchange={(event) => bindTarget(position, event.currentTarget.value)}>
                <option value="">Choose saved investigation</option>
                {#if draft[position].investigationId && !item}<option value={draft[position].investigationId}>Unavailable saved investigation</option>{/if}
                {#each investigations as candidate (candidate.id)}<option value={candidate.id}>{candidate.title} · {candidate.status}</option>{/each}
              </select>
              <label class="small-label" for={`compare-${side}-context`}>Context aperture</label>
              <select id={`compare-${side}-context`} value={draft[position].contextId} onchange={(event) => bindContext(position, event.currentTarget.value)}>
                {#each item?.contexts ?? [] as context, index (context.id)}
                  <option value={context.id}>Revision {index + 1}{context.id === item?.artifact?.contextId ? ' · returned artifact input' : context.id === item?.currentContextId ? ' · current' : ' · historical'}</option>
                {/each}
              </select>
              {#if draft.lens === 'result'}
                <label class="small-label" for={`compare-${side}-artifact`}>Exact returned artifact</label>
                <select id={`compare-${side}-artifact`} bind:value={draft[position].artifactId}>
                  <option value="">No result version bound</option>
                  {#if draft[position].artifactId && !artifacts(item).some((artifact) => artifact.id === draft[position].artifactId)}<option value={draft[position].artifactId}>Unavailable saved artifact</option>{/if}
                  {#each artifacts(item).filter((artifact) => artifact.contextId === draft[position].contextId) as artifact (artifact.id)}
                    <option value={artifact.id}>{artifact.kind === 'eidos-evidence-review' ? 'Native answer + local review receipt' : 'Original native answer'} · {artifact.id.slice(-12)}</option>
                  {/each}
                </select>
              {/if}
            </div>
          {/each}
        </div>
        <div class="arrangement-options">
          <label>Lens <select id="compare-lens" value={draft.lens} onchange={(event) => setLens(event.currentTarget.value as Arrangement['lens'])}><option value="result">Returned work</option><option value="context">Context & evidence</option></select></label>
          <label>Placement <select id="compare-layout" bind:value={draft.layout}><option value="beside">Side by side</option><option value="stacked">Stacked</option></select></label>
          <button class="composition-primary" disabled={!canReview} onclick={() => reviewing = true}>Review arrangement</button>
          {#if arranged}<button onclick={cancelEdit}>Cancel changes</button>{/if}
        </div>
        {#if reviewing}
          <div class="arrangement-review" aria-label="Review arrangement change">
            <h3>Presentation change</h3>
            <div class="proposal-lines"><p><span>−</span> {arranged ? `${label(arranged.left)} / ${label(arranged.right)} · ${arranged.lens} · ${arranged.layout}` : 'No comparison on this surface'}</p><p><span>+</span> {label(draft.left)} / {label(draft.right)} · {draft.lens} · {draft.layout}</p></div>
            <p>Retain {composition.focus ? `focus on ${label(composition.focus)}` : 'the current investigation and source focus'}. Applies only to this browser’s arrangement; no task is launched or conclusion adopted.</p>
            <button class="composition-primary" onclick={apply}>Apply arrangement</button>
            <button onclick={cancelEdit}>Cancel changes</button>
          </div>
        {/if}
      {/if}
    </section>
  {/if}

  {#if arranged}
    <div class="composition-meta"><span>Lens / {arranged.lens === 'result' ? 'returned work' : 'context & evidence'} · v1</span><span>Saved references · browser arrangement · {arranged.layout === 'beside' ? 'side by side' : 'stacked'}</span></div>
    <div class="comparison-apertures">
      {#each sides as item (item.side)}
        <article class="comparison-aperture" data-aperture={item.side} data-investigation-id={arranged[item.side].investigationId} data-context-id={arranged[item.side].contextId} data-artifact-id={arranged[item.side].artifactId ?? ''} aria-label={item.label}>
          <header class="aperture-heading"><span class="eyebrow">{item.label}</span><span class="state-label">{item.investigation?.status ?? 'unavailable'}</span><h3>{item.investigation?.title ?? 'Saved investigation unavailable'}</h3>
            {#if item.investigation && item.context}<p>Revision {item.investigation.contexts.indexOf(item.context) + 1} · {item.context.records.length} frozen records · {new Set(item.context.records.map((r) => r.threadId)).size} threads</p>{/if}
          </header>
          {#if !item.investigation || !item.context}
            <p class="work-notice">This saved reference cannot be resolved by the current server. It has not been rebound. Edit the arrangement to choose an available target.</p>
            <p class="object-ref">{arranged[item.side].investigationId}<br />{arranged[item.side].contextId}</p>
          {:else if arranged.lens === 'context'}
            <div class="context-question"><span class="aperture-caption">Question supplied</span><Markdown source={item.context.question} /></div>
            <div class="context-ranges">
              {#each item.context.selections as selection}<p><strong>{selection.threadId} · {selection.startSeq}–{selection.endSeq}</strong><br />{selection.rationale || 'No inclusion rationale recorded.'}</p>{/each}
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
            <p class="aperture-caption">{artifact.kind === 'eidos-evidence-review' ? 'Native answer + local review receipt' : 'Original native answer'} · citations establish supplied input, not proof</p>
            <WorkContent source={artifact.text} focusedBlockId={composition.focus?.artifactId === artifact.id ? composition.focus.blockId : undefined} onFocus={(block) => focusBlock(item.investigation!, artifact, block)} />
            {#if artifact.unsupportedCitations.length}<p class="work-notice">Outside the supplied packet: {artifact.unsupportedCitations.map((seq) => `[evidence:${seq}]`).join(', ')}. Support is unverified.</p>{/if}
            {#if item.investigation.adoption?.artifactId === artifact.id}<p class="comparison-adoption">Conclusion {item.investigation.adoption.decision === 'adopt' ? 'adopted' : 'rejected'} · {item.investigation.adoption.note || 'No note recorded.'}</p>{/if}
            <details class="aperture-details"><summary>Inspect binding & provenance</summary><p class="object-ref">Artifact {artifact.id}<br />Context {artifact.contextId}<br />Attempt {artifact.attemptId}</p><p>Recorded output: {artifact.outputSeqs.join(', ') || 'No output sequence recorded'}</p><p>Provider context, native instructions, tools and configuration are not fully observed.</p></details>
          {:else}
            <div class="pending-question"><span class="aperture-caption">{['running', 'dispatching'].includes(item.investigation.status) ? 'Question awaiting a result' : item.investigation.status === 'unknown' ? 'Question / outcome unknown' : 'Question in this revision'}</span><Markdown source={item.context.question} /></div>
            <p class="work-muted">{arranged[item.side].artifactId ? 'This exact artifact version is unavailable. Its binding is retained; no other result has been substituted.' : artifacts(item.investigation).length ? 'This arrangement has no pinned result version. Edit the arrangement and select an exact artifact; it will not silently follow the latest result.' : item.investigation.status === 'unknown' ? 'The server has no confirmed outcome. Missing output does not establish that nothing ran.' : item.investigation.status === 'failed' ? 'This attempt failed. No completed artifact is available.' : 'No returned artifact version is bound. Review a result binding when work completes.'}</p>
            {#if item.investigation.attempt?.error}<p class="work-error">{item.investigation.attempt.error}</p>{/if}
            {#if item.investigation.status === 'unknown'}<p class="work-notice">Missing output does not establish that nothing ran. Recovery checks recorded evidence and never resends this attempt.</p>{/if}

          {/if}
          {#if item.investigation?.continuation}
            <div class="pending-question"><span class="aperture-caption">Owner-started local evidence review · {item.investigation.continuation.status}</span><Markdown source={item.investigation.continuation.question} /><p class="work-muted">This is a local disclosure decision, not a new Codex question. Open this saved investigation in the Investigation view to inspect its decisions or respond.</p></div>
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
  {/if}

  <section class="focus-evidence" data-investigation-id={composition.focus?.investigationId} data-context-id={composition.focus?.contextId} aria-label="Focused original evidence">
    <header><div><span class="eyebrow">Focus / original evidence</span><h3 bind:this={evidenceHeading} tabindex="-1">{composition.focus ? 'The source stays with the claim.' : 'Inspect a claim. Keep both readings.'}</h3></div><span class="focus-shortcut">Alt E · evidence</span></header>
    {#if composition.focus}
      <div class="focus-binding"><span>{label(composition.focus)}</span><button onclick={() => composition = { ...composition, focus: null }}>Release focus</button></div>
      {#if !focused.context || (composition.focus.artifactId && !focusedBlock)}
        <p class="work-notice">This focus cannot be resolved. Its saved reference is retained; no other claim has been substituted.</p>
      {:else}
        <div class="evidence-body">
          <div class="evidence-nav">
            <p class="aperture-caption">{focusedBlock ? 'Support cited by this passage' : 'Selected frozen context record'}</p>
            {#each support as seq}
              {@const valid = focused.context.records.some((r) => r.seq === seq) && (!focusedArtifact || focusedArtifact.citations.includes(seq))}
              <button data-evidence-seq={seq} disabled={!valid} aria-pressed={composition.focus.seq === seq} onclick={() => chooseEvidence(seq)}>[evidence:{seq}] {valid ? '' : '· outside packet'}</button>
            {/each}
            {#if !support.length}<p>No evidence cited by this passage. Its support is unverified.</p>{/if}
            {#if focusedBlock}<details><summary>Focused passage</summary><Markdown source={focusedBlock.text} /></details>{/if}
          </div>
          <div class="evidence-record">
            {#if focusedRecord}<EvidenceRecord record={focusedRecord} />
            {:else if support.length}<p class="work-notice">No supplied record selected. References outside this packet cannot be resolved here.</p>
            {:else}<p class="work-muted">Uncited interpretation remains visible above. No source has been inferred for it.</p>{/if}
          </div>
        </div>
      {/if}
    {:else}<p>Select “Inspect support” beside a returned passage, or inspect a frozen context record. Evidence opens here without replacing either aperture.</p>{/if}
  </section>
</section>
