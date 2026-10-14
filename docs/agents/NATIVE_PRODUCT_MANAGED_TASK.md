# Exact product preparation against local native fixtures

**2026-10-13 · accepted implementation/evaluation contract · base `8ed2f0a`.**
This extends the [managed attempt integration](MANAGED_ATTEMPT_TASK.md) to test a
remaining compatibility question: does pinned native0.154.0 actually acknowledge
its exact new production config and traverse production managed preparation,
receipt validation, private publication and reopen? Authored browser success and
the prior [owned native join](../evidence/NATIVE_OWNED_WORKER_EXPERIMENT.md) do not
answer this because they used different native startup/preparation code.

Code and offline default tests are authorized. A native invocation is admitted
only after root and independent reviewer inspect the concrete diff, script hash,
effects and defaults. Preserve the first native outcome separately; a failure is
not permission to widen endpoints, budgets, tools or silently repeat execution.
No real account, owner auth/config, DNS, provider or model call is authorized.

## Ownership and narrow extension

history_ui owns a new explicit `managedProductText` mode in
`scripts/probe_native_managed_lifecycle.py`, its focused tests in
`tests/test_native_managed_lifecycle_probe.py`, and sanitized result evidence.
No production-module or shared TLS-helper edits; existing modes retain behavior.
Root owns this contract, integration seams, final review and commit. gateway_review
reviews the concrete code independently before execution. Copied root integration
files in the agent worktree are test seams, not part of its delivery.

Use `PrivateInvestigationWorker(managed_profile=ManagedExecutionProfile(...))`
with actual production config/catalog bytes, ManagedLaunch preparation and receipt
validation. A script-local OfflineManagedRuntime labels transport authored-local
and execution synthetic. Never construct ContainedRuntime: it can resolve real
hosts during startup. Retain the existing private client, recorder and worker
thread/turn packets. Hash/read-only mount exact config/catalog at their production
paths; this mode omits the legacy fixture config rewrite and URL overrides.

The explicit exception to old fixture authority labels is **auth.openai.com:443**
and **chatgpt.com:443**, mapped solely to two already constructed local socketpair/
TLS endpoint factories, with matching disposable certificate SANs. No resolver,
remote TCP dial or fallback route exists. The local CA remains fixture-only.
Unmapped authorities and historical `.fixture.invalid` labels are refused in this
mode. Production config/replies must not be rewritten to satisfy validation.

The fixture's provider HTTP handler refuses requests until runtime.activate_provider
closes issuer paths. Its historical CONNECT broker can open the local provider TLS
endpoint earlier; this fixture does not implement the production broker's phase
enforcement. Positive assessment requires exactly three issuer connections at the
closure cut followed by exactly three provider connections, so early provider
connection is a failed observation. Production CONNECT phase enforcement is tested
separately. Runtime.close joins owned local relay/broker/TLS/client resources. Retain
disposable state only until the probe inspects auth-file absence/hashes; record
`stateRetainedForFixtureInspection=true`. The outer temporary directory then
removes it. Do not claim ephemeral storage from checking after deletion, or remove
main/private trace storage before proof/reopen inspection.

## Unchanged effects and bounds

Keep existing HTTP routes, authored invalid tokens, settings body, empty tool
refusal, WebSocket426 and2769-byte text SSE. No new cloud/settings/tool producer
is implicitly admitted. Expected HTTP:three issuer plus three provider exchanges.
Expected nine RPCs:initialize, account/read, config/read, account/login/start,
account/read, config/read, thread/start, MCP list, turn/start. Require one matching
login completion then account update before ordered account/config checks.

Existing fixture limits remain:8 processed CONNECTs/2 active; shared received
ciphertext2MiB plus proof byte; directional262144/524288 bytes;8192-byte buffers;
relay140000/20000 bytes and4s; HTTP8/read128KiB/accepted issuer16KiB/response8192;
consumed events100; existing derived capture4MiB. Fixture policy preparation8s,
turn120s declaration, hard lifetime18s; effective turn is bounded by remaining18s.
Outer18s/guard20s unchanged. Report declared/effective bounds separately. Product
180s/305s defaults do not become probe time limits.

## Acceptance and refusal evidence

Both raw config replies must pass unchanged production validation:all27 disabled
features false, skip_host_skill_discovery true, all three OTEL exporter fields
none, plus remaining fixed settings. Preserve unknown raw fields and provider
payload. Immediately before thread, actual receipt validation binds exact source,
context/prompt hashes, manifest and correlated readiness. One exact successful
managedClose must support one synthetic public result and matching private proof
on reopen, with no challenge or live owner restored.

Default counterexamples cover missing/true disabled features, missing/null OTEL
trace exporter, ordered configuration drift, source/hash/readiness mismatch and
missing/failed closure. A no-live-route case forbids DNS/remote dial/production
runtime construction while exercising local TLS mapping. Offline tests do not
claim actual native acknowledgment.

Pre-execution checks include managed module, managed worker/control and lifecycle
probe defaults, plus diff/compile review. Proposed invocation after concrete
review:

