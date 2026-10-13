# Archived handoff — exact result discovery and native worker join preparation

**2026-10-13 · main `63cd47f11fa6` (full identity from git), pushed.**
Exact result discovery is committed with
[successful CI](https://github.com/keeganpoppen/eidos/actions/runs/38482966827).
Owned preparation/cancellation is integrated with
[successful CI](https://github.com/keeganpoppen/eidos/actions/runs/38481196908).
[Owned integration handoff](OWNED_ATTEMPT_CONTROL.md) and
[evidence](../../evidence/OWNED_ATTEMPT_CONTROL_INTEGRATION.md) retain verification.
Continuing mission remains active; green does not end it. [PROGRAM](../PROGRAM.md)
owns revisable conjectures. No human decision blocks the current offline work.

## Completed product lane: exact result discovery

[Accepted contract](../RESULT_DISCOVERY_TASK.md). Artifact catalog was title-only;
remembered question/result phrases returned nothing. Root baseline report
`/tmp/nema-result-discovery-baseline.json` reproduces that failure. Search now uses
only owner title, exact artifact-context question and published result text. Public
raw records, prompts, nested inputs, unknown fields and private stores are excluded.
Historical results keep their own context/attempt. Bounded labelled plain-text
excerpts do not become interpretation or authority. No-result investigations remain
explicitly title-searchable.

Commit `63cd47f` includes root-owned `investigation_reads.py`, new `test_result_discovery.py`, new
`result_discovery_demo.py` and docs. Search uses a separate replaceable projection
joined to existing artifact metadata; missing legacy rows dirty only those owners.
Existing empty-query payloads stay unchanged. New searched-artifact cursor kind
rejects old title-only membership. Unicode casefold offsets map back to original
text, excerpts max240 code points including omission markers. Large folded matches
may be honestly truncated. Root focused **26 checks passed** (11 new +15 existing).

UI agent native_frontier owns `/tmp/nema-result-discovery-ui`, branch
`codex/result-discovery-ui`; commit `2740be1` integrated into `63cd47f`. Existing
picker shows field/excerpt, retained out-of-page selections are labelled separately,
Inspect precedes Add and passes exact context, lineage shows Original question.
Agent browser commit `de08df5` is also integrated. Parent 99 Bun /499 assertions and
check/build passed. Actual browser 65 captured responses (one injected 404, one
ordinary 201 draft save), six discovery/reuse checkpoints, zero dispatch/native/model
calls or JS exceptions. Root inspected desktop original-question/support and mobile
frozen-input screenshots. Independent backend/UI review accepted; 26 checks rerun.
Report `/tmp/nema-result-discovery-complete.json`; hashes and five screenshot paths
in [discovery evidence](../../evidence/RESULT_DISCOVERY_INTEGRATION.md).

Root full suite **1,287 passed /53 explicit native skips in25.60s**,
`/tmp/nema-discovery-parent-suite.log`. UI **99 tests /499 assertions**, clean
Svelte/build, Bun log `/tmp/nema-discovery-parent-bun.log`. Scale report `/tmp/nema-result-discovery-scale.json`:1000
canonical authored results about128KiB each; cold projection0.562s, warm empty
0.10–0.27ms/8724serialized bytes, rare tail130–194ms/844bytes, absent123–129ms/140bytes.
No native/model calls. Query still scans text; only response/canonical parsing are
bounded. Scale temporary DB was removed after the run.

Accepted browser fixture API8767/Vite5181/Chromium9231 are now stopped. Exact root
PythonPID351734 and VitePID351753 were verified and terminated; agent stopped
Chromium351997. Synthetic DB `/tmp/nema-result-discovery-parent-20261013.db` and
marker with matching .json stem remain. Earlier harness runs left draft-only saves;
the accepted run captured every response, changed no historical artifact and used
no navigation-retirement fallback. Do not infer active workers from prior PIDs.

## Active independent lane: contained native worker join

[Accepted packet](../NATIVE_OWNED_WORKER_TASK.md). history_ui owns
`/tmp/nema-native-owned-worker`, branch `codex/native-owned-worker`, based on worker
commits `3efcb2c` + `88c6da3` over7d3354a. New commits `7b4e52b` + `90e8f79` + `9739cab` + `3b03aba` are
frozen but NOT applied to main. They own existing managed lifecycle probe/tests and
new native-owned-worker evidence note only. Root API/store copies in that worktree
are uncommitted seams and must not enter its commits.

New explicit managedWorkerText mode uses actual PrivateInvestigationWorker,
NativePreparation, existing native turn loop and tracked private reader. A fixture
wrapper uses `/usr/bin/python3 -I -S` then the existing namespace command, mirroring
only cwd spelling into empty namespace tmpfs. No owner mount/packet rewrite.
Preparation8s and ordinary stored turn120s remain beneath outer18s/process20s cap;
report effective minimum, never claim120s admitted traffic. Existing controls,
invalid synthetic credentials and capture/HTTP/CONNECT limits stay fixed.

Final default probe **137 passed /4 skipped**; dependencies **225 passed /13 skipped**.
Independent reviewer accepted final `3b03aba` and independently reran 137/4. Script
SHA256 `c0fc756458c4988d94c59786a1ac752ca26811cf4f89b40eb93474042df58f15`.
Root inspected concrete final bytes and accepted one contained managedWorkerText
opt-in under the packet. history_ui is executing it now; no outcome known yet.
Retain exact raw failed and successful reports before changing any fixture control.

Review had reproduced malformed terminal/control acknowledgements losing the
report, host environment inheritance before namespace entry, and incomplete
cleanup/watchdog accounting. Final code uses env={} / inherit_env=False before
host ELF/Python, -I/-S, shape checks plus a fail-closed assessment envelope, retained
raw rejected evidence, joined watchdog and separate cleanup errors. These are
probe changes, not a production live profile. No real auth/model/upstream call or
quota increase is authorized. Prior manual managedText evidence remains unchanged.

native_frontier now performs a bounded read-only scout of the smallest remaining
implementation/evidence for a user-operated managed account attempt. It must separate
buildable offline code from observations requiring explicit sign-in/provider use,
and identify claims to drop rather than chase another broad token matrix. No edits
or live calls. gateway_review remains available for actual probe evidence review.


## Integration and next decisions

Result discovery is committed/pushed and CI passed. Review the first contained
native worker outcome, reconcile any mismatch without enlarging bounds, then apply
reviewed commits and independently reproduce the accepted case. Native probe
integrates separately after raw evidence review and root reproduction. Neither lane blocks the other's meaningful progress.

Strategic scouts agree: finish the native join because it tests a real seam; further
containment matrices need a concrete unresolved decision. Offline cases cannot prove
real subscription/model availability or acceptable login friction. Result discovery
advances owner recovery now. A recipe activation framework remains premature without
observed repeated selection friction. Scripted discovery success cannot establish
human reorientation speed or reasoning quality; do not access personal traces to
manufacture that claim.
