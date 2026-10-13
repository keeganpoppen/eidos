# Stable recovery from substantial history

**2026-10-13 · integration base `ad73408` on main.** The commit containing this
report integrates bounded server history, exact source navigation and the native
account acknowledgement prerequisite. This serves V1-01/02/03 and advances the
V1-05/12 admission work; it does not establish the full V1 loop.

## Integrated behavior

The browser requests at most 40 complete turns from authoritative persisted
evidence. Stable record anchors survive new turns, late old-turn events and a
delayed native acknowledgement. Exact source seeks reject another thread's record,
even when it lies inside the selected turn's min/max extent. Returned items and
turns carry constituent record references: interval overlap alone no longer
creates a highlight or source target. Disjoint semantic support remains selectable
across pages and reload; turn-only evidence has a focusable destination.

A SQLite read snapshot binds metadata, semantic revision selection, projection
and version. An unchanged poll returns only identity/version/window and retains
the existing browser evidence object. Semantic revision or observer-reliability
changes invalidate the version. Delayed requests cannot overwrite newer user
navigation or resurrect cleared focus. No raw trace or historical map is replaced.

Separately, a profiled native worker now checks `account/read` before creating a
thread. This acknowledgement is not entitlement, startup containment or provider
context evidence. The default native startup gate is unchanged. See the
[native admission investigation](NATIVE_ADMISSION_FRONTIER.md).

## Integration and verification

Recovered lanes: UI `dc906cb`, acceptance `8183ac6`, account check `86b3767`.
Independent review produced UI `f2dff07`/`76afb59` and acceptance `afaae8a`/`bdabf82`; the parent added
snapshot-bound paging, exact projected membership, versioning and backend tests.
Source worktrees retain their original histories; integration used reviewed file
diffs, not a blanket merge of overlapping trees.

Combined commands on the integrated tree:

- `uv sync`; `uv run eidos --help`; `git diff --check`: passed.
- `uv run pytest`: **653 passed, 5 skipped** (explicit native probe opt-ins).
- `cd ui && bun install && bun test tests && bun run check && bun run build`:
  **46 tests / 225 assertions**, **0 errors / 0 warnings**, build passed.

Backend counterexamples include 1,200-turn complete pagination, unknown native
fields, interleaved threads/items/turns, pending sends, acknowledgement merges,
invalid anchors, unrelated semantic revisions, semantic-only updates and a writer
appending through another SQLite connection during projection. The unchanged path
is tested to avoid raw-record and outline loading.

The real Chromium workflow used a persisted 1,200-turn/2,498-record synthetic
history through actual HTTP responses. It recovered the rejection at record 138
and later decision at 2397 into one frozen two-record context, rejected the
neighbor thread's record 1348, and displayed the whole 98-event tool item. Sixteen
full page responses each contained at most 40 turns. The first response body was
42,835 bytes; two idle unchanged responses were at most 297 bytes. Measured bodies
were decoded UTF-8 bytes, not network wire size. Appending a late old-turn record
and a new turn grew history to 1,201 turns while preserving the old decision page,
selection, keyboard focus and scroll, then preserved its source anchor on reload.
The parent independently inspected the desktop source capture. The complete
[retrieval measurements](paged-history-retrieval.json) came from the full workflow
before the localized responsive header change. Final acceptance commits `8bd00f9`,
`ee66d70`, `c6e7ce6` add the [supplementary current-UI checks](paged-history-navigation.json):
delayed real 404/200 responses cannot steal newer focus or undo Clear focus, and
restored disjoint source links work at 900px and 390px without horizontal overflow.
The delayed-response checks do not alter HTTP bodies and are separate from the
unintercepted transfer measurements. The parent also inspected the final narrow
capture. Preserved views: [decision](paged-history-decision.png),
[desktop controls](paged-history-navigation-1600.png),
[narrow controls](paged-history-navigation-390.png).

Reproduction: start `scripts/investigation_demo.py --db <fresh /tmp path>
--long-history --serve`, Vite on 5173, and isolated Chromium with debugging on 9222.
Run `NEMA_UI_DEMO_DB=<same path> NEMA_UI_EVIDENCE_PREFIX=/tmp/nema-history
node scripts/check_investigation_ui.mjs`, then
`NEMA_UI_EVIDENCE_PREFIX=/tmp/nema-history-navigation node scripts/check_history_navigation_ui.mjs`.
The full script appends once, so repeat full runs need a fresh database. All owned
services were stopped after acceptance.

The separate native outer-boundary experiment `dc9767c` also integrates here.
The parent reviewed its source and reran
`NEMA_NATIVE_OUTER_PROBE=1 uv run pytest tests/test_native_outer_boundary_probe.py`:
**8 passed**, including real Codex 0.154.0 startup in a disconnected bubblewrap
namespace. An enabled synthetic MCP ran before inventory inspection but could not
perform the tested outside reads/writes, network access, packet remount or nested
namespace operation. Its detached child's heartbeat stopped on shutdown. No
credentials were mounted; no model turn ran. This demonstrates a promising startup
boundary for the tested fixture, not general security or a production launcher.
See [the experiment and next test](NATIVE_OUTER_ADMISSION_EXPERIMENT.md).

## Limits and next implication

Forty turns bound projection count, not a huge turn's bytes, semantic outline size,
or every SQL aggregation. Browser focus remains reference-only local storage.
An item range added to context still selects the selected thread's records within
that range; preview exposes possible same-thread interleaving. Source-only records
without a conversation turn are not yet presented in this conversation view.

The authored history is synthetic, not a private native export. Scripted navigation
does not measure human reorientation speed or model quality. No authenticated
model request, provider capture or paid API call is part of this integration.
Useful recovery now has a persisted large-history baseline. The next semantic
integration should make exact derived results reusable as context while preserving
their original support and the distinction between an artifact and live authority.