```
NEMA_NATIVE_PRODUCT_MANAGED_PROBE=1 NEMA_NATIVE_PRODUCT_MANAGED_OUTPUT=/tmp/native_product_managed_20261013.json uv run pytest -q tests/test_native_managed_lifecycle_probe.py -k product_managed
```

Pinned binary SHA256:
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
Prior probe SHA256:
`4b2dfd40abc83c42f2923eb80b175d391e04d7bac8158f5811cb2631425cf50a`.
This establishes native config/protocol compatibility on authored transport, not
real service availability, account suitability, model answer quality or production
ContainedRuntime connectivity. Those remain separate questions.

## Concrete pre-execution review

Root and gateway_review accepted frozen probe commit `41ad934` for one parent
contained invocation. Script SHA256:
`db3a72b110e2f3e3cd67e0b9d69c85324103431dafb1e6c34e6dc0636461fd53`.
Test SHA256:
`1044858c436985b9eee2b7a2d3bd8e50719a6cec795e95c29efbda1c3ee74acb`.
Parent264 defaults/5 explicit native skips passed in5.96s; independent reviewer
reproduced264/5 in6.04s. Actual production resources, preparation and private
worker are retained; no production runtime construction, resolver or remote dial
fallback exists in the fixture. Authority-label mapping, HTTP-vs-CONNECT phase
scope, exact nine RPCs, fixed routes/SSE/empty-tool check and unchanged budgets
were reviewed. This accepts only the above local contained experiment, not real
account access or production service traffic.

## First observed outcome

The one admitted parent run stopped at initial config validation, before any
login, thread, turn, CONNECT or HTTP request. Native0.154.0 reports the resolved
`chatgpt_base_url` as `https://chatgpt.com/backend-api/`; the validator had required
absence. All27 feature disables and all three OTEL exporter values were correctly
acknowledged. There were13 private records and the unchanged two selected public
inputs, no publication, gap, auth file, cleanup failure or outer timeout; all
workers joined. Twenty selected default checks passed and the native case failed.

Raw report `/tmp/native_product_managed_20261013_first.json`,65,634 bytes, SHA256
`e2e68f68379761cf057dd9e0b31db9c1ef711b6fcd57d86faae442e785d6e0f0`.
Keep this outcome separate. Root accepted a source-supported correction requiring
the exact canonical effective URL (missing/null and alternative spellings refuse)
without changing startup config, destinations, routes, tools or limits. Cached
tagged core/src/config/mod.rs:4281–4283 supplies that exact default; source SHA256
`4967b9f719ac886d5c6dd923f4d07263fe4eef2a7070078c5a291f57973c76a1`.
The requested experimental_request_user_input setting appears in origins but is
omitted from effective tools; core:2651–2656 consumes it. It is requested and
source-supported, not an observed effective acknowledgment. The ordinary refusal
of native interactive requests and empty provider tool guard remain in force.

Old authored managed fixtures omitted the resolved URL. Preserve their historical
reports and generate fresh disposable fixtures for the stricter interpreter; do
not rewrite historical receipts. No successful actual-native product receipt
existed before this correction. Another native invocation still requires reviewed
changed bytes and passing defaults; it is not automatically admitted by failure.

## Reviewed second invocation

Root and gateway_review accepted the concrete `d5307b3` correction and `2de82dd`
authored-fixture/evidence changes. Managed module SHA256:
`604b1d660650782a547bf78176f27bca5f3edc72fc2ed2b059a554614874ca68`.
The probe script remains byte-identical to the first run. The reviewer reproduced
97 managed defaults, validated the original initial reply without mutation and
checked that requested startup bytes still match the first report. Parent125
managed/control/worker checks pass. This admits one separately recorded parent
run to `/tmp/native_product_managed_20261013_second.json` with the unchanged local
transport, routes, tools and bounds above. It does not admit real service access.

Review also identified a default-test race: the local TLS helper sent an empty
response after its peer closed. That helper must omit the empty send while still
reporting genuine exchange errors; it does not change native probe/runtime bytes.


## Second observed outcome

The admitted second parent run passed all22 selected checks (21 defaults and one
actual-native case). Test-only empty-send correction `60c3528` was integrated;
probe/runtime bytes and effects were unchanged. Raw report242,094 bytes, SHA256
`5175384248ebb905c31949c07f452134d31f8b39584b8592c89be1b7a533cc5d`.
Nine allowed RPCs, one login/thread/turn, three issuer then three provider CONNECT/
HTTP exchanges; no assessment problem, fixture violation, capture gap, outer
expiry, auth file or cleanup error. Private output39 and terminal43 precede exact
successful managedClose44. One public projection joins the two selected inputs;
saved/reopened artifact matches and ownership remains false. All workers joined.
The result remains synthetic and real auth/model/upstream counts remain zero.
See the [evidence report](../evidence/NATIVE_PRODUCT_MANAGED_EXPERIMENT.md).
