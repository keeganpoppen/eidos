<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Markdown from './Markdown.svelte';
  import ContextProvenance from './ContextProvenance.svelte';
  import RecordedExperiment from './RecordedExperiment.svelte';
  import { artifacts, attempts, outputEvidence } from './comparison';
  import EvidenceReview from './EvidenceReview.svelte';
  import ArtifactContent from './ArtifactContent.svelte';
  import ArtifactLineage from './ArtifactLineage.svelte';
  import CatalogPicker from './CatalogPicker.svelte';
  import { savedWork, type ResultSummary } from './saved-work';
  import { artifactInputDiff, artifactInputKey, artifactKind, changedFrozenArtifactInputs, readArtifactInputs, sameArtifactInputs, type ArtifactSourceTarget } from './artifact-inputs';
  import { sameSelections } from './semantic';
  import type { ArtifactInputSelection, FrozenArtifactInput, EvidenceSelection, Investigation, InvestigationArtifact, InvestigationContext, InvestigationCapabilities } from './types';

  let { selections = $bindable([]), onSource, onCompare }: {
    selections: EvidenceSelection[];
    onSource: (selection: EvidenceSelection) => void;
    onCompare: (investigationId: string, intent?: 'comparison' | 'evidence-chain' | 'alternative-review', experimentId?: string) => void;
  } = $props();

  const storageKey = 'nema.investigation-draft.v1';
  let current = $state<Investigation | null>(null);
  let selectedId = $state('');
  let title = $state('');
  let question = $state('');
  let note = $state('');
  let busy = $state(false);
  let error = $state('');
  let notice = $state('');
  let ready = $state(false);
  let capabilities = $state<InvestigationCapabilities | null>(null);
  let previewId = $state('');
  let poll: ReturnType<typeof setInterval> | undefined;
  let pendingRequest = $state<{ body: string; id: string } | null>(null);
  let artifactInputs = $state<ArtifactInputSelection[]>([]);
  let artifactChoice = $state('');
  let artifactChoiceSummary = $state<ResultSummary | undefined>();
  let resultLabels = $state<ResultSummary[]>([]);
  let navigation = 0;
  let disposed = false;
  let restoreAfterLoad = true;
  let lineageTarget = $state<(ArtifactSourceTarget & { snapshot?: FrozenArtifactInput }) | null>(null);

  const activeContext = $derived(current?.contexts.find((context) => context.id === current?.currentContextId));
  const preview = $derived(current?.contexts.find((context) => context.id === previewId) ?? activeContext);
  const previewAttempt = $derived(attempts(current ?? undefined).find((item) => item.contextId === preview?.id));
  const baseline = $derived(current?.contexts.find((context) => context.id === preview?.parentContextId));
  const displayedArtifact = $derived(current?.artifact?.continuedFrom ? current.artifact : current?.nativeArtifact ?? current?.artifact);
  const displayedAttempt = $derived(attempts(current ?? undefined).find((item) => item.id === displayedArtifact?.attemptId));
  const artifactContext = $derived(current?.contexts.find((context) => context.id === displayedArtifact?.contextId));
  const dirty = $derived(!!activeContext && (
    activeContext.question !== question || !sameSelections(activeContext.selections, selections) || !sameArtifactInputs(activeContext.artifactInputs, artifactInputs)
  ));
  const inputCount = $derived(selections.length + artifactInputs.length);
  const canSave = $derived(title.trim().length > 0 && question.trim().length > 0 && inputCount > 0 && inputCount <= 32 && !busy && ready && (!selectedId || current?.id === selectedId));
  const threadCount = $derived(new Set(selections.map((selection) => selection.threadId)).size);

  function jumpTo(selector: string) {
    document.querySelector(`.investigation-pane ${selector}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function key(selection: EvidenceSelection): string {
    return `${selection.threadId}:${selection.startSeq}:${selection.endSeq}`;
  }

  function removed(from: InvestigationContext, to: InvestigationContext): EvidenceSelection[] {
    return from.selections.filter((selection) => !to.selections.some((other) => key(other) === key(selection)));
  }

  function updated(from: InvestigationContext, to: InvestigationContext): EvidenceSelection[] {
    return to.selections.filter((selection) => from.selections.some((other) => key(other) === key(selection) && other.rationale !== selection.rationale));
  }

  async function api<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(path, body === undefined ? undefined : {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? `${response.status} ${response.statusText}`);
    return payload as T;
  }

  function useInvestigation(investigation: Investigation, restoreDraft = true, mutation = false) {
    if (mutation) savedWork.remember(investigation);
    current = investigation;
    selectedId = investigation.id;
    if (restoreDraft || !previewId) previewId = investigation.currentContextId;
    if (restoreDraft) {
      const context = investigation.contexts.find((item) => item.id === investigation.currentContextId);
      title = investigation.title;
      question = context?.question ?? '';
      selections = context?.selections.map((selection) => ({ ...selection })) ?? [];
      artifactInputs = readArtifactInputs(context?.artifactInputs);
      note = investigation.adoption?.note ?? '';
    }
  }

  async function choose(id: string, restoreDraft = true) {
    if (!id || busy) return;
    selectedId = id;
    current = null;
    restoreAfterLoad = restoreDraft;
    const request = ++navigation;
    busy = true;
    error = '';
    notice = '';
    try {
      const result = await savedWork.view(id);
      if (!disposed && request === navigation && selectedId === id) useInvestigation(result, restoreDraft);
    } catch (cause) {
      if (!disposed && request === navigation) error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      if (!disposed && request === navigation) busy = false;
    }
  }

  function newDraft(keepContext = false) {
    navigation++;
    current = null;
    selectedId = '';
    previewId = '';
    title = keepContext ? `${title || 'Investigation'} — alternative` : '';
    if (!keepContext) {
      question = '';
      selections = [];
      artifactInputs = [];
    }
    note = '';
    notice = '';
    error = '';
    pendingRequest = null;
  }

  function addArtifact() {
    const selected = artifactChoiceSummary;
    if (!selected || busy || inputCount >= 32) return;
    const input = { investigationId: selected.investigationId, artifactId: selected.artifactId, rationale: '' };
    if (!artifactInputs.some((existing) => artifactInputKey(existing) === artifactInputKey(input))) artifactInputs = [...artifactInputs, input];
    resultLabels = [...resultLabels.filter((item) => artifactInputKey(item) !== artifactInputKey(input)), selected];
  }

  function inspectArtifact(input: ArtifactInputSelection | FrozenArtifactInput) {
    lineageTarget = { investigationId: input.investigationId, artifactId: input.artifactId,
      ...('artifact' in input ? { contextId: input.sourceContextId, snapshot: input } : {}) };
  }

  async function useResult(investigation: Investigation, artifact: InvestigationArtifact) {
    const input = { investigationId: investigation.id, artifactId: artifact.id, rationale: '' };
    const sourceTitle = investigation.title;
    newDraft();
    title = `Follow-up: ${sourceTitle}`.slice(0, 200);
    artifactInputs = [input];
    await tick();
    document.querySelector<HTMLTextAreaElement>('#investigation-question')?.focus();
  }

  async function save() {
    if (!canSave || (current && current.status !== 'draft')) return;
    busy = true;
    error = '';
    try {
      const original = current
        ? { parentContextId: current.currentContextId, question, selections }
        : { title, question, selections };
      const body = { ...original, ...(artifactInputs.length ? { artifactInputs: readArtifactInputs(artifactInputs) } : {}) };
      const serialized = JSON.stringify({ id: current?.id ?? null, ...body });
      if (!pendingRequest || pendingRequest.body !== serialized) {
        pendingRequest = { body: serialized, id: crypto.randomUUID() };
      }
      const path = current ? `/api/investigations/${encodeURIComponent(current.id)}/contexts` : '/api/investigations';
      const saved = await api<Investigation>(path, { requestId: pendingRequest.id, ...body });
      useInvestigation(saved, true, true);
      pendingRequest = null;
      notice = 'Context saved. Review its exact input before starting the specialist.';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  async function act(action: 'dispatch' | 'recover' | 'adoption', body: unknown) {
    if (!current || busy) return;
    const id = current.id;
    busy = true;
    error = '';
    notice = '';
    try {
      const result = await api<Investigation>(`/api/investigations/${encodeURIComponent(id)}/${action}`, body);
      if (selectedId === id) useInvestigation(result, false, true);
      if (action === 'recover') notice = 'Recorded evidence checked. No work was resent.';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  async function refresh() {
    const id = selectedId;
    const request = navigation;
    if (!id || !current || busy || !ready) return;
    try {
      const result = await savedWork.view(id);
      if (!disposed && request === navigation && selectedId === id && !busy) current = result;
    } catch (cause) {
      if (!disposed && request === navigation && selectedId === id) error = cause instanceof Error ? cause.message : String(cause);
    }
  }

  function changeRationale(index: number, rationale: string) {
    selections = selections.map((selection, position) => position === index ? { ...selection, rationale } : selection);
  }

  onMount(() => {
    void api<InvestigationCapabilities>('/api/investigations/capabilities').then((value) => capabilities = value).catch(() => {});
    let rememberedId = '';
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (stored && typeof stored === 'object') {
        title = typeof stored.title === 'string' ? stored.title : '';
        question = typeof stored.question === 'string' ? stored.question : '';
        note = typeof stored.note === 'string' ? stored.note : '';
        rememberedId = typeof stored.selectedId === 'string' ? stored.selectedId : '';
        previewId = typeof stored.previewId === 'string' ? stored.previewId : '';
        pendingRequest = stored.pendingRequest && typeof stored.pendingRequest.body === 'string' && typeof stored.pendingRequest.id === 'string'
          ? stored.pendingRequest : null;
        selections = Array.isArray(stored.selections) ? stored.selections.filter((item: EvidenceSelection) =>
          item && typeof item.threadId === 'string' && Number.isInteger(item.startSeq) && Number.isInteger(item.endSeq) && typeof item.rationale === 'string'
        ) : [];
        artifactInputs = readArtifactInputs(stored.artifactInputs);
      }
    } catch { /* Browser storage is a convenience; saved contexts remain on the server. */ }
    selectedId = rememberedId;
    restoreAfterLoad = false;
    const request = ++navigation;
    void (async () => {
      try {
        if (rememberedId) {
          const saved = await savedWork.view(rememberedId);
          if (!disposed && request === navigation) useInvestigation(saved, false);
        }
      } catch (cause) {
        if (!disposed && request === navigation) error = cause instanceof Error ? cause.message : String(cause);
      } finally {
        ready = true;
      }
    })();
    poll = setInterval(() => void refresh(), 1500);
    return () => { disposed = true; navigation++; if (poll) clearInterval(poll); };
  });

  $effect(() => {
    if (!ready) return;
    const draft = JSON.stringify({ selectedId, previewId, title, question, selections, artifactInputs: readArtifactInputs(artifactInputs), note, pendingRequest });
    try { localStorage.setItem(storageKey, draft); } catch { /* Private browsing may disable storage. */ }
  });
</script>

<aside class="investigation-pane" aria-label="Investigation workbench">
  <header class="work-heading">
    <div class="eyebrow">Work / context / result</div>
    <h2>Investigation</h2>
    <p>Bring evidence together, ask a bounded question, keep the result connected to its sources.</p>
  </header>

  <div class="work-picker">
    <CatalogPicker id="saved-investigation" label="Saved work" value={selectedId} selectedLabel={current?.title} disabled={busy} emptyLabel="New investigation" onChoose={(id) => id ? void choose(id) : newDraft()} />
    <button class="work-secondary" disabled={busy} onclick={() => newDraft()}>New investigation</button>
    {#if selectedId && !current && ready && !busy}<button class="work-secondary" onclick={() => choose(selectedId, restoreAfterLoad)}>Retry selected investigation</button>{/if}
    {#if current}<button class="work-secondary" onclick={() => onCompare(current!.id)}>Compare saved work</button>{/if}
    {#if current?.continuation?.inquiry}<button class="work-secondary" onclick={() => jumpTo('.evidence-review')}>Go to inquiry</button><button class="work-secondary" onclick={() => onCompare(current!.id, 'evidence-chain')}>Follow evidence & response</button>{/if}
    {#if current && artifacts(current).length}<button class="work-secondary" onclick={() => jumpTo('.recorded-experiments')}>Go to experiments</button>{/if}
  </div>

  <section class="context-builder" aria-label="Selected context">
    <label for="investigation-title">Name this work</label>
    <input id="investigation-title" bind:value={title} disabled={busy || current !== null} placeholder="Recovery decision across two experiments" />
    <label for="investigation-question">Bounded question</label>
    <textarea id="investigation-question" bind:value={question} disabled={busy} rows="4" placeholder="Compare the approaches using this evidence. Explain what remains unknown."></textarea>

    <div class="context-count">{selections.length} ranges from {threadCount} {threadCount === 1 ? 'thread' : 'threads'} · {artifactInputs.length} exact result{artifactInputs.length === 1 ? '' : 's'}</div>
    {#if !inputCount}
      <p class="work-empty">Use “Add to context” on messages, or select an outline entry and add its evidence. Switch threads to collect another source.</p>
    {/if}
    <ol class="source-list">
      {#each selections as selection, index (key(selection))}
        <li>
          <div class="source-row">
            <button class="source-link" onclick={() => onSource(selection)}>{selection.threadId} · {selection.startSeq}–{selection.endSeq}</button>
            <button class="source-remove" aria-label={`Remove ${selection.threadId} evidence ${selection.startSeq} to ${selection.endSeq}`} disabled={busy} onclick={() => selections = selections.filter((_, position) => position !== index)}>Remove</button>
          </div>
          <input aria-label={`Why include source ${index + 1}`} value={selection.rationale} disabled={busy} placeholder="Why this evidence matters" oninput={(event) => changeRationale(index, event.currentTarget.value)} />
        </li>
      {/each}
    </ol>
    <div class="artifact-picker">
      <CatalogPicker id="context-artifact-picker" label="Include a saved result" kind="artifacts" value={artifactChoice} disabled={busy} emptyLabel="Choose an exact result version" onChoose={(value, item) => { artifactChoice = value; artifactChoiceSummary = item && 'artifactId' in item ? item : undefined; }} />
      <button class="work-secondary" disabled={busy || !artifactChoice || inputCount >= 32} onclick={addArtifact}>Add selected result to context</button>
      <p class="work-muted">Each result keeps its original input and support links. The new packet contains that result; its underlying records are supplied only when separately selected.</p>
    </div>
    <ol class="source-list artifact-input-list">
      {#each artifactInputs as input, index (artifactInputKey(input))}
        {@const source = resultLabels.find((item) => item.investigationId === input.investigationId && item.artifactId === input.artifactId)}
        <li data-selected-artifact-id={input.artifactId}>
          <div class="source-row">
            <button class="source-link" onclick={() => inspectArtifact(input)}>{source?.investigationTitle ?? input.investigationId} · {source ? artifactKind(source) : 'selected exact result'}</button>
            <button class="source-remove" aria-label={`Remove result ${input.artifactId}`} disabled={busy} onclick={() => artifactInputs = artifactInputs.filter((_, position) => position !== index)}>Remove</button>
          </div>
          <p class="object-ref">{input.artifactId}</p>
          <input aria-label={`Why include result ${index + 1}`} value={input.rationale} maxlength="2000" disabled={busy} placeholder="Why this result matters" oninput={(event) => artifactInputs = artifactInputs.map((value, position) => position === index ? { ...value, rationale: event.currentTarget.value } : value)} />
        </li>
      {/each}
    </ol>
    {#if inputCount > 32}<p class="work-error">Select at most 32 evidence ranges and results in total.</p>{/if}
    {#if !current || current.status === 'draft'}
      <button class="work-primary" disabled={!canSave || (!!current && !dirty)} onclick={save}>
        {busy ? 'Saving…' : current ? 'Save context revision' : 'Save and preview context'}
      </button>
      {#if dirty}<p class="work-notice">Selection or question changed. Save a revision before starting work.</p>{/if}
    {:else}
      <p class="work-muted">This attempt keeps its saved context. Changes here can become a separate alternative.</p>
      <button class="work-secondary" disabled={busy} onclick={() => newDraft(true)}>New alternative from selection</button>
    {/if}
    <p class="work-muted">Unsaved selections stay in this browser. Saved contexts and results belong to the persisted investigation.</p>
  </section>

  {#if current && preview}
    <section class="context-preview" aria-label="Saved context preview">
      <h3>Reviewed input</h3>
      <label for="context-revision">Context revision</label>
      <select id="context-revision" bind:value={previewId}>
        {#each current.contexts as context, index (context.id)}
          <option value={context.id}>Revision {index + 1}{context.id === current?.currentContextId ? ' · current' : ' · historical'}</option>
        {/each}
      </select>
      <p class="object-ref">{preview.id}</p>
      <div class="saved-question"><Markdown source={preview.question} /></div>
      <p>{preview.records.length} frozen evidence records from {new Set(preview.selections.map((selection) => selection.threadId)).size} threads · {preview.artifactInputs?.length ?? 0} frozen result inputs.</p>
      <p class="coverage-note">This packet captures selected evidence, exact result inputs and the input below. Provider context, native instructions, tools, and configuration are not fully observed.</p>
      {#if baseline}
        {@const resultDiff = artifactInputDiff(baseline.artifactInputs, preview.artifactInputs)}
        {@const changedResults = changedFrozenArtifactInputs(baseline.artifactInputs, preview.artifactInputs)}
        <details class="context-diff" open>
          <summary>Changes from previous revision</summary>
          <p>Evidence ranges: {removed(baseline, preview).length} removed · {removed(preview, baseline).length} added · {updated(baseline, preview).length} rationale changes</p>
          {#if baseline.artifactInputs?.length || preview.artifactInputs?.length}<p>Result inputs: {resultDiff.removed.length} removed · {resultDiff.added.length} added · {resultDiff.updated.length} rationale changes · {changedResults.length} frozen snapshots changed</p>{/if}
          {#each removed(baseline, preview) as selection}<p class="diff-removed">− {selection.threadId} · {selection.startSeq}–{selection.endSeq}</p>{/each}
          {#each removed(preview, baseline) as selection}<p class="diff-added">+ {selection.threadId} · {selection.startSeq}–{selection.endSeq}</p>{/each}
          {#each updated(baseline, preview) as selection}<p>Rationale: {selection.rationale}</p>{/each}
          {#each resultDiff.removed as input}<p class="diff-removed">− Result {input.artifactId}</p>{/each}
          {#each resultDiff.added as input}<p class="diff-added">+ Result {input.artifactId}</p>{/each}
          {#each resultDiff.updated as input}<p>Result rationale · {input.artifactId}: {input.rationale}</p>{/each}
          {#each changedResults as input}<p>Frozen source snapshot changed · {input.artifactId}. Compare the saved source review and pins in each revision.</p>{/each}
          {#if baseline.question !== preview.question}
            <p class="diff-removed">Previous question: {baseline.question}</p>
            <p class="diff-added">Current question: {preview.question}</p>
          {:else}<p>Question unchanged.</p>{/if}
        </details>
      {/if}
      <ContextProvenance investigationId={current.id} contextId={preview.id} attemptId={previewAttempt?.id} attemptStatus={previewAttempt?.status} />
      <details class="exact-input">
        <summary>Exact specialist input · {preview.projectedPrompt.length.toLocaleString()} characters</summary>
        <pre>{preview.projectedPrompt}</pre>
      </details>
      {#each preview.artifactInputs ?? [] as input (artifactInputKey(input))}
        <section class="frozen-artifact-input" data-frozen-artifact-id={input.artifactId} aria-label="Frozen result input">
          <h4>{artifactKind(input.artifact)}</h4>
          <p>{input.rationale || 'No inclusion rationale recorded.'}</p>
          <p class="object-ref">{input.artifactId}<br />Original input {input.sourceContextId}</p>
          <button class="source-link" onclick={() => inspectArtifact(input)}>Inspect result provenance</button>
          <details><summary>Read frozen result · {outputEvidence(input.artifact)}</summary><ArtifactContent artifact={input.artifact} /></details>
          {#if input.sourceAdoption}<p class="source-review">Source review when selected: {input.sourceAdoption.decision === 'adopt' ? 'adopted' : 'rejected'}. {input.sourceAdoption.note} This records a decision, not proof of the result.</p>{:else}<p class="work-muted">No matching source adoption decision was recorded when this input was selected.</p>{/if}
          <details><summary>Source context and attempt pins</summary><p class="object-ref">Context manifest {input.sourceManifestId ?? 'not recorded'}<br />Attempt manifest {input.sourceAttemptManifestId ?? 'not recorded'}</p></details>
        </section>
      {/each}
      <details class="frozen-evidence">
        <summary>Inspect frozen source evidence</summary>
        {#each preview.records as record (record.seq)}
          <details>
            <summary>[evidence:{record.seq}] · {record.threadId} · {record.method ?? record.direction}</summary>
            <button class="source-link" onclick={() => onSource({ threadId: record.threadId, startSeq: record.seq, endSeq: record.seq, rationale: '' })}>Return to source</button>
            <pre>{record.rawText}</pre>
            <p class="object-ref">SHA-256 {record.sha256}</p>
          </details>
        {/each}
      </details>
      {#if current.status === 'draft'}
        <div class="dispatch-scope">
          <strong>{capabilities?.nativeExecution.mode === 'synthetic' ? 'One synthetic specialist turn' : 'One native specialist turn'}</strong>
          <p>{capabilities?.nativeExecution.reason ?? 'Execution capability has not been established. Native model resources require a separate authorization gate.'}</p>
          <button class="work-primary" disabled={busy || dirty || preview.id !== current.currentContextId || !capabilities?.nativeExecution.available} onclick={() => act('dispatch', { contextId: current?.currentContextId })}>Start specialist with this context</button>
          {#if preview.id !== current.currentContextId}<p>Select the current revision to start work.</p>{/if}
        </div>
      {/if}
    </section>

    <section class="investigation-state" aria-label="Investigation status">
      <div class="work-status"><h3>{current.title}</h3><span class:uncertain={current.status === 'unknown'}>{current.status}</span></div>
      <p class="object-ref">{current.id}</p>
      {#if current.status === 'dispatching' || current.status === 'running'}
        <p>Waiting for this native attempt. You can switch sources or reload; the investigation retains its identity.</p>
      {:else if current.status === 'unknown'}
        <p>Native outcome is unknown. Check recorded evidence to find a completed result. This action never resends the task.</p>
      {:else if current.status === 'failed'}
        <p>The attempt did not complete successfully. Its recorded evidence remains available.</p>
      {/if}
      {#if current.attempt}
        <p class="work-muted">Native attempt {current.attempt.status} · {current.attempt.id}</p>
        {#if current.attempt.threadId}<p class="work-muted">Native thread {current.attempt.threadId}</p>{/if}
        {#if current.attempt.error}<p class="work-error">{current.attempt.error}</p>{/if}
      {/if}
      {#if current.attempt}
        <button class="work-secondary" disabled={busy} onclick={() => act('recover', {})}>Check recorded outcome</button>
      {/if}
    </section>

    {#if displayedArtifact}
      <section class="investigation-result" aria-label="Specialist result" data-result-artifact-id={displayedArtifact.id}>
        <h3>{displayedArtifact.continuedFrom ? 'Follow-up specialist result' : displayedArtifact.kind === 'native-needs-evidence' ? 'Specialist evidence request' : current.nativeArtifact ? 'Original specialist result' : 'Specialist result'}</h3>
        <ArtifactContent artifact={displayedArtifact} context={artifactContext} onArtifact={inspectArtifact} />
        <button class="work-secondary" disabled={busy} onclick={() => useResult(current!, displayedArtifact!)}>New investigation using this result</button>
        <button class="source-link" onclick={() => lineageTarget = { investigationId: current!.id, artifactId: displayedArtifact!.id, contextId: displayedArtifact!.contextId }}>Inspect result provenance</button>
        {#if displayedAttempt?.threadId && displayedArtifact.outputSeqs.length}
          <button class="source-link" onclick={() => onSource({ threadId: displayedAttempt!.threadId!, startSeq: displayedArtifact!.outputSeqs[0], endSeq: displayedArtifact!.outputSeqs.at(-1)!, rationale: '' })}>Inspect recorded native output</button>
        {/if}
        <h4>Cited source evidence</h4>
        <p class="work-muted">A source link confirms the record was supplied; it does not prove the conclusion.</p>
        <div class="citation-links">
          {#each displayedArtifact.citations as seq}
            {@const record = artifactContext?.records.find((item) => item.seq === seq)}
            {#if record}
              <button class="source-link" onclick={() => onSource({ threadId: record.threadId, startSeq: seq, endSeq: seq, rationale: '' })}>[evidence:{seq}] · {record.threadId}</button>
            {/if}
          {/each}
        </div>
        {#if !displayedArtifact.citations.length && !displayedArtifact.artifactCitations?.length}<p class="work-notice">No supplied-input citations were returned.</p>{/if}
        {#each artifacts(current).filter((artifact) => artifact.id !== displayedArtifact.id) as historical (historical.id)}
          <details class="reviewed-artifact" data-result-artifact-id={historical.id}><summary>{artifactKind(historical)} · {outputEvidence(historical)} · retained version</summary><ArtifactContent artifact={historical} context={current.contexts.find((context) => context.id === historical.contextId)} onArtifact={inspectArtifact} /><p class="object-ref">{historical.id}<br />Input {historical.contextId}</p><button class="work-secondary" disabled={busy} onclick={() => useResult(current!, historical)}>New investigation using this result</button><button class="source-link" onclick={() => lineageTarget = { investigationId: current!.id, artifactId: historical.id, contextId: historical.contextId }}>Inspect result provenance</button></details>
        {/each}
        {#if current.adoption}
          <div class="adoption-receipt"><strong>{current.adoption.decision === 'adopt' ? 'Conclusion adopted' : 'Conclusion rejected'}</strong><p>{current.adoption.note || 'No note added.'}</p><p class="work-muted">Source history and files remain unchanged.</p></div>
        {:else if current.artifact && current.status === 'completed' && !['native-needs-evidence', 'native-inquiry-invalid'].includes(current.artifact.kind ?? '') && !(current.continuation?.origin === 'native-specialist' && current.artifact.kind === 'eidos-evidence-review')}
          <label for="adoption-note">Decision note</label>
          <textarea id="adoption-note" bind:value={note} rows="3" placeholder="What should carry forward, and why?"></textarea>
          <div class="decision-actions">
            <button class="work-primary" disabled={busy} onclick={() => act('adoption', { artifactId: current?.artifact?.id, decision: 'adopt', note })}>Adopt conclusion</button>
            <button class="work-secondary" disabled={busy} onclick={() => act('adoption', { artifactId: current?.artifact?.id, decision: 'reject', note })}>Reject conclusion</button>
          </div>
          <p class="work-muted">Records your decision about this artifact. It does not apply a patch or alter the source histories.</p>
        {/if}
      </section>
    {/if}
    {#if current.inquiryAdmissionError}<p class="work-error" role="alert">Inquiry admission: {current.inquiryAdmissionError}</p>{/if}
    {#key current.id}<EvidenceReview investigation={current} {selections} onUpdate={(value) => { if (selectedId === value.id) useInvestigation(value, false, true); }} /><RecordedExperiment investigation={current} onCompare={(experimentId) => onCompare(current!.id, 'alternative-review', experimentId)} />{/key}
  {/if}

  {#if error}<p class="work-error" role="alert">{error}</p>{/if}
  {#if notice}<p class="work-notice" role="status">{notice}</p>{/if}
  <ArtifactLineage target={lineageTarget} onClose={() => lineageTarget = null} />
</aside>

<style>
  .artifact-picker { margin:18px 0; padding:14px 0; border-block:1px solid var(--line); }
  .frozen-artifact-input { margin:18px 0; border-left:2px solid var(--accent); padding:6px 12px; background:var(--selection); }
  .frozen-artifact-input h4 { font-size:16px; margin:6px 0; }
  .source-review { font-size:13px; line-height:1.5; }
  .context-diff p { overflow-wrap:anywhere; }
</style>
