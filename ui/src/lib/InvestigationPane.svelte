<script lang="ts">
  import { onMount } from 'svelte';
  import Markdown from './Markdown.svelte';
  import ContextProvenance from './ContextProvenance.svelte';
  import EvidenceReview from './EvidenceReview.svelte';
  import { sameSelections } from './semantic';
  import type { EvidenceSelection, Investigation, InvestigationContext } from './types';

  let { selections = $bindable([]), onSource, onCompare }: {
    selections: EvidenceSelection[];
    onSource: (selection: EvidenceSelection) => void;
    onCompare: (investigationId: string) => void;
  } = $props();

  const storageKey = 'nema.investigation-draft.v1';
  let investigations = $state<Investigation[]>([]);
  let current = $state<Investigation | null>(null);
  let selectedId = $state('');
  let title = $state('');
  let question = $state('');
  let note = $state('');
  let busy = $state(false);
  let error = $state('');
  let notice = $state('');
  let ready = $state(false);
  let previewId = $state('');
  let poll: ReturnType<typeof setInterval> | undefined;
  let pendingRequest = $state<{ body: string; id: string } | null>(null);

  const activeContext = $derived(current?.contexts.find((context) => context.id === current?.currentContextId));
  const preview = $derived(current?.contexts.find((context) => context.id === previewId) ?? activeContext);
  const baseline = $derived(current?.contexts.find((context) => context.id === preview?.parentContextId));
  const displayedArtifact = $derived(current?.nativeArtifact ?? current?.artifact);
  const artifactContext = $derived(current?.contexts.find((context) => context.id === displayedArtifact?.contextId));
  const dirty = $derived(!!activeContext && (
    activeContext.question !== question || !sameSelections(activeContext.selections, selections)
  ));
  const canSave = $derived(title.trim().length > 0 && question.trim().length > 0 && selections.length > 0 && !busy);
  const threadCount = $derived(new Set(selections.map((selection) => selection.threadId)).size);

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

  function useInvestigation(investigation: Investigation, restoreDraft = true) {
    current = investigation;
    selectedId = investigation.id;
    previewId = investigation.currentContextId;
    if (restoreDraft) {
      const context = investigation.contexts.find((item) => item.id === investigation.currentContextId);
      title = investigation.title;
      question = context?.question ?? '';
      selections = context?.selections.map((selection) => ({ ...selection })) ?? [];
      note = investigation.adoption?.note ?? '';
    }
    investigations = [investigation, ...investigations.filter((item) => item.id !== investigation.id)];
  }

  async function choose(id: string) {
    if (!id || busy) return;
    selectedId = id;
    busy = true;
    error = '';
    notice = '';
    try {
      const result = await api<Investigation>(`/api/investigations/${encodeURIComponent(id)}`);
      if (selectedId === id) useInvestigation(result);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  function newDraft(keepContext = false) {
    current = null;
    selectedId = '';
    previewId = '';
    title = keepContext ? `${title || 'Investigation'} — alternative` : '';
    if (!keepContext) {
      question = '';
      selections = [];
    }
    note = '';
    notice = '';
    error = '';
    pendingRequest = null;
  }

  async function save() {
    if (!canSave || (current && current.status !== 'draft')) return;
    busy = true;
    error = '';
    try {
      const body = current
        ? { parentContextId: current.currentContextId, question, selections }
        : { title, question, selections };
      const serialized = JSON.stringify({ id: current?.id ?? null, ...body });
      if (!pendingRequest || pendingRequest.body !== serialized) {
        pendingRequest = { body: serialized, id: crypto.randomUUID() };
      }
      const path = current ? `/api/investigations/${encodeURIComponent(current.id)}/contexts` : '/api/investigations';
      const saved = await api<Investigation>(path, { requestId: pendingRequest.id, ...body });
      useInvestigation(saved);
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
      if (selectedId === id) useInvestigation(result, false);
      if (action === 'recover') notice = 'Recorded evidence checked. No work was resent.';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      busy = false;
    }
  }

  async function refresh() {
    const id = selectedId;
    if (!id || busy) return;
    try {
      const result = await api<Investigation>(`/api/investigations/${encodeURIComponent(id)}`);
      if (selectedId === id && !busy) {
        current = result;
        investigations = investigations.map((item) => item.id === id ? result : item);
      }
    } catch (cause) {
      if (selectedId === id) error = cause instanceof Error ? cause.message : String(cause);
    }
  }

  function changeRationale(index: number, rationale: string) {
    selections = selections.map((selection, position) => position === index ? { ...selection, rationale } : selection);
  }

  onMount(() => {
    let rememberedId = '';
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (stored && typeof stored === 'object') {
        title = typeof stored.title === 'string' ? stored.title : '';
        question = typeof stored.question === 'string' ? stored.question : '';
        note = typeof stored.note === 'string' ? stored.note : '';
        rememberedId = typeof stored.selectedId === 'string' ? stored.selectedId : '';
        pendingRequest = stored.pendingRequest && typeof stored.pendingRequest.body === 'string' && typeof stored.pendingRequest.id === 'string'
          ? stored.pendingRequest : null;
        selections = Array.isArray(stored.selections) ? stored.selections.filter((item: EvidenceSelection) =>
          item && typeof item.threadId === 'string' && Number.isInteger(item.startSeq) && Number.isInteger(item.endSeq) && typeof item.rationale === 'string'
        ) : [];
      }
    } catch { /* Browser storage is a convenience; saved contexts remain on the server. */ }
    void (async () => {
      try {
        const result = await api<{ investigations: Investigation[] }>('/api/investigations');
        investigations = result.investigations;
        const saved = investigations.find((item) => item.id === rememberedId);
        if (saved) useInvestigation(saved, false);
      } catch (cause) {
        error = cause instanceof Error ? cause.message : String(cause);
      } finally {
        ready = true;
      }
    })();
    poll = setInterval(() => void refresh(), 1500);
    return () => { if (poll) clearInterval(poll); };
  });

  $effect(() => {
    if (!ready) return;
    const draft = JSON.stringify({ selectedId, title, question, selections, note, pendingRequest });
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
    <label for="saved-investigation">Saved work</label>
    <select id="saved-investigation" value={selectedId} disabled={busy} onchange={(event) => event.currentTarget.value ? void choose(event.currentTarget.value) : newDraft()}>
      <option value="">New investigation</option>
      {#each investigations as item (item.id)}
        <option value={item.id}>{item.title} · {item.status}</option>
      {/each}
    </select>
    <button class="work-secondary" disabled={busy} onclick={() => newDraft()}>New investigation</button>
    {#if current}<button class="work-secondary" onclick={() => onCompare(current!.id)}>Compare saved work</button>{/if}
  </div>

  <section class="context-builder" aria-label="Selected context">
    <label for="investigation-title">Name this work</label>
    <input id="investigation-title" bind:value={title} disabled={busy || current !== null} placeholder="Recovery decision across two experiments" />
    <label for="investigation-question">Bounded question</label>
    <textarea id="investigation-question" bind:value={question} disabled={busy} rows="4" placeholder="Compare the approaches using this evidence. Explain what remains unknown."></textarea>

    <div class="context-count">{selections.length} ranges from {threadCount} {threadCount === 1 ? 'thread' : 'threads'}</div>
    {#if !selections.length}
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
      <p>{preview.records.length} frozen evidence records from {new Set(preview.selections.map((selection) => selection.threadId)).size} threads.</p>
      <p class="coverage-note">This packet captures selected app-server evidence and the input below. Provider context, native instructions, tools, and configuration are not fully observed.</p>
      {#if baseline}
        <details class="context-diff" open>
          <summary>Changes from previous revision</summary>
          <p>{removed(baseline, preview).length} removed · {removed(preview, baseline).length} added · {updated(baseline, preview).length} rationale changes</p>
          {#each removed(baseline, preview) as selection}<p class="diff-removed">− {selection.threadId} · {selection.startSeq}–{selection.endSeq}</p>{/each}
          {#each removed(preview, baseline) as selection}<p class="diff-added">+ {selection.threadId} · {selection.startSeq}–{selection.endSeq}</p>{/each}
          {#each updated(baseline, preview) as selection}<p>Rationale: {selection.rationale}</p>{/each}
          {#if baseline.question !== preview.question}
            <p class="diff-removed">Previous question: {baseline.question}</p>
            <p class="diff-added">Current question: {preview.question}</p>
          {:else}<p>Question unchanged.</p>{/if}
        </details>
      {/if}
      <ContextProvenance investigationId={current.id} contextId={preview.id} attemptId={current.attempt?.id} attemptStatus={current.attempt?.status} />
      <details class="exact-input">
        <summary>Exact specialist input · {preview.projectedPrompt.length.toLocaleString()} characters</summary>
        <pre>{preview.projectedPrompt}</pre>
      </details>
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
          <strong>One native specialist turn</strong>
          <p>Read-only policy, temporary working directory, 120-second turn deadline. Ambient native startup integrations are not contained. Native account resources are used; this is not a token or cost cap.</p>
          <button class="work-primary" disabled={busy || dirty || preview.id !== current.currentContextId} onclick={() => act('dispatch', { contextId: current?.currentContextId })}>Start specialist with this context</button>
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
      <section class="investigation-result" aria-label="Specialist result">
        <h3>{current.nativeArtifact ? 'Original native result' : 'Specialist result'}</h3>
        <p class="work-muted">Model interpretation · input {displayedArtifact.contextId}</p>
        <Markdown source={displayedArtifact.text} />
        {#if current.attempt?.threadId && displayedArtifact.outputSeqs.length}
          <button class="source-link" onclick={() => onSource({ threadId: current!.attempt!.threadId!, startSeq: displayedArtifact!.outputSeqs[0], endSeq: displayedArtifact!.outputSeqs.at(-1)!, rationale: '' })}>Inspect recorded native output</button>
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
        {#if !displayedArtifact.citations.length}<p class="work-notice">No selected-evidence citations were returned.</p>{/if}
        {#if displayedArtifact.unsupportedCitations.length}
          <p class="work-error">References outside this packet: {displayedArtifact.unsupportedCitations.map((seq) => `[evidence:${seq}]`).join(', ')}. Their support is unverified.</p>
        {/if}
        {#if current.nativeArtifact && current.artifact}
          <details class="reviewed-artifact"><summary>Reviewed artifact / native answer with local decision receipt</summary><Markdown source={current.artifact.text} /><p class="object-ref">{current.artifact.id}</p></details>
          <p class="work-muted">Adoption below selects this reviewed artifact. The original native answer and its input are preserved.</p>
        {/if}
        {#if current.adoption}
          <div class="adoption-receipt"><strong>{current.adoption.decision === 'adopt' ? 'Conclusion adopted' : 'Conclusion rejected'}</strong><p>{current.adoption.note || 'No note added.'}</p><p class="work-muted">Source history and files remain unchanged.</p></div>
        {:else if current.artifact}
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
    {#key current.id}<EvidenceReview investigation={current} {selections} onUpdate={(value) => { if (selectedId === value.id) useInvestigation(value, false); }} />{/key}
  {/if}

  {#if error}<p class="work-error" role="alert">{error}</p>{/if}
  {#if notice}<p class="work-notice" role="status">{notice}</p>{/if}
</aside>
