# Paired startup-catalog policy challenge

**Observed 2026-10-13, implementation base `555a317`, Codex 0.154.0, Linux
aarch64.** This research serves C6 / V1-05/12: making a bounded, read-only native
specialist tractable without admitting an unreviewed tool surface. It changes no
production profile or admission gate.

The paired experiment succeeded within its synthetic contract. Both cases used
the actual `gpt-6-astra` slug and Responses Lite. With the original public catalog,
code/async tools remained registered and the authored clock call executed. With
exactly two local metadata changes, every observed request had empty
`additional_tools.tools`, and the same clock call was rejected. Both cases rejected
the disabled MCP resource call, contacted no MCP endpoint, completed the fixed
authored text, and recovered a result labelled `executionEvidence: synthetic`.

There were **two native turn RPCs and six local provider requests**, zero real
model calls, zero upstream requests, and no credentials or existing Codex state.
The new bounded transport reported no capture gap; the accepted native terminal
was recovered. This does not establish that an unreceived tail was absent when
the fixture closed the client after completion.

## Exact inputs and observed contrast

[Raw evidence](NATIVE_DERIVED_CATALOG_0_154_0.json) retains requested config, actual
config replies, packet and prompt, complete recorded provider request bodies and
hashes, authored SSE responses, native events and raw trace records, transport
limits/status, launcher report, correlation IDs, and the synthetic result. Public
fixture temporary paths are normalized to `<probe>`; native IDs and observed clock
text are retained. Provider input includes additional native instructions/messages
beyond the selected packet; each observed request contains the exact selected
prompt once.

Both cases use the earlier `allMcpDisabled` profile, adding:

```toml
[agents]
enabled = false

[features]
multi_agent_v2 = false
sleep_tool = false
current_time_reminder = false
```

The existing feature settings, including `multi_agent=false`, `code_mode=false`
and `shell_tool=false`, remain. Both actual `config/read` replies confirm all four
new controls, the selected model, immutable startup catalog path and local no-auth
provider. The replies do not themselves expose the loaded `ModelInfo`; the hashed
catalog, matched slug, protocol shape, registry behavior and absence of a fallback
warning provide the narrower evidence. No account availability is inferred.

The original is the exact committed
[public tagged catalog](NATIVE_MODEL_CATALOG_0_154_0_PUBLIC.json), 515,190 bytes,
SHA-256 `f3b8104396daf6381bed9d7c4b154a8664f9b5089b44b01a9d54f421566ec9a7`.
The derivative is generated before startup, 515,124 bytes,
SHA-256 `6571b50e45135f71d0200cb029fb37ffd67d7e829f5b1e3d3a1450c8183dceda`.
The evidence contains the RFC6902 patch including tests for the target slug and
original values. Its only mutations are:

```json
[
  {"op":"replace","path":"/models/0/tool_mode","value":"direct"},
  {"op":"replace","path":"/models/0/experimental_supported_tools","value":[]}
]
```

`slug`, `use_responses_lite=true`, `multi_agent_version=v2`, all other model
metadata and all other models remain unchanged. Validation compares canonical
JSON, preserving unknown fields and distinguishing JSON booleans from numbers;
plain Python equality would incorrectly equate `true` and `1`. A regression rejects
that counterexample. The derivative is explicitly **Nema local startup policy**,
not unchanged upstream metadata or a new source of authority. Labels and hashes
are outside the catalog. The original's upstream [license](NATIVE_MODEL_CATALOG_LICENSE.txt)
and [notice](NATIVE_MODEL_CATALOG_NOTICE.txt) also apply to this derivation.

Each case receives the same three fixed responses: `read_mcp_resource` for
`{"server":"fixture","uri":"fixture://isolated/observation"}`, then
`clock.curr_time` with `{}`, then the fixed final text. No exec/code, collaboration,
shell, user-interaction or other tool call is authored.

