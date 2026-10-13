# Native investigation boundary — NEMA-SEED-1

**2026-10-13. Base:** `ac2c093b675c5765abccaeff33a721f48f4318ce`.
**Integration branch/worktree:** `codex/native-boundary`, supplied isolated worktree.
**Target:** V1-05/07/12, the native contract beneath the saved two-thread investigation.
This report supersedes native assumptions in [Cycle A](INVESTIGATION_CYCLE_A.md), not its historical evidence or the destination.

The installed native harness admits the worker's initial policy and passes standalone filesystem/network sandbox probes. The actual worker passes native preflight up to an explicit guard before `turn/start`. **A completed native model turn remains unverified.** No subscription-backed or API inference was requested, no personal conversation or credentials were inspected, and no user Codex state was changed.

The strongest counterexample is outside model execution: configured MCP subprocesses run and can write files during thread startup, before the worker's admission check. An empty MCP tool inventory also conceals resource capabilities. Therefore the worker is **not a general containment boundary for arbitrary ambient native configuration**. Its gate is now stricter, but a post-start gate cannot undo startup effects.

## Evidence and reproduction

Installed binary: `/usr/bin/codex`, `codex-cli 0.154.0`, Linux/aarch64; SHA-256 `9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`. Generated experimental schema fingerprints, native responses, sandbox results, and synthetic MCP startup markers are in [the sanitized observation artifact](NATIVE_BOUNDARY_0_154_0.json). Temporary paths are replaced with `<probe>` / `<mcp-probe>`; the artifact contains only purpose-created data. Each script regenerates its observations; version/hash changes require renewed review.

```bash
uv sync
uv run pytest
uv run python scripts/probe_native_boundary.py --output /tmp/nema-native-boundary.json
uv run python scripts/native_mcp_probe.py > /tmp/nema-native-mcp-boundary.json
NEMA_NATIVE_PROBE=1 uv run pytest tests/test_native_boundary_probe.py tests/test_native_mcp_probe.py
uv run eidos --help
```

Default pytest never invokes installed Codex. Native tests require the explicit environment opt-in. Both scripts use new synthetic HOME/CODEX_HOME/cwd directories, a minimal child environment, no copied auth, and a synthetic provider pointing at loopback port 9. Their method allowlists exclude model-turn operations. The standalone probe alone permits `command/exec`, running fixed Python sentinel operations against temporary files and a temporary loopback listener. The worker-preflight probe substitutes a guarded client that refuses `turn/start` before transport; it does not weaken the worker gate.

The probes isolate user configuration, not every machine-level configuration source. They do not certify the owner's ordinary account configuration. No fallback to a paid API, Desktop process attachment, persistent config write, or personal thread lookup occurs. Successful empty-thread construction does not establish model entitlement.

Labels below mean: **OBSERVED** is a returned native value or installed schema; **TESTED** is an exercised assertion with its stated scope; **INFERRED** is a plausible interpretation lacking direct execution evidence; **UNSUPPORTED** means the next integration cannot rely on the claim from this evidence (some calls explicitly fail, others remain untested).

## Reproducible compatibility matrix

