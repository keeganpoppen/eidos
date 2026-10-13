import { readComposition, type Arrangement, type Attention, type Composition } from './comparison';
import { rendererVersion } from './semantic';

export type SnapshotSummary = { id: string; title: string; createdAtMs: number; rendererVersion: string; copiedFrom: string | null };
export type CompositionSnapshot = SnapshotSummary & { schemaVersion: 1; contentId: string; arrangement: Arrangement; focus: Attention | null };
export type SnapshotSave = { requestId: string; title: string; rendererVersion: string; arrangement: Arrangement; focus: Attention | null; copiedFrom?: string };
export const snapshotDraftKey = 'nema.saved-comparison.v1';

export function snapshotRenderer(composition: Composition): string {
  return composition.focus?.blockId ? composition.focusRendererVersion ?? rendererVersion : rendererVersion;
}

export function supportsBlockFocus(focus: Attention | null, version: string): boolean {
  return !focus?.blockId || version === rendererVersion;
}

/** Capture ordinary reference fields only. Local UI state and source data never
 * cross this boundary. Retrying must reuse the resulting body without recapture. */
export function captureSnapshot(title: string, composition: Composition, requestId: string = crypto.randomUUID()): SnapshotSave {
  const clean = readComposition(JSON.stringify(composition));
  if (!clean.arrangement) throw new Error('Apply a comparison before saving it.');
  if (!title.trim() || title.trim().length > 160) throw new Error('Use a name between 1 and 160 characters.');
  return { requestId, title: title.trim(), rendererVersion: snapshotRenderer(composition), arrangement: clean.arrangement,
    focus: clean.focus, ...(composition.snapshotId ? { copiedFrom: composition.snapshotId } : {}) };
}

function referenceKey(value: Pick<CompositionSnapshot, 'arrangement' | 'focus'> | Composition): string {
  const clean = readComposition(JSON.stringify({ version: 1, arrangement: value.arrangement, focus: value.focus }));
  return JSON.stringify({ arrangement: clean.arrangement, focus: clean.focus });
}

export function sameSnapshotView(composition: Composition, value: Pick<CompositionSnapshot, 'arrangement' | 'focus' | 'rendererVersion'>): boolean {
  return referenceKey(composition) === referenceKey(value) && snapshotRenderer(composition) === value.rendererVersion;
}

export function openSnapshot(composition: Composition, value: CompositionSnapshot): Composition {
  return { ...composition, open: true, arrangement: structuredClone(value.arrangement), focus: structuredClone(value.focus),
    focusRendererVersion: value.rendererVersion, snapshotId: value.id,
    undo: [...composition.undo, composition.arrangement].slice(-12) };
}

export function readSnapshotDraft(raw: string | null): { title: string; pending: SnapshotSave | null } {
  try {
    const value = JSON.parse(raw ?? 'null');
    if (!value || value.version !== 1) return { title: '', pending: null };
    const pending = value.pending;
    if (pending && (typeof pending.requestId !== 'string' || typeof pending.title !== 'string' || typeof pending.rendererVersion !== 'string' ||
      !readComposition(JSON.stringify({ version: 1, arrangement: pending.arrangement })).arrangement || !('focus' in pending))) {
      throw new Error('The saved comparison request cannot be recovered. Browser data was left unchanged.');
    }
    // Do not normalize a recovered request: its exact body belongs to this ID.
    return { title: typeof value.title === 'string' ? value.title : '', pending: pending ?? null };
  } catch (cause) {
    if (cause instanceof Error && cause.message.startsWith('The saved')) throw cause;
    throw new Error('Saved comparison browser state cannot be read. Browser data was left unchanged.');
  }
}

export class CompositionRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export class CompositionClient {
  constructor(private fetcher: (path: string, init?: RequestInit) => Promise<Response> = (path, init) => fetch(path, init)) {}
  private async request(path: string, init?: RequestInit) {
    const response = await this.fetcher(path, init);
    const data = await response.json();
    if (!response.ok) throw new CompositionRequestError(data.error || `Saved comparison request failed (${response.status}).`, response.status);
    return data;
  }
  async list(query = '', cursor = ''): Promise<{ compositions: SnapshotSummary[]; nextCursor: string | null }> {
    const params = new URLSearchParams({ limit: '20' });
    if (query) params.set('q', query);
    if (cursor) params.set('cursor', cursor);
    return this.request(`/api/compositions?${params}`);
  }
  async get(id: string): Promise<CompositionSnapshot> {
    const data = await this.request(`/api/compositions/${encodeURIComponent(id)}`);
    if (data.composition?.id !== id || data.composition.schemaVersion !== 1) throw new Error('The saved comparison identity or schema does not match.');
    return data.composition;
  }
  async save(body: SnapshotSave): Promise<CompositionSnapshot> {
    const data = await this.request('/api/compositions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!data.composition?.id || data.composition.schemaVersion !== 1) throw new Error('The saved comparison receipt is incomplete. Retry the same request.');
    // Receipt identity belongs to the captured request, including its old
    // renderer version after an upgrade. Current display compatibility is a
    // separate question and must not prevent confirmation of an earlier commit.
    if (data.composition.title !== body.title || (data.composition.copiedFrom ?? null) !== (body.copiedFrom ?? null) ||
      data.composition.rendererVersion !== body.rendererVersion || referenceKey(body) !== referenceKey(data.composition)) {
      throw new Error('The saved comparison receipt does not match the captured references. Retry the same request.');
    }
    return data.composition;
  }
}
export const compositionSnapshots = new CompositionClient();
