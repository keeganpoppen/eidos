<script lang="ts">
  import { onMount } from 'svelte';
  import LineDiff from './LineDiff.svelte';
  import ExperimentEvaluation from './ExperimentEvaluation.svelte';
  import { contextText } from './comparison';
  import { experimentBaselines } from './artifact-inputs';
  import type { Investigation, WorkbenchExperiment } from './types';

  let { investigation, onCompare }: { investigation: Investigation; onCompare: (experimentId: string) => void } = $props();
  let experiments = $state<WorkbenchExperiment[]>([]);
  let baselineArtifactId = $state('');
  let alternativeContextId = $state('');
  let rationale = $state('');
  let reviewNotes = $state<Record<string, string>>({});
  let error = $state('');
  let busy = $state(false);
  let ready = $state(false);
  let staged = $state(false);
  let pending = $state<{ path: string; body: Record<string, unknown> } | null>(null);
  const basePath = $derived(`/api/investigations/${encodeURIComponent(investigation.id)}/experiments`);
  const storageKey = $derived(`nema.experiment-request.v1.${investigation.id}`);
  const availableArtifacts = $derived(experimentBaselines(investigation));
  const baselineArtifact = $derived(availableArtifacts.find((item) => item.id === baselineArtifactId));
  const baseline = $derived(investigation.contexts.find((item) => item.id === baselineArtifact?.contextId));
  const alternative = $derived(investigation.contexts.find((item) => item.id === alternativeContextId));

  async function load() {
    const response = await fetch(basePath);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error ?? 'Could not load experiments.');
    experiments = result.experiments;
  }

  onMount(() => {
    baselineArtifactId = investigation.nativeArtifact?.id ?? availableArtifacts[0]?.id ?? '';
    alternativeContextId = investigation.continuation?.nativeNext?.contextId ?? investigation.currentContextId;
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (value && typeof value.path === 'string' && (value.path === basePath || (value.path.startsWith(basePath + '/') && /^[A-Za-z0-9_.%:-]+\/(review|rollback)$/.test(value.path.slice(basePath.length + 1)))) && typeof value.body?.requestId === 'string') pending = value;
    } catch { error = 'Stored experiment request is unavailable.'; }
    void load().catch((cause) => error = String(cause)).finally(() => ready = true);
  });

  async function send(request: { path: string; body: Record<string, unknown> }) {
    if (busy) return;
    try { localStorage.setItem(storageKey, JSON.stringify(request)); pending = request; }
    catch { error = 'Could not retain the retry identity. No request was sent.'; return; }
    busy = true; error = '';
    try {
      const response = await fetch(request.path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request.body) });
      const result = await response.json();
      if (!response.ok) {
        if ([400, 404, 409].includes(response.status)) { localStorage.removeItem(storageKey); pending = null; }
        throw new Error(result.error ?? 'Experiment action failed.');
      }
      localStorage.removeItem(storageKey); pending = null; staged = false;
      await load();
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }

  function evaluate() {
    if (!baseline || !baselineArtifact || !alternative || !staged || pending) return;
    void send({ path: basePath, body: { requestId: crypto.randomUUID(), baselineContextId: baseline.id, baselineArtifactId: baselineArtifact.id, alternativeContextId: alternative.id, rationale } });
  }

  function review(experiment: WorkbenchExperiment, decision: 'adopt' | 'reject') {
    void send({ path: `${basePath}/${encodeURIComponent(experiment.id)}/review`, body: { requestId: crypto.randomUUID(), decision, rationale: reviewNotes[experiment.id] ?? '' } });
  }
</script>

