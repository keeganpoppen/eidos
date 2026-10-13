import { matchesExperiment, resolveAttention, resolveTarget, validateEvidenceChain, validateRecordedExperiment } from './comparison';
import { supportsBlockFocus, type CompositionSnapshot } from './composition-snapshots';
import { contentBlocks } from './semantic';
import { savedWork, type SavedWorkClient } from './saved-work';
import type { Investigation, WorkbenchExperiment } from './types';

/** Read only the named snapshot's owners and experiment. These results never
 * choose a current context, compile an arrangement, or populate a draft. */
export async function loadSavedQuestion(snapshot: CompositionSnapshot, client: Pick<SavedWorkClient, 'view' | 'experiment'> = savedWork) {
  const ids = [...new Set([snapshot.arrangement.left.investigationId, snapshot.arrangement.right.investigationId,
    snapshot.focus?.investigationId].filter((id): id is string => !!id))];
  const experimentId = snapshot.arrangement.experimentId;
  const [results, experimentResult] = await Promise.all([
    Promise.allSettled(ids.map((id) => client.view(id))),
    experimentId ? client.experiment(snapshot.arrangement.left.investigationId, experimentId)
      .then((value) => ({ value, error: '' })).catch((cause) => ({ value: undefined, error: String(cause instanceof Error ? cause.message : cause) }))
      : Promise.resolve({ value: undefined, error: '' })
  ]);
  const owners = results.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []);
  const errors = results.flatMap((result, index) => result.status === 'rejected'
    ? [`${ids[index]}: ${String(result.reason instanceof Error ? result.reason.message : result.reason)}`] : []);
  const chainError = validateEvidenceChain(owners, snapshot.arrangement);
  if (chainError) errors.push(chainError);
  let experiment: WorkbenchExperiment | undefined = experimentResult.value;
  let experimentError = experimentResult.error;
  if (experiment) {
    experimentError = validateRecordedExperiment(owners, experiment) ??
      (matchesExperiment(snapshot.arrangement, experiment) ? '' : 'This experiment does not match the exact saved comparison targets.');
    if (experimentError) experiment = undefined;
  }
  return { owners, errors, experiment, experimentError };
}

/** A saved record is scoped to its context, thread and artifact citations.
 * Unknown renderer selectors cannot establish passage membership. */
export function savedQuestionFocus(snapshot: CompositionSnapshot, owners: Investigation[]) {
  const supported = supportsBlockFocus(snapshot.focus, snapshot.rendererVersion);
  const artifact = resolveTarget(owners, snapshot.focus).artifact;
  const block = supported && artifact && snapshot.focus?.blockId
    ? contentBlocks(artifact.text).find((item) => item.id === snapshot.focus?.blockId) : undefined;
  const focus = supported ? snapshot.focus : snapshot.focus ? { ...snapshot.focus, blockId: undefined } : null;
  return { ...resolveAttention(owners, focus, block?.citations), block, supported };
}
