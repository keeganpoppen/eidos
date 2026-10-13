# Offline native-managed account lifecycle

This is an authored local authentication experiment with the reviewed Codex
0.154.0 executable. It is **not subscription execution or live admission**.
Native owns an ephemeral store containing invalid synthetic tokens. No existing
credentials, owner state, real issuer, upstream provider or real model is used.
The [accepted packet](../agents/NATIVE_MANAGED_LIFECYCLE_TASK.md) defines the
boundary; [source analysis](NATIVE_ADMISSION_FRONTIER.md) explains the conditional
candidate and its remaining buffered-response limitation.

The user-visible purpose is a useful bounded subscription specialist whose native
account and admitted context remain inspectable. This experiment tests part of
its startup sequence, without opening the production account gate.

## What the first attempts established

A near-expiry synthetic Plus login produced `account/login/completed` before an
automatic refresh completed. The issuer held that refresh for a controller
observation interval, then authored generation B with a Free plan. Native
subsequently reported `account/updated` and an ordered non-refreshing account read
with Free. The fixture rejected that candidate and created no thread or turn.
Login completion alone is therefore insufficient evidence for the plan check.

The first closed-issuer attempt found an omitted producer: a POST to
`/backend-api/codex/analytics-events/events` during thread startup. Its authored
fixture-only payload described `codex_thread_initialized`. The fixed endpoint
refused it and stopped native. A `turn/start` attempt was recorded but no turn
start reply was recovered; it is not a confirmed started turn. Explicitly
setting `[analytics] enabled=false` is necessary independently of both OTEL
exporters being `none`. Root reviewed and amended that startup control before a
second pair was run.

With analytics disabled, the next attempt reached a builtin-provider WebSocket
handshake. The fixture authored 426, the supported fallback discriminator. Native
then made a GET to `/backend-api/wham/settings/user`; the fixture refused that
unapproved route and stopped. This attempt did **not** reach the planned provider
401 challenge. Neither refusal is evidence that issuer closure prevents a later
refresh.

Git attribution explains the settings request. The tagged app-server installs
this context contributor unconditionally. It resolves workspace attribution
policy through managed auth and adds developer-role world-state text for commit
and pull-request attribution when enabled. It does not register tools or grant
execution authority in this code. A fresh disabled policy contributes no text.
The policy resolver nevertheless calls `auth().await` and can invoke unauthorized
recovery after a settings 401. This is an additional native context producer and
possible auth writer, not evidence that the selected packet was the entire
native prompt.

## Final controlled result

Root explicitly amended the packet to admit exactly one empty GET to that fixed
settings path with generation A's bearer. Its only authored response is
`{"commit_attribution_enabled":false}`. No other route or quota changed. The next
development run reached the intended 401 challenge but continued until the
consumer timeout after repeated CONNECT-cap refusals. That exposed a fixture
stop-path defect: the shared broker enforced its cap, but the driver had not
latched those refusals. The final implementation latches the first over-cap
refusal, records `fixtureResourceStop`, and closes native immediately.

The final closed-issuer case observed this exact processed CONNECT sequence:
three successful issuer connections for device login, a provider WebSocket GET
answered 426, the settings GET answered 200, two Responses Lite POSTs answered
401, then an issuer CONNECT answered **403 `destination-closed`**. The denied
issuer request created no endpoint. Generation A was the only token response
authored in that case. Both effective config reads acknowledged the controls,
ordered account read reported Plus, and native acknowledged the read-only,
never-approval thread with empty environments before the one acknowledged turn.

A ninth exchange was refused by the unchanged eight-connection cap. The driver
recorded `connect-limit-exhausted` and `AppServerClosed`, joined every owned
worker and retained no active tunnel. There was **no recovered native terminal
turn or post-abort account read**. The assessor accepts this exact bounded
negative evidence, while still rejecting generic driver failures, unexpected
producers, capture gaps, copied limit sources and missing destination denial.
It does not transform the deliberate stop into a native failed/completed turn.

The [raw artifact](NATIVE_MANAGED_LIFECYCLE_0_154_0.json) preserves all three
development iterations and the final pair, including original assessments. An
assessor placement bug in the second development iteration incorrectly applied
Plus/thread checks to the successful near-expiry case; its raw data was retained
and the pure interpretation fixed before final reproduction.

