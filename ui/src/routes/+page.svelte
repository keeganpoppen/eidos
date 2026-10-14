<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import InvestigationPane from '#lib/InvestigationPane.svelte';
  import ComparisonSurface from '#lib/ComparisonSurface.svelte';
  import FocusPane from '#lib/FocusPane.svelte';
  import Markdown from '#lib/Markdown.svelte';
  import SemanticRail from '#lib/SemanticRail.svelte';
  import ThreadItemCard from '#lib/ThreadItem.svelte';
  import { createHistoryRequests, hasSourceEvidence, historyQuery, readSourceFocus, retainThread, sourceTarget } from '#lib/history.ts';
  import { itemRecords, recordsSelected, type EvidenceEditor } from '#lib/evidence-selection.ts';
  import type {
    EvidenceSelection,
    EvidenceHit,
    InvestigationCapabilities,
    ObserverJob,
    ObserverJobEvent,
    SemanticNode,
    SupportSpan,
    ThreadItem,
    ThreadPayload,
    ThreadResponse,
    ThreadSummary
  } from '#lib/types.ts';

  let threads = $state<ThreadSummary[]>([]);
  let capabilities = $state<InvestigationCapabilities | null>(null);
  const liveAvailable = $derived(capabilities?.legacyLiveActions?.available === true);
  const liveReason = $derived(capabilities?.legacyLiveActions?.reason ?? 'Live model actions require separate resource authorization.');
  let selections = $state<EvidenceSelection[]>([]);
  let evidenceEditor = $state<EvidenceEditor | null>(null);
  let sourceNavigation = $state(0);
  let workMode = $state(true);
  let comparisonOpen = $state(false);
  let comparisonSeed = $state('');
  let comparisonRequest = $state(0);
  let comparisonIntent = $state<'comparison' | 'evidence-chain' | 'alternative-review'>('comparison');
  let comparisonExperimentId = $state('');
  let savedWorkRequest = $state(0);
  let historyAnchorSeq = $state<number | null>(null);
  let recordQuery = $state('');
  let historyNotice = $state('');
  let workspaceReady = $state(false);
  const historyRequests = createHistoryRequests();
  function navigateHistory() { sourceNavigation++; return historyRequests.navigate(); }
  let historyView = '';
  let threadLoads = 0;
  let selectedThread = $state('');
  let thread = $state<ThreadPayload | null>(null);
  let composer = $state('');
  let cwd = $state('');
  let selectedRevision = $state('');
  let selectedNodeId = $state<string | null>(null);
  const selectedSemanticNode = $derived(thread?.outline?.nodes?.find((node) => node.node_id === selectedNodeId) ?? null);
  let focusSpans = $state<SupportSpan[]>([]);
  let sending = $state(false);
  let startingThread = $state(false);
  let observerBusy = $state(false);
  let observerProgress = $state('');
  let observerEvents = $state<ObserverJobEvent[]>([]);
  let status = $state('');
  let error = $state('');

  let threadPoll: ReturnType<typeof setInterval> | undefined;
  let listPoll: ReturnType<typeof setInterval> | undefined;
  const visibleTurns = $derived(thread?.turns ?? []);

  function hasSemanticChildren(node: SemanticNode | null): boolean {
    if (!node || !thread?.outline?.nodes) return false;
    return thread.outline.nodes.some(
      (candidate) => candidate.parent_node_id === node.node_id
    );
  }

  const focusedItems = $derived(
    thread && selectedSemanticNode && !hasSemanticChildren(selectedSemanticNode)
      ? thread.turns
          .flatMap((turn) => turn.items)
          .filter((item) =>
            selectedSemanticNode?.support.some((span) => hasSourceEvidence(item, span))
          )
      : []
  );

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(path, {
      ...init,
      headers: {
        'content-type': 'application/json',
        ...(init?.headers ?? {})
      }
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error ?? `${response.status} ${response.statusText}`);
    }
    return payload as T;
  }

  async function loadThreads() {
    try {
      const result = await api<{ threads: ThreadSummary[] }>('/api/threads');
      threads = result.threads;
      if (!selectedThread && threads.length) {
        selectedThread = threads[0].thread_id;
        await loadThread();
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    }
  }

  async function loadThread(options: { anchorSeq?: number | null; aroundSeq?: number; conditional?: boolean } = {}): Promise<boolean> {
    if (!selectedThread) {
      thread = null;
      return false;
    }
    const id = selectedThread;
    const revision = selectedRevision;
    const isCurrent = historyRequests.request();
    const anchorSeq = options.anchorSeq === undefined ? historyAnchorSeq : options.anchorSeq;
    const knownVersion = options.conditional && thread?.id === id && thread.window.anchorSeq === anchorSeq ? thread.version : undefined;
    threadLoads += 1;
    try {
      const query = historyQuery(revision, anchorSeq, options.aroundSeq, knownVersion);
      const result = await api<ThreadResponse>(
        `/api/threads/${encodeURIComponent(id)}${query}`
      );
      if (id === selectedThread && revision === selectedRevision && isCurrent()) {
        thread = retainThread(thread, result);
        historyAnchorSeq = result.window.anchorSeq;
        error = '';
        return true;
      }
    } catch (cause) {
      if (isCurrent()) error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      threadLoads -= 1;
    }
    return false;
  }

  async function chooseThread(id: string, aroundSeq?: number): Promise<(() => boolean) | null> {
    const isCurrent = navigateHistory();
    selectedThread = id;
    thread = null;
    selectedRevision = '';
    selectedNodeId = null;
    focusSpans = [];
    historyAnchorSeq = null;
    historyNotice = '';
    return await loadThread({ aroundSeq }) && isCurrent() ? isCurrent : null;
  }

  async function newThread() {
    if (!liveAvailable) return;
    startingThread = true;
    error = '';
    try {
      const result = await api<{ threadId: string }>('/api/threads', {
        method: 'POST',
        body: JSON.stringify({ cwd: cwd.trim() || undefined })
      });
      navigateHistory();
      selectedThread = result.threadId;
      thread = null;
      selectedRevision = '';
      selectedNodeId = null;
      focusSpans = [];
      historyAnchorSeq = null;
      status = 'new Codex thread started';
      await loadThreads();
      await loadThread();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      startingThread = false;
    }
  }

  async function send() {
    const text = composer.trim();
    if (!liveAvailable || !selectedThread || !text || sending) return;
    sending = true;
    error = '';
    composer = '';
    try {
      const result = await api<{ turnId: string }>(
        `/api/threads/${encodeURIComponent(selectedThread)}/messages`,
        {
          method: 'POST',
          body: JSON.stringify({ text })
        }
      );
      status = `turn ${result.turnId} started`;
      await loadThread();
    } catch (cause) {
      composer = text;
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      sending = false;
    }
  }

  function handleComposerKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void send();
    }
  }

  function isDimmed(source: { startSeq: number; endSeq: number; recordSeqs?: number[] }) {
    return focusSpans.length > 0 && !focusSpans.some((span) => hasSourceEvidence(source, span));
  }

  function isHighlighted(source: { startSeq: number; endSeq: number; recordSeqs?: number[] }) {
    return focusSpans.length > 0 && focusSpans.some((span) => hasSourceEvidence(source, span));
  }

  function clearFocus() {
    navigateHistory();
    focusSpans = [];
    selectedNodeId = null;
    historyNotice = '';
  }

  function sourceElement(span: SupportSpan): HTMLElement | null {
    const target = sourceTarget(thread?.turns ?? [], span);
    if (!target) return null;
    const turnSelector = `.workspace [data-turn-id="${CSS.escape(target.turnId)}"]`;
    return document.querySelector<HTMLElement>(target.itemId === undefined ? turnSelector : `${turnSelector} [data-item-id="${CSS.escape(target.itemId)}"]`);
  }

  async function focusSource(span: SupportSpan, isCurrent: () => boolean) {
    await tick();
    if (!isCurrent()) return;
    const target = sourceElement(span);
    target?.scrollIntoView({ block: 'center' });
    target?.focus({ preventScroll: true });
  }

  async function selectSemanticNode(node: SemanticNode | null) {
    navigateHistory();
    historyNotice = '';
    selectedNodeId = node?.node_id ?? null;
    // A node belongs to an immutable interpretation, not whichever map is latest.
    if (node && thread?.outline) selectedRevision = thread.outline.revision_id;

    // Aggregate tree nodes are navigation, not giant raw-trace selections.
    // Only leaves project their tight support back onto transcript items.
    focusSpans = node && !hasSemanticChildren(node) ? node.support : [];
    if (!focusSpans.length) return;
    await revealSupport(focusSpans[0]);
  }

  async function revealSupport(span: SupportSpan) {
    const isCurrent = navigateHistory();
    if (!await loadThread({ aroundSeq: span.start }) || !isCurrent()) return;
    historyNotice = '';
    await focusSource(span, isCurrent);
  }

  async function selectRevision(revision: string) {
    navigateHistory();
    selectedRevision = revision;
    selectedNodeId = null;
    focusSpans = [];
    await loadThread();
  }

  async function jumpToItem(item: ThreadItem) {
    const isCurrent = navigateHistory();
    if (!await loadThread({ aroundSeq: item.startSeq }) || !isCurrent()) return;
    await tick();
    if (!isCurrent()) return;
    const selector = `.workspace [data-item-id="${CSS.escape(item.id)}"]`;
    document.querySelector<HTMLElement>(selector)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    });
  }

  async function runObserver() {
    if (!liveAvailable || !selectedThread || observerBusy) return;
    observerBusy = true;
    observerProgress = 'planning';
    observerEvents = [];
    error = '';
    status = 'building map…';
    try {
      const started = await api<{ jobId: string }>(
        `/api/threads/${encodeURIComponent(selectedThread)}/observe`,
        {
          method: 'POST',
          body: JSON.stringify({ maxWindows: 0, effort: 'low' })
        }
      );

      let seenRevisionCount = 0;
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 900));
        const job = await api<ObserverJob>(`/api/jobs/${encodeURIComponent(started.jobId)}`);

        observerEvents = job.events ?? [];
        observerProgress = job.detail || (
          job.totalWindows
            ? `window ${job.currentWindow}/${job.totalWindows}`
            : 'planning retrospective windows'
        );
        status = observerProgress;

        if (job.revisions.length > seenRevisionCount) {
          seenRevisionCount = job.revisions.length;
          selectedRevision = '';
          await loadThread();
          await loadThreads();
        }

        if (job.status === 'completed') {
          status = job.detail || 'retrospective semantic tree updated';
          await loadThread();
          await loadThreads();
          break;
        }
        if (job.status === 'failed') {
          throw new Error(job.error ?? job.detail ?? 'retrospective rewrite failed');
        }
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      observerBusy = false;
      observerProgress = '';
    }
  }

  function addItem(item: ThreadItem) {
    if (!thread || !evidenceEditor || evidenceEditor.disabled) return;
    if (evidenceEditor.add({ threadId: thread.id, recordSeqs: itemRecords(item) })) workMode = true;
  }

  function itemSelected(item: ThreadItem): boolean {
    return !!thread && recordsSelected(selections, thread.id, itemRecords(item));
  }

  function addSemanticEvidence() {
    if (!thread || !selectedSemanticNode || !evidenceEditor || evidenceEditor.disabled) return;
    const added = focusSpans.map((span) => ({
      threadId: thread!.id, startSeq: span.start, endSeq: span.end,
      rationale: selectedSemanticNode!.title
    }));
    if (evidenceEditor.add({ ranges: added })) workMode = true;
  }

  async function showEvidence(hit: EvidenceHit) {
    const isCurrent = await chooseThread(hit.threadId, hit.anchorSeq);
    if (!isCurrent?.() || comparisonOpen) return;
    focusSpans = hit.recordSeqs.map(seq => ({ start: seq, end: seq, weight: 1 }));
    historyNotice = 'Surrounding history for the inspected source. Later updates may differ from the exact inspected records.';
    await focusSource(focusSpans[0], isCurrent);
  }

  async function returnToSource(selection: EvidenceSelection) {
    const isCurrent = await chooseThread(selection.threadId, selection.startSeq);
    if (!isCurrent?.()) return;
    const span = { start: selection.startSeq, end: selection.endSeq, weight: 1 };
    focusSpans = [span];
    await focusSource(span, isCurrent);
  }

  async function goToRecord() {
    const isCurrent = navigateHistory();
    const seq = Number(recordQuery);
    if (!Number.isSafeInteger(seq) || seq < 1) {
      historyNotice = 'Enter a positive record sequence.';
      return;
    }
    const loaded = await loadThread({ aroundSeq: seq });
    if (!isCurrent()) return;
    if (!loaded) {
      historyNotice = error || 'That record is unavailable in this thread.';
      return;
    }
    const span = { start: seq, end: seq, weight: 1 };
    focusSpans = [span];
    selectedNodeId = null;
    historyNotice = `Showing the source page containing record ${seq}.`;
    await focusSource(span, isCurrent);
  }

  async function moveHistory(delta: number) {
    const anchorSeq = delta < 0 ? thread?.window.previousAnchorSeq : thread?.window.nextAnchorSeq;
    if (anchorSeq == null) return;
    const isCurrent = navigateHistory();
    if (!await loadThread({ anchorSeq }) || !isCurrent()) return;
    historyNotice = '';
    await tick();
    if (!isCurrent()) return;
    document.querySelector('.history-navigation')?.scrollIntoView({ block: 'start' });
  }

  function compareInvestigation(id: string, intent: 'comparison' | 'evidence-chain' | 'alternative-review' = 'comparison', experimentId = '') {
    comparisonSeed = id;
    comparisonIntent = intent;
    comparisonExperimentId = intent === 'alternative-review' ? experimentId : '';
    comparisonRequest += 1;
    comparisonOpen = true;
  }

  function returnToSavedWork() {
    savedWorkRequest += 1;
    comparisonOpen = true;
  }

  function inputText(input: Record<string, unknown>): string {
    if (input.type === 'text') return String(input.text ?? '');
    return JSON.stringify(input, null, 2);
  }

  onMount(() => {
    void api<InvestigationCapabilities>('/api/investigations/capabilities').then((value) => capabilities = value).catch(() => {});
    try {
      const saved = readSourceFocus(localStorage.getItem('nema.source-focus.v1'));
      if (saved) {
        selectedThread = saved.threadId;
        selectedRevision = saved.revision;
        focusSpans = saved.spans;
        selectedNodeId = saved.selectedNodeId;
        workMode = saved.workMode;
        historyAnchorSeq = saved.anchorSeq;
      }
    } catch { /* The trace remains available when browser storage is disabled. */ }
    historyView = `${workMode}:${comparisonOpen}`;
    workspaceReady = true;
    void loadThreads();
    if (selectedThread) {
      const isCurrent = navigateHistory();
      void loadThread({ aroundSeq: historyAnchorSeq === null ? focusSpans[0]?.start : undefined }).then((loaded) => {
        if (!loaded || !isCurrent()) return;
        const span = focusSpans.find((candidate) => sourceTarget(thread?.turns ?? [], candidate));
        if (span) void focusSource(span, isCurrent);
      });
    }
    threadPoll = setInterval(() => { if (!threadLoads && !comparisonOpen) void loadThread({ conditional: true }); }, 1500);
    listPoll = setInterval(() => void loadThreads(), 4000);

    return () => {
      navigateHistory();
      if (threadPoll) clearInterval(threadPoll);
      if (listPoll) clearInterval(listPoll);
    };
  });

  $effect(() => {
    const view = `${workMode}:${comparisonOpen}`;
    if (historyView && historyView !== view) untrack(() => navigateHistory());
    historyView = view;
  });

  $effect(() => {
    if (!workspaceReady) return;
    const state = JSON.stringify({ threadId: selectedThread, revision: selectedRevision, spans: focusSpans, workMode, anchorSeq: historyAnchorSeq, selectedNodeId });
    try { localStorage.setItem('nema.source-focus.v1', state); } catch { /* Optional browser focus memory. */ }
  });
