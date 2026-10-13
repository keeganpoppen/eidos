# Native model-catalog discriminator — 2026-10-13

## Result and scope

**The previous tools-disabled configuration does not survive every exact public
model-catalog entry.** With the unmodified Codex `rust-v0.154.0` public catalog,
`gpt-6-astra` offers code execution, asynchronous user input, sleep and collaboration
tools despite the inherited `code_mode=false` / `multi_agent=false` configuration.
An authored direct `clock.curr_time` call succeeds. The same configuration with
`gpt-5.5` offers `tools=[]` and rejects that call.

Both native turns finish and recover the fixed authored fixture text. This is
**native transport with synthetic provider responses**, not model inference,
subscription execution, caller authentication, or complete native admission.
No credentials, existing auth/state directories, external forwarding, actual model
service or paid API were used. No shell/code/collaboration call was authored.

This supports the eventual V1-05/C6 bounded specialist by falsifying a tempting
profile-generalization before enabling a production gate. Production code and
profiles are unchanged. The inherited process filter remains in place throughout.

## Reproduce and inspect

Implementation base: `2c447e4`. New files:

- [Probe](../../scripts/probe_native_model_catalog.py)
- [Tests](../../tests/test_native_model_catalog_probe.py)
- [Raw final-run evidence](NATIVE_MODEL_CATALOG_0_154_0.json)
- [Exact public catalog bytes](NATIVE_MODEL_CATALOG_0_154_0_PUBLIC.json)

Default checks start no native process and access no network:

```sh
uv run pytest -o addopts='' -q tests/test_native_model_catalog_probe.py tests/test_native_tool_boundary_probe.py tests/test_native_synthetic_turn_probe.py
```

Observed: **90 passed, 10 skipped**. Native opt-in:

```sh
NEMA_NATIVE_MODEL_CATALOG_PROBE=1 NEMA_NATIVE_MODEL_CATALOG_EVIDENCE=/tmp/native-model-catalog.json uv run pytest -o addopts='' -q tests/test_native_model_catalog_probe.py
```

Observed: **29 passed**. Alternatively, explicitly running the script launches the
same two contained native turns:

```sh
uv run python scripts/probe_native_model_catalog.py --output /tmp/native-model-catalog.json
```

The worktree used the existing environment with
`UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync`.
These are explicit native probes; the default suite skips all three native checks.
No ordinary test relies on credentials or a live service.

The recorded final run contains **2 native `turn/start` RPCs and 6 local provider
requests**, 1 turn and 3 accepted provider requests per model. An initial development
run rejected Astra because the fixture incorrectly required an empty `instructions`
field. Tagged serialization source established that it must be omitted; the fixture
was corrected to require absence, without changing routes or limits. Across the
three development/verification executions there were 6 native turn RPCs and 16
local provider requests. All had zero real model or upstream requests. The committed
raw artifact is the final 2-turn/6-request run, not an aggregate of those executions.

## Public source and exact startup input