| Closed-issuer iteration | CONNECT attempts / processed | Issuer / provider HTTP | Turn attempts / outbound / acknowledged | Observed end |
| --- | --- | --- | --- | --- |
| Analytics unpinned | 4 / 4 | 3 / 1 | 1 / 1 / 0 | Unknown analytics route stopped native |
| Analytics disabled | 5 / 5 | 3 / 2 | 1 / 1 / 1 | Unknown settings route stopped native |
| Settings admitted, cap stop not latched | 13 / 8 | 3 / 4 | 1 / 1 / 1 | Consumer timeout; five cap refusals; actual later Plus read |
| Final, cap stop latched | 9 / 8 | 3 / 4 | 1 / 1 / 1 | One cap refusal; native closed; terminal unknown |

Every corresponding near-expiry case used four issuer HTTP/CONNECT requests,
authored A then B, observed Free and admitted zero threads/turns. Across the four
pairs there were eight native login RPCs and four recorded turn-start attempts,
three acknowledged. Real auth, upstream and model calls remained zero. Final
pair counts are two login RPCs, one recorded/acknowledged turn, seven issuer HTTP
requests and four provider HTTP requests. These are actual native synthetic-auth
RPCs, not a claim of no native authentication or model-protocol RPC activity.

## Trust and observation limits

The trust boundary is the reviewed native executable and explicit configuration,
exclusive private stdio client, outer disconnected namespace, reviewed pre-exec
process filter, fixed local TLS destinations and bounded fixture implementation.
The provider requires the authored bearer only to discriminate fixture protocol
states. A bearer visible to native, a relay PID, an app-server item or the
post-effect assessor is not caller authentication against a compromised native
process.

`account/updated` contains no login identifier. Correlation uses one fresh process,
one exclusive login, the matching `account/login/completed.loginId`, subsequent
raw notification order and expected account fields. Controller timeline times
are local observations, not a universal native clock. `fixtureHttpResponse`
records response construction before the TLS worker sends it; `nativeEvent`
records client consumption. The held-response check establishes no observed
account update during this bounded hold, not global auth-writer quiescence.

Destination closure shuts active tunnels and prevents new mapped endpoint opens;
it cannot recall a complete response already delivered or buffered inside native.
The client checks a visible abort latch before later RPCs and a watcher closes
native on the first fixture violation. That is not an atomic barrier against an
RPC already passing its preflight when another thread discovers the violation.

Capture acceptance requires no reported gap or diagnostic error and exact
source-matched `$transport/limits`. It does not prove that native had no unreceived
tail when bounded close cancelled the process. Raw app-server records, selected
context, requested and effective config, fixed provider/issuer payloads and native
outcomes remain separately attributable. The file observation checks only absence
of `/state/codex/auth.json`; it is not a proof that no other state was written.

## Source provenance

All linked source is public tag `rust-v0.154.0`; local research copies are in
`/tmp/nema-codex-0.154-source`. Source findings are distinct from the observed
synthetic runs.

