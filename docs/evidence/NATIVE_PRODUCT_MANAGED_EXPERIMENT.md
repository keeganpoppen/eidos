# Exact product managed preparation against local native fixtures

**2026-10-13 · contained synthetic native evidence · one product-managed turn observed.**
The [accepted packet](../agents/NATIVE_PRODUCT_MANAGED_TASK.md) tests the actual
production config/catalog, preparation, private receipt and worker against fixed
local TLS fixtures. It does not admit real DNS, accounts, upstream or model work.
The first parent run refused the native effective URL. After a separately reviewed
exact-value validator correction, the second parent run passed through one native
login, thread, turn, private publication and evidence-only reopen.

| Observation | First run | Reviewed second run |
| --- | --- | --- |
| Initial / ordered config | Initial captured, then refused / absent | Both pass exact product validation |
| Login / thread / turn RPCs | 0 / 0 / 0 | 1 / 1 / 1 |
| CONNECTs / issuer HTTP / provider HTTP | 0 / 0 / 0 | 6 / 3 / 3 |
| Main / private records | 2 / 13 | 3 / 44 |
| Native terminal / public result | Absent / absent | Completed / synthetic publication at seq 3 |
| Capture gap / cleanup failure / outer timeout | None | None |
| All workers joined / auth file at pre-removal inspection | Yes / absent | Yes / absent |
| Reopened artifact / live ownership | No artifact / absent | Exact / absent |

## First outcome, preserved unchanged

The parent ran the reviewed `managedProductText` mode at probe commit `41ad934`:

```
NEMA_NATIVE_PRODUCT_MANAGED_PROBE=1 NEMA_NATIVE_PRODUCT_MANAGED_OUTPUT=/tmp/native_product_managed_20261013_first.json uv run pytest -q tests/test_native_managed_lifecycle_probe.py -k product_managed
```

Twenty selected default checks passed; the single native check failed. The
[raw report](NATIVE_PRODUCT_MANAGED_0_154_0_FIRST_FAILURE.json) remains exactly
65,634 bytes, SHA-256
`e2e68f68379761cf057dd9e0b31db9c1ef711b6fcd57d86faae442e785d6e0f0`.
The probe SHA-256 was
`db3a72b110e2f3e3cd67e0b9d69c85324103431dafb1e6c34e6dc0636461fd53`;
the then-current managed module SHA-256 was
`326977f9c58ff44f1dfe9e5c3ff4d5792e070f70a3ee318aae2af8206c436422`.
Native 0.154.0 binary SHA-256 was
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
All other exact source and resource hashes remain in the report.

Only initialize, account/read and config/read were sent. The initial account was
empty. No login, thread, turn, CONNECT, local HTTP exchange, result or publication
followed. The private store retained 13 records; the main store retained only two
selected synthetic records. Capture had no gap/error, cleanup had no failure,
all workers joined, no auth file was present before disposable-state removal,
and the outer deadline did not expire. This is refusal evidence, not a passed
end-to-end managed attempt.

## The precise compatibility correction

The actual configuration reply acknowledged all 27 requested disabled features
as false, `skip_host_skill_discovery` as true, and `otel.exporter`,
`otel.trace_exporter` and `otel.metrics_exporter` as `none`. It also materialized
`chatgpt_base_url="https://chatgpt.com/backend-api/"`; the original validator
incorrectly rejected every nonnull value for that field.

