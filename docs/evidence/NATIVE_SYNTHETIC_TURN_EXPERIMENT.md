# A guarded native turn completes against an authored local provider

**2026-10-13 · implementation base `348f736` · C6 / V1-05 / V1-12.**
Codex **0.154.0** completes a real native `turn/start` through a local synthetic
Responses provider while the reviewed pre-exec process filter remains installed.
The authored answer is recorded, correlated with the selected context and native
thread/turn, saved as an investigation artifact, and recovered after reopening
the trace. This establishes compatibility of this text-response path with process
denial. It does not establish native subscription execution or complete admission.

The [JSON artifact](NATIVE_SYNTHETIC_TURN_0_154_0.json) records **two native turn
RPCs, zero real model calls and zero real upstream requests**. The service contains
no upstream implementation. There are no credential mounts, authentication
refreshes, existing owner state, production profile changes or paid API calls.
`executionEvidence` remains **`synthetic`** in each durable result despite real
native transport. This experiment must not be described as having no model RPCs:
native Codex issues a provider request, which the authored fixture answers.

## Observed result

Both cases start with fresh disposable state in the disconnected bubblewrap
namespace and reuse the unchanged filter from the
[process-boundary experiment](NATIVE_PROCESS_BOUNDARY_EXPERIMENT.md). A trusted
loopback relay, launched before the filter, connects only to the mounted fixture
Unix socket. The native process has no external network route. The fixture broker
has no outbound client and returns only fixed local bytes.

| Case | Executable MCP | HTTP MCP requests | Native provider request | Durable result |
| --- | --- | --- | --- | --- |
| Provider plus enabled executable MCP | Fails with EPERM; marker absent | Not configured | One POST, accepted 200 | Exact authored text; citations 1 and 2 |
| Same setup plus enabled HTTP MCP | Same failure | Ten initialization/discovery requests, rejected 422/403 | One POST, accepted 200 | Same text and citations |

The native turn status is `completed` in both cases. The native MCP inventory
acknowledges the executable's `Operation not permitted` error; the configuration
still enables that executable. The HTTP MCP targets the **same** `/v1/responses`
route as the provider. Its two JSON-RPC initialization bodies fail fixture shape
checking; the other eight GET/discovery requests fail the route check. The actual
provider request is accepted once after the fixture permit opens. No second
provider request is needed, and the fixture asks for no actions or tools.

This comparison does **not** attempt valid-provider-request impersonation by an
HTTP MCP or a same-namespace sibling. Its artifact explicitly records
`validProviderRequestImpersonationTested: false`. The broker checks a model name,
streaming flag and exact selected prompt within the input, not a caller identity
or the entire request envelope. A matching body remains forgeable. The
[previous gateway counterexample](NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md), where
an identical request from another process consumed the permit, is not repaired
by accepting this provider request. Neither the relay PID nor public prompt bytes
authenticate the originating client.

## The selected packet is only part of the native request

Each captured provider body is **12,219 bytes**. `brokerEvents[].bodyRaw` preserves
the exact body, with its SHA-256 and request headers; `providerRequestAnalysis`
indexes its text fragments and offered tools without replacing the raw capture.
The selected prompt is 2,579 characters and appears once as a user text part.
Native Codex also sends:

- The fixture's explicit base instruction in the top-level `instructions` field.
- A developer message containing two text parts: a built-in skill catalog and
  permission instructions, generated in the fresh isolated state.
- An additional user environment message with the fixture date/timezone.
- Tool schemas for `list_mcp_resources`, `list_mcp_resource_templates`,
  `read_mcp_resource`, `request_user_input`, and the `skills.list`/`skills.read`
  namespace; `tool_choice` is `auto`.

Disabling shell, apps, plugins, hooks, image generation, multi-agent features,
memories and host skill discovery did **not** remove every tool schema or native
instruction from the wire. The observed selected prompt is therefore not claimed
to be the whole model input, and the wire is not claimed to be tools-disabled.
The service sends only an assistant text message. Tool/action execution branches
remain untested. The client refuses all server requests and aborts on observed
non-text action items, but that observer is not a pre-effect security boundary.

The exact authored answer is:

```text
SYNTHETIC FIXTURE: both selected records survived [evidence:1] [evidence:2].
```

## Correlation and recovery

The script creates two synthetic source records with an unknown fixture field,
selects them through the existing `InvestigationStore`, and claims one attempt.
It sends exactly that context's `projectedPrompt` as the sole `turn/start` input.
The saved attempt binds the native trace source, thread ID, turn ID, context ID,
attempt ID and manifest ID. The artifact retains the context/attempt IDs, cited
record numbers and native output sequence numbers. Every app-server message and
selected source record is retained as `traceRecords[].rawText`; future/unknown
fields are not replaced by the derived analysis.

The existing `NativeInvestigationWorker.recover` reconstructs the authored text
from native evidence. Before persistence the fixture explicitly changes the
execution classification to `synthetic`: seeing native transport alone does not
prove real model execution. The script closes and reopens the SQLite trace,
reloads the canonical saved work, independently recovers the artifact again, and
compares both structures for equality. Both cases record
`durableReopenMatches: true`. The public JSON is a synthetic evidence export; the
temporary databases are cleaned up after that reopen check.

