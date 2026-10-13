# Owned private worker joining experiment

**2026-10-13 · implementation base `4b91892` · contained synthetic native evidence.**
The [accepted packet](../agents/NATIVE_OWNED_WORKER_TASK.md) joins the existing
managed-text fixture to `PrivateInvestigationWorker`, its preparation hook, the
ordinary native turn loop and private publication/recovery. The first native run
was refused. A separately reviewed worker-only startup setting produced one exact
synthetic result; the parent independently reproduced that outcome. Production
native admission remains closed.

## Outcomes and retained evidence

| Observation | First run | Reviewed follow-up | Parent reproduction |
| --- | --- | --- | --- |
| Startup goal control | Native default | `features.goals=false` | `features.goals=false` |
| Provider POST bytes | 31,734 | 28,684 | 28,685 |
| Final provider response | 400, tool declaration refused | 200, fixed 2,769-byte SSE | 200, same fixed SSE |
| CONNECTs / local HTTP exchanges | 6 / 6 | 6 / 6 | 6 / 6 |
| Main / private records | 2 / 36 | 3 / 42 | 3 / 42 |
| Native terminal / result publication | Absent / absent | Completed / main seq 3 | Completed / main seq 3 |
| Reopened artifact / live ownership | No result / absent | Exact / absent | Exact / absent |
| Capture gap, resource refusal, cleanup failure | None | None | None |
| All owned workers joined | Yes | Yes | Yes |

The [first raw report](NATIVE_OWNED_WORKER_0_154_0_FIRST_FAILURE.json) remains
byte-identical to the initial output. Its SHA-256 is
`0fa26b035cca90b1a1d5da4dcd6e5bea01149331ddc41beaf7d7b74bf6e23fe1`.
Script commit `3b03aba35488e6a0466a26905c58eb04c25320d6` had SHA-256
`c0fc756458c4988d94c59786a1ac752ca26811cf4f89b40eb93474042df58f15`.
The opt-in command returned **one failed, 137 passed, three skipped** in 3.97 seconds.
This failed assertion is evidence of the boundary refusal, not a passed joining test.