{#if !ready || busy || availableArtifacts.length || experiments.length || pending || error}
<section class="recorded-experiments" aria-label="Controlled context experiment">
  <h3>Evaluate a context alternative</h3>
  <p>Keep an exact baseline and test a saved alternative input. The evaluator measures evidence selection and input size. It runs no model and does not grade the answer.</p>
  {#if availableArtifacts.length && investigation.contexts.length > 1}
    <label for="experiment-baseline">Retained baseline artifact</label>
    <select id="experiment-baseline" bind:value={baselineArtifactId} onchange={() => staged = false} disabled={busy || !!pending}>
      {#each availableArtifacts as artifact (artifact.id)}<option value={artifact.id}>{artifact.kind ?? 'recorded output'} · {artifact.id.slice(-12)}</option>{/each}
    </select>
    <label for="experiment-alternative">Alternative context</label>
    <select id="experiment-alternative" bind:value={alternativeContextId} onchange={() => staged = false} disabled={busy || !!pending}>
      {#each investigation.contexts as context, index (context.id)}<option value={context.id}>Input {index + 1} · {context.records.length} records · {context.artifactInputs?.length ?? 0} results · {context.id.slice(-12)}</option>{/each}
    </select>
    <label for="experiment-rationale">Proposed selection improvement</label>
    <textarea id="experiment-rationale" bind:value={rationale} oninput={() => staged = false} placeholder="What should this alternative improve, and what could regress?" rows="3" disabled={busy || !!pending}></textarea>
    <button disabled={!ready || busy || !!pending || !baseline || !alternative || baseline.id === alternative.id || !rationale.trim()} onclick={() => staged = true}>Review controlled alternative</button>
    {#if staged && baseline && alternative}
      <div class="experiment-preview"><h4>Frozen inputs for comparison</h4><p class="object-ref">Baseline {baseline.id}<br />Artifact {baselineArtifactId}<br />Alternative {alternative.id}</p><LineDiff before={contextText(baseline)} after={contextText(alternative)} /><p>This records a named experiment and a deterministic evaluation. A passing check grants no adoption or execution authority.</p><button disabled={busy || !!pending} onclick={evaluate}>Evaluate saved inputs</button><button onclick={() => staged = false}>Cancel experiment preview</button></div>
    {/if}
  {:else if availableArtifacts.length}<p class="work-muted">An exact returned artifact and a second saved input are required. Respond to a specialist inquiry to prepare a separately frozen follow-up input.</p>
  {:else if !ready}<p role="status">Checking saved experiments…</p>{/if}

  {#each experiments as experiment (experiment.id)}
    <article class="recorded-experiment" data-experiment-id={experiment.id} data-experiment-status={experiment.status}>
      <h4>{experiment.rationale}</h4><p class="experiment-state">{experiment.status} · {experiment.mode} · {experiment.evidenceClass} evidence</p>
      <details><summary>Inspect experiment bindings</summary><p class="object-ref">Experiment {experiment.id}<br />Proposal {experiment.proposalId}<br />Baseline {experiment.baseline.artifactId}<br />Alternative {experiment.alternative.contextId}</p></details>
      <button class="compare-recorded-experiment" onclick={() => onCompare(experiment.id)}>Compare these saved inputs</button>
      <ExperimentEvaluation {experiment} />
      {#if experiment.review}
        {#if experiment.adoption && !experiment.rollback}<label for={`rollback-${experiment.id}`}>Rollback rationale</label><textarea id={`rollback-${experiment.id}`} bind:value={reviewNotes[experiment.id]} rows="2"></textarea><button disabled={busy || !!pending || !reviewNotes[experiment.id]?.trim()} onclick={() => send({ path: `${basePath}/${encodeURIComponent(experiment.id)}/rollback`, body: { requestId: crypto.randomUUID(), rationale: reviewNotes[experiment.id] ?? '' } })}>Record rollback</button>{/if}
      {:else}
        <label for={`review-${experiment.id}`}>Owner review rationale</label><textarea id={`review-${experiment.id}`} bind:value={reviewNotes[experiment.id]} rows="2" placeholder="What does this measurement justify carrying forward?"></textarea>
        <button disabled={busy || !!pending || !reviewNotes[experiment.id]?.trim() || !experiment.evaluation.passes} onclick={() => review(experiment, 'adopt')}>Adopt recorded proposal</button><button disabled={busy || !!pending || !reviewNotes[experiment.id]?.trim()} onclick={() => review(experiment, 'reject')}>Reject recorded proposal</button>
        <p class="work-muted">Records a reviewed version and rollback target. This does not activate a context recipe, change configuration, or launch native work.</p>
      {/if}
    </article>
  {/each}
  {#if pending}<p role="status">A saved request awaits confirmation. Its scope and retry identity are retained.</p><button disabled={busy} onclick={() => pending && send(pending)}>Retry saved experiment action</button>{/if}
  {#if error}<p class="work-error" role="alert">{error}</p>{/if}
</section>
{/if}

<style>
  .recorded-experiments { margin-top:24px; padding-top:18px; border-top:1px solid var(--line-dark); font-size:14px; line-height:1.6; min-width:0; overflow-wrap:anywhere; }
  h3 { font-size:22px; font-weight:500; margin:0 0 12px; } h4 { font-size:17px; margin:12px 0; }
  label { display:block; margin-top:14px; } select,textarea { display:block; width:100%; box-sizing:border-box; margin:6px 0 12px; padding:8px; }
  button { padding:7px 10px; margin:6px 8px 6px 0; border:1px solid var(--line-dark); background:transparent; color:var(--accent); cursor:pointer; font:inherit; }
  button:disabled { opacity:.5; cursor:default; } button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .recorded-experiment,.experiment-preview { border-left:2px solid var(--accent); padding:8px 14px; margin:18px 0; background:var(--selection); }
  .experiment-state { color:var(--accent); font-size:13px; } .object-ref { font:12px/1.6 monospace; overflow-wrap:anywhere; }
</style>
