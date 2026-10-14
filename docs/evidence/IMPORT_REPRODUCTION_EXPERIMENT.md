# A saved review becomes precisely repeatable

**2026-10-14 · inspected base `3d4f396afbb4603adb0aadcc301224796dd5e397`.**
This public-code developer experiment follows the
[supplied-text integration](SUPPLIED_TEXT_INTEGRATION.md). No account, private
history, native Codex/app-server or project-initiated inference operation participated.
The fresh participant used host collaboration and resolved explicitly named public
Git objects over HTTPS. The local check itself made no native/model call.

## Question and result

The earlier saved review was understandable but omitted its exact runner, input
bytes, executing TraceStore and runtime identity. Could existing text evidence,
contexts and findings preserve enough support for a fresh participant to reproduce
the bounded check without original chat or an unspecified working repository?

**Yes, on the available matching host runtime.** The participant's entire execution
record and stdout matched byte-for-byte. The result does not require an execution
entity or relaxing the native-only experiment gate. It does require availability
of the explicitly addressed public source: the packet does not embed the whole
repository or an operating-system image.

## New pinned run, with the old finding retained

[Runner](../../scripts/import_reproduction.py) requires `-I -S -B`, a fresh clean
checkout at `3d4f396afbb4603adb0aadcc301224796dd5e397`, and a new `/tmp` output
directory. It executes that revision's unchanged `supplied_text_episode.py` probe,
using the historical method at `2386b294cfe700622d672ff7e1a35dd9229eba30` and adapter
at `d2b5fdb06a88c5c1ac8f6d1b53ea71274ff3d290`. It verifies all loaded project source
files against the runtime commit. The repaired adapter is called directly; this
does not test the forwarding wrapper supplied in the older review.

The new record captures exact input strings/hashes and retry schedule, harness and
runner identity, 26 loaded project modules, interpreter binary, Python/SQLite and
platform versions, and 114 loaded standard-library/extension file hashes. Python
was3.14.7, SQLite3.53.4. It is a recorded environment identity, not full dependency
closure, a machine image or an authenticated execution attestation.

Observed cases remain historical retry counts1 then2, repaired0 then0, intentional
duplicate valid records2. The complete stdout matches the previous716-byte report.
The original repair `2aae982806de5386d0e42dc22f499bdb6d5e77f4` has exact parent
`2386b294cfe700622d672ff7e1a35dd9229eba30`; this resolves the earlier ambiguous
“reviewed parent” wording without changing the old finding. No rollback patch is
proposed; restoring the defective method restores prefix retention.

Root ran:

```sh
uv run python -I -S -B /tmp/nema-import-reproduction-20261014/reproduce-import.py \
  --checkout /tmp/nema-import-reproduction-20261014/source \
  --output-dir /tmp/nema-import-reproduction-20261014/observed-final
```

Root copied the marked source-deleted prior fixture into a new database before
admitting five ordinary files: runner, recipe, execution record, stdout and public
revision relationships. Existing API dispatch saved a new context/finding with the
old review as an exact result input; close/reopen returned identical canonical data.
No native attempt was created. The source observations/review remained byte-exact.
The producer's final diagnostic first used nonexistent `context.prompt`; the bundle
had already saved successfully. Root corrected the diagnostic and inspected the
saved bundle without replaying mutations.

Saved reproduction owner `investigation_6d5f257bfc7740ca928e51eee532ff6d`, finding
`artifact_2bc8b0f4da678aa5d2f62ebae4367a276cf3c4f8cd1711fbbe059a9155bd1de2`.
`/tmp/nema-import-reproduction-20261014/saved-reproduction-bundle.json` has SHA256
`575df0531232486d41102b0c98eef7f2c75c476a30dcdb1fc7387f29d3e9ed8c`.

## Independent reconstruction and refusal

A fresh high-effort participant received only that saved bundle and a separate
host-task authorization for the bounded local check. It verified all nine frozen
supplied-file original-byte hashes/lengths and host-record hashes, extracted only
five reproduction files, and fetched the exact public commits into a new checkout.
It reviewed the runner and relevant pinned execution paths before running; file
prose did not grant execution authority. No ambient repository or original runner,
output or source directory was consulted.

The participant ran `uv run --no-project python -I -S -B` with the extracted runner
under `/tmp/nema-independent-reproduction-20261014-hl280msa`. It disabled Python
downloads, used task-owned uv/temp directories and disabled Git credential prompts
and global/system configuration. Exact commands are in `independent-report.json`:
SHA256 `f4c914a7a5c4b9ae512bd1adb32e0257f617964df2410c6cae4aa7c335338996`.
Root read that report and independently compared the two output files with `cmp`.

| Matched artifact | SHA256 |
| --- | --- |
| Complete execution record |993e8a44023b3a25ce77cd382554e7fff1c738366a3fe077512e7ac0c25bec3e|
| Observed stdout |90eedb09dd716ddb6407b338d15c804d82dba4f862dd5de7a3c02933fe0e9623|
| Runner bytes |3d7a0b90c9fecce108fac5d268fbb25efe3c5d79e52b0f05f841b270e71e26c7|
| Runtime fingerprint |bd5d794a69adfc884b94e1730c74979eabea5d80a80196778d5f390225cb5c36|

Stderr was empty; source checkout remained clean. A separate modified-source copy
was refused with exit1 before an execution record was created. The earlier output
and original source stayed unchanged.

Independent review also found that `-B` prevents bytecode writes but can load ignored
existing caches. Root reproduced this in an isolated worktree using an authored
unchecked-hash `__init__.pyc` that wrote a benign marker: the old runner passed while
that cached code executed. The accepted runner rejects all ignored files before
importing project source; the same case then refused before the marker was written.
Artifacts are `cache-refusal-counterexample.json`, before/after stdout/stderr and
the separate marker under `/tmp/nema-import-reproduction-20261014`. The original
source checkout was freshly created and cache-free. This guard is not a security
boundary against concurrent hostile filesystem mutation.

The independent report was itself admitted through existing text preview/commit and
saved in a separate exact-input finding, then reopened unchanged. Owner
`investigation_c09a2febdb8048c087f1b75d33a208cd`, finding
`artifact_cc19666f33c164df689a11dcc9de9d403f7bfc5cec99379a53d79c3e436241c3`.
The earlier finding remains unchanged, including its then-accurate statement that
independent repetition had not yet happened. Local file admission does not certify
the report's author; the separate collaboration/tool evidence supports this audit.

## Consequence and limit

This removes a mistaken prerequisite: a precisely recoverable local review does
not yet need a new experiment/execution ontology. Use ordinary Values and explicit
dependencies until a concrete missing operation appears. Same-host repeatability
does not establish cross-platform portability, authenticated past execution,
whole-release compatibility, performance, formal adoption or human usefulness.

Actual browser inspection then exposed a different gap: “Compare saved work” seeds
both sides with the same finding and advertises a fixture-only alternative, while
the authored review shows unavailable native inquiry guidance. The next
[bounded comparison task](../agents/SUPPLIED_RESULT_COMPARISON_TASK.md) connects an
exact displayed result to its exact supplied basis and demotes irrelevant examples.
