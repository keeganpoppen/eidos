<script lang="ts">
  import { onMount } from 'svelte';
  import WorkContent from './WorkContent.svelte';
  import type { Experiment, Improvement } from './reflection';
  import {
    applyImprovementPreview, emptyImprovementPreview, readImprovementPreview, undoImprovementPreview,
    type ImprovementPreview
  } from './improvement-preview';

  let { experiment, improvement, onchange }: {
    experiment: Experiment;
    improvement: Improvement;
    onchange?: (version: string | null) => void;
  } = $props();

  let reviewed = $state(false);
  let staged = $state(false);
  let ready = $state(false);
  let storedPreview = $state<ImprovementPreview | null>(null);
  let notice = $state('');
  const preview = $derived(storedPreview ?? emptyImprovementPreview(experiment, improvement));
  const previewActive = $derived(preview.activeVersion === improvement.afterVersion);
  const linked = $derived(improvement.experimentId === experiment.id);
  const storageKey = 'nema.improvement-presentation-preview.v1';

  onMount(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      storedPreview = readImprovementPreview(raw, experiment, improvement);
      if (raw && storedPreview.activeVersion === null && raw !== JSON.stringify(storedPreview)) {
        notice = 'Saved references could not establish a current preview. The original presentation is shown.';
      }
      onchange?.(storedPreview.activeVersion);
    } catch {
      notice = 'Browser storage is unavailable. Preview changes will last for this visit only.';
    }
    ready = true;
  });

  function save(next: ImprovementPreview) {
    storedPreview = next;
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      notice = next.canUndo
        ? 'Presentation preview applied in this browser. Source artifacts and future execution context are unchanged.'
        : 'Previous presentation restored. The proposal remains available for review.';
    } catch {
      notice = 'Presentation preview changed for this visit. Browser storage is unavailable; reload recovery is unavailable.';
    }
    onchange?.(next.activeVersion);
  }

  function apply() {
    if (!staged || !linked || previewActive || !ready) return;
    save(applyImprovementPreview(preview));
    staged = false;
  }
</script>