| Capability / claim | Classification and exact result | Safe integration consequence |
| --- | --- | --- |
| Stdio initialize/initialized and experimental API | **OBSERVED / TESTED:** installed process accepts handshake and returns native version/platform. | This binary supports the traced JSONL transport; retain unknown fields. |
| Actual worker native preflight | **TESTED:** worker reaches guard before turn submission with an acknowledged thread; zero `turn/start` records. | Native initial policy + empty-inventory path works under the synthetic configuration. |
| Read-only thread policy admitted | **OBSERVED / TESTED:** returned `sandbox={type:readOnly,networkAccess:false}`, `approvalPolicy=never`, requested cwd, `thread.environments=[]`. | Check the response before dispatch. A requested setting alone is insufficient. |
| Filesystem sandbox enforcement | **TESTED, standalone `command/exec`:** cwd creation, outside-file overwrite, and symlink overwrite fail with errno 30; host verifies no mutation. | Native command sandbox enforces these cases on this host. **INFERRED**, not tested, that every model-triggered tool follows this exact path. |
| Read visibility | **TESTED:** the same command reads a synthetic file outside cwd. | Read-only is not packet-only context or filesystem confidentiality. |
| Network sandbox | **TESTED, standalone command:** unsandboxed loopback control succeeds; sandboxed connection fails with errno 1. | Direct networking is blocked for that command. This does not contain provider traffic, MCP startup, or all host integrations. |
| Feature configuration | **OBSERVED:** CLI lists apps/shell_tool/multi_agent/hooks/memories false with the fixed overrides. Native thread config rejects a nonboolean shell_tool value (`-32600`). | Keys are recognized/parsed. Actual model tool removal remains **UNSUPPORTED** without observing a model request/tool path. |
| Unknown config keys | **OBSERVED:** nonexistent `features.nema_nonexistent_probe=false` is accepted. | Acceptance is not proof that a setting is implemented or enforced. |
| Policy conflict validation | **TESTED:** `permissions` plus `sandbox` is rejected (`-32600`). | Do not combine legacy sandbox and named permissions fields. |
| `config/read` as per-thread attestation | **OBSERVED:** global config before/after thread start is unchanged; thread overrides are absent there. | **UNSUPPORTED:** interpreting global config/read as the worker's effective tool/context manifest. |
| MCP inventory with no configuration | **TESTED:** empty data and null nextCursor under synthetic clean configuration. | Worker permits this case. Pagination remains checked synthetically. |
| MCP compact inventory completeness | **TESTED:** connected resource-only server returns tools={}, resources=[], templates=[] under toolsAndAuthOnly; full detail reveals both resource and template. | Empty tool map does not bound MCP capabilities. Worker now refuses every enabled or unresolved server. |
| MCP startup containment | **TESTED counterexample:** synthetic processes write marker files after thread/start and before inventory; additional discovery can launch more subprocesses. Disabled server never launches. | **UNSUPPORTED:** sandbox/feature flags plus a post-start inventory check preventing startup side effects. |
| Zero-turn metadata read / fork | **OBSERVED:** metadata-only thread/read and fork acknowledge success. | Narrow empty-thread control support; no claim about full-history forks or workspace isolation. |
| Zero-turn history read / pagination | **OBSERVED rejection:** includeTurns read and turns/list return `-32601`, `list_turns is not supported yet`; items/list returns `thread/items/list is not supported yet`. | **UNSUPPORTED on tested path:** native history reconciliation via these advertised methods. |
| Resume in same process | **OBSERVED rejection:** excludeTurns=true still returns `list_turns is not supported yet` for the zero-turn thread. | Do not assume the convenience client's resume works in this state. |
| Resume after process restart | **OBSERVED:** same zero-turn thread ID resumes with read-only policy explicitly supplied again; environments becomes local and runtimeWorkspaceRoots becomes cwd. | Native resume is available in this narrow state, but **UNSUPPORTED** as restriction-preserving continuation. No worker resume was added. |
| Native turn lifecycle | **OBSERVED schema:** completed/interrupted/failed/inProgress; error event includes willRetry; completed turn carries error/items. **TESTED synthetic:** only coherent completed evidence can yield an artifact. | Completed live model turns, retry ordering, approvals, interruption, billing, and model tools remain **UNSUPPORTED by this run**. |
| Crash / missing acknowledgement / blocked write | **TESTED synthetic subprocesses:** EOF wakes readers; writes obey a deadline; partial sends terminalize the incarnation; late replies remain evidence; no adapter resend. | Rely on conservative local delivery uncertainty, not exactly-once native execution. |
| Completion recovery without re-execution | **TESTED synthetic:** frozen input + source/thread/turn matching recovers recorded completion without a native executable or new RPC. | Recover already recorded evidence only. Missing evidence stays unknown; a native thread ID is not proof of completion. |

