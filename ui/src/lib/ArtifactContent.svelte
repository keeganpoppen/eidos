<script lang="ts">
  import WorkContent from './WorkContent.svelte';
  import { outputEvidence } from './comparison';
  import { artifactKind } from './artifact-inputs';
  import { isAuthoredFinding, findingSupport } from './authored-finding';
  import type { FrozenArtifactInput, InvestigationArtifact, InvestigationContext } from './types';

  let { artifact, context, onArtifact }: {
    artifact: InvestigationArtifact;
    context?: InvestigationContext;
    onArtifact?: (input: FrozenArtifactInput) => void;
  } = $props();
  let rawOpen = $state(false);
</script>

<div class="artifact-content" data-artifact-id={artifact.id}>
  <p class="artifact-classification">{artifactKind(artifact)} · {outputEvidence(artifact)}</p>
  <WorkContent source={artifact.text} />
  {#if isAuthoredFinding(artifact)}
    <p class="work-notice">{findingSupport(artifact)}</p>
  {/if}
  {#if artifact.kind === 'eidos-evidence-review'}
    <p class="work-notice">This receipt records an evidence decision; it is not a new specialist analysis.</p>
  {:else if ['native-needs-evidence', 'native-inquiry-invalid'].includes(artifact.kind ?? '')}
    <p class="work-notice">This is a recorded inquiry, not a conclusion. Inspecting or supplying it starts no continuation.</p>
  {/if}
  {#if artifact.artifactCitations?.length}
    <div class="artifact-citations" aria-label="Cited result inputs">
      <p>Cited results supplied to this artifact:</p>
      {#each artifact.artifactCitations as id}
        {@const input = context?.artifactInputs?.find((item) => item.artifactId === id)}
        {#if input && onArtifact}
          <button class="source-link" data-artifact-citation={id} onclick={() => onArtifact?.(input)}>[artifact:{id}] · inspect source result</button>
        {:else}<span class="object-ref">[artifact:{id}]</span>{/if}
      {/each}
      <p class="work-muted">A citation identifies a supplied result. Its claims and original support remain attributed to that result.</p>
    </div>
  {/if}
  {#if artifact.unsupportedCitations.length || artifact.unsupportedArtifactCitations?.length}
    <p class="work-error">References outside this artifact’s supplied packet: {[...artifact.unsupportedCitations.map((seq) => `[evidence:${seq}]`), ...(artifact.unsupportedArtifactCitations ?? []).map((id) => `[artifact:${id}]`)].join(', ')}. Support is unverified.</p>
  {/if}
  <details bind:open={rawOpen}>
    <summary>Exact saved artifact and classification</summary>
    {#if rawOpen}<pre>{JSON.stringify(artifact, null, 2)}</pre>{/if}
  </details>
</div>

<style>
  .artifact-content { min-width:0; overflow-wrap:anywhere; }
  .artifact-classification { color:var(--accent); font-size:13px; line-height:1.5; }
  .artifact-citations { margin:14px 0; border-left:2px solid var(--line-dark); padding-left:12px; }
  .artifact-citations button,.artifact-citations span { display:block; margin:5px 0; }
  details { margin-top:12px; font-size:13px; }
  pre { max-height:360px; overflow:auto; white-space:pre-wrap; background:var(--code); padding:12px; font:12px/1.5 monospace; }
</style>
