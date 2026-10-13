# Current handoff — saved comparisons and native tool controls

**NEMA-SEED-1 · 2026-10-13 · latest integration base `579af9d` on main.**
The commit containing this handoff identifies the completed integration. The continuing mission
remains active; [PROGRAM](PROGRAM.md) owns conjectures and opportunity ordering.
The [previous scale integration](history/SAVED_WORK_SCALE_INTEGRATED.md) is pushed;
its [public CI](https://github.com/keeganpoppen/eidos/actions/runs/38455597139) passed.
Neither a green suite nor this milestone completes the mission or V1.

## Active successor checkpoint

`579af9d475045936ccfc24d53104990e6064e56b` was committed and pushed with a clean
tree; public CI passed [run 38458842177](https://github.com/keeganpoppen/eidos/actions/runs/38458842177).
The next [recorded-experiment contract](RECORDED_EXPERIMENT_COMPOSITION_TASK.md) is
active from that revision. UI owns `/tmp/nema-recorded-experiment-ui`; independent
acceptance owns `/tmp/nema-recorded-experiment-acceptance`. Root's read-only backend
review found existing exact experiment GET/immutable targets adequate; no new route
or mutation is planned. Acceptance will label later attempt/result state as authored
trusted-host fixtures because public draft revision freezes after dispatch.

Native tool-control contributions `22009db` + `7afd982` are inspected and integrated
in this successor integration. Independent default review passed **64 passed / 7 skipped**; parent
combined native opt-in passed **71**, including earlier text-only probes. The final
metadata fix distinguishes two accepted provider requests from the 24 total HTTP
request bound. Combined default suite: **849 passed, 38 skipped**.
[Native evidence](../evidence/NATIVE_TOOL_BOUNDARY_EXPERIMENT.md). No production admission changes.
Native lane is now a read-only scout ranking the next discriminator: known model
metadata, resource bounds, and the explicit trusted-client/caller-auth boundary.
The delivered status below belongs to `579af9d`.

## Implemented loop and contract

Save an applied comparison and exact focus under a name, find/preview/open it in a
fresh browser on the same database, then save an altered copy with ancestry.
[V1-01/10, C5; frozen contract](DURABLE_ARRANGEMENTS_TASK.md). The snapshot stores
compiled historical references, never an intent to re-resolve against newer work.
Create-only ordinary ContextManifest Values and a thin local catalog/idempotency
index preserve content. No mutation, dispatch or shared mutable workspace head.

GET/POST `/api/compositions` provides bounded metadata discovery and immutable
creation; GET `/:id` returns exact content. New saves validate owner/context/
artifact/record and inquiry/experiment relationships. Exact successful retries
return the original receipt even after source loss; changed-body retries conflict.
Existing source loss remains unresolved references, never a latest substitute.
Browser drafts and their pending save identities remain local. Passage selectors
carry the installed parser version; unknown versions retain artifact/record IDs
without interpreting a passage under a different parser. [D29](../roadmap/DECISIONS.md).

## Snapshot integration verification

- Integrated `uv run pytest`: **821 passed, 34 skipped**, explicit native opt-ins.
- Integrated final Bun: **67 tests / 344 assertions**;
  Svelte **0 errors / 0 warnings**, build passed.
- Independent UI source review found a pending-save upgrade failure: exact old
  renderer receipts with no passage were compared to the newly installed renderer.
  Fix `c4fa791` separates receipt identity from display compatibility. Further
  review fixed mobile long-title wrapping (`06893af`) and legal whole-artifact
  cited-record focus without a passage selector (`849729b`). Parent full UI
  tests/check/build above include all fixes.
- Independent API acceptance **33 tests**, plus parent **20 focused backend tests**
  pass. Actual HTTP, two-connection concurrency, reopen/retry, malformed reference
  rejection, missing source, exact inquiry/experiment pins, metadata pages covered.
- Parent generated/reopened a fresh synthetic snapshot database; JSON reports
  `/tmp/nema-composition-integrator-20261013.json` and its reopened counterpart are
  byte-identical. Fixture source state remains intact.
- Parent guarded native synthetic-provider opt-in: **39 passed**. Two native
  turn RPCs, **zero real model/upstream calls**, no credentials or gate changes.
  [Exact scope](../evidence/NATIVE_SYNTHETIC_TURN_EXPERIMENT.md).
- Parent independently reran the complete actual Chromium check against main:
  fresh-browser preview/open, committed-lost-reply retry, exact raw-source bytes,
  changed copies, historical inquiry pins, missing-source repair and renderer
  fallback all pass. Desktop/390px screenshots inspected; long-title and focus
  overflow zero, no JavaScript exceptions, six intended POSTs, no native dispatch.
  [Full evidence and reproduction](../evidence/COMPOSITION_SNAPSHOT_INTEGRATION.md).
- Final integrated Python was repeated after the fixture addition: **821 passed,
  34 skipped**. Seed-context tests and diff check passed.

## Active ownership and next runnable action

Accepted independent acceptance `0abeed7` + `17d7be6`; UI `4234a9f`, `c4fa791`,
`06893af`, `849729b`; synthetic native transport `b1896ae`. Parent owns backend,
shared docs and the final main commit. Worktrees remain recoverable at
`/tmp/nema-durable-arrangements-ui` and `/tmp/nema-durable-arrangements-acceptance`.
All owned snapshot fixture services have been stopped after parent reproduction.
Local parent artifacts: `/tmp/composition_snapshot_main_reproduction.json` and
matching PNGs; final fixture DB `/tmp/nema-composition-snapshot-final-20261013.db`.

**Next runnable action:** after committing/pushing this wave, dispatch the
[recorded-experiment composition contract](RECORDED_EXPERIMENT_COMPOSITION_TASK.md)
from the new main revision into separate UI and acceptance worktrees. Root reviews
existing experiment HTTP/frozen-reference invariants while those lanes implement.
No human decision blocks ordinary repository work.

Native lane `/root/native_frontier` in `/tmp/nema-native-account-admission` completed
the tool-boundary probe above and now owns a read-only discriminator scout. New script/tests/evidence plus approved extraction of
bounded HTTP parsing from its prior synthetic probe. Fresh disconnected namespace,
noauth local fake provider, no private state, upstream, real models or production
profile changes. Default checks launch no native. This work need not delay the
snapshot integration. Observing an action after execution is not admission.

## Frontier decision and limits

The next product loop connects **real recorded context experiments** to comparison
and snapshots. The existing comparison surface only resolves authored fixture
experiments; real alternatives are context-only. Independent UI scout recommends
exact experiment GET, reviewable context-lens composition, source-level frozen
input differences and separately labelled current review. Challenge later C2/A2
and a new result for C1: old experiment must stay C0/A1 versus C1 with no invented
alternative result. Preserve dirty drafts and saved snapshots. No recipe activation
until observed selection friction and an evaluation justify one. The [next task contract](RECORDED_EXPERIMENT_COMPOSITION_TASK.md) records the
reviewed sketch; implementation has not begun.

Same-database recovery only; no authentication/collaboration synchronization or
human-speed claim. First preview loads complete referenced owners via the existing
cache; metadata discovery does not cap all internal SQL/memory. Legacy browser
focus without renderer metadata retains prior local behavior. Native text-only
transport leaves tool execution/caller binding unproven; production gate is closed.
Generic TM remains a trusted-host API, not arbitrary-caller security.
