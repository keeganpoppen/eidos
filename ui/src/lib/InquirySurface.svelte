<script lang="ts">
  import Markdown from './Markdown.svelte';
  import WorkContent from './WorkContent.svelte';
  import EvidenceRecord from './EvidenceRecord.svelte';
  import EvidenceReview from './EvidenceReview.svelte';
  import { resolveTarget, validateEvidenceChain, evidenceChain, outputEvidence } from './comparison';
  import { resolveInquiryBinding } from './reflection';
  import type { Arrangement, Attention } from './comparison';
  import type { ReflectionInquiry } from './reflection';
  import type { Investigation, InvestigationArtifact, InvestigationContext, ContextRecord, EvidenceSelection } from './types';

  let { arrangement, investigations, fixtureInquiry, selections = [], focus, onBlock, onRecord, onUpdate, onRebind, onPreview }: {
    arrangement: Arrangement; investigations: Investigation[]; fixtureInquiry?: ReflectionInquiry;
    selections?: EvidenceSelection[]; focus: Attention | null;
    onBlock: (investigation: Investigation, artifact: InvestigationArtifact, block: { id: string; citations: number[] }) => void;
    onRecord: (investigation: Investigation, context: InvestigationContext, record: ContextRecord) => void;
    onUpdate: (value: Investigation) => void; onRebind: () => void; onPreview: () => void;
  } = $props();
  const original = $derived(resolveTarget(investigations, arrangement.left));
  const result = $derived(resolveTarget(investigations, arrangement.right));
  const bound = $derived(arrangement.inquiry ? resolveInquiryBinding(investigations, arrangement.left, arrangement.inquiry) : null);
  const offered = $derived(bound?.evidenceContext);
  const synthetic = $derived(fixtureInquiry?.id === arrangement.inquiry?.inquiryId);
  const bindingError = $derived(validateEvidenceChain(investigations, arrangement));
  const latestChain = $derived(original.investigation ? evidenceChain(original.investigation) : null);
  const hasNewDecision = $derived(!!latestChain && ((latestChain.right.artifactId ?? '') !== (arrangement.right.artifactId ?? '') || latestChain.right.contextId !== arrangement.right.contextId || (!arrangement.inquiry?.responseId && bound?.inquiry?.responses.some((response) => response.decision !== 'defer'))));
  let originalPage = $state(0);
  let offeredPage = $state(0);
  $effect(() => { arrangement.left.contextId; originalPage = 0; });
  $effect(() => { arrangement.inquiry?.evidenceContextId; offeredPage = 0; });
</script>

