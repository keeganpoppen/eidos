# Native tool controls survive an authored tool-call challenge

**2026-10-13 · implementation base `b1896ae` · C6 / V1-05 / V1-12.**
For installed Codex **0.154.0**, a fresh configuration can remove every tool from
the observed synthetic provider request. When the fixture nevertheless returns a
`read_mcp_resource` call, native Codex returns **`unsupported call:
read_mcp_resource`**, contacts no fixture MCP endpoint, and completes the turn
after receiving the authored final text. A positive control executes the same
resource call and sends its exact fixture result back to the provider.

This is a concrete pre-turn configuration result, under the unchanged
[pre-exec process boundary](NATIVE_PROCESS_BOUNDARY_EXPERIMENT.md). It is not
subscription execution, caller authentication or complete native admission.
The selected synthetic model uses **fallback model metadata**; another model's
catalog may affect available tools. Production profiles and the closed admission
gate remain untouched.

The [raw JSON evidence](NATIVE_TOOL_BOUNDARY_0_154_0.json) contains **three native
turn RPCs and six actual provider requests**, all answered by a local authored
service. Each case sends one `turn/start` and two provider POSTs: the initial
request, followed by the function-call result. There are zero real model calls,
real upstream requests, existing credential mounts or owner-state reads.
Recovered artifacts remain `executionEvidence: synthetic`.
`providerRequests` counts all recorded requests to the provider route, including
rejections; `acceptedProviderRequests` counts fixture steps. They coincide here.

## Three configurations, one identical tool-call response

All cases use fresh state, `requires_openai_auth=false`, no environment keys,
`environments: []`, a disconnected bubblewrap namespace and the reviewed native
process filter. The fixed loopback relay reaches only the fixture Unix socket.
The host fixture has two routes, `/v1/responses` and `/mcp`, and no upstream client.
Configuration is written before native launch; no late tool-list rewriting or
provider request editing occurs.

| Case | Tool schemas in initial request | Fixture resource read | Second provider request |
| --- | --- | --- | --- |
| Baseline; HTTP MCP enabled with `enabled_tools=[]` | Three MCP resource functions, user input, skills namespace | One successful read | Exact authored resource bytes |
| User-input/skills controls disabled; same MCP still enabled | Three MCP resource functions | One successful read | Same resource bytes |
| Same controls; MCP server also disabled | `tools: []` | Zero; no MCP HTTP requests | `unsupported call: read_mcp_resource` |

All three native turns finish with the same authored final text. Both provider
requests in the last case have empty tools arrays, although `tool_choice` remains
`auto`. The first two cases each make 19 fixture HTTP requests: two provider POSTs,
nine accepted MCP initialization/inventory/read messages, and eight refused
GET/discovery routes. The disabled case makes only its two provider POSTs.

The fixture advertises an unused `fixture_echo` MCP tool. `enabled_tools=[]`
removes it: native inventory reports an empty tool map while the server remains
connected. It does **not** remove generic MCP resource observation. The injected
built-in `read_mcp_resource` call successfully reads the fixture URI anyway.
That is a counterexample to treating an empty server-tool allowlist as disabling
every in-process MCP action. The middle case also sets `orchestrator.mcp.enabled`
to false; this does not disable an explicitly configured custom MCP server.

The only requested action is:

```json
{"name":"read_mcp_resource","arguments":{"server":"fixture","uri":"fixture://isolated/observation"}}
```

The fake resource contains `AUTHORED_MCP_RESOURCE_READ: disposable fixture only.`
It is an in-memory authored response, not a filesystem read or an external
service. The positive cases record matching native `mcpToolCall` start/completion
items and a provider `function_call_output`, all with the fixture call ID. The
negative case records no such MCP action item and returns the literal unsupported
call error in the same correlated output position. The native event observer is
after-the-fact evidence, not a pre-effect authorization mechanism.

## Controls and source evidence

The controls come from the installed protocol schemas and matching public
`rust-v0.154.0` source, not guessed hidden settings. The constrained cases add:

```toml
[tools.experimental_request_user_input]
enabled = false
[orchestrator.skills]
enabled = false
[orchestrator.mcp]
enabled = false
[skills]
include_instructions = false
[skills.bundled]
enabled = false
```

The final case additionally sets `mcp_servers.fixture.enabled=false` before
startup. The shared baseline disables shell, apps, plugins, hooks, memories,
multi-agent features and image generation, and retains empty turn environments.
`requestedConfigToml` records the full exact template; native `config/read`
acknowledges the orchestrator, skills and MCP settings, and inventory identifies
the final server as `disabled`.

There is one significant acknowledgement limit: the installed `config/read`
projection omits `tools.experimental_request_user_input`, even though the tagged
configuration schema accepts it and the actual provider wire shows user input
removed. The evidence therefore combines requested configuration, source and
observed behavior. It does not claim that config/read alone verifies every tool
control. The recorded skill catalog also disappears, while native permission and
environment messages remain alongside the selected prompt.
The constrained settings change as a group; the runtime comparison does not
isolate every setting's individual effect. The source findings below are a
separate explanation of the installed release's implementation.

