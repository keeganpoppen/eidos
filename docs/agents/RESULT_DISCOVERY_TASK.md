# Recover an exact result from a remembered phrase

**2026-10-13 · accepted root contract · base `4b9189232e12c83e12a87e94540fc6255b5337ce`
· C1/C5 / V1-03/ 04/ 08/12.** This product lane is independent of the bounded native
worker joining probe. It introduces no dispatch, account access or authority.

## Observed gap and user loop

The artifact catalog indexes only investigation titles. Root reproduced a result
titled “Release review” whose exact saved question mentions “cancelled preparation”
and result mentions “stopped claim”: both phrases return zero hits, while the title
returns one. Local authored report: `/tmp/nema-result-discovery-baseline.json`.

Find an old result using a remembered question or conclusion; inspect that exact
question, result and source support; deliberately add it to the working context;
save and inspect its frozen references. Search and inspection preserve local draft,
pending-save identity and current investigation. This makes existing provenance
and reuse discoverable without another model loop or graph framework.

## Frozen interface

- Extend only GET `/api/investigations/artifacts?q=...`. Literal trimmed Unicode
  casefold substring search matches owner title OR the question of this exact
  artifact's context OR this exact published artifact text. No owner-wide question
  concatenation, newer-context substitution, private capsule read, raw record,
  inherited artifact input, rationale or arbitrary unknown-field indexing.
- Keep one row per owner/artifact and its existing exact context/attempt IDs;
  current, native and historical artifacts retain existing deduplication.
  Existing title-only investigation catalog stays unchanged and labelled clearly.
  Empty artifact query retains its current metadata-only response.
- For nonempty artifact queries add `match:{field,excerpt}` to each ResultSummary.
  field is exactly title/question/result, deterministic precedence in that order.
  excerpt is at most 240 Unicode code points including optional ellipses; it is a
  plain-text fragment of that matching field, not generated interpretation. Preserve
  match visibility across casefold expansion. Snippet text is never execution policy.
- Keep limit 1–40, keyset ordering, query-bound cursors, conditional versions and
  replaceable derived indexes. Migrate existing warm databases and independent
  writers correctly. Do not parse canonical histories for each hot catalog read.
  Cursor semantics must distinguish old title-only searched artifact pages from
  new content search; do not silently mix their membership. Empty-query compatibility
  remains. State substring-scan and dirty-owner costs honestly.
- UI search explains its result-only fields and shows the matched field/excerpt.
  Add “Inspect selected result” before existing Add; bind the selected summary's
  owner/artifact/context to the existing ArtifactLineage source resolver. Show the
  original question plainly in that dialog. Missing or changed sources fail with
  exact references retained; never substitute a newer result.
- Search/select/inspect/close/reload do not alter draft/save/retry identity or send
  mutations. Only explicit Add changes selected result references, and ordinary
  Save freezes them. Existing busy/input-count constraints stay intact.

## Ownership and integration

- Root owns `src/eidos/investigation_reads.py`, backend tests, authored demonstration
  fixture and canonical docs. No native/authority/controller changes.
- native_frontier owns UI saved-work.ts, CatalogPicker.svelte, InvestigationPane.svelte,
  ArtifactLineage.svelte, relevant focused UI tests and a browser acceptance script,
  in a fresh isolated worktree at the base. Coordinate additional files first.
- gateway_review independently challenges migration, historical matching, privacy,
  stale UI responses and final exact-source reuse. Owns only separately named new
  tests if needed; root integrates. Native probe source review remains a separate
  bounded task when that lane is ready.

Acceptance includes old A1/C0 and newer A2/C1 under one owner: a phrase unique to
A1 selects, previews and includes A1/C0 with original support. Add title-only decoy,
same-owner question-only match, result-only match, Unicode expansion, literal SQL
wildcards, source loss, delayed query/detail, independent writer, rebuild/reopen,
bounded pages and private-only canaries. Record a prechange failure and actual
postchange desktop/mobile API/browser loop with no native/model call.

A returning reader trial may use already authorized public or synthetic retained
work without a supplied title/ID. Report navigation and incorrect choices; scripted
success is not proof of human speed, answer quality or usefulness. Do not access
personal traces merely to make that claim. Default Python/UI checks and direct UI
inspection precede one coherent commit and nonforce push. Native joining evidence
can integrate separately when independently verified; neither lane gates the other.