The [positive raw report](NATIVE_OWNED_WORKER_0_154_0.json) was produced by reviewed
commit `704a429`, script SHA-256
`4b2dfd40abc83c42f2923eb80b175d391e04d7bac8158f5811cb2631425cf50a`.
Its file SHA-256 is
`cd1cfb7ead4f2b4f72bedf376370a4cfd2b5ba49d32ebc3b649de33335cb68ca`.
The second opt-in returned **144 passed, three skipped** in 3.91 seconds.
Each report retains exact source hashes for the production worker, private adapter,
recorder, context store and fixture dependencies. Both used native 0.154.0 binary
SHA-256 `9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.

The parent independently ran the same mode against integrated main. Its report at
`/tmp/native_owned_worker_parent_20261013.json` is 223,484 bytes, SHA-256
`7f6bcfe1cc13438afe61432e5e8c2cc12556feb70ed974569f60a60a9871a744`.
It passed **144 tests, three skipped** in 3.87 seconds, with the same exact recovery
and closure conditions. The parent default suite passed **1,328 tests, 54 skipped**
in 29.13 seconds before the final saved-report replay regression was added.

## The refusal changed a concrete integration decision

Fresh empty account/config, native device login, ordered Plus/config, issuer closure,
worker thread policy acknowledgement, disabled MCP inventory and turn dispatch all
succeeded in the first run. The provider POST nevertheless included one `functions`
namespace declaring `get_goal`, `create_goal` and `update_goal`. The unchanged
empty-tool fixture returned HTTP 400 and latched cancellation before any authored
SSE. No terminal, result or publication ledger was created. The private stream
retained the refusal and closure evidence; the main store held only selected input.

Tagged source describes Goals as stable and enabled by default
([feature declaration](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/features/src/lib.rs#L1589)).
The [app-server extension installation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/extensions.rs#L80)
is conditional on a state database and honors that feature. This suggests the
ordinary worker's `ephemeral:false` exposes state-backed tools absent from the
manual driver's `ephemeral:true`; that causal explanation remains a source-backed
inference. The tagged source cache SHA-256 values are respectively
`451604ebcb3e805ce22e62a87fc425b95f774bcdadc9bcc60b422075cedd7c85` and
`5e578d25d67d0692c65fb36d8d5c88bf01a0996ce7e9b82f38c5477789abda04`.

The reviewed follow-up adds only `features.goals=false` to this mode's startup
configuration and requires exact `false` in both configuration replies. Historical
manual modes retain identical startup bytes. Missing or true acknowledgements stop
before thread creation in authored-process tests. The ordinary worker packets,
empty-tool refusal, limits and routes remain unchanged. The observed follow-up
provider payload contains one empty `additional_tools` declaration and no tool call.
The first recorded goal payload still fails the default replay test's provider guard.

## What the joined worker establishes

The preparation hook checks fresh account/config, one matching device login,
ordered Plus/config, then closes the fixed issuer authority. It never starts a
thread or turn. The existing worker performs policy acknowledgement, MCP inventory,
turn dispatch and closure; the private adapter handles evidence, publication and
recovery. A probe-only before-send guard wraps the existing private client factory
without replacing its reader or recorder. The host launcher receives an empty
environment before isolated Python startup and the disconnected namespace/filter.

The worker's temporary cwd spelling is created in namespace tmpfs. No host cwd is
mounted, and no request or acknowledgement is rewritten. Actual worker packets
retain `ephemeral:false`, `threadSource`, explicit configuration and turn sandbox
policy. Native thread storage is disposable state; credentials remain Ephemeral.
The post-turn account read is explicitly absent because worker closure ends that
capability. No `auth.json` was observed in any of these runs.

The positive result text is the fixed authored sentence citing records 1 and 2.
Private item seq 38 and terminal seq 42 support recovery. The main record is a
labelled derived `$capsule/result` at seq 3, with typed private provenance; its
artifact never treats private seq 38 as a main-store sequence. Reopening both stores
preserves the exact pinned context, result, typed evidence resolver and absence of
an inquiry. Recovery creates no native process, login or turn. Reopened control is
`{owned:false, canCancel:false}`; copied names restore no live owner.

The 28,684-byte provider request contains the selected 2,579-byte prompt exactly
once. It also contains native-added developer text (21,269 bytes), permissions and
collaboration instructions (341 and 1,328 bytes), and a 117-byte environment message.
These additions are retained separately from the selected context. The request
keeps Responses Lite, an empty tools declaration and no tool-call history. This is
observed payload for an authored local provider, not proof of complete production
provider-context control or caller authentication.

Capture uses the unchanged `derived.LIMITS`; preparation is bounded to eight
seconds, the outer stop to eighteen and the supervisor to twenty. The ordinary
stored turn timeout remains 120 seconds and does not extend the outer fixture
budget. Both accepted runs used three issuer exchanges and three provider exchanges
(WebSocket 426, settings-false 200, fixed text SSE 200). No quota was increased, no
real account or upstream was contacted, and no subscription/model call occurred.
The production profile still rejects live admission.

## Reproduction and remaining scope

Default tests use local authored children or replay retained synthetic bytes. They
cover malformed terminal/control evidence, environment isolation, cleanup failures,
exact publication/recovery, both goal-control acknowledgement stages, unchanged
manual startup configuration, retained refusal and the positive raw replay. They
do not launch native without opt-in. The full joining path remains in the existing
script; there is no second RPC reader or native turn loop.
The final focused default command below passed **237 tests, 13 skipped**.

```sh
uv run pytest tests/test_native_managed_lifecycle_probe.py \
  tests/test_native_tls_connect_probe.py tests/test_native_synthetic_turn_probe.py \
  tests/test_seed_context.py
```

The reviewed first and second native commands differed only in output path and the
reviewed worker-only startup setting in their respective source commits:

```sh
NEMA_NATIVE_MANAGED_LIFECYCLE_PROBE=0 NEMA_NATIVE_MANAGED_TEXT_PROBE=0 \
  NEMA_NATIVE_OWNED_WORKER_PROBE=1 \
  NEMA_NATIVE_OWNED_WORKER_OUTPUT=/tmp/native_owned_worker_20261013_second.json \
  uv run pytest tests/test_native_managed_lifecycle_probe.py
```

The first output path was `/tmp/native_owned_worker_20261013_first.json`; the parent
used `/tmp/native_owned_worker_parent_20261013.json`. No additional native run,
historical token-matrix rerun or held-login case was needed for this discriminator.
The result establishes compatibility of the contained managed preparation and
existing owned private worker. It does not establish real-account availability,
global credential-writer closure, full hidden-provider context control, acceptable
fresh-login friction or any production execution admission. The next decision is
whether a separately reviewed product preparation contract can use these same
interfaces; this experiment does not itself enable sign-in.
