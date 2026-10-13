import type { ApertureTarget } from './comparison';
import type { ReflectionFixture } from './reflection';
import type { ContextRecord, Investigation, InvestigationArtifact, InvestigationContext } from './types';

const ids = {
  investigation: 'fixture:recovery-investigation-v1', alternative: 'fixture:recovery-alternative-v1',
  context: 'fixture:recovery-original-context-v1', offered: 'fixture:recovery-offered-context-v1',
  alternativeContext: 'fixture:recovery-alternative-context-v1',
  native: 'fixture:recovery-original-artifact-v1', receipt: 'fixture:recovery-receipt-artifact-v1',
  alternativeArtifact: 'fixture:recovery-alternative-artifact-v1',
  attempt: 'fixture:recovery-attempt-v1', alternativeAttempt: 'fixture:recovery-alternative-attempt-v1',
  continuation: 'fixture:recovery-continuation-v1', inquiry: 'fixture:recovery-inquiry-v1',
  response: 'fixture:recovery-offer-v1', experiment: 'fixture:recovery-experiment-v1'
};

function records(): ContextRecord[] {
  return [
    {
      seq: 12, threadId: 'fixture:design', source: 'synthetic reflection fixture', direction: 'internal', method: null,
      rawText: '{"type":"userMessage","text":"Recovery rule: if a native send has an unknown outcome, reconcile the recorded source before considering a new attempt. Never automatically resend an uncertain external operation.","fixture":true,"unrecognizedFutureField":{"retain":"original bytes"}}',
      sha256: 'f963309ab1f9749486154d4ab8cdd8fc3cc9f269a951d8ccaeabb2a4fbfcb570'
    },
    {
      seq: 38, threadId: 'fixture:design', source: 'synthetic reflection fixture', direction: 'internal', method: null,
      rawText: '{"type":"agentMessage","text":"Observed in the original cut: turn/start request 41 was recorded before pipe write. This proves an outbound logging event, not delivery. No matching native acknowledgement is included in this packet.","fixture":true,"request":{"id":41,"method":"turn/start"},"delivery":"unknown"}',
      sha256: 'c917a14f709c546cbd9f37960ab9f9d02bae2e650cfa4f63fad5d82af4a600c5'
    },
    {
      seq: 72, threadId: 'fixture:recovery', source: 'synthetic reflection fixture', direction: 'internal', method: null,
      rawText: '{"type":"agentMessage","text":"Additional synthetic recovery evidence: the same recorded source contains a numeric RPC response 41 after the turn/start request, with matching thread and turn identities; a terminal result follows for that turn. The fixture supports one correlated completed turn, not exactly-once external effects.","fixture":true,"correlation":{"rpcId":41,"threadId":"fixture-native-thread","turnId":"fixture-native-turn","requestSeq":38,"responseSeq":71,"terminalSeq":72},"externalEffects":"unknown"}',
      sha256: 'f9915950ace789745f2dfc3bc79865ede5a16114b0bccfcc67373d70e9899570'
    }
  ];
}

function context(id: string, question: string, selected: number[], parentContextId: string | null = null): InvestigationContext {
  const evidence = records().filter((record) => selected.includes(record.seq));
  return {
    id, parentContextId, question, records: evidence,
    selections: evidence.map((record) => ({ threadId: record.threadId, startSeq: record.seq, endSeq: record.seq,
      rationale: record.seq === 12 ? 'Preserve the controlling recovery decision.' : record.seq === 38 ? 'Identify what the original cut actually observed.' : 'Inspect the additional correlation evidence requested by the scripted specialist.' })),
    projectedPrompt: `SYNTHETIC FIXTURE — never sent to a model.\n${question}\n\n${evidence.map((record) => `[evidence:${record.seq}] ${record.rawText}`).join('\n\n')}`,
    coverage: { origin: 'synthetic-fixture', providerContext: 'unknown', externalEffects: 'unknown' },
    manifestId: null, createdAtMs: 1
  };
}