</script>

<svelte:head>
  <title>Eidos</title>
  <meta
    name="description"
    content="A live semantic surface over persisted Codex traces."
  />
</svelte:head>

<div class:comparison-mode={comparisonOpen} class:focus-mode={selectedSemanticNode !== null && !workMode} class:work-mode={workMode} class="shell">
  <aside class="thread-rail">
    <div class="brand-block">
      <h1>eidos</h1>
      <p>threads · outline · trace</p>
    </div>

    <nav class="aperture-switch" aria-label="Workbench view">
      <button class:active={workMode && !comparisonOpen} aria-pressed={workMode && !comparisonOpen} onclick={() => { workMode = true; comparisonOpen = false; }}>Investigation</button>
      <button class:active={!workMode && !comparisonOpen} aria-pressed={!workMode && !comparisonOpen} onclick={() => { workMode = false; comparisonOpen = false; }}>Evidence map</button>
      <button class:active={comparisonOpen} aria-pressed={comparisonOpen} onclick={() => comparisonOpen = true}>Compare</button>
    </nav>

    <div class="new-thread">
      <input bind:value={cwd} placeholder="cwd (optional)" aria-label="working directory" />
      <button disabled={startingThread || !liveAvailable} title={liveReason} onclick={newThread}>
        {startingThread ? 'starting…' : 'new thread'}
      </button>
    </div>

    <div class="thread-list">
      {#each threads as summary}
        <button
          class:active={summary.thread_id === selectedThread}
          class="thread-button"
          onclick={() => chooseThread(summary.thread_id)}
        >
          {#if summary.hasSemanticMap}<span class="map-dot" title="semantic map"></span>{/if}
          <strong>{summary.preview || summary.thread_id}</strong>
          <small>{summary.turn_count} turns · {summary.record_count} records</small>
        </button>
      {/each}
    </div>
  </aside>

  <ComparisonSurface bind:open={comparisonOpen} initialId={comparisonSeed} requestId={comparisonRequest} requestIntent={comparisonIntent} requestExperimentId={comparisonExperimentId} browseRequest={savedWorkRequest} {selections} />

  <div class:hidden-aperture={!workMode || comparisonOpen} class="work-aperture">
    <InvestigationPane active={workMode && !comparisonOpen} bind:selections bind:evidenceEditor {threads} {sourceNavigation} onSource={returnToSource} onShowEvidence={showEvidence} onCompare={compareInvestigation} onSavedWork={returnToSavedWork} />
  </div>

  {#if !workMode && !comparisonOpen}
  <SemanticRail
    outline={thread?.outline ?? null}
    revisions={thread?.revisions ?? []}
    {selectedRevision}
    selectedNodeId={selectedSemanticNode?.node_id ?? null}
    onSelectNode={selectSemanticNode}
    onSelectRevision={selectRevision}
    onObserve={runObserver}
    observerAvailable={liveAvailable}
    observerUnavailableReason={liveReason}
    {observerBusy}
    {observerProgress}
    {observerEvents}
  />

  {#if selectedSemanticNode}
    <FocusPane
      node={selectedSemanticNode}
      outline={thread?.outline ?? null}
      items={focusedItems}
      sourceTurns={thread?.turns ?? []}
      onSelectNode={selectSemanticNode}
      onSupport={revealSupport}
      onJump={jumpToItem}
    />
  {/if}

  {/if}

  <main class:hidden-aperture={comparisonOpen} class="workspace" aria-label="Source evidence">
    {#if thread}
      <header class="thread-header">
        <h2>{thread.preview || thread.id}</h2>
        <div class="meta">
          {thread.recordCount} persisted records · seq {thread.lastSeq} · {thread.id}
        </div>
        {#if focusSpans.length}
          <div class="source-focus-notice">
            <span>Source focus:</span>
            {#each focusSpans as span}
              <button
                class="inline-control source-range"
                data-support-start={span.start}
                aria-label={`Open source records ${span.start} to ${span.end}${span.label ? `: ${span.label}` : ''}`}
                aria-current={thread.turns.some((turn) => hasSourceEvidence(turn, span)) ? 'location' : undefined}
                onclick={() => revealSupport(span)}
              >{span.start}–{span.end}{#if span.label} · {span.label}{/if}</button>
            {/each}
            <button class="inline-control" onclick={clearFocus}>Clear focus</button>
            {#if selectedSemanticNode}<button class="inline-control" disabled={!evidenceEditor || evidenceEditor.disabled} title={evidenceEditor?.reason} onclick={addSemanticEvidence}>Add selected evidence to context</button>{/if}
          </div>
        {/if}
      </header>

      <nav class="history-navigation" aria-label="History navigation">
        <div><button disabled={!thread.window.hasEarlier} onclick={() => moveHistory(-1)}>Earlier turns</button><span>Turns {thread.turns.length ? thread.window.startIndex + 1 : 0}–{thread.window.startIndex + thread.turns.length} of {thread.window.totalTurns}</span><button disabled={!thread.window.hasLater} onclick={() => moveHistory(1)}>Later turns</button></div>
        <form onsubmit={(event) => { event.preventDefault(); void goToRecord(); }}><input aria-label="Find source record" type="number" min="1" bind:value={recordQuery} placeholder="Record sequence" /><button type="submit">Go to record</button></form>
        {#if historyNotice}<p role="status">{historyNotice}</p>{/if}
      </nav>

      <div data-testid="history-window" data-anchor-seq={thread.window.anchorSeq} data-version={thread.version}>
      {#each visibleTurns as turn (turn.id)}
        <section
          class:dimmed={isDimmed(turn)}
          class:highlighted={isHighlighted(turn)}
          class="turn"
          data-turn-id={turn.id}
          data-start={turn.startSeq}
          data-end={turn.endSeq}
          tabindex="-1"
        >
          <span class="turn-label">{turn.id} · {turn.eventCount} events</span>

          {#if !turn.items.some((item) => item.type === 'userMessage')}
            {#each turn.inputs as input}
              <article
                class="item-card user"
                data-start={turn.startSeq}
                data-end={turn.endSeq}
              >
                <header><span>user input</span></header>
                <Markdown source={inputText(input)} />
              </article>
            {/each}
          {/if}

          {#each turn.items as item (item.id)}
            <ThreadItemCard
              {item}
              dimmed={isDimmed(item)}
              highlighted={isHighlighted(item)}
              semanticFocus={selectedSemanticNode !== null}
              selected={itemSelected(item)}
              selectionDisabled={!evidenceEditor || evidenceEditor.disabled}
              selectionReason={evidenceEditor?.reason}
              onSelect={addItem}
            />
          {/each}
        </section>
      {/each}
      </div>

      {#if !thread.turns.length}
        <div class="empty-map">
          <strong>EMPTY THREAD</strong>
          <p>Send the first message below. The native app-server events will become the transcript.</p>
        </div>
      {/if}
    {:else}
      <header class="thread-header">
        <h2>NO THREAD SELECTED</h2>
        <div class="meta">start one on the left, or import existing Codex history</div>
      </header>
    {/if}
  </main>
</div>

<div class:hidden-aperture={comparisonOpen} class="composer">
  <div class="composer-inner">
    <textarea
      bind:value={composer}
      disabled={!selectedThread || sending || !liveAvailable}
      onkeydown={handleComposerKeydown}
      placeholder={selectedThread
        ? 'Message Codex · ⌘↵ / Ctrl↵ to send'
        : 'Select or start a thread first.'}
    ></textarea>
    <button disabled={!selectedThread || !composer.trim() || sending || !liveAvailable} title={liveReason} onclick={send}>
      {sending ? 'sending…' : 'send'}
    </button>
  </div>
  {#if error}
    <div class="status-line error">{error}</div>
  {:else if status}
    <div class="status-line">{status}</div>
  {/if}
</div>
