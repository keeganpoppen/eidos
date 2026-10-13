<script lang="ts">
  import type { WorkbenchExperiment } from './types';
  let { experiment }: { experiment: WorkbenchExperiment } = $props();
</script>

<div class="experiment-evaluation-summary" data-evaluation-id={experiment.evaluation.id}>
  <p>Observed selection measurement: {experiment.evaluation.baseline.recordCount} → {experiment.evaluation.alternative.recordCount} records; {experiment.evaluation.baseline.promptBytes} → {experiment.evaluation.alternative.promptBytes} input bytes.</p>
  <p>Added records: {experiment.evaluation.addedRecordIds.join(', ') || 'none'}. Removed records: {experiment.evaluation.removedRecordIds.join(', ') || 'none'}.</p>
  {#if experiment.evaluation.method === 'context-selection-comparison/v2'}
    <p>Exact result inputs: {experiment.evaluation.baseline.artifactCount ?? 0} → {experiment.evaluation.alternative.artifactCount ?? 0}.</p>
    <p>Added results: {experiment.evaluation.addedArtifactIds?.join(', ') || 'none'}. Removed results: {experiment.evaluation.removedArtifactIds?.join(', ') || 'none'}.</p>
    <p>Changed frozen result inputs: {experiment.evaluation.changedArtifactIds?.join(', ') || 'none'}.</p>
  {/if}
  <ul><li>Question retained: {experiment.evaluation.checks.sameQuestion ? 'yes' : 'no'}</li><li>Baseline evidence retained: {experiment.evaluation.checks.baselineEvidenceRetained ? 'yes' : 'no'}</li>{#if experiment.evaluation.checks.baselineArtifactsRetained !== undefined}<li>Frozen result inputs retained: {experiment.evaluation.checks.baselineArtifactsRetained ? 'yes' : 'no'}</li>{/if}<li>Within context bound: {experiment.evaluation.checks.withinContextBound ? 'yes' : 'no'}</li></ul>
  <p class="work-notice">{experiment.evaluation.passes ? 'Structural checks passed.' : 'Structural checks did not all pass.'} Model calls: 0. Better reasoning or user benefit is unmeasured.</p>
  <details><summary>Evaluation identity and limits</summary><p>{experiment.evaluation.id} · {experiment.evaluation.method}</p><ul>{#each experiment.evaluation.limitations as limit}<li>{limit}</li>{/each}</ul></details>
  <div class="current-experiment-review" data-review-status={experiment.status}>
    <h4>Current review of this saved experiment</h4>
    {#if experiment.review}
      <p>{experiment.review.kind === 'human' ? 'Owner decision' : 'Synthetic review decision'}: {experiment.review.decision} · {experiment.review.rationale}</p>
      <p>Durable {experiment.review.kind} review {experiment.review.id}. Configuration activation: not performed.</p>
      {#if experiment.rollback}<p>Rollback retained: {experiment.rollback.rationale}</p>{/if}
    {:else}<p>No review decision recorded.</p>{/if}
    <p class="work-muted">Review status is read separately from the frozen comparison targets and saved arrangement.</p>
  </div>
</div>

<style>
  .experiment-evaluation-summary { min-width:0; overflow-wrap:anywhere; font-size:14px; line-height:1.6; }
  p { margin:8px 0; } ul { padding-left:20px; } h4 { font-size:16px; font-weight:500; margin:14px 0 8px; }
  .current-experiment-review { margin-top:14px; border-top:1px solid var(--line); }
</style>
