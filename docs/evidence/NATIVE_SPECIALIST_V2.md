# Native specialist boundary, capability matrix v2

**NEMA-SEED-1 · 2026-10-13 · implementation base
`50d1bc91870b9118a84706606d6a06008dffcdf7` · branch `codex/native-specialist-v2`.**
This is the evidence/contract for the commit containing this report. The native
target is **Codex 0.154.0, Linux/aarch64**, binary SHA-256
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
It advances V1-05/06/07/12 boundary work; a real specialist answer and interactive
disclosure remain unverified. No subscription-backed or paid API model turn ran.

The operational result is conservative: **the default investigation worker now
refuses before native startup**. A useful local configuration profile is implemented
and tested, but its account-backed startup gate remains closed because configuration
can also arrive through authenticated cloud loading. Disabling that gate to get a
green smoke test would restore the exact startup risk this task addresses.

## Versioned capability matrix

Evidence levels: **native** means actual response/marker in a disposable no-model
probe; **schema** means the installed generated contract; **synthetic** means a
local protocol fixture; **unverified** means no execution evidence. Prior observations
retain their original revision and scope; they are not relabelled as new live tests.

| Capability | Evidence and supported interpretation | Admission decision |
| --- | --- | --- |
| Initialize/stdio | Native handshake on this binary in both previous and new probes. Raw unknown fields survive the recorder. | Supported owned-child transport; no attachment to an independently owned process. |
| Thread policy | Native acknowledges `readOnly`, `networkAccess:false`, approval `never`, requested cwd, `environments:[]`; new interaction probe also acknowledges empty workspace roots. | Recheck each response. Requested configuration is not attestation. |
| Conflicting or invalid policy | Prior native probe rejects sandbox plus permissions and nonboolean feature settings. Unknown feature keys may be accepted. | Refuse conflicting/unknown policy fields; do not use mere parser acceptance as enforcement evidence. |
| Local MCP startup | Native fixture starts before inventory. Empty-table CLI override still permits startup. Named `enabled=false` suppresses the fixture startup. | Disable every admitted local MCP name before process launch; retain post-start inventory as a second check. |
| Apps/plugins/hooks/environment | Prospective profile moves feature restrictions to the process command and uses an exact child environment. Synthetic inheritance tests reject unreviewed configuration. | Constrains enumerated local sources. No complete account-backed effective-configuration claim. |
| Cloud/managed configuration | Installed binary contains cloud-bundle loader/cache paths; official documentation describes authenticated startup loading and requirements that may enforce hooks. No verified disable control was found. | Current profile has `live_admitted=False`; no account-backed child starts. This is an unresolved source, not proof a particular account has such a policy. |
| Subscription authentication | Profile preserves original HOME/CODEX_HOME, forces builtin OpenAI/ChatGPT settings, drops ambient API keys, never reads/copies auth. Account-type validator is synthetically tested. | No API fallback. Real entitlement and account-mode acknowledgement remain unverified because launch is closed. |
| Filesystem and network | Prior standalone native command denies writes/symlink overwrite and loopback networking, but permits an outside-file read. | Read-only is not packet-only visibility. Does not contain app-server startup, all descendants, or provider traffic. |
| Context observation | Exact projected user input, native request/reply records and returned instruction-source fields are observable. Global config/read does not attest thread overrides. | Preserve projection, observation and hidden provider context as distinct. Empty instruction sources do not prove no other instructions. |
| Dynamic evidence-tool registration | New native probe accepts canonical function and namespace tools; rejects duplicate/invalid names. It also accepts some weaker shapes. | A legitimate candidate for future evidence requests. Registration alone proves neither model exposure nor invocation. No tool is registered by the worker yet. |
| User-input request | Installed schema defines `item/tool/requestUserInput` with native IDs, questions and required `isBlocking`; synthetic adapter recognizes a matching server request. | Only a real RPC request envelope can create observed pending state. Text questions and counters cannot. Native emission remains unverified. |
| Nonblocking input | Installed schema explicitly distinguishes `isBlocking:false`; synthetic adapter retains it. | An open nonblocking request is not a suspended turn. Deprecated `autoResolutionMs` is not the blocking test. |
| Request resolution | Schema defines `serverRequest/resolved` with thread and typed request ID; synthetic tests match original pending identity. | Resolution reports closure, not answer delivery, disclosure approval or task success. |
| Counter-based elicitation | New native probe increments an empty-thread counter to `paused:true` while thread metadata remains idle, with no observed request envelope. | Never manufacture a specialist inquiry from this counter. |
| Answers, dynamic calls, approvals, MCP elicitation | Schemas expose several distinct request/response contracts. No live request was answered. | Adapter `respond()` is unsupported; default worker refuses server requests once. Request shape never grants evidence or execution authority. |
| Completed/failed/interrupted | Installed schema has these plus `inProgress`. Synthetic tests preserve errors and require coherent terminal/item evidence. | Notifications and partial output alone are not admitted artifacts. Conflicting or unresolved interaction evidence stays unknown. |
| Interrupt | New native probe rejects interruption of an empty thread with `no active turn to interrupt`. | Running-turn cancellation is unverified. Local process closure means local waiting ended, not confirmed native cancellation. |
| Timeout, EOF, duplicate requests | Synthetic subprocess/evidence tests exercise blocked writes, timeout, duplicate IDs, changed payloads, cancellation and ambiguity. | No automatic retry. Identical request repeats retain one identity; changed payloads conflict. Recorded response does not prove delivery. |
| Restart/history | Prior native evidence: empty-thread history methods and same-process resume reject; restart resume changes environment/root reporting. | Worker recovery reads Eidos evidence only. No native resume, pending-RPC reconnection or hidden-stack recovery is admitted. |

