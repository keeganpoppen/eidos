# Find and inspect an exact saved result

**2026-10-13 · integration base `4b91892` · C1/C5 / V1-03/ 04/ 08/12.**
[Accepted contract](../agents/RESULT_DISCOVERY_TASK.md). This read/reuse loop needs
no model, account or native execution. It improves access to retained work without
changing its evidence, context pins or authority.

## Observed gap and implementation

Before this change, artifact search matched only investigation titles. Root's
authored counterexample titled “Release review” had the question “Why did cancelled
preparation resume after restart?” and a result about a “stopped claim.” Searching
either remembered phrase returned zero results; searching the title returned one.
Report: `/tmp/nema-result-discovery-baseline.json`.

Artifact catalog queries now match literal Unicode-casefolded substrings in the
owner title, the exact artifact-context question, or that published result's text.
Each hit retains its owner/artifact/context/attempt tuple and a plain-text excerpt
of at most 240 code points. Field precedence is title, question, result; no ranking
or inferred relevance is claimed. Unicode expansion maps folded offsets back to
original text. Oversized expanded matches may be truncated with omission markers.

The separate search table is a replaceable projection of ordinary canonical rows.
It indexes no raw records, projected prompts, nested inputs, arbitrary unknown
fields or private capsule databases. A historical result cannot borrow a newer
question from the same owner. Missing old context leaves result-text discovery
possible, but exact-source inspection fails instead of substituting another context.

The ordinary investigation catalog remains explicitly title-only. Empty artifact
queries keep their previous metadata-only payloads. Searched artifacts use a new
cursor kind so old title-only pages cannot silently mix membership with content
search. Keyset ordering, query binding and conditional response versions remain.
Migration marks existing unindexed artifact owners dirty; warm reopen does not
rebuild everything. Independent writes and owner deletion invalidate derived rows.
Rebuild leaves canonical state and response identity unchanged.

The existing picker labels match fields and excerpts. Selections retained outside
the current page are labelled separately from current-query hits. “Inspect selected
result” appears before Add and opens the existing exact-source dialog with the
selected context pin. The dialog now states the original question. Search,
inspection and closing preserve the draft; explicit Add chooses the result reference
and ordinary Save freezes its content. No execution controller is introduced.

## Verification and measured costs

Parent full default suite: **1,287 passed / 53 explicit native skips in 25.60s**,
`/tmp/nema-discovery-parent-suite.log`. Focused **26 passed**, including 11 new
discovery cases and 15 existing read-projection cases. Backend checks exercise exact
old A1/C0 versus newer A2/C1, title decoy, result-only hit, private/raw/prompt/input/
unknown-field exclusions, lost historical context, literal SQL wildcards, Unicode
expansion, migration, actual independent writer/reopen, rebuild and cursor rejection.
The full API path freezes the discovered old result into a new context without a
turn request or changing original canonical rows.

Parent frontend: **99 tests / 499 assertions**, Svelte **0 errors / 0 warnings**,
build passed. Tests include isolated query caches, retained matches and preserving
the old context/attempt if a later row reuses an artifact key inconsistently.
Independent review inspected the concrete backend/UI diff and reran 26 focused
checks, with no remaining material issue.

Actual API/Vite/Chromium acceptance captured all 65 response bodies: 63 GET 200,
one deliberately injected missing-source 404, and one ordinary draft-create 201.
Six checkpoints establish the old question/result hit beside a title decoy;
pre-Add original support inspection; no raw-only search hit; correct retained
selection; stale query/detail rejection; exact missing-source references; unchanged
dirty draft/pending save through inspection/reload; and explicit Add/Save freezing
A1/C0 instead of newer A2/C1. No dispatch/native/model call or browser exception.
Desktop 1600px and 390px screenshots show no page/dialog/picker horizontal overflow.
Root directly inspected original-question/support and mobile frozen-input images.

Report `/tmp/nema-result-discovery-complete.json`, SHA256
`06ec3230c001fb1d826e2e7e0e71faebf8fbe56a54685bc2b25de7f02801ae83`.
Five screenshots share its prefix with question-hit, original-question-support,
mobile-match, mobile-original-question and mobile-frozen-input suffixes. The exact
successful [browser script](../../scripts/result_discovery_browser.mjs) is retained.
Earlier harness runs needed explicit opening of lazy raw evidence, correct 201
expectation and navigation/interception bookkeeping; they left authored draft-only
saves in this fixture, without changing artifact search membership. Accepted run
has no missing response bodies and used no navigation-retirement fallback. This
is scripted recovery evidence, not measured human benefit. Owned API/Vite/Chromium
were stopped after acceptance; synthetic fixture artifacts remain locally.

The separate scale run created 1,000 canonical authored results of about 128 KiB each.
Initial derived projection took 0.562s. Three local warm observations per query:

| Query | Observed time | Serialized response bytes | Page results |
| --- | --- | --- | --- |
| Empty | 0.10–0.27ms | 8,724 | 20 |
| Rare phrase at result tail | 130–194ms | 844 | 1 |
| Absent phrase | 123–129ms | 140 | 0 |

Report: `/tmp/nema-result-discovery-scale.json`; temporary scale database removed.
These are local measurements, not performance guarantees. Hot reads do not decode
canonical source histories, and response size is bounded by metadata/excerpts.
Substring matching still scans stored text, so a larger corpus can cost more.
First migration, changed-owner projection and exact-source detail retain their
existing costs. The byte column measures serialization, not an HTTP packet capture.

Authored reproduction:

```sh
uv run python scripts/result_discovery_demo.py --db /tmp/result-discovery.db --output /tmp/result-discovery.json
uv run python scripts/result_discovery_demo.py --db /tmp/result-discovery.db --resume --serve --port 8767
uv run pytest tests/test_result_discovery.py tests/test_investigation_reads.py
```

The fixture has an old result/question, a newer unrelated result under the same
owner, a title-only decoy and raw-only retained source data. All completions are
explicitly authored through the existing trusted history helper. No native/model
call or human reorientation/answer-quality claim follows from it.
