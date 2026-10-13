import type { Experiment, Improvement } from './reflection';

/** A browser preference, never an adoption receipt or authority token. */
export type ImprovementPreview = {
  schemaVersion: 1;
  scope: 'browser-presentation-preview';
  experimentId: string;
  proposalId: string;
  proposalVersion: number;
  beforeVersion: string;
  afterVersion: string;
  activeVersion: string | null;
  previousVersion: string | null;
  canUndo: boolean;
};

export function emptyImprovementPreview(experiment: Experiment, improvement: Improvement): ImprovementPreview {
  return {
    schemaVersion: 1,
    scope: 'browser-presentation-preview',
    experimentId: experiment.id,
    proposalId: improvement.id,
    proposalVersion: improvement.version,
    beforeVersion: improvement.beforeVersion,
    afterVersion: improvement.afterVersion,
    activeVersion: null,
    previousVersion: null,
    canUndo: false
  };
}

/** Resolve persisted references against the current proposal; discard all extra fields. */
export function readImprovementPreview(raw: string | null, experiment: Experiment, improvement: Improvement): ImprovementPreview {
  const empty = emptyImprovementPreview(experiment, improvement);
  if (!raw || raw.length > 4096 || improvement.experimentId !== experiment.id) return empty;
  try {
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object') return empty;
    for (const key of ['schemaVersion', 'scope', 'experimentId', 'proposalId', 'proposalVersion', 'beforeVersion', 'afterVersion'] as const) {
      if (value[key] !== empty[key]) return empty;
    }
    if (typeof value.canUndo !== 'boolean') return empty;
    if (![null, improvement.beforeVersion, improvement.afterVersion].includes(value.activeVersion)) return empty;
    if (![null, improvement.beforeVersion].includes(value.previousVersion)) return empty;
    if (value.canUndo && value.activeVersion !== improvement.afterVersion) return empty;
    if (!value.canUndo && (value.previousVersion !== null || value.activeVersion === improvement.afterVersion)) return empty;
    return {
      ...empty,
      activeVersion: value.activeVersion,
      previousVersion: value.previousVersion,
      canUndo: value.canUndo
    };
  } catch {
    return empty;
  }
}

export function applyImprovementPreview(preview: ImprovementPreview): ImprovementPreview {
  if (preview.activeVersion === preview.afterVersion) return preview;
  return { ...preview, activeVersion: preview.afterVersion, previousVersion: preview.activeVersion, canUndo: true };
}

export function undoImprovementPreview(preview: ImprovementPreview): ImprovementPreview {
  if (!preview.canUndo) return preview;
  return { ...preview, activeVersion: preview.previousVersion, previousVersion: null, canUndo: false };
}