<section class="inquiry-chain" aria-label="Original evidence, requested evidence, and result">
  <header class="inquiry-lead">
    <div><span class="eyebrow">Active investigation / {synthetic ? 'synthetic specialist scenario' : bound?.continuation?.origin === 'native-specialist' ? 'specialist evidence inquiry' : 'owner-started local review'}</span>
      <h3>{bound?.inquiry?.question ?? 'The exact inquiry is unavailable.'}</h3>
      <p>{synthetic ? 'Fixture question attributed to a recovery specialist. No model was called.' : bound?.continuation?.origin === 'native-specialist' ? 'The specialist requested missing evidence in its terminal output. Disclosure, local incorporation, and new execution are distinct.' : 'This question records a local Eidos disclosure decision. The originating attempt has already finished.'}</p>
    </div>
    <span class="inquiry-status">{bound?.response?.decision === 'refuse' ? 'Terminal refusal' : bound?.response?.decision === 'offer' ? 'Evidence supplied' : bound?.inquiry?.status === 'deferred' ? 'Pending · deferred' : hasNewDecision ? 'New decision available' : 'Pending evidence'}</span>
  </header>
  {#if bindingError}<p class="work-error" role="alert">{bindingError} Saved bindings are retained.</p>{/if}
  {#if hasNewDecision}<p class="work-notice">A decision has arrived. This arrangement retains its original result binding. <button onclick={onRebind}>Review completed evidence chain</button></p>{/if}
  <div class="inquiry-columns" class:stacked={arrangement.layout === 'stacked'}>
    <article data-inquiry-role="original" data-context-id={arrangement.left.contextId} data-artifact-id={arrangement.left.artifactId}>
      <span class="eyebrow">01 / Original output</span><h4>What the first input supported</h4>
      <p class="aperture-caption">{synthetic ? 'Synthetic model interpretation' : outputEvidence(original.artifact)} · inference from the original input</p>
      {#if original.artifact && original.investigation}
        <WorkContent source={original.artifact.text} focusedBlockId={focus?.artifactId === original.artifact.id ? focus.blockId : undefined} onFocus={(block) => onBlock(original.investigation!, original.artifact!, block)} />
      {:else}<p class="work-notice">Exact original artifact unavailable. No current answer has been substituted.</p>{/if}
      {#if original.context && original.investigation}
        <h4>Original supplied evidence</h4>
        <div class="record-index">{#each original.context.records.slice(originalPage * 20, (originalPage + 1) * 20) as record (`${record.threadId}:${record.seq}`)}<button onclick={() => onRecord(original.investigation!, original.context!, record)}>[evidence:{record.seq}]</button>{/each}</div>
        {#if original.context.records.length > 20}<nav class="record-pagination" aria-label="Original input records"><button disabled={!originalPage} onclick={() => originalPage--}>Earlier evidence</button><span>{originalPage * 20 + 1}–{Math.min((originalPage + 1) * 20, original.context.records.length)} of {original.context.records.length}</span><button disabled={(originalPage + 1) * 20 >= original.context.records.length} onclick={() => originalPage++}>Later evidence</button></nav>{/if}
        <p class="work-muted">{original.context.records.length} frozen records · availability is not proof of the inference.</p>
        {#if original.context.records[0]}<EvidenceRecord record={original.context.records[0]} />{/if}
      {/if}
      <details><summary>Original binding</summary><p class="object-ref">Artifact {arrangement.left.artifactId}<br />Input {arrangement.left.contextId}</p></details>
    </article>
    <article data-inquiry-role="requested" data-inquiry-id={arrangement.inquiry?.inquiryId} data-context-id={arrangement.inquiry?.evidenceContextId ?? ''} data-response-id={arrangement.inquiry?.responseId ?? ''}>
      <span class="eyebrow">02 / Requested evidence</span><h4>The missing observation</h4>
      {#if bound?.inquiry}<div class="question-native"><Markdown source={bound.inquiry.question} /></div>{/if}
      {#if offered && original.investigation && !bindingError}
        <p class="aperture-caption">Separately offered packet · never sent to the original native turn</p>
        <div class="record-index">{#each offered.records.slice(offeredPage * 20, (offeredPage + 1) * 20) as record (`${record.threadId}:${record.seq}`)}<button onclick={() => onRecord(original.investigation!, offered, record)}>[evidence:{record.seq}]</button>{/each}</div>
        {#if offered.records.length > 20}<nav class="record-pagination" aria-label="Offered input records"><button disabled={!offeredPage} onclick={() => offeredPage--}>Earlier evidence</button><span>{offeredPage * 20 + 1}–{Math.min((offeredPage + 1) * 20, offered.records.length)} of {offered.records.length}</span><button disabled={(offeredPage + 1) * 20 >= offered.records.length} onclick={() => offeredPage++}>Later evidence</button></nav>{/if}
        {#if offered.records[0]}<EvidenceRecord record={offered.records[0]} />{/if}
        <details><summary>Exact offered input</summary><pre>{offered.projectedPrompt}</pre><p class="object-ref">{offered.id}</p></details>
      {:else if bound?.response?.decision === 'refuse'}
        <p>Evidence was refused. This terminal decision does not mean the evidence was absent.</p>
        <p>{bound.response.note}</p>
      {:else}
        <p>No offered packet is bound. The original input stays unchanged while this request waits.</p>
        {#if synthetic}<button onclick={onPreview}>Preview supplied-evidence outcome</button><p class="work-muted">Loads the next authored fixture stage. It does not answer a live inquiry.</p>{/if}
      {/if}
      {#if !synthetic && original.investigation && !bindingError}
        {#key original.investigation.id}<EvidenceReview investigation={original.investigation} {selections} {onUpdate} />{/key}
      {/if}
      <details><summary>Inquiry identity</summary><p class="object-ref">{arrangement.inquiry?.inquiryId}<br />{arrangement.inquiry?.continuationId}<br />{arrangement.inquiry?.responseId ?? 'No terminal response pinned'}</p></details>
    </article>
    <article data-inquiry-role="result" data-context-id={arrangement.right.contextId} data-artifact-id={arrangement.right.artifactId ?? ''}>
      <span class="eyebrow">03 / After disclosure</span><h4>{result.artifact ? 'What actually followed' : 'An open continuation'}</h4>
      {#if bindingError}<p class="work-notice">The requested result cannot be resolved as part of this inquiry. Review a corrected arrangement.</p>
      {:else if result.artifact && result.investigation}
        <p class="aperture-caption">{synthetic ? 'Synthetic Eidos process receipt' : outputEvidence(result.artifact)}</p>
        <WorkContent source={result.artifact.text} focusedBlockId={focus?.artifactId === result.artifact.id ? focus.blockId : undefined} onFocus={(block) => onBlock(result.investigation!, result.artifact!, block)} />
        {#if result.artifact.kind === 'eidos-evidence-review'}<p class="work-notice">This receipt preserves the answer and records the evidence decision. It establishes no new native model analysis.</p>{:else}<p class="work-notice">A new attempt produced this result from a separately frozen input. The original output and local disclosure receipt remain preserved.</p>{/if}
      {:else}
        <p class="open-question">What will follow this evidence decision?</p>
        <p>Offer, defer, and refusal are distinct continuations. A pending request is not a refusal and no result is inferred.</p>
      {/if}
      <details><summary>Result binding</summary><p class="object-ref">{arrangement.right.artifactId ?? 'No result version pinned'}<br />{arrangement.right.contextId}</p></details>
    </article>
  </div>
</section>

<style>
  .inquiry-chain { border-top: 1px solid var(--line-dark); margin-top: 18px; }
  .inquiry-lead { display:flex; justify-content:space-between; gap:24px; padding:22px 0; }
  .inquiry-lead h3 { font-size:25px; line-height:1.25; letter-spacing:-.025em; max-width:850px; margin:10px 0; }
  .inquiry-lead p { color:var(--muted); font-size:14px; margin:8px 0 0; }
  .inquiry-status { align-self:flex-start; white-space:nowrap; font:13px/1.5 monospace; color:var(--accent); border-bottom:2px solid var(--accent); padding:4px 0; }
  .inquiry-columns { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); border-top:1px solid var(--line-dark); }
  .inquiry-columns.stacked { grid-template-columns:minmax(0,1fr); }
  .inquiry-columns.stacked article { padding:20px 0; border-left:0; border-bottom:1px solid var(--line); }
  article { min-width:0; padding:22px 22px 26px 0; overflow-wrap:anywhere; }
  article + article { padding-left:22px; border-left:1px solid var(--line); }
  article:last-child { padding-right:0; }
  h4 { font-size:21px; font-weight:500; letter-spacing:-.035em; margin:10px 0 16px; }
  p { font-size:15px; line-height:1.6; }
  details { margin-top:16px; }
  pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:280px; overflow:auto; }
  .question-native { padding:12px; border-left:2px solid var(--accent); background:var(--selection); }
  .open-question { font-family:Georgia,serif; font-size:23px; line-height:1.4; }
  @media(max-width:1100px) { .inquiry-columns { grid-template-columns:1fr; } article,article + article { padding:20px 0; border-left:0; border-bottom:1px solid var(--line); } .inquiry-lead { flex-direction:column; gap:10px; } }
</style>