Pinned official source selects exactly this URL in
[core/config/mod.rs:4281](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/config/mod.rs#L4281).
The cached source SHA-256 is
`4967b9f719ac886d5c6dd923f4d07263fe4eef2a7070078c5a291f57973c76a1`.
The [configuration read service](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/config_manager_service.rs#L133)
serializes effective configuration through its API type; cached SHA-256
`239eac692e3d1839105345708f61f8dc4b7056fcd41c2de1ee25f568210921dc`.

The correction requires equality with that exact canonical effective URL in both
readiness checks. Missing/null values, alternate hosts, ports, schemes, paths,
case, queries, fragments and credential-bearing URLs remain refused. Startup
config bytes, catalog, every other override restriction, routes, tools and limits
are unchanged. Authored test replies now include the observed effective default;
real replies and historical receipts are never rewritten. Earlier disposable
authored receipts omitting the default no longer pass the stricter managed check.

The raw response reports an origin for the requested
`tools.experimental_request_user_input.enabled=false`, but its effective `tools`
object omits that field. Its effective value is therefore **not acknowledged by
this response**. The [tagged core resolver](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/config/mod.rs#L2651)
consumes the setting; the tagged schema also defines it (schema SHA-256
`2e1fcf1cbb20f255c3baca2e174b4a3c954cef577a130587b8935e2d12c8ade6`).
This source support does not fabricate a runtime acknowledgement. The independent
empty-tool provider check and refusal of native interactive requests remain in
place; this first run did not reach a provider request.

## Reviewed second outcome

After independent source/diff review, the parent invoked:

```
NEMA_NATIVE_PRODUCT_MANAGED_PROBE=1 NEMA_NATIVE_PRODUCT_MANAGED_OUTPUT=/tmp/native_product_managed_20261013_second.json uv run pytest -q tests/test_native_managed_lifecycle_probe.py -k product_managed
```

All **22 selected checks passed**: 21 default checks and one contained native case.
The [positive report](NATIVE_PRODUCT_MANAGED_0_154_0.json) remains exactly 242,094
bytes, SHA-256
`5175384248ebb905c31949c07f452134d31f8b39584b8592c89be1b7a533cc5d`.
The probe script and startup config/catalog bytes were unchanged. The corrected
managed module from `d5307b3` has SHA-256
`604b1d660650782a547bf78176f27bca5f3edc72fc2ed2b059a554614874ca68`.
The raw report records worker SHA-256
`f450d8b6887046200a5ed122c24ae269fbfbe6e7723386f5b24ed1456edfeb79`
and private adapter SHA-256
`97bdd42d43ece8e4bdcd6c4cfbb459cbe89090e49858fe6d80846174176de784`,
plus every fixture dependency and runtime asset hash. Native binary identity is
the same pinned 0.154.0 hash as the first run.

The actual worker sent the nine expected RPCs: initialize, initial account/config,
one device login, ordered account/config, thread/start, MCP inventory, turn/start.
Matching login completion at private seq 15 preceded account update at seq 16.
Both configuration responses acknowledge all 27 disabled features, all three
OTEL exporter settings and the canonical ChatGPT URL. The requested user-input
tool setting remains absent from both effective tools objects; that observation
has not been upgraded into an acknowledgement.

Exact production receipt validation admitted synthetic readiness at private
seq 22, before thread/start at seq 23 and turn/start at seq 30. The final item at
seq 39 and completed terminal at seq 43 were followed by one source/identity-bound
successful `$native/managedClose` at seq 44. The main store contains the two exact
selected records plus one labelled derived publication at seq 3. Its artifact
cites records 1 and 2, remains `synthetic`, and carries typed private provenance;
private seq 39 is never presented as a main-store evidence sequence. Reopened
stores recover the identical artifact and private proof with no live ownership,
challenge, child, login or resend.

The fixed local endpoints observed exactly three issuer requests, one authored
WebSocket 426, one fixed settings response and one provider POST. The POST was
28,683 bytes, including native-added instructions/context as well as the exact
pinned prompt; its additional-tools declaration was empty. Its response was the
unchanged 2,769-byte authored SSE. The retained 226 stderr bytes report the expected
WebSocket 426 fallback. No tool call, new producer route, capture failure, resource
refusal or cleanup failure was observed. This payload is evidence of that local
request, not complete knowledge or control of hidden provider context.

## Bounds and remaining scope

Both runs retain the reviewed fixture budgets: eight CONNECTs, two active tunnels,
2 MiB shared ciphertext plus one proof byte, directional 262,144/524,288-byte caps,
8,192-byte pending buffers, and relay 140,000/20,000-byte directional caps with
four-second relay handling. HTTP remains capped at eight requests, 128 KiB body
read, 16 KiB accepted issuer bodies and 8,192 response bytes; processed native
events remain capped at 100. Private capture keeps its existing 4 MiB received
bound and separate frame/event limits. Preparation is eight seconds; the stored
turn declaration remains 120 seconds but its effective time is bounded by the
remaining 18-second launch lifetime. The outer watchdog remains 18 seconds and
guard supervisor 20 seconds. Product 180/305-second defaults were not substituted.

The transport is explicitly `authored-local`/synthetic. Production hostname labels
map only to preconstructed local socketpair/TLS factories; no production resolver,
real dial or fallback exists. This case does not test production ContainedRuntime
connectivity, real account availability or suitability, model answer quality,
native Desktop ownership, real sign-in friction, a global credential-writer barrier,
CPU/RSS/disk containment or exactly-once external effects. The fixture enforces
pre-cut provider refusal at HTTP handling; the observed three-before/three-after
CONNECT sequence is not a broader claim about all potential producer schedules.
Native thread storage remains `ephemeral:false` in disposable state, distinct from
Ephemeral credentials. Post-turn account state is unobserved because worker closure
ends that live capability. Unknown native fields remain in exact private evidence.

Default replay checks preserve both outcomes without child creation. They verify
that corrected initial validation cannot fabricate the first report's missing
login/turn and that the positive report still yields the exact readiness receipt,
successful close, translated publication and private proof. Further native or live
execution requires its own concrete reviewed purpose; these reports do not grant
fresh authority.