| Observation | Original + added controls | Derived + same controls |
| --- | --- | --- |
| Lite header | `true` | `true` |
| Top-level `tools` / `instructions` | absent / absent | absent / absent |
| Developer `additional_tools.tools` | `functions`: exec, wait, request_user_input_async | `[]` |
| Nested clock description | `clock__curr_time` under exec | absent |
| Resource output | `unsupported call: read_mcp_resource` | same rejection |
| Clock output | `It is 2026-10-13 20:44:02 UTC.` | `unsupported call: clockcurr_time` |
| Native turns / provider requests | 1 / 3 | 1 / 3 |
| Provider request body bytes | 13,544; 13,906; 14,202 | 6,591; 6,953; 7,251 |
| Native stdout / stderr received bytes | 25,027 / 152 | 25,027 / 301 |
| Accepted stdout frames / consumed events / trace rows | 24 / 18 / 34 | 24 / 18 / 34 |

The schema contrast holds on all three requests, not only the first. Both inventories
report the fixture MCP disabled; there were zero resource reads and no `/mcp`
requests. Stderr contains the expected unsupported-call diagnostics. Neither case
has a separate native action item for the clock challenge: item events contain only
user/agent messages. The correlated provider call/output proves the original clock
execution; an observer's lack of action events does not prove inactivity or provide
pre-effect admission.

## Supported source and implementation

These are source observations from public tag `rust-v0.154.0`, inspected locally
from the same tagged source cache as the preceding experiment:

The parent also checked the current [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference),
which documents startup catalog paths and the agent enable setting. Exact
precedence and the observed behavior below remain tied to the tested native tag.