The complete returned interaction observations and schema fingerprints are in
[NATIVE_INTERACTIONS_0_154_0.json](NATIVE_INTERACTIONS_0_154_0.json), explained in
[NATIVE_INTERACTIONS.md](NATIVE_INTERACTIONS.md). The earlier policy, standalone
sandbox, MCP/resource and restart observations remain in
[NATIVE_VERIFICATION_INTEGRATED.md](NATIVE_VERIFICATION_INTEGRATED.md) and its
[artifact](NATIVE_BOUNDARY_INTEGRATED_0_154_0.json).
The new startup counterexample and generated-profile observations are retained in
[NATIVE_PROFILE_0_154_0.json](NATIVE_PROFILE_0_154_0.json). Its controls explicitly
remove the prospective MCP override; only the profiled case applies the entire
generated command. Their prospective profile description is not a claim that the
controls were contained.

## Pre-launch strategy and its exact boundary

`NativeExecutionProfile` lives in [codex.py](../../src/eidos/codex.py). It fingerprints
the reviewed executable, admits a narrow set of local settings, inspects user/system
and cwd-ancestor sources, rejects discovered managed/cloud sources and unsafe paths,
and builds explicit per-server disabling overrides. It preserves existing auth
placement and never copies credentials into a clean home. The process environment
contains only HOME, CODEX_HOME, a fixed PATH and LANG. `AppServerClient` can replace
its environment and run a guard immediately before `Popen`; its generic default
behavior remains compatible with other callers.

The launch description exposes source fingerprints, profile version, containment
limits, and `live_admitted`. The guard detects changed or newly present sources.
It is **not an atomic snapshot**: configuration can change between the final check
and native loading. It also does not prevent host reads, native state/auth writes,
all descendant effects, or undisclosed provider context. A complete mechanism would
need a supported native admission boundary covering all configuration sources, or
an independently reviewed OS boundary compatible with existing subscription auth.
Neither is established here.

