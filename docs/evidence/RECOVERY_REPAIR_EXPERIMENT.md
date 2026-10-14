# Recovering a repair exposes an unstated requirement

**2026-10-14 · workbench base `035104de1e109f72fb160bc9bf2b5e5d80c1f8f0`.**
[Contract](../agents/RECOVERY_REPAIR_TASK.md); C3/C4/C5, V1-01/04/11.
Participants used host collaboration. Product operations and local checks started
no native Codex/app-server, account, private-history or upstream inference work.

## Result

A fresh participant discovered the source of a historical request-identity failure
through existing workbench search, saved sufficient support for an independent
reader, and proposed a defensible repair. It differed from the coordinator's intended
repair because the coordinator had omitted an explicit compatibility requirement
from the delegated question. This was not a demonstrated retrieval defect.

The participant's test-only proposal passes its revised contract; an unchanged copy
of the original contract still fails. A second question explicitly required all
original identities and the original test to remain unchanged. Its source-only
proposal passes the original two cases. Both interpretations, their distinct
questions and the later verification remain separately inspectable. The second
result is conditioned on a recorded clarification, not an unassisted blind success.

## Corpus and independent entry

[Producer](../../scripts/recovery_repair_demo.py), lane `dc457438`, admits thirteen
complete pinned public Git files (177,215 bytes), a neutral revision/path/hash
inventory and an explicit local observation through ordinary text preview/commit.
No question, selected context, finding or answer is seeded. It reads historical
source as bytes and never executes it. All fifteen previews precede admission.
Root independently compared every original download with staged bytes and all
thirteen public Git blobs. The initial marker has SHA256
`1cefcfa6b7dd620926780a4f85772a6c7b835f84b5cd17e58f1be2236812080a`.

Producer checks: fifteen exact original/receipt roundtrips after reopen, ordinary
search, zero investigations/attempts; invalid UTF-8 retains staged files and fifteen
preview responses with zero admissions. Existing supplied-text tests: **56 passed**.
Independent review found no blocker. Unexpected raised exceptions during preview
can lose earlier in-memory diagnostic responses; ordinary refusal retains them.

Root first ran the original two-case compatibility test in a clean isolated checkout
at `fa7eabffe93b87b62ed91ac51b84f4fb1ca101c8`: both fail at the attempt-manifest
assertion after the context ID, context manifest and prompt-hash assertions pass.
The observation records Python3.14.7, SQLite3.53.4, interpreter hash, exact command,
stdout/stderr and offline locked dependencies. SHA256
`41a55669b63b55fb688a4df8f85dbe3214da4025b0853866d2be15caa015f9a4`.

The fresh participant received the natural release-review task, local UI/API
addresses and generic interface instructions. Current repository, database, later
Git history, known correction, coordinator packet and other temporary experiments
were withheld. Actual UI discovery/source and saved-context inspection were required;
ordinary HTTP reads/writes could supplement them. It executed no recovered code.

## First interpretation and its review

Searches “manifest”, “startup” and “unchanged” returned10,6,7hits. The participant
found the sole changed `limits` sentence and correctly explained how content identity
changes when that text changes. Nine records became a113,585-byte projected context.
It proposed updating the fresh-request golden while keeping three packet/prompt
goldens, old stored pins and the newer policy description. Its saved finding calls
the golden stale; that characterization depends on its inferred compatibility policy.

Owner `investigation_65bdf83cdd814d5dacb458f7ec7e3704`, finding
`artifact_92e859b08fbc743c0c9443b76805c1246f697c1a654537a21ec0141b93dd955a`.
Context `context_fe453a8ec11e74a7b14ef3f8c7c6379cb6301adb0d3ff1c8abc820e011b1de4c`;
promptSHA `38930e908f4c50b963eb841ed25035dc4e8d977940f07e14f36d710303597b53`.

Its retained main-session log contains628requests:626GET200 and twoPOST201 (question
and finding), including periodic UI reads. Recorded response bodies total2,437,694
bytes; this excludes headers and initial orphan-context traffic. The first non-TTY
driver lost stdin and left an isolated browser context; root clarified ownership
so it could be closed. That is one operational assistance exchange, zero case help.
Initial orphan polling was not exported. No browser exception was captured.

A second fresh participant received only the exact finding-source endpoint. It
verified all nine raw/file hashes and independently found the reasoning sufficient
for bounded verification. It also identified a concrete omission: the finding
referred to a unified diff whose bytes were absent from the saved packet. Its report
SHA is `3e9e5dbc540445af7b0bcdefdb893bbc85453745f537b2220bcd323ee52ccb18`.

Root manually inspected the patch and applied it in another isolated historical
checkout. Its renamed two-case test passes; a byte-exact copy of the original test
fails both cases. Runtime source remained unchanged. PatchSHA
`05d40ed060a8fee12b4a4bf8ce1f2632e9b6431074ef1c4348ee6a4cf19e9bcd`;
competing-check observationSHA
`3fa5126d2f393345699b8199baa02092481e4973775403f1a36b3f08fa694105`.
These results distinguish contracts; tests alone do not choose the governing policy.
The strategic scout withdrew its initial “wrong answer” characterization.