<section class="improvement-review" aria-labelledby="improvement-title" data-preview-active={previewActive}>
  <header class="proposal-heading">
    <div>
      <p class="eyebrow">Reflect on this investigation · synthetic fixture</p>
      <h2 id="improvement-title">{improvement.title}</h2>
      <p class="proposal-state">Proposed improvement <span aria-hidden="true">/</span> {previewActive ? 'browser presentation preview active' : 'not adopted'}</p>
    </div>
    <button id="review-improvement" aria-expanded={reviewed} aria-controls="improvement-detail" onclick={() => reviewed = !reviewed}>
      {reviewed ? 'Close improvement review' : 'Review improvement'}
    </button>
  </header>

  <p class="benefit"><span class="label">Expected benefit · hypothesis</span>{improvement.expectedBenefit}</p>

  {#if reviewed}
    <div id="improvement-detail" class="review-detail">
      <div class="identity-line"><code>{improvement.id}</code><span>proposal v{improvement.version}</span><span>experiment <code>{experiment.id}</code></span></div>
      <p class="origin">This is a hand-authored synthetic proposal and evaluation. It is not an agent-generated proposal, a native model evaluation, or an Eidos adoption receipt.</p>

      <section class="evidence-bindings" aria-labelledby="improvement-evidence-title">
        <h3 id="improvement-evidence-title">Evidence behind the proposal</h3>
        <p>Exact source bindings are retained; the interpretation and its evidence stay distinct.</p>
        <ol>
          {#each improvement.evidence as evidence}
            <li>
              <span>Investigation <code>{evidence.investigationId}</code></span>
              <span>Context <code>{evidence.contextId}</code></span>
              <span>Artifact {#if evidence.artifactId}<code>{evidence.artifactId}</code>{:else}<em>context only; no artifact bound</em>{/if}</span>
            </li>
          {/each}
        </ol>
      </section>

      <section aria-labelledby="improvement-change-title">
        <h3 id="improvement-change-title">Proposed presentation change</h3>
        <p>The patch describes a presentation recipe. The original context and artifacts remain independently addressable.</p>
        <dl class="versions">
          <div><dt>Baseline recipe</dt><dd><code>{improvement.beforeVersion}</code></dd></div>
          <div><dt>Proposed recipe</dt><dd><code>{improvement.afterVersion}</code></dd></div>
        </dl>
        <WorkContent source={improvement.patch.startsWith('```') ? improvement.patch : `\`\`\`diff\n${improvement.patch}\n\`\`\``} patchLabel="Proposed presentation diff · preview only" />
      </section>

      <section aria-labelledby="improvement-evaluation-title">
        <h3 id="improvement-evaluation-title">What the evaluation establishes</h3>
        <p>{experiment.evaluation.method}</p>
        <p><span class="label">Input change in the named counterfactual</span>{experiment.change}</p>
        <p class="identity-line">Evaluation <code>{experiment.evaluation.id}</code></p>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (Horizontal table scrolling needs keyboard focus on narrow screens.) -->
        <div class="table-scroll" tabindex="0" role="region" aria-label="Synthetic evaluation cases">
          <table>
            <thead><tr><th scope="col">Case</th><th scope="col">Baseline</th><th scope="col">Alternative</th><th scope="col">Established by this case</th></tr></thead>
            <tbody>
              {#each experiment.evaluation.cases as evaluationCase}
                <tr><th scope="row">{evaluationCase.name}</th><td>{evaluationCase.baseline}</td><td>{evaluationCase.alternative}</td><td>{evaluationCase.result}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
        <div class="evaluation-scope">
          <div><h4>Established in the synthetic evaluation</h4><ul>{#each experiment.evaluation.established as claim}<li>{claim}</li>{/each}</ul></div>
          <div><h4>Limits and open questions</h4><ul>{#each experiment.evaluation.limitations as limitation}<li>{limitation}</li>{/each}<li>No real user timing, native model quality, or production resource measurements are established by this preview.</li></ul></div>
        </div>
        <p><span class="label">Resource cost and tradeoffs</span>{experiment.evaluation.cost}</p>
      </section>

      <section class="adoption-review" aria-labelledby="improvement-adoption-title">
        <h3 id="improvement-adoption-title">Review the activation boundary</h3>
        <p>A presentation preview changes the order and emphasis of this synthetic workbench. Adopting a durable recipe or changing future context needs a backend decision and receipt.</p>
        <p><span class="label">Rollback</span>{improvement.rollback}</p>
        {#if !linked}<p class="warning">The experiment does not match this proposal. Preview is unavailable until the reference resolves.</p>{/if}
        <div class="actions">
          <button id="preview-adoption" disabled={!ready || !linked || previewActive} aria-expanded={staged} aria-controls="presentation-preview-review" onclick={() => staged = !staged}>Review presentation preview</button>
          <button id="undo-improvement-preview" disabled={!ready || !preview.canUndo} onclick={() => { save(undoImprovementPreview(preview)); staged = false; }}>Undo presentation preview</button>
          <button id="adopt-improvement" disabled aria-describedby="adoption-unavailable">Adopt durable improvement · unavailable</button>
        </div>
        <p id="adoption-unavailable" class="boundary-note">This authored example has no durable proposal. Use Evaluate a context alternative in the investigation to record a durable decision. Browser preferences cannot authorize policy, context, execution, or repository changes.</p>
        {#if staged}
          <div id="presentation-preview-review" class="preview-review">
            <h4>Presentation preview · ready for review</h4>
            <p><code>{preview.activeVersion ?? improvement.beforeVersion}</code> <span aria-label="changes to">→</span> <code>{improvement.afterVersion}</code></p>
            <p>The evidence chain receives the first position and stronger emphasis. Its original, requested, and supplied evidence retain their exact identities.</p>
            <p class="boundary-note">Stored in this browser: proposal, experiment, and presentation version references only. Undo restores the previous presentation after reload.</p>
            <div class="actions"><button id="apply-improvement-preview" onclick={apply}>Apply presentation preview</button><button onclick={() => staged = false}>Cancel preview</button></div>
          </div>
        {/if}
      </section>
    </div>
  {/if}
  <p class="notice" role="status">{notice || (previewActive ? 'Browser-local preview only. The improvement has not been durably adopted.' : '')}</p>
</section>

<style>
  .improvement-review { min-width: 0; padding: 24px 0 12px; border-top: 1px solid var(--line-dark); color: var(--ink); font-size: 15px; line-height: 1.6; }
  .proposal-heading { display: flex; flex-wrap: wrap; gap: 16px; justify-content: space-between; align-items: center; }
  .eyebrow { margin: 0 0 5px; color: #575d51; font-size: 12px; letter-spacing: .07em; text-transform: uppercase; }
  h2 { margin: 0; font-size: 23px; font-weight: 550; line-height: 1.3; letter-spacing: -.02em; }
  h3 { margin: 0 0 7px; font-size: 17px; line-height: 1.4; font-weight: 600; }
  h4 { margin: 0 0 8px; font-size: 14px; line-height: 1.5; font-weight: 600; }
  p { margin: 8px 0 12px; }
  .proposal-state { margin: 6px 0 0; font-size: 13px; color: #555d50; }
  .proposal-state span { padding: 0 6px; color: #7f8479; }
  .benefit { max-width: 82ch; margin-top: 18px; }
  .label { display: block; font-size: 12px; color: #565e50; text-transform: uppercase; letter-spacing: .055em; }
  .review-detail { display: grid; grid-template-columns:minmax(0,1fr); gap: 24px; margin-top: 22px; }
  .review-detail > * { min-width:0; }
  .review-detail > section + section { border-top: 1px solid var(--line); padding-top: 22px; }
  .identity-line { display: flex; gap: 7px 18px; flex-wrap: wrap; font-size: 12px; color: #555d50; }
  .origin { margin-top: -15px; font-size: 13px; color: #665836; }
  code { font: 12px/1.5 monospace; overflow-wrap: anywhere; }
  .evidence-bindings ol { margin: 12px 0 0; padding-left: 23px; }
  .evidence-bindings li { padding: 7px 0 10px 4px; border-top: 1px solid var(--line); }
  .evidence-bindings li span { display: block; font-size: 13px; }
  em { color: #64665e; }
  .versions { display: flex; flex-wrap: wrap; gap: 12px 36px; margin: 15px 0; }
  dt { color: #596052; font-size: 12px; }
  dd { margin: 0; }
  .table-scroll { overflow-x: auto; margin: 15px 0; }
  table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; line-height: 1.55; }
  th, td { padding: 10px 12px 10px 0; border-top: 1px solid var(--line); vertical-align: top; min-width: 145px; }
  thead th { color: #535c4b; font-size: 12px; font-weight: 500; }
  tbody th { font-weight: 550; }
  .evaluation-scope { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }
  ul { margin: 0; padding-left: 19px; }
  li { margin-bottom: 7px; }
  .evaluation-scope li { font-size: 14px; }
  .actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 15px; }
  button { padding: 8px 11px; color: var(--accent); background: transparent; border: 1px solid var(--line-dark); border-radius: 3px; font: inherit; font-size: 13px; cursor: pointer; }
  button:hover:enabled { background: var(--accent-soft); }
  button:disabled { opacity: .5; cursor: not-allowed; }
  button:focus-visible, .table-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .boundary-note { color: #5d6256; font-size: 13px; }
  .preview-review { border-left: 3px solid var(--accent); padding: 15px 18px; margin-top: 18px; background: var(--paper-3); }
  .notice { min-height: 1.6em; color: #525e49; font-size: 13px; }
  .warning { color: #805331; }
  @media (max-width: 760px) { .evaluation-scope { grid-template-columns: 1fr; } h2 { font-size: 20px; } .proposal-heading > button { width: 100%; text-align: left; } }
</style>