The [official managed-configuration documentation](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
describes identity-matched cache/fetch at startup and managed requirements that can
enforce hooks despite local choices. This supports the unresolved-source concern;
it is not an observation of this owner's policy. We did not launch with the owner's
configuration to discover it after potential effects. No global configuration was
rewritten and no native state was impersonated.

The existing API's explicit Codex argv receives the same admission as the default
constructor; renamed native executables with flags before `app-server` also receive
the gate. Python fixtures and explicit `env` wrappers retain the **trusted-host
fixture/probe seam**, not a contained alternative live path. Callers that supply
arbitrary commands own their startup behavior. Do not wrap or rename a live native
command to bypass admission. Constructor callers can already execute Python and
are not authenticated by this interface. No new remote command endpoint was added.

## Adapter interface for Codecy B

[investigation_worker.py](../../src/eidos/investigation_worker.py) exports frozen
`NativeSpecialistEvent` values and `NativeSpecialistAdapter`.

```python
worker.run(attempt, context, update_attempt, on_event=accept_observation)

adapter = NativeSpecialistAdapter(trace, attempt, context, attempt["source"])
events = adapter.refresh()       # evidence interpretation; sends nothing
pending = adapter.pending_requests
```

`update_attempt` keeps the existing source/thread/turn/status contract. `on_event`
is an additive trusted-host callback, not a new investigation database or API.
It runs synchronously and must persist or enqueue promptly; do not wait for a human
or run controller work inside it. Arbitrary blocking callback code is not bounded
by the native transport's deadline.
Events contain schema version, stable event identity, attempt/context/source,
native thread/turn/item coordinates, typed RPC ID and request key, evidence sequence
references, request state, blocking flag, terminal observation and explanatory detail.
Raw payloads and unknown fields stay in TraceStore. Persist/reconcile derived events
by their event IDs; reference the original evidence rather than replacing it.

The source identifies one owned process incarnation. Integer and string RPC IDs
remain distinct; booleans are invalid. An actual pending input requires a matching
recorded turn submission and native request. Matching questions may precede the
turn acknowledgement; contradictory later identity makes the projection ambiguous.
Use `request_state == "pending"` and `is_blocking is True` to describe a native
wait. The unresolved collection can also contain unsupported/nonblocking requests
and locally recorded responses; do not present all of them as answerable questions.

`response_recorded` describes an outbound record, not native receipt. `resolved`
describes native closure with unspecified reason. `abandoned` describes local
waiting ended. `terminal_observed` is still evidence: the worker's conservative
`recover()` must validate terminal status, input, identities and output before
producing an artifact. `respond()` raises `UnsupportedNativeOperation`; native
resume/fork/replay and new disclosure are not exposed. Replaying a descriptor cannot
revive a request capability. Codecy B must add its own durable admission and decide
how to present historical unresolved requests before a future live responder exists.

No changes were made to investigation.py, investigation_continuations.py, api.py or
ui/. This supplies the interface for the next lane; it does not claim that the
existing workbench renders or answers native-originated questions.

## Bounded real-native smoke procedure

The runnable helper [native_specialist_smoke.py](../../scripts/native_specialist_smoke.py)
prepares three synthetic records across two threads, creates a frozen context, and
prints the exact 2,595-byte prompt and identities. Preparation invokes no native
process and leaves a draft with no attempt:

```bash
uv run python scripts/native_specialist_smoke.py prepare --db /tmp/nema-specialist-smoke.db
uv run python scripts/native_specialist_smoke.py inspect --db /tmp/nema-specialist-smoke.db --investigation <printed-id>
```

The later live gate requires **both** a reviewed safe profile and explicit user
authorization: one fresh subscription-backed thread, one turn using only that
packet, at most 120 seconds locally, output limited to 131,072 characters, no
automatic retry, and a requested answer of at most 200 words. This consumes native
subscription resources; provider retries, tokens and cost have no verified hard cap.
Do not claim the prose length request is a token limit. The exact run command is:

```bash
uv run python scripts/native_specialist_smoke.py run --db /tmp/nema-specialist-smoke.db --investigation <printed-id> --authorize-model <reviewed-context-id>
```

The flag is an operator acknowledgement, not permission inferred by an agent.
The current profile refuses this command before launch, even if the resource flag
is supplied. No authorization was requested for an unsafe/ unavailable gate. After
the profile gap is resolved, request permission with the scope above before running.
Do not weaken admission, substitute an API, copy auth, or switch to a custom-command
bypass. A claimed attempt is durable even on refusal or timeout; repeating the
command cannot send another turn. Preserve private traces locally and publish only
explicitly sanitized evidence.

Acceptance for that future run: one recorded turn/start, exact frozen prompt,
admitted native policy, coherent terminal artifact citing actual synthetic inputs,
and evidence-only recovery without another send. An interactive test is a separate
scope: register a canonical synthetic evidence tool, observe an actual request,
admit one response through the controller, and observe resolution/cancellation and
terminal state. Registration/counter probes do not satisfy that acceptance.

## Verification and integration review

- `uv sync` passed; initial base suite: **361 passed, 2 skipped**.
- Final `uv run pytest`: **446 passed, 4 skipped**. The skips are explicit native
  opt-ins, never model tests in the default suite.
- `NEMA_NATIVE_PROBE=1 uv run pytest tests/test_native_boundary_probe.py tests/test_native_mcp_probe.py tests/test_native_interactions_probe.py tests/test_native_profile.py`:
  **52 passed, zero skips, 3.21 seconds**; zero model-turn methods. New artifacts
  retain the directly captured observations from their earlier no-model runs;
  this final combined invocation rechecked behavior after integration.
- `uv run eidos --help`, seed-context tests and `git diff --check` passed.
- The synthetic continuation demo at `/tmp/nema-adapter-demo-20261013.db` passed;
  the staged smoke at `/tmp/nema-specialist-v2-smoke-20261013.db` remains an
  unattempted draft. No `run` command was issued for it.

Independent lanes inspected configuration, protocol acceptance and adapter behavior.
Reviews caught and repaired the API-shaped argv bypass, wrong source/context
correlation, unresolved local refusal mistaken for resolution, late requests after
local close, and prospective-profile labels on deliberately unsuppressed controls.
Source-filtered incremental event reads avoid repeatedly materializing unrelated
history. Tests retain ambiguous outcomes, duplicates, timeouts and cancellation.
No UI or presentation files changed; no rendered-UI validation is claimed.