The [tagged configuration schema](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/config.schema.json)
defines the controls. The [native tool plan](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/spec_plan.rs)
registers MCP resource handlers when MCP servers are present and separately gates
the user-input handler. The [skills tool contributor](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/skills/src/tools/mod.rs)
omits its tools when neither orchestrator skills nor an executor query is
available. The [resource handler scope](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/handlers/mcp_resource.rs)
explains why the orchestrator MCP flag does not disable arbitrary custom servers.
Official [configuration documentation](https://learn.chatgpt.com/docs/config-file/config-reference)
documents per-server enablement and tool allow/deny lists. These release-specific
controls are not represented as a permanent cross-version API guarantee.

Locally inspected source SHA-256 values:

| Tagged file | SHA-256 |
| --- | --- |
| `core/config.schema.json` | `2e1fcf1cbb20f255c3baca2e174b4a3c954cef577a130587b8935e2d12c8ade6` |
| `core/src/tools/spec_plan.rs` | `451622e76c45dd1585318c200fdee9a00d7aaf785d4a540facca1010146307b7` |
| `ext/skills/src/tools/mod.rs` | `9195992e69aa4bd91f679b8edcdb7ada620e7c1d78a38d833fd8718f9904f51b` |
| `core/src/tools/handlers/mcp_resource.rs` | `42c1b9ed21abaf7082037ca3c46aed3f03c801a2ddc09e71ce499545f0af5df3` |

The release tree identifier is `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`.
The artifact separately records the installed binary and filter-source hashes;
release-source inspection is not a reproducible-build attestation for that binary.

## Scope, bounds and reproduction

`brokerEvents` retains exact request bodies/hashes, headers, authored SSE and MCP
response bodies. `traceRecords` retains raw native messages and unknown fields.
Derived tool summaries do not replace either capture. The initial provider
bodies are 12,244 / 6,838 / 4,965 bytes respectively. The original selected prompt
remains one user text part, not the whole native provider input.

The broker refuses other routes, methods, resource URIs, tool calls and duplicate
provider requests. The second provider request must contain one output with the
authored call ID. This is fixture sequencing, **not caller authentication**: the
IDs and body contents are public, and no valid-request impersonation challenge is
claimed. Existing [shared-relay identity failure](NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md)
remains applicable. No synthetic response asks for process execution, arbitrary
file access, writes or an external service. Client process/exec RPCs and all native
approval responses remain refused.

The launch assumptions from the process experiment are unchanged: trusted native
executable/runtime, launcher, relay and kernel; aarch64-only filter installed
before the one initial native exec; no general native-code-compromise claim. This
run exercises an HTTP resource observation, not new clone/exec syscall challenges.
The unknown-model warning and fallback metadata are preserved. Empty tools for
this model do not establish the tool registry for an authenticated account model.
Only the one removed resource function is challenged dynamically; other absent
functions are observed on the wire, not exhaustively adversarially invoked.

```sh
uv run pytest tests/test_native_tool_boundary_probe.py tests/test_native_synthetic_turn_probe.py
NEMA_NATIVE_TOOL_BOUNDARY_PROBE=1 NEMA_NATIVE_SYNTHETIC_TURN_PROBE=1 uv run pytest tests/test_native_tool_boundary_probe.py tests/test_native_synthetic_turn_probe.py
uv run python scripts/probe_native_tool_boundary.py --output /tmp/native-tool-boundary.json
```

Default verification: **64 passed, 7 intentional opt-in skips**. Combined native
opt-in verification: **71 passed**, including the previous text-only native probe
after the approved shared parser extraction. The new probe itself contributes
28 default tests and four native checks. The standalone invocation generated the
linked artifact. Worktree commands use the existing environment via
`UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync`.
The related tool/synthetic/process/gateway/outer/account/profile/worker/native-
review/seed suite passed **264 tests with 35 intentional opt-in skips**. An
independent read-only reviewer reproduced the 64 default passes, inspected the
source and evidence, and accepted these narrow claims; they ran no native probes.

The parent independently reproduced the combined native opt-in on the integrated
tree: **71 passed**, including both prior text-only cases and all three tool-call
cases. The later accepted-request limit-label correction changes no behavior or
raw observation.

The shared parser retains two-second request deadlines, 8 KiB headers, 128 KiB
bodies and 16 KiB response bodies, including controlled deeply nested JSON failure.
Each case handles at most 24 HTTP requests, with at most two accepted provider
requests; rejected provider-route requests count toward the total HTTP cap. The native
watchdog is 18 seconds; the reviewed C supervisor has its 20-second alarm. The
unchanged relay bounds connections, transfer bytes and time. The completion loop
consumes at most 100 events within eight seconds; asynchronous native stdout and
total trace bytes are not capped by that counter. These are fixture bounds, not
aggregate CPU, memory or disk quotas. Unsupported containment fails without an
uncontained fallback.

**Production implication:** an empty offered tool set is tractable for this
fresh, known native configuration, and the observed unregistered resource call
does not execute. A future text-only specialist still needs a separately reviewed
model/profile and account-transport decision. Its effective tool/integration
controls must be checked for that actual native model/catalog; the fallback-model
result and an incomplete config/read projection cannot grant admission. This
experiment changes no production gate or subscription authority.

Lane ownership: new script/tests/evidence plus the explicitly coordinated parser
extraction in the prior synthetic-turn script. The integrator owns canonical
state/handoff, independent acceptance and any later real-provider decision.