The catalog came from the
[tagged public OpenAI repository](https://raw.githubusercontent.com/openai/codex/rust-v0.154.0/codex-rs/models-manager/models.json).
Its unmodified 515,190 bytes have SHA-256
`f3b8104396daf6381bed9d7c4b154a8664f9b5089b44b01a9d54f421566ec9a7`.
The probe bounds the read, checks this exact hash before compiling/launching native,
copies the bytes into `/fixture/models.json`, and mounts `/fixture` read-only.
There is no runtime download or alternate catalog fallback. The redistributed public catalog
is accompanied by the tagged upstream [license](NATIVE_MODEL_CATALOG_LICENSE.txt)
and [notice](NATIVE_MODEL_CATALOG_NOTICE.txt); the catalog bytes are unmodified.

`model_catalog_json="/fixture/models.json"` is written before configuration loads.
The [tagged config schema](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/config.schema.json)
explicitly describes this as startup-only; per-thread overrides do not reload it.
Both `config/read` replies retain this path, the requested model, the local no-auth
provider and disable settings. Neither turn emits a fallback-metadata warning.
The matching catalog slugs, captured effective configuration and distinct resulting
wire behavior together support use of these entries; `config/read` alone is not a
complete tool-policy attestation. As in the prior probe, its projection omits the
accepted `tools.experimental_request_user_input` setting.

| Exact catalog entry | `tool_mode` | `use_responses_lite` | `experimental_supported_tools` |
| --- | --- | --- | --- |
| `gpt-6-astra` | `code_mode_only` | `true` | `send_user_message_async`, `clock` |
| `gpt-5.5` | `null` | `false` | empty |

Presence in this public catalog establishes neither account availability nor a
subscription transport entitlement.

The [tagged tool-mode selection](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/mod.rs#L68)
uses model metadata before feature flags. The
[tagged registry construction](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/spec_plan.rs#L1167)
adds async-user and clock handlers from model metadata. Those explain why disabling
the previous experimental user-input feature is insufficient for this catalog entry;
the runtime evidence below establishes the observed behavior of this exact build.

Native `/usr/bin/codex` reports 0.154.0 through contained `initialize.userAgent`.
Binary SHA-256:
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
The reused process-filter C source SHA-256 is
`274c79ec32bd8ab307a883bbdb74805c1a040c969ca32a3cdc7b514d35910e56`.
Host/kernel identities are in the raw artifact. No native command was run outside
the reviewed disconnected namespace/pre-exec filter.

## What crossed the local provider wire

Both models use `POST /v1/responses` and the existing Responses SSE response decoder.
The [tagged request builder](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/client.rs#L891)
and [serialization](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/codex-api/src/common.rs#L280)
establish these differences:

| Captured wire property | `gpt-6-astra` | `gpt-5.5` |
| --- | --- | --- |
| Lite header | `x-openai-internal-codex-responses-lite: true` | absent |
| Top-level `tools` | absent | `[]` |
| Tool declaration location | one developer `additional_tools` input item | top-level field |
| Top-level `instructions` | absent; base instructions become an input message | present |
| Request body bytes, steps 1–3 | 22,619 / 22,981 / 23,277 | 4,984 / 5,346 / 5,644 |

The fixture validates the model/header/envelope combination, exactly one selected
prompt, and the expected sequence of tool-output call IDs. It refuses all other
routes, MCP requests, authentication/transfer/content-encoding headers, duplicate
headers, early requests, repeated steps and requests beyond the budget. This is
synthetic dispatch validation, **not caller authentication**.

Astra's `additional_tools` item contains these exact namespaces/functions:

- `functions`: `exec`, `wait`, `request_user_input_async`.
- `clock`: `sleep`.
- `collaboration`: `followup_task`, `interrupt_agent`, `list_agents`, `send_message`,
  `spawn_agent`, `wait_agent`.

The `exec` description additionally exposes the nested `clock__curr_time` tool.
Checking only top-level `tools` would miss the whole Lite declaration. The preserved
raw JSON includes every schema and additional native message, not just this summary.
The selected packet appears exactly once as user input; it is only part of the
complete native provider payload.

## Authored challenges and native results

The service sends three fixed responses, requesting no shell or JavaScript:

1. A function call to `read_mcp_resource` with exactly
   `{"server":"fixture","uri":"fixture://isolated/observation"}`.
2. A function call with `namespace="clock"`, `name="curr_time"`, `arguments="{}"`.
3. The fixed final text:
   `SYNTHETIC FIXTURE: both selected records survived [evidence:1] [evidence:2].`

Both models return `unsupported call: read_mcp_resource` in the next provider
request. Inventory reports the fixture MCP disabled; there are **zero MCP HTTP
contacts/resource reads**. The broker has no MCP dispatch path.

Astra returns `It is 2026-10-13 20:14:24 UTC.` for the clock call in the final recorded
run. The [tagged clock implementation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/handlers/current_time.rs)
confirms this is the safe built-in time observation. The `gpt-5.5` control instead
returns the native literal `unsupported call: clockcurr_time`.

Each case has only `userMessage` and `agentMessage` `item/started`/`item/completed`
events. **The successful clock operation has no separate action item in those
events.** The authored provider call plus correlated native function-call output is
the evidence of execution. An after-action observer cannot infer inactivity from
the absence of a tool item, much less provide pre-effect authorization.

Both turns produce the expected final message. The existing recovery reader matches
source/thread/turn and stores an artifact explicitly classified `executionEvidence:
"synthetic"`. Raw native JSONL records, unknown fields, selected context, outgoing
RPCs, provider requests and authored responses remain in the artifact. Both cases
have 18 consumed native events and 33 recorded trace rows.

## Boundaries, limits and decision

The experiment reuses the prior namespace, launcher, broker parser and pre-exec
process filter unchanged. Fresh state has no credentials, and `account/read` is
allowed only with `refreshToken=false`; both replies are `account:null` and
`requiresOpenaiAuth:false`. The custom provider points only to the loopback relay's
fixed host Unix socket. There is no upstream client implementation. The RPC allowlist
is inherited and excludes process/exec, auth mutation and direct MCP execution.
The filter is installed before native configuration startup, allowing native threads
while denying later child-process creation/exec under its previously reviewed ABI
assumptions. Its policy JSON remains a trusted-launcher report, not kernel attestation.

Each case retains: 18-second native watchdog, unchanged 20-second C supervisor alarm,
8-second/100-consumed-event completion loop, 24 HTTP requests, at most 3 accepted
provider steps, 2-second request parsing, 8,192 header bytes, 131,072 body bytes and
16,384 response bytes. The reused relay caps each connection at 140,000 request bytes,
20,000 response bytes and 4 seconds. Catalog reads cap at 600,000 bytes. Parser tests
cover nested JSON/controlled `RecursionError`, malformed shapes and unconsumed permits.
The exact-content constraints do not distinguish a same-boundary impersonating caller.

The consumed-event limit still does **not** cap asynchronous native stdout allocation,
queued events, total trace bytes, or aggregate CPU/memory/disk. The separate transport
budget work is not incorporated into this base. No arbitrary-code/native-compromise
security claim follows from the process filter, safe clock call, or local provider.

The production decision is narrower than selecting a preferred model: **the tested
all-disabled candidate must be tied to exact model metadata and actual registered
behavior, not inferred from feature flags or one fallback model.** This candidate
fails a tools-disabled claim for Astra. The gpt-5.5 control preserves the two tested
tool refusals and empty offered tools; it does not prove rejection of every possible
unoffered tool or compatibility with a real subscription service.

Next discriminating work would identify supported pre-turn controls for the exact
remaining Astra registrations, then challenge safe observations again with this
unchanged public catalog. Alternatively, the integrator can explicitly narrow the
candidate profile to the observed ordinary-Responses metadata. Execution of offered
code/collaboration tools remains untested and outside this experiment. Credential,
transport authority, resource admission and subscription decisions remain separate;
the production default gate stays closed.

## Parent reproduction and independent review

The integrator inspected the full new probe/tests and reproduced the explicit
catalog opt-in from `f848ae1`: **29 passed**, two native turns and six local provider
requests with zero real model/upstream calls. Parent raw evidence is
`/tmp/native_model_catalog_parent_20261013.json`. An independent reviewer verified
the catalog/request hashes, source explanation and wire/event distinction and ran
**95 default checks / 10 skipped**, with no native invocation or adoption blocker.
The combined main suite passed **891 tests / 41 skipped**. Production admission
remains unchanged; neither review nor reproduction enlarges the stated scope.