The fixture client allowlists `initialize`, non-refreshing `account/read`,
`config/read`, `thread/start`, `mcpServerStatus/list`, and one exact prepared
`turn/start`; only `initialized` notifications are allowed. It cannot answer
approval/tool requests. The effective provider URL and no-auth setting are
checked before the turn. Account acknowledgement is
`{"account":null,"requiresOpenaiAuth":false}`. Native version comes from the
contained initialize response, so no separate uncontained native command runs.

## Supported wire and unchanged assumptions

The local generated 0.154.0 app-server schemas supplied the `thread/start` and
`turn/start` shapes. Official Codex documentation supports no-auth local custom
providers with `requires_openai_auth = false` and no `env_key`.
[Codex authentication](https://learn.chatgpt.com/docs/auth).
The custom provider uses `wire_api = "responses"`, HTTP POST to `/v1/responses`
and a terminal `response.completed` SSE event. Gateway compatibility does not
cover independent MCP network paths.
[Codex gateway compatibility](https://learn.chatgpt.com/docs/enterprise/gateway-compatibility).
The fixture authors typed SSE text events; the app-server reports matching
`item/completed` and `turn/completed` events.
[Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
[Codex app-server](https://learn.chatgpt.com/docs/app-server).

The artifact includes the installed binary hash and unchanged filter-source hash.
The observed host is Linux 7.2.4-1-aarch64-ARCH with bubblewrap 0.12.0. The trusted
launcher installs its aarch64 filter before the one initial native exec; process
creation and later exec are denied while native threads remain possible. The
launcher, runtime, native executable, approved relay and kernel remain trusted.
The policy JSON is a launcher self-report, not kernel attestation. The separate
syscall challenges, initial-exec assumptions and negative controls remain in the
prior report; this run repeats executable-MCP denial, not every outer-boundary or
clone/exec challenge. No protection against native-code compromise is claimed.

The SSE events are delivered in one bounded response body. This tests native SSE
parsing and completion, not production streaming latency, arbitrary chunk loss,
retries, tool loops or external-effect recovery. In-process integrations and
shared-broker caller binding remain open scope. No production gate changes.

## Reproduction and next decision

```sh
uv run pytest tests/test_native_synthetic_turn_probe.py
NEMA_NATIVE_SYNTHETIC_TURN_PROBE=1 uv run pytest tests/test_native_synthetic_turn_probe.py
uv run python scripts/probe_native_synthetic_turn.py --output /tmp/native-synthetic-turn.json
```

Default tests use synthetic sockets and client guards; they never launch native
Codex or compile the filter. The opt-in tests and standalone script each perform
two real native turn RPCs against the authored local provider. They require the
reviewed Linux/aarch64, compiler, bubblewrap and seccomp facilities; there is no
uncontained fallback. Worktree runs use the existing uv environment with
`UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync`.

Focused verification: **36 passed, 3 skipped** by default; the native opt-in
passed **38 tests** before the review's parser-only robustness fix. A JSON body
within the byte cap but nested 2,000 arrays deep now returns a recorded 400 without
consuming the permit; its new default regression covers the fix. The standalone
invocation generated the linked evidence artifact before that parser-only change.
The related synthetic/process/gateway/outer/account/profile/worker/native-review/
seed suite passed **236 tests with 31 intentional opt-in skips** after that fix. Captured body and
source-record hashes, output-record references and internal report links checked.
Independent source review accepted the narrow experiment subject to that fix;
the parent integrator independently reproduced the complete opt-in suite on the
integrated tree after the parser fix: **39 passed**, including both guarded native
turns with zero real model or upstream calls.

Each case has an 18-second native watchdog and the unchanged supervisor's
20-second alarm. The broker accepts at most 24 requests, parses each within two
seconds, and caps headers at 8 KiB, bodies at 128 KiB, and response bodies at
16 KiB. The relay accepts at most 24 connections, bounds each transfer to four
seconds and request/response bytes to 140,000/20,000, and exits after 18 seconds.
The completion loop consumes at most 100 native events with an eight-second
deadline. That counter does not bound asynchronously recorded stdout or total
trace events/bytes; the native executable and authored response remain trusted.
These are experiment bounds, not aggregate CPU, memory or disk quotas.

**Next discriminating result:** use this captured request as the baseline for a
separate no-credential experiment that tests a supported way to remove or
constrain the remaining native tools and in-process integrations before the turn.
Require the effective configuration and actual provider wire to agree; use a
synthetic tool-call response as the counterexample instead of inferring safety
from this text-only response. Caller binding still requires a distinct supported
mechanism or explicit trusted-client boundary. A real subscription/auth transport
decision belongs to the integrator and is not authorized or implemented here.

Lane ownership: only the new probe, focused tests and these uniquely named
evidence files change. The integrator owns canonical state/handoff and any future
admission decision.
