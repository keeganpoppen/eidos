<script lang="ts">
  import { onMount, tick } from 'svelte';
  import InvestigationPane from '#lib/InvestigationPane.svelte';
  import ComparisonSurface from '#lib/ComparisonSurface.svelte';
  import FocusPane from '#lib/FocusPane.svelte';
  import Markdown from '#lib/Markdown.svelte';
  import SemanticRail from '#lib/SemanticRail.svelte';
  import ThreadItemCard from '#lib/ThreadItem.svelte';
  import type {
    EvidenceSelection,
    InvestigationCapabilities,
    ObserverJob,
    ObserverJobEvent,
    SemanticNode,
    SupportSpan,
    ThreadItem,
    ThreadPayload,
    ThreadSummary
  } from '#lib/types.ts';

  let threads = $state<ThreadSummary[]>([]);
  let capabilities = $state<InvestigationCapabilities | null>(null);
  const liveAvailable = $derived(capabilities?.legacyLiveActions?.available === true);
  const liveReason = $derived(capabilities?.legacyLiveActions?.reason ?? 'Live model actions require separate resource authorization.');
  let selections = $state<EvidenceSelection[]>([]);
  let workMode = $state(true);
  let comparisonOpen = $state(false);
  let comparisonSeed = $state('');
  let comparisonRequest = $state(0);
  let comparisonIntent = $state<'comparison' | 'evidence-chain'>('comparison');
  let historyStart = $state(0);
  const historyWindow = 40;
  let recordQuery = $state('');
  let historyNotice = $state('');
  let workspaceReady = $state(false);
  let threadRequest = 0;
  let threadLoads = 0;
  let selectedThread = $state('');
  let thread = $state<ThreadPayload | null>(null);
  let composer = $state('');
  let cwd = $state('');
  let selectedRevision = $state('');
  let selectedSemanticNode = $state<SemanticNode | null>(null);
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
  const visibleTurns = $derived(thread?.turns.slice(historyStart, historyStart + historyWindow) ?? []);

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
            selectedSemanticNode?.support.some((span) =>
              item.startSeq <= span.end && span.start <= item.endSeq
            )
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

  async function loadThread() {
    if (!selectedThread) {
      thread = null;
      return;
    }
    const id = selectedThread;
    const revision = selectedRevision;
    const request = ++threadRequest;
    threadLoads += 1;
    try {
      const query = revision ? `?revision=${encodeURIComponent(revision)}` : '';
      const result = await api<ThreadPayload>(
        `/api/threads/${encodeURIComponent(id)}${query}`
      );
      if (id === selectedThread && revision === selectedRevision && request === threadRequest) {
        thread = result;
        if (historyStart >= result.turns.length) historyStart = Math.max(0, Math.floor((result.turns.length - 1) / historyWindow) * historyWindow);
        error = '';
      }
    } catch (cause) {
      if (request === threadRequest) error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      threadLoads -= 1;
    }
  }

  async function chooseThread(id: string) {
    selectedThread = id;
    thread = null;
    selectedRevision = '';
    selectedSemanticNode = null;
    focusSpans = [];
    historyStart = 0;
    historyNotice = '';
    await loadThread();
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
      selectedThread = result.threadId;
      selectedRevision = '';
      selectedSemanticNode = null;
      focusSpans = [];
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

  function overlaps(start: number, end: number, span: SupportSpan) {
    return start <= span.end && span.start <= end;
  }

  function isDimmed(start: number, end: number) {
    return focusSpans.length > 0 && !focusSpans.some((span) => overlaps(start, end, span));
  }

  function isHighlighted(start: number, end: number) {
    return focusSpans.length > 0 && focusSpans.some((span) => overlaps(start, end, span));
  }

  function selectSemanticNode(node: SemanticNode | null) {
    selectedSemanticNode = node;

    // Aggregate tree nodes are navigation, not giant raw-trace selections.
    // Only leaves project their tight support back onto transcript items.
    focusSpans = node && !hasSemanticChildren(node) ? node.support : [];
    if (!focusSpans.length) return;
    revealSpan(focusSpans[0].start, focusSpans[0].end);

    requestAnimationFrame(() => {
      const regions = [
        ...document.querySelectorAll<HTMLElement>('.workspace [data-start][data-end]')
      ];
      const first = regions.find((element) => {
        const start = Number(element.dataset.start ?? 0);
        const end = Number(element.dataset.end ?? start);
        return focusSpans.some((span) => overlaps(start, end, span));
      });
      first?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  async function selectRevision(revision: string) {
    selectedRevision = revision;
    selectedSemanticNode = null;
    focusSpans = [];
    await loadThread();
  }

  async function jumpToItem(item: ThreadItem) {
    revealSpan(item.startSeq, item.endSeq);
    await tick();
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

  function selectionKey(selection: EvidenceSelection): string {
    return `${selection.threadId}:${selection.startSeq}:${selection.endSeq}`;
  }

  function addItem(item: ThreadItem) {
    if (!thread) return;
    const source = { threadId: thread.id, startSeq: item.startSeq, endSeq: item.endSeq, rationale: '' };
    const exists = selections.some((selection) => selectionKey(selection) === selectionKey(source));
    selections = exists
      ? selections.filter((selection) => selectionKey(selection) !== selectionKey(source))
      : [...selections, source];
    workMode = true;
  }

  function itemSelected(item: ThreadItem): boolean {
    return selections.some((selection) => selection.threadId === thread?.id && selection.startSeq === item.startSeq && selection.endSeq === item.endSeq);
  }

  function addSemanticEvidence() {
    if (!thread || !selectedSemanticNode) return;
    const added = focusSpans.map((span) => ({
      threadId: thread!.id, startSeq: span.start, endSeq: span.end,
      rationale: selectedSemanticNode!.title
    }));
    selections = [...selections, ...added.filter((source) => !selections.some((selection) => selectionKey(selection) === selectionKey(source)))];
    workMode = true;
  }

  async function returnToSource(selection: EvidenceSelection) {
    await chooseThread(selection.threadId);
    if (selectedThread !== selection.threadId) return;
    focusSpans = [{ start: selection.startSeq, end: selection.endSeq, weight: 1 }];
    revealSpan(selection.startSeq, selection.endSeq);
    await tick();
    requestAnimationFrame(() => {
      const regions = [...document.querySelectorAll<HTMLElement>('.workspace .item-card[data-start][data-end], .workspace .turn[data-start][data-end]')];
      const matches = regions.filter((element) => overlaps(Number(element.dataset.start), Number(element.dataset.end), focusSpans[0]));
      const target = matches.find((element) => element.classList.contains('item-card')) ?? matches[0];
      target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      target?.focus({ preventScroll: true });
    });
  }

  function revealSpan(start: number, end: number): boolean {
    const index = thread?.turns.findIndex((turn) => overlaps(turn.startSeq, turn.endSeq, { start, end, weight: 1 })) ?? -1;
    if (index < 0) return false;
    historyStart = Math.floor(index / historyWindow) * historyWindow;
    return true;
  }

  async function goToRecord() {
    const seq = Number(recordQuery);
    if (!Number.isSafeInteger(seq) || seq < 1 || !revealSpan(seq, seq)) {
      historyNotice = 'That record is not in the loaded thread.';
      return;
    }
    focusSpans = [{ start: seq, end: seq, weight: 1 }];
    selectedSemanticNode = null;
    historyNotice = `Showing the turn range containing sequence ${seq}. Interleaved records may belong to another thread.`;
    await tick();
    document.querySelector<HTMLElement>('.workspace .item-card.highlighted')?.scrollIntoView({ block: 'center' });
  }

  async function moveHistory(delta: number) {
    historyStart = Math.max(0, Math.min(historyStart + delta * historyWindow, Math.floor(Math.max(0, (thread?.turns.length ?? 1) - 1) / historyWindow) * historyWindow));
    await tick();
    document.querySelector('.history-navigation')?.scrollIntoView({ block: 'start' });
  }

  function compareInvestigation(id: string, intent: 'comparison' | 'evidence-chain' = 'comparison') {
    comparisonSeed = id;
    comparisonIntent = intent;
    comparisonRequest += 1;
    comparisonOpen = true;
  }

  function inputText(input: Record<string, unknown>): string {
    if (input.type === 'text') return String(input.text ?? '');
    return JSON.stringify(input, null, 2);
  }

  onMount(() => {
    void api<InvestigationCapabilities>('/api/investigations/capabilities').then((value) => capabilities = value).catch(() => {});
    try {
      const saved = JSON.parse(localStorage.getItem('nema.source-focus.v1') ?? 'null');
      if (saved && typeof saved.threadId === 'string') {
        selectedThread = saved.threadId;
        selectedRevision = typeof saved.revision === 'string' ? saved.revision : '';
        focusSpans = Array.isArray(saved.spans) ? saved.spans.filter((span: SupportSpan) => Number.isInteger(span.start) && Number.isInteger(span.end)) : [];
        workMode = saved.workMode !== false;
        historyStart = Number.isSafeInteger(saved.historyStart) && saved.historyStart >= 0 ? saved.historyStart : 0;
      }
    } catch { /* The trace remains available when browser storage is disabled. */ }
    workspaceReady = true;
    void loadThreads();
    if (selectedThread) void loadThread();
    threadPoll = setInterval(() => { if (!threadLoads && !comparisonOpen) void loadThread(); }, 1500);
    listPoll = setInterval(() => void loadThreads(), 4000);

    return () => {
      if (threadPoll) clearInterval(threadPoll);
      if (listPoll) clearInterval(listPoll);
    };
  });

  $effect(() => {
    if (!workspaceReady) return;
    const state = JSON.stringify({ threadId: selectedThread, revision: selectedRevision, spans: focusSpans, workMode, historyStart });
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

  <ComparisonSurface bind:open={comparisonOpen} initialId={comparisonSeed} requestId={comparisonRequest} requestIntent={comparisonIntent} {selections} />

  <div class:hidden-aperture={!workMode || comparisonOpen} class="work-aperture">
    <InvestigationPane bind:selections onSource={returnToSource} onCompare={compareInvestigation} />
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
      onSelectNode={selectSemanticNode}
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
            <span>Source focus: {focusSpans.map((span) => `${span.start}–${span.end}`).join(', ')}</span>
            <button class="inline-control" onclick={() => { focusSpans = []; selectedSemanticNode = null; }}>Clear focus</button>
            {#if selectedSemanticNode}<button class="inline-control" onclick={addSemanticEvidence}>Add selected evidence to context</button>{/if}
          </div>
        {/if}
      </header>

      <nav class="history-navigation" aria-label="History navigation">
        <div><button disabled={historyStart === 0} onclick={() => moveHistory(-1)}>Earlier turns</button><span>Turns {thread.turns.length ? historyStart + 1 : 0}–{Math.min(historyStart + historyWindow, thread.turns.length)} of {thread.turns.length}</span><button disabled={historyStart + historyWindow >= thread.turns.length} onclick={() => moveHistory(1)}>Later turns</button></div>
        <form onsubmit={(event) => { event.preventDefault(); void goToRecord(); }}><input aria-label="Find source record" type="number" min="1" bind:value={recordQuery} placeholder="Record sequence" /><button type="submit">Go to record</button></form>
        {#if historyNotice}<p role="status">{historyNotice}</p>{/if}
      </nav>

      <div data-testid="history-window">
      {#each visibleTurns as turn (turn.id)}
        <section
          class:dimmed={isDimmed(turn.startSeq, turn.endSeq)}
          class:highlighted={isHighlighted(turn.startSeq, turn.endSeq)}
          class="turn"
          data-start={turn.startSeq}
          data-end={turn.endSeq}
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
              dimmed={isDimmed(item.startSeq, item.endSeq)}
              highlighted={isHighlighted(item.startSeq, item.endSeq)}
              semanticFocus={selectedSemanticNode !== null}
              selected={itemSelected(item)}
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