/** Authored, deterministic preview data. This does not call an API or persist work. */
export function makeReflectionFixture(stage: 'pending' | 'supplied'): ReflectionFixture {
  const supplied = stage === 'supplied';
  const question = 'Can this investigation recover without sending the uncertain native operation again?';
  const request = 'Show the matching native acknowledgement and terminal result for request 41, including the source, thread, and turn identities. Is there enough recorded evidence to recover the result without resending?';
  const original = context(ids.context, question, [12, 38]);
  const offered = context(ids.offered, request, [72], ids.context);
  const alternativeContext = context(ids.alternativeContext, question, [12, 38, 72]);
  const native: InvestigationArtifact = {
    id: ids.native, contextId: ids.context, attemptId: ids.attempt, kind: 'synthetic-native-output',
    outputSeqs: [], citations: [12, 38], unsupportedCitations: [],
    text: '**Synthetic model-output fixture · original interpretation**\n\nThe selected packet establishes a recovery rule and an outbound logging event. It does not establish delivery or completion. [evidence:12] [evidence:38]\n\n**Inference:** keep the outcome unknown while requesting a correlated acknowledgement and terminal result. Automatic resend would violate the recorded recovery rule.\n\n**Not established:** what the provider received, whether an external effect occurred, or whether the operation completed.'
  };
  const receipt: InvestigationArtifact = {
    ...native, id: ids.receipt, kind: 'eidos-evidence-review', nativeArtifactId: ids.native,
    continuationId: ids.continuation, evidenceContextId: ids.offered,
    inquiryId: ids.inquiry, responseId: ids.response, decisionOccurrenceId: 'fixture:recovery-offer-occurrence-v1',
    text: `${native.text}\n\n---\n\n**Synthetic Eidos process receipt · additional evidence supplied**\n\nThe authored fixture records an offer of the separate frozen packet \`${ids.offered}\`. The original model-output fixture above remains unchanged.\n\nThis is a disclosure receipt, not a new model conclusion. The additional evidence was not part of the original input and no second native turn was run. Inspect the separately named counterfactual for an interpretation using that evidence.`
  };
  const primary: Investigation = {
    schemaVersion: 1, id: ids.investigation, title: 'Recover without resending · synthetic investigation',
    createdAtMs: 1, contexts: [original], currentContextId: ids.context,
    status: supplied ? 'completed' : 'pending', nativeArtifact: native, artifact: supplied ? receipt : null, adoption: null,
    attempt: { id: ids.attempt, contextId: ids.context, status: 'completed', source: 'synthetic-fixture',
      threadId: null, turnId: null, startedAtMs: 1, timeoutSeconds: 0, error: null },
    continuation: {
      schemaVersion: 1, id: ids.continuation, attemptId: ids.attempt, origin: 'synthetic-eidos',
      question: request, status: supplied ? 'completed' : 'pending', error: null,
      processId: 'fixture:recovery-process-v1', checkpointId: 'fixture:recovery-checkpoint-v1',
      outcomeId: supplied ? 'fixture:recovery-outcome-v1' : null,
      inquiry: { id: ids.inquiry, question: request, status: supplied ? 'offer' : 'pending', responses: supplied ? [{
        id: ids.response, requestId: 'fixture:recovery-offer-request-v1', decision: 'offer',
        note: 'Synthetic offer: retain the requested correlation evidence without changing the original native packet.',
        status: 'committed', evidenceContext: offered, occurrenceId: 'fixture:recovery-offer-occurrence-v1'
      }] : [] }
    }
  };
  const alternativeArtifact: InvestigationArtifact = {
    id: ids.alternativeArtifact, contextId: ids.alternativeContext, attemptId: ids.alternativeAttempt,
    kind: 'synthetic-counterfactual', outputSeqs: [], citations: [12, 38, 72], unsupportedCitations: [],
    text: '**Synthetic counterfactual · acknowledgement included**\n\n**Observed within this authored fixture:** the expanded packet retains the original recovery rule and request, then adds a matching acknowledgement and terminal result from the same recorded source. [evidence:12] [evidence:38] [evidence:72]\n\n**Alternative inference:** the extra correlation supports recovering this recorded completed turn without sending it again. It resolves the original packet’s uncertainty about this result. [evidence:72]\n\n**Still not established:** provider context, every external effect, or an exactly-once guarantee. This is an authored interpretation using later evidence, not a native model run or a prospective replay.'
  };
  const alternative: Investigation = {
    schemaVersion: 1, id: ids.alternative, title: 'Acknowledgement included · named counterfactual',
    createdAtMs: 2, contexts: [alternativeContext], currentContextId: ids.alternativeContext,
    status: 'completed', nativeArtifact: null, artifact: alternativeArtifact, adoption: null,
    attempt: { id: ids.alternativeAttempt, contextId: ids.alternativeContext, status: 'synthetic-counterfactual',
      source: 'synthetic-fixture', threadId: null, turnId: null, startedAtMs: 2, timeoutSeconds: 0, error: null }
  };
  const baseline: ApertureTarget = { investigationId: ids.investigation, contextId: ids.context, artifactId: ids.native };
  const changed: ApertureTarget = { investigationId: ids.alternative, contextId: ids.alternativeContext, artifactId: ids.alternativeArtifact };
  return {
    investigations: [primary, alternative],
    inquiry: { id: ids.inquiry, continuationId: ids.continuation, question: request,
      requester: 'Recovery specialist · authored fixture', origin: 'synthetic-fixture', status: supplied ? 'offered' : 'pending',
      baseline, result: supplied ? { investigationId: ids.investigation, contextId: ids.context, artifactId: ids.receipt } : null,
      ...(supplied ? { evidenceContextId: ids.offered, responseId: ids.response } : {}) },
    experiment: {
      id: ids.experiment, name: 'Acknowledgement included', origin: 'synthetic-fixture', baseline, alternative: changed,
      change: 'Add the later correlation record [evidence:72] to an explicitly counterfactual context. Preserve [evidence:12] and [evidence:38] byte for byte. The original native packet stays fixed.',
      evaluation: {
        id: 'fixture:recovery-evaluation-v1',
        method: 'Authored synthetic comparison with deterministic binding checks. These examples exercise the representation; no specialist or judge model ran and no human performance measurement was made.',
        cases: [
          { name: 'Original input remains inspectable', baseline: 'Exact records 12 and 38; result remains uncertain.', alternative: 'Records 12 and 38 retain their hashes beside added record 72.', result: 'Pass: the changed context is explicit and the baseline remains available.' },
          { name: 'Receipt and interpretation retain distinct identities', baseline: 'Original model-output fixture with its exact context.', alternative: 'Separate Eidos disclosure receipt and separately named counterfactual interpretation.', result: 'Pass: distinct artifact IDs and output kinds can be inspected.' },
          { name: 'Recovery improves in real work', baseline: 'No measured recovery time or error rate.', alternative: 'No measured recovery time or error rate.', result: 'Not established: requires actual user tasks and native evidence.' }
        ],
        established: ['The synthetic case distinguishes original input, offered evidence, process receipt, and counterfactual interpretation.', 'Exact context/artifact references allow the comparison without rewriting the original packet.'],
        limitations: ['Authored examples are not model-generated results or empirical quality scores.', 'The counterfactual intentionally uses later evidence; it is not a blind prospective evaluation.', 'No human speed, cost reduction, provider visibility, or external-effects guarantee is established.'],
        cost: 'No model calls in this fixture. Runtime, memory, and human attention costs have not been measured.'
      }
    },
    improvement: {
      id: 'fixture:recovery-improvement-v1', version: 1, origin: 'synthetic-fixture',
      title: 'Keep the evidence request beside its original and outcome', evidence: [baseline, changed], experimentId: ids.experiment,
      expectedBenefit: 'Hypothesis: preserving the original evidence, requested addition, and resulting receipt together will reduce reconstruction during recovery. The fixture demonstrates inspectability; it does not measure that benefit.',
      beforeVersion: 'fixture:recovery-presentation-v1', afterVersion: 'fixture:recovery-presentation-v2',
      patch: '--- attention/comparison-v1\n+++ attention/comparison-v2\n@@ -1,3 +1,5 @@\n Pin the original artifact and the named alternative\n-Open their evidence separately\n+Precede the comparison with the original evidence and pending question\n+Show the separately offered evidence packet\n+Show the Eidos receipt as a receipt\n Keep exact context differences and evaluation available',
      rollback: 'Restore fixture:recovery-presentation-v1. Preserve the original artifacts, evidence, and evaluation; only the fixture presentation preference changes.'
    }
  };
}
