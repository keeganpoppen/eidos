# Direct saved result uses — integration evidence

**Completed · 2026-10-14 · implementation base `25d6350b104c2543060fe76a9447502c81f56caa`.**
The base authored-finding commit is pushed and
[CI38503232607](https://github.com/keeganpoppen/eidos/actions/runs/38503232607) passed.
[Contract](../agents/RESULT_USES_TASK.md). No real account, native/model or private
history calls are part of this slice.

## Decision and independently observed baseline

The question is “Which saved questions included F0, and what did each receive?”
Upstream lineage and text search already exist. Neither is an inverse membership
query. This slice derives the existing context.artifactInputs relation; it does not
invent a dependency ontology or infer that a claim relied on a supplied input.

The backend scout's six-owner/seven-context disposable fixture needed32,543bytes
to scan all owners. Root independently reproduced the relation on public repository
excerpts from the authored-finding case. F0 records the existing import-overlap
boundary; F1 is an uncited alternative hypothesis, with no supersession relation.
B0 includes F0 and produces a finding, then current B1 drops it. C includes B's
finding. D copies B0 inputs. E shares raw records only. F mentions F0 in prose.
Exact direct uses are historical B0 and current D. Text search returns B and F,
missing D; the proposed uses route404s. Root's full-owner response was104,509bytes.

- Root baseline `/tmp/nema-result-uses-baseline.py` and `.json`;
  reportSHA256 `212b292440b6178f45775aa395f967a1f80dfce6fd0bd315c2cb6dd05ef07350`.
- Actual baseline browser **21GETs/zeroPOSTs**, desktop1600/narrow390 inspected.
  Exact independent pending question/finding storage survived original-provenance
  inspection. Report `/tmp/nema-result-uses-browser-20261013-baseline.json`,
  SHA256 `86001bfc89d3d776b544a59e67165b1f9c9afb1c13f7d51ac0a5886840da6ec9`.
- Root fixture `scripts/result_uses_demo.py`, marked database
  `/tmp/nema-result-uses-20261013.db`, marker `/tmp/nema-result-uses-marker.json`.
  Two authored public excerpt records; six owners/seven contexts; no attempts.
  `/tmp/nema-result-uses-canonical-before.json` records exact owner JSON hashes/raw
  bytes before integration. Browser script `scripts/result_uses_browser.mjs`.

All fixture records are explicitly authored public repository excerpts, not private
conversation history or observed native output. Screenshots and large reports stay
outside this public repository. Scripted availability does not measure human benefit.

## Integrated behavior and review

Backend `18b5fc44720087ba6517ee81f225f67b9772c22b`, UI
`4466c9142e5cd319a49006d81702ed8c4ef79b0a` plus presentation follow-up
`05b8e5e9ef887f55b46ab0e6a397461d0fb46849`, independent tests `a2c88d6`.
Root owns scripts/docs and combined integration. [D36](../roadmap/DECISIONS.md#d36--direct-saved-uses-describe-input-membership-not-inferred-dependence)
records the relation's deliberately narrow meaning.

Two read routes expose bounded direct-use metadata and exact consumer/context
detail. Replaceable SQL projections retain one row per source pair/consumer/context;
dirty triggers observe independent writers. A relation version binds cursors;
ownerVersion binds detail. Source-owner existence is not required. Migration,
consumer deletion and rebuild preserve canonical bytes. List responses cap the whole
UTF-8 JSON envelope at128KiB and40rows, reducing page length without skipping uses.
The UI opens inside existing result provenance, keeps independent drafts/source
focus unchanged, and places long exact references in expandable details.

Review found and repaired two implementation issues:

- Frozen authored text/citation arrays could be changed under the same artifact ID.
  Shared standalone validation now checks retained schema/owner-bound content hash
  without re-resolving the original context or reclassifying its citations.
- Strict new projection validation broke an existing result-search fixture whose
  ignored input field was intentionally malformed. A fixed derived error marker
  now isolates the new uses failure; legacy catalogs retain their behavior. Uses
  reads refuse completeness while malformed projections remain, clearing on repair.

Explicit inspection now scrolls/focuses its preview. A late original-source read
cannot steal that focus after uses navigation began. Actual narrow review also
caused the reference disclosures: the first layout put long IDs ahead of the finding.

## Parent verification

`uv run pytest`: **1,742passed /55explicit native skips in61.08s**.
`/tmp/nema-result-uses-parent-full.log`, SHA256
`ea7f102134cf136833b3fd55c0e43a23aa506b6fa5fdae93632fc93203750a5b`.
UI: **242tests /1,075assertions**, Svelte0errors/0warnings, clean production build.
After the presentation-only follow-up, parent check/build passed again; focused
22tests/135assertions passed in the UI lane. Parent logs:
`/tmp/nema-result-uses-parent-ui-{tests,final-check,final-build}.log`.

Independent9cases and backend27cases cover source/raw loss, consumer deletion,
independent-writer cursor/detail invalidation, historical/current labels, unchanged
canonical bytes on rebuild, missing/wrong membership, ambiguous identities, malformed
snapshots and altered authored content. Emoji and JSON-escaped control text exercise
actual serialized envelope reduction with complete pagination. Warm list/conditional
reads prove no canonical-owner parsing. Legacy source/prompt/manifest behavior passes.

## Actual rendered acceptance

Final reports share prefix `/tmp/nema-result-uses-final-browser-20261013`:

| Run | Observed outcome | Requests | Report SHA256 |
| --- | --- | --- | --- |
| `flow` | Exact B0/D list; F0 snapshots/rationales; F1 empty uses; explicit error recovery; cancellation and held original-source focus guard |40GET/zeroPOST|`098625d9dd953a1d4a12154f9b0faa7bc575e6d10a35db9f32f0f94315e67b77`|
| `reopened` | Fresh browser after actual API restart recovers the same uses and exact contexts |24GET/zeroPOST|`6aefc521e5929cf30e89740d0b767532bd0b73b507aa9e6f2fae8f113063354c`|
| `source-deleted` | Original source404 after trusted fixture deletion/restart; surviving B0/D snapshots still exact |23GET/zeroPOST|`a732b05211aa25815d3d94dc4c69a3c1e7b523c1ef594851f0b32ec53bcebd82`|

Each final list is1,311bytes; baseline full-owner scan was104,509bytes. This compares
relation metadata with the previous discovery requirement, not total task transfer
or human speed. All runs preserve exact pending question/finding storage and source
focus. No runtime exceptions or horizontal overflow; desktop1600/narrow390 actual
screenshots inspected. No mutation or native/account call occurred through the UI.

The held detail was **aborted by Chromium on close**, retiring its interception ID.
The first harness incorrectly tried to release that retired ID; retained evidence:
`/tmp/nema-result-uses-browser-20261013-flow-first-failure.json`, SHA256
`ddb59406b2fc4a9437e3e22802764ccd931effaf2940f7af232315c79c752387`.
The corrected script distinguishes cancellation from delivered stale data. Separate
helper tests cover fetchers that ignore abort. Held original-source delivery really
does complete after B0 inspection, preserving focus/scroll. No stale-delivery claim
is inferred from cancellation alone.

The deletion harness also initially omitted the source creation-request foreign key,
so fixture preparation refused and the API did not start. No owner/raw row was
deleted. Corrected fixture-only transaction removes that owner's creation/revision
request rows before deleting its owner/raw evidence; authored finding receipts remain.
The browser now requires the completed fixture marker. Preserved failure report:
`/tmp/nema-result-uses-final-browser-20261013-source-deleted-first-failure.json`, SHA256
`d978277b7cd1ff88495c8c29fd91a60c72bab73ed03e2d345bea979b2ce9969b`.
Corrected full deletion/restart/browser mode passed afterward. This is failure
injection, not a newly exposed product deletion operation.

Before deletion, all6owner JSON hashes and2raw records matched their original bytes.
After deliberate deletion, all5surviving owner JSON hashes remain identical, with
zero raw records and all attempts/native artifacts null. Parent verification report
`/tmp/nema-result-uses-parent-verification.json`, SHA256
`c1de1a78048d8c1fb56a7a88cf2afd2095e148cb3c84f93832f1ee1b528bbf7a`.

All owned API/Vite/Chromium descendants and crash handlers stopped;8767/5173/9233
closed, temporary Vite config removed. Chromium used fresh profile/config/cache
directories. `/tmp/nema-result-uses-cleanup.json` records cleanup.

## Limits and next discriminator

The relation reports saved input membership, not native consumption, claim reliance,
transitive effects, automatic supersession or invalidation. Standalone authored hash
validation does not authenticate an author or re-establish original support. Cold
and dirty indexing still parses whole owners; relation versions scan matching
metadata. Exact context detail retains existing packet limits; there is no new global
owner/database/CPU quota. A malformed uses projection blocks completeness globally,
without breaking legacy catalogs. Scripted/fresh-agent success cannot measure human
benefit or model quality.

The next read-only strategy scout challenges whether these connected Values support
an actual repository improvement decision. Prefer a pinned before/after change and
observed failing/repaired regression, recovered through existing findings/comparisons,
before relaxing native experiment gates or adding another reflection abstraction.