- [Config schema](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/config.schema.json#L6636)
  declares `model_catalog_json` as startup input; per-thread overrides do not reload it.
- [Tool selection](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/mod.rs#L68)
  gives catalog `tool_mode` priority over feature defaults. The
  [typed enum](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/protocol/src/openai_models.rs#L342)
  supports `direct`; this is not an invented hidden setting.
- [Agent selection](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/config/mod.rs#L1544)
  honors the disabled agent setting when the v2 feature is false, ahead of the
  model's agent metadata. Leaving only `multi_agent=false` was insufficient.
- [Registration](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/spec_plan.rs#L1167)
  uses experimental metadata for async interaction and clock; sleep has its own
  feature control. This explains why the added controls alone retain clock/code.
- [Provider model manager](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/model-provider/src/provider.rs#L449)
  chooses `StaticModelsManager` when a startup catalog is supplied, including the
  configured OpenAI provider implementation. No authenticated refresh behavior was
  exercised here.
- [Request construction](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/client.rs#L911)
  preserves Lite while serializing its tool list into an `additional_tools` input
  item; empty top-level tools alone would not establish an empty declaration.

Source SHA-256 values, in the same order except enum listed separately:

| Tagged source | SHA-256 |
| --- | --- |
| core/config.schema.json | `2e1fcf1cbb20f255c3baca2e174b4a3c954cef577a130587b8935e2d12c8ade6` |
| core/src/tools/mod.rs | `0c8ec9324f67053cf7c14dac5d53504c9e8c370b84cb2323fdb0239e674572d7` |
| protocol/src/openai_models.rs | `2e9923d405a497441a0b264efc07de6ce21cdb108442e660a8b9fb63ca415aed` |
| core/src/config/mod.rs | `4967b9f719ac886d5c6dd923f4d07263fe4eef2a7070078c5a291f57973c76a1` |
| core/src/tools/spec_plan.rs | `451622e76c45dd1585318c200fdee9a00d7aaf785d4a540facca1010146307b7` |
| model-provider/src/provider.rs | `b76d1837802ef08b12cada67de9080a1361a7b43ba45155e452c930180fe874a` |
| core/src/client.rs | `6979098f4ad7b5ec16f19ca90d5c927d3b1e33d0f6d926c70388d0237c52af35` |

The [new script](../../scripts/probe_native_derived_catalog.py) reuses the reviewed
catalog runner, broker, fixed SSE, synthetic client, namespace and process filter.
The integrator owns a minimal compatible extension to `run_case`: optional keyword
arguments `config` and `limits`, retaining the original defaults. There is no copied
harness or runtime module-global substitution. The helper with that extension has
SHA-256 `ae39045f5c36ec536f4a79009516d21bed3c4015073e3cc526443af73e55394e`.
The new-file commit depends on that separately integrated helper extension.

The disconnected bwrap namespace mounts `/fixture` read-only and uses fresh empty
state. The reviewed launcher installs process restrictions before the trusted
native executable reads config, permits its one initial exec transition and native
threads, and denies the previously tested child/exec transitions. The separate
fixture relay exists before that filter and reaches only the fixed host Unix socket.
No forward route exists. The current run verifies the launcher's policy report;
it does not rerun the earlier exhaustive syscall challenges. The binary and filter
hashes are in the raw evidence and match the preceding experiments.

## Bounds, verification and limits of the result

Per case, stdout frames are limited to 1 MiB, stderr frames to 64 KiB, aggregate
receipt to 4 MiB, retained events to 128 / 2 MiB, and stderr tail to 64 KiB / 100
lines. The trusted limit record agrees with actual capture status. There were no
reported gaps or diagnostic errors, and retained event count/bytes were zero at
the final snapshot. Capture gaps fail this candidate even if an earlier result
could be recovered. Receipt accounting does not claim an unseen tail was captured
after explicit shutdown; it is not a quota on all trace database storage.

Unchanged fixture bounds: HTTP headers 8 KiB, body 128 KiB, response 16 KiB,
24 HTTP requests and at most three accepted provider requests per case, 2-second
parser deadline; relay 140,000 request / 20,000 response bytes and 4 seconds per
connection; 18-second native watchdog, 20-second helper alarm, 100 consumed events
and 8-second completion window. Native request retries are disabled. There is no
aggregate CPU/RSS/disk quota claim. Unknown routes, redirected targets, invalid
framing/headers, oversized or deeply nested bodies, early/duplicate requests and
wrong call correlation remain refused by the unchanged tested broker.

From the worktree root, the default focused suite starts no native process:

```sh
uv run pytest -o addopts='' -q tests/test_native_derived_catalog_probe.py tests/test_native_model_catalog_probe.py tests/test_native_tool_boundary_probe.py tests/test_native_synthetic_turn_probe.py tests/test_bounded_transport.py tests/test_codex.py tests/test_seed_context.py
```

Result: **159 passed / 13 explicit native tests skipped**. The single paired native
run passed **21 checks** before three further pure assertions were added; the final
default suite applies the strengthened interpretation to its stored raw evidence.
No second development native run was made. Reproduce the explicit native experiment:

The parent independently reproduced the final **24 checks** on integrated main,
including another two contained native turns/six local provider requests, with no
real model/upstream/credentials. Both expectations pass; the local report is
`/tmp/native_derived_catalog_parent_20261013.json`. This parent run is separate from
the committed raw development evidence.

```sh
NEMA_NATIVE_DERIVED_CATALOG_PROBE=1 NEMA_NATIVE_DERIVED_CATALOG_EVIDENCE=/tmp/nema-derived-catalog-rerun.json uv run pytest -o addopts='' -q tests/test_native_derived_catalog_probe.py
```

The recorded run used the existing shared uv environment via
`UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync`; that is
host setup, not part of the boundary. The standard command above is for a synced
checkout. Direct script use also explicitly starts the contained experiment:
`PYTHONPATH=src uv run python scripts/probe_native_derived_catalog.py --output /tmp/nema-derived-catalog-rerun.json`.

This result supports a local, startup-configured text-only Astra candidate under
trust in the reviewed executable/configuration. It establishes rejection of the
two challenged handlers and an empty observed declaration, not exhaustive testing
of every possible hidden handler or a compromised native process. No exec/code or
interaction execution branch was exercised. Fixture body matching and relay PID
are not caller authentication; valid-request impersonation was not tested here.

The next production decision can choose this transparent derived policy or the
already tested ordinary-Responses model. The indispensable remaining account fact
is whether a fresh Nema-owned native session can use the intended model through
supported managed ChatGPT authentication and bounded egress. That requires its own
explicit contract, retaining native credential ownership and avoiding copied user
auth/owner state. This probe grants no subscription availability or live admission.
