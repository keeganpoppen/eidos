<script lang="ts">
  import { onMount } from 'svelte';
  import FocusPane from '#lib/FocusPane.svelte';
  import Markdown from '#lib/Markdown.svelte';
  import SemanticRail from '#lib/SemanticRail.svelte';
  import ThreadItemCard from '#lib/ThreadItem.svelte';
  import type {
    ObserverJob,
    SemanticNode,
    SupportSpan,
    ThreadItem,
    ThreadPayload,
    ThreadSummary
  } from '#lib/types.ts';

  let threads = $state<ThreadSummary[]>([]);
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
  let status = $state('');
  let error = $state('');

  let threadPoll: ReturnType<typeof setInterval> | undefined;
  let listPoll: ReturnType<typeof setInterval> | undefined;

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
    try {
      const query = selectedRevision
        ? `?revision=${encodeURIComponent(selectedRevision)}`
        : '';
      thread = await api<ThreadPayload>(
        `/api/threads/${encodeURIComponent(selectedThread)}${query}`
      );
      error = '';
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause);
    }
  }

  async function chooseThread(id: string) {
    selectedThread = id;
    selectedRevision = '';
    selectedSemanticNode = null;
    focusSpans = [];
    await loadThread();
  }

  async function newThread() {
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
    if (!selectedThread || !text || sending) return;
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

  function jumpToItem(item: ThreadItem) {
    const selector = `.workspace [data-item-id="${CSS.escape(item.id)}"]`;
    document.querySelector<HTMLElement>(selector)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center'
    });
  }

  async function runObserver() {
    if (!selectedThread || observerBusy) return;
    observerBusy = true;
    observerProgress = 'planning';
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

  function inputText(input: Record<string, unknown>): string {
    if (input.type === 'text') return String(input.text ?? '');
    return JSON.stringify(input, null, 2);
  }

  onMount(() => {
    void loadThreads();
    threadPoll = setInterval(() => void loadThread(), 700);
    listPoll = setInterval(() => void loadThreads(), 4000);

    return () => {
      if (threadPoll) clearInterval(threadPoll);
      if (listPoll) clearInterval(listPoll);
    };
  });
</script>

<svelte:head>
  <title>Eidos</title>
  <meta
    name="description"
    content="A live semantic surface over persisted Codex traces."
  />
</svelte:head>

<div class:focus-mode={selectedSemanticNode !== null} class="shell">
  <aside class="thread-rail">
    <div class="brand-block">
      <h1>eidos</h1>
      <p>threads · outline · trace</p>
    </div>

    <div class="new-thread">
      <input bind:value={cwd} placeholder="cwd (optional)" aria-label="working directory" />
      <button disabled={startingThread} onclick={newThread}>
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

  <SemanticRail
    outline={thread?.outline ?? null}
    revisions={thread?.revisions ?? []}
    {selectedRevision}
    selectedNodeId={selectedSemanticNode?.node_id ?? null}
    onSelectNode={selectSemanticNode}
    onSelectRevision={selectRevision}
    onObserve={runObserver}
    {observerBusy}
    {observerProgress}
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

  <main class="workspace">
    {#if thread}
      <header class="thread-header">
        <h2>{thread.preview || thread.id}</h2>
        <div class="meta">
          {thread.recordCount} persisted records · seq {thread.lastSeq} · {thread.id}
        </div>
      </header>

      {#each thread.turns as turn}
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
            />
          {/each}
        </section>
      {/each}

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

<div class="composer">
  <div class="composer-inner">
    <textarea
      bind:value={composer}
      disabled={!selectedThread || sending}
      onkeydown={handleComposerKeydown}
      placeholder={selectedThread
        ? 'Message Codex · ⌘↵ / Ctrl↵ to send'
        : 'Select or start a thread first.'}
    ></textarea>
    <button disabled={!selectedThread || !composer.trim() || sending} onclick={send}>
      {sending ? 'sending…' : 'send'}
    </button>
  </div>
  {#if error}
    <div class="status-line error">{error}</div>
  {:else if status}
    <div class="status-line">{status}</div>
  {/if}
</div>