## Explicit second contract and verification from saved support

Root retained the first result and admitted its patch, competing-check observation
and independent review as ordinary files. One follow-up explicitly required all
four original identities and the original test to remain unchanged. It also required
exact proposal bytes in the saved context before the next finding. This is one
case-constraint intervention, not a correction secretly supplied to the first run.

The participant saved a new question containing that constraint, eight source records
and the exact first finding as a result input. Its129,221-byte context includes the
1,273-byte patch as record19. The patch restores the legacy policy string and adds
three comments distinguishing identity-bearing v1 input from managed-startup
observations. The participant explicitly notes that preserving an identity and
changing the serialized words within that object cannot both be satisfied.

Owner `investigation_c166d20a00074e5fb63f82812e85dc74`, finding
`artifact_b379c2ff9d46dd79d3c4d92a0e64990e7b1b7e9df8901e2673d749145481e365`.
Context `context_d0a6938144a979c313e471de8e704097c85a8cb7020f24eba3d8f4a63845e90e`;
promptSHA `46663f857d2de834eb7dba009802a2597af5801a916c13a3de5467c4598b77ae`.
Its693requests contain689GET200, one previewPOST200 and threePOST201 (patch admission,
new question, finding). No HTTP/browser error or additional assistance occurred.
The complete first owner remained equal to its saved final snapshot.

Root extracted the patch from the canonical frozen record, verified its hash, reviewed
it and ran the unchanged original test in the original clean historical checkout:

```sh
uv run --offline --locked pytest \
  tests/test_artifact_context_compatibility.py::test_legacy_packet_and_request_manifest_match_prechange_revision
```

**2 passed**, same recorded runtime. Test and dependency hashes remained unchanged;
only `investigation_context.py` changed. PatchSHA
`1ece8b39e2ebe7fde4347d6d3a58c7bad898705dd8145da3be9653e44be8b63a`;
verification reportSHA
`9cc953723a0923f992d2538e010ca39388aed07ea5e5d198712406855bcacd98`.
No full historical suite, upgrade/reopen or current native behavior was tested.

That report was admitted as record20 and a separate verification finding, owner
`investigation_af2d4267cb4f4bf786113c8e7e206d3c`, finding
`artifact_de9f6a9fd9fea334373a4f8afa74024a787a50b12753790648a3e62a446c54bc`.
Earlier proposals retain their then-accurate unexecuted status. Actual browser flow
29requests/two compositionPOSTs saves both the two interpretations and the constrained
proposal beside its verification. Fresh browser after API restart:22GETs/zeroPOSTs,
both comparisons exact; final narrow presentation read:22GETs/zeroPOSTs. All three
canonical owners remain exact with null attempts. Root inspected desktop/390px;
the first narrow capture showed controls, so a later read-only capture scrolls to
the results after resizing. No global overflow or browser exception occurred.

## Accepted change, artifacts and limits

Current main already preserves the legacy string. Only the three explanatory source
comments are adopted from the second proposal; the serialized policy value and tests are unchanged.
The orchestration method now says governing constraints belong in the actual delegated
question and exact patch bytes must accompany patch review. Parent seed/legacy checks:
**7 passed**. No new UI/backend feature or semantic schema was justified. The prior
full product suites and CI belong to035104d, not a new full-suite run here.

Artifacts: `/tmp/nema-recovery-repair-20261014`, participant
`/tmp/nema-blind-recovery-participant-Z0i46V` (and `stage2/`), independent review
`/tmp/nema-selected-context-review-sZjJg1lS`, baseline and competing check directories
`/tmp/nema-recovery-repair-baseline-20261014` and
`/tmp/nema-recovery-repair-test-proposal-20261014`. Root read the reports, diffs,
request logs and canonical values; `coordinator-*-audit.json` records checks.
Root browser script `/tmp/nema-recovery-repair-browser.mjs`; report hashes:

```text
browser-flow.json         fae141dac5176d647f440c88d0d7b29f6814f6352b073ecf417d7228da43e79b
browser-reopened.json     06a0ee5bcdbba1e279490fb742e552e42e16d7fdd4fbe64cdad39dfe7aa97c85
browser-presentation.json fea4265143c90b217a75761d79e723eba74ada352ead8b9ed88a50538e3bd14a
saved-verification.json   084929c0ffc2462e61a3e53e115bcab83bc8fc6da7a7ab9179727f74d2e84cc5
```

All owned API/Vite/Chromium groups/helpers stopped;8767/5173/9233closed, temporary
Vite config removed: `/tmp/nema-recovery-repair-cleanup.json`. This is retrospective
developer continuity evidence, not a human-speed or controlled model-quality study.
It shows neither that this selection outperformed another nor that a new export,
recipe, executor or provenance type is needed. The next real repository task should
start from its actual saved question, constraints and support, with every later
case instruction recorded as a revision rather than an invisible coordinator rule.