The installed generated schema is the version-specific contract used here. Public [App Server documentation](https://learn.chatgpt.com/docs/app-server) describes `command/exec` as sandboxed standalone execution and distinguishes it from unsandboxed host process APIs; it also describes thread/turn control. The [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) describes the feature switches. These explain intended interfaces; the local probes establish the narrower behavior above. Neither documentation nor generated schema overrides an observed native rejection.

## Repairs and adversarial regressions

`src/eidos/investigation_worker.py` now validates returned sandbox, approval policy, canonical cwd, and empty environments before inventory or turn submission. It rejects unknown sandbox fields for review and nonboolean network values; an omitted networkAccess follows this installed schema's false default. Raw unknown fields remain in the trace. Enabled MCP servers are refused even when their tool map is empty; explicitly disabled servers require empty tools and no discovery error, including no empty-string error.

Recovery excludes explicit commentary from artifacts, retains legacy null/absent phases, and differentiates known failed/interrupted terminals from unknown/future/nonterminal statuses. Conflicting status/error acknowledgements and conflicting text/phase for a completed item identity remain unknown. Equivalent repeated completion can recover without changing evidence or sending another turn. This remains a trusted-host evidence interpreter, not an authenticator for arbitrary trace writers.

`src/eidos/codex.py` uses cancellable nonblocking UTF-8 pipe writes with one request deadline across lock acquisition, writing, and acknowledgement. A partial-frame timeout closes the logical incarnation to prevent subsequent JSONL corruption. EOF is `AppServerClosed`, not an invented native RPC error. Pending RPC entries are cleaned on every exit; an EOF sentinel wakes even an unbounded event waiter after prior events drain. Closing cancels writers even if a descendant retains stdin, without signalling unrelated processes. Platforms unable to configure nonblocking pipes fail closed; only Linux was tested. Closing the direct child does not establish descendant termination.

Regressions in the two owned test modules cover weaker/missing/malformed policy acknowledgements, enabled empty MCP inventory, error discovery, commentary-only output, failed output with text, contradictory terminals and completed item content, duplicate equivalent terminals, error notifications with either willRetry value, missing acknowledgements, late replies, fragmented UTF-8, process death, blocked writes, lock contention, inherited pipes, and concurrent close. The shared synthetic fixture was updated only to return required policy/environment acknowledgement fields, keeping API/demo tests compatible; `investigation.py`, `api.py`, and `ui/` are unchanged.

## Remaining boundary and continuation contract

The real worker still inherits the native host environment/account configuration. Its temporary cwd does not remove ancestor/global instructions, skill/plugin loading, model/provider defaults, managed configuration, server-side instructions, or process-start integrations. Thread response instructionSources was empty in the sterile probe; this is not a complete model-input capture. Native feature flags and rejecting interactive requests are defense in depth, not an exhaustive tool allowlist or an OS/container boundary around app-server. The MCP marker test directly disproves such a broader boundary claim.

Native thread continuation means asking this native process implementation to reconstruct supported thread state from its own store. Eidos serialized continuations describe local code/context/protocol state and require their own admission/realization. Neither includes a serialized provider stack, pending native tool process, credential, or revived authority. A native conversation fork does not isolate files. A copied Eidos checkpoint does not authorize another native turn. The worker intentionally starts one fresh thread and recovers only from its own recorded evidence; it neither calls resume/fork during recovery nor resends an uncertain request.

A transport request recorded before writing may never reach the server; a missing acknowledgement may accompany completed work. The new deadline and recovery tests protect those local distinctions. They do not prove exactly-once external effects, resource quotas, maximum provider tokens/cost, or recovery after loss of local terminal evidence. Generic native errors with willRetry are not accepted as successful terminal completion.

## Integration handoff

One integrator owns the final commit on `codex/native-boundary`; `main` was not modified. Independent transport and worker scouts implemented disjoint patches in temporary worktrees; a third lane produced the native MCP probe and reviewed probe isolation. Final independent review found the duplicate completed-content ambiguity, which was repaired. No background native or agent work is required to use these artifacts.

Verification on the integrated tree: `uv sync`; `uv run pytest` (**230 passed, 2 explicitly skipped native probes**); opt-in native probe tests (**13 passed**); both standalone probe scripts; `uv run eidos --help`; `git diff --check`. No UI changes or UI validation are claimed.

**Next runnable action:** rerun the two opt-in probe suites on the integration host and compare the matrix before enabling an investigation worker there. Preserve the stricter gate. Treat native history/resume and arbitrary ambient tool containment as unavailable until independently established. A future explicitly authorized bounded model test can then use one synthetic packet in an audited native configuration, record a real turn and its admitted policy/tool/input evidence, and exercise interruption without automatic replay. That model test is a separate authorization and was not performed here.