- [Device flow](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/device_code_auth.rs#L162)
  and [code exchange](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/server.rs#L809)
  establish the three exact issuer routes and grant shapes.
- [Login completion ordering](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L907)
  sends completion before post-login cloud loading and account update. See the
  [frontier source appendix](NATIVE_ADMISSION_FRONTIER.md) for normal config-read
  error propagation, cloud timers, static catalog and OTEL conditions.
- [Analytics construction](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/analytics/src/client.rs#L239)
  omits its queue only when explicitly disabled; its sender calls managed auth.
  SHA-256 `2d991d3399163c791ab709dbd5985adb9e153e94fb5fa0a8c9573e0d225717e7`.
  [App-server forwarding](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/analytics_utils.rs#L7)
  SHA-256 `1467215f959bb4a5d8b8b9676679ca272668b61c85ac040ab8b390f3cf12d858`.
- [Unconditional Git attribution installation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/extensions.rs#L94)
  SHA-256 `5e578d25d67d0692c65fb36d8d5c88bf01a0996ce7e9b82f38c5477789abda04`;
  [policy resolver](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/git-attribution/src/policy.rs#L53)
  SHA-256 `a603f1f07160322ec3adb96733f2de036be0b00c8d97f21bbc998a71aa33e598`.
  [Context contributor](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/git-attribution/src/lib.rs#L32)
  SHA-256 `15c0832b529b635ade611cff651ec819561e1dab7bc0ad41d6c7f3dd9414c7fa`;
  [world-state renderer](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/git-attribution/src/world_state.rs#L34)
  supplies native-added attribution instructions.

## Bounds and reproduction

The binary is hash-checked before any launch:
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
Fresh invalid JWT-shaped strings use only `.invalid` identities and deliberately
invalid signatures. Issuer and refresh URL environment overrides are test hooks,
not recommendations for live account configuration. Fixture TLS private keys
remain outside native and the repository. Only the public CA enters native.

The existing disconnected serial relay, process filter and TLS broker are reused.
Limits remain eight processed CONNECTs, two active streams, two-MiB shared receipt
budget plus its proof byte, 256/512-KiB directional limits, eight-KiB buffers,
eight-second tunnels and four-second idle timeout. The stricter namespace relay
allows 140,000 outgoing and 20,000 incoming bytes per connection, four seconds,
24 accepted sockets and an 18-second watchdog; the supervisor uses 20 seconds.
The native recorder uses the exact derived-catalog `AppServerLimits` preserved in
raw evidence. There is no aggregate CPU, RSS or SQLite quota claim.

The shared HTTP parser receives at most 128 KiB of body; issuer dispatch accepts
at most 16 KiB. Those are different limits. Responses are at most eight KiB, HTTP
requests at most eight per case, consumed native events at most 100, and held
refresh at most 1.5 seconds. Unknown routes, malformed input and quota exhaustion
latch failure. The default suite exercises these paths with synthetic sockets and
never launches native.

```sh
uv run pytest -o addopts='' tests/test_native_managed_lifecycle_probe.py
NEMA_NATIVE_MANAGED_LIFECYCLE_PROBE=1 \
  NEMA_NATIVE_MANAGED_LIFECYCLE_OUTPUT=/tmp/native-managed-lifecycle.json \
  uv run pytest -o addopts='' tests/test_native_managed_lifecycle_probe.py
```

Final controlled native reproduction: **59 passed in 1.26 seconds** before the
additional pure artifact-mutation tests were added. Final default probe checks:
**78 passed, 2 opt-in skips**. Executed source SHA-256 is
`203f7232d5fbc6fbdff22837266820cd3fee2e3aaa5d49da7fb8405b08a9313a`;
artifact SHA-256 is
`420a0d9a6e43bc98471a383d61fe2f3d0d36ce1b5072eb7f752bc0588fada7c4`.
The artifact also records helper hashes and the native-reported 0.154.0 user
agent. Default artifact checks re-evaluate the stored observations without
another native launch.

Independent review found two weaknesses in the post-effect assessor: a removed
turn acknowledgement and an issuer-denial record moved ahead of provider 401
still passed. The final assessor now correlates raw request/reply IDs with the
selected input and acknowledged thread/turn, and requires the fixed serial
HTTP/CONNECT challenge sequence. Six new mutation checks pass against the
unchanged captured artifact. Only this pure assessor changed after native
reproduction; final script SHA-256 is
`f52508f3ed38ecb1621e215df9d334859ce221f37fc7810f0389713eb6d3fbe6`.
The artifact's executed-source hash remains unchanged to preserve provenance.

## Parent integration reproduction

The integrator independently ran the final `f52508f3…d3fbe6` source on main's
combined helpers. The report at `/tmp/native_managed_lifecycle_parent_20261013.json`
has SHA-256 `6fe042ffd06e6f775ece39f69e6a6a70e22b786e06eb1ed42b0532e3047969b2`.
Both cases reproduce the final development outcomes and satisfy the current
opt-in assertions when re-evaluated. An independent reviewer checked raw RPC
correlation, ordering, counts, capture and all six source hashes. The original
pytest summary was unavailable after context rollover; no test count is inferred.
This separate invocation used two login RPCs, one acknowledged turn, seven issuer
and four provider HTTP requests, and thirteen CONNECT attempts. No real auth,
upstream or model calls. All workers joined and active tunnels returned to zero.

The combined default suite passed **1,161 tests, with 52 explicit native skips**.
The integrator also repeated the earlier TLS opt-in against the shared helper
changes: **58 passed**, three turns, six CONNECTs and three fixture HTTP requests,
with zero real upstream calls. These results do not widen the claim beyond the
observed synthetic lifecycle and unchanged production admission boundary.

## Resulting decision and next discriminator

Keep production admission closed pending a separate account/transport decision.
Retain the ordered login/update/account/config candidate, explicitly disable
analytics, and acknowledge Git attribution as native-added governance context.
The observed issuer denial supports closing issuer destinations before thread
startup for this challenged recovery path. It does not establish a global writer
barrier, revoke delivered tokens, cover settings-401 recovery, or prove a real
Plus/Pro account can complete useful work under this routing policy.

The next useful offline discriminator is one successful managed synthetic turn
under these same controls: keep the fixed false-attribution response and issuer
closed, replace only the provider's authored 401 with the already reviewed fixed
text SSE, and require correlated terminal/result recovery. That would distinguish
an operational managed native path from a boundary that only succeeds by stopping
work. It needs its own root-frozen contract; this contribution does not execute it
or authorize any real sign-in/provider call.
