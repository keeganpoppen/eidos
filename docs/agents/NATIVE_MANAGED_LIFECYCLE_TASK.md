# Offline native-managed account lifecycle

**2026-10-13 · base `13abac7` · C6 / V1-05/12.** Root accepts this
contract for wholly local synthetic device-code login and at most one authored
native turn per case. Production admission remains closed. The preceding
[TLS experiment](../evidence/NATIVE_TLS_CONNECT_EXPERIMENT.md) supplies transport
evidence, not authorization to contact an actual issuer or provider.

## Question and permitted effects

Can a native-owned ephemeral account change during login completion, and does
closing its issuer before thread startup prevent the challenged later refresh?
These are discriminators for a proposed admission sequence, not a global account
freeze or a claim that a real subscription is usable.

Use the reviewed 0.154.0 executable, fresh private Ephemeral credential storage,
disconnected bwrap namespace and unchanged pre-exec process filter. Inherit no
ambient environment or owner state. A fixed CONNECT map has only authored local
issuer/provider endpoint factories: no DNS resolver, TCP upstream, existing
credentials, token import/export RPC, browser, real sign-in, model or paid API.
Native alone stores invalid synthetic tokens in its ephemeral credential backend.
TLS keys remain outside the native namespace and repository; only the public
fixture CA is mounted. The proxy forwards ciphertext; endpoint observations are
separate authored-fixture plaintext evidence.

Pin the builtin OpenAI provider with explicit fixture-only `openai_base_url` and
`chatgpt_base_url`; do not substitute the existing custom no-auth provider.
Builtin WebSockets remain enabled. An authored 426 can cause HTTP fallback and
must be labelled as such. `CODEX_APP_SERVER_LOGIN_ISSUER` and
`CODEX_REFRESH_TOKEN_URL_OVERRIDE` are source-specific fixture hooks, not proposed
live controls. Any other destination or route is refused, never added to make a
case pass without a separately reviewed contract change below.

The issuer supports exactly POST `/api/accounts/deviceauth/usercode`,
`/api/accounts/deviceauth/token`, and `/oauth/token`. The latter accepts the exact
form authorization-code grant or JSON refresh-token grant. Responses and tokens
are authored: invalid-signature three-segment JWT-shaped strings, `.invalid`
issuer/email, fixed fixture account/user IDs, Plus/Free plan claims, and far/near
expiry. Record generation and exact causal ordering. This does not demonstrate
token verification by a real service.

## Cases and admission predicates

1. **Near-expiry login:** hold the automatic post-login refresh. Observe matching
   `account/login/completed` (use the native protocol's actual method name) before
   the held refresh finishes; challenge whether matching `account/updated` can
   overtake it. Release a changed-plan Free generation. The candidate must reject
   Free and make zero thread/turn admissions. A config read against an earlier
   loader is not post-login readiness; do not assume every config read blocks.
2. **Closed issuer / 401:** fresh far-expiry Plus login; await matching login
   completion and account update, then `account/read(refreshToken=false)` and a
   successful normal managed `config/read`. Verify all configured controls.
   Close issuer access and every active issuer tunnel **before `thread/start`**.
   Permit at most one thread and one turn against the fixed local provider;
   authored WebSocket 426 and HTTP 401 responses challenge endogenous recovery.
   Observe an issuer denial before endpoint creation and no replacement token
   generation. Report failed terminal versus bounded timeout exactly as observed.

Explicit startup controls: static derived catalog, both OTEL exporters `none`,
`analytics.enabled=false`, plugins/apps/hooks/AgentIdentity disabled, and the established derived-catalog
tool controls. The static catalog neutralizes the model worker's immediate and
4m30 online refresh path; exporter settings suppress a separate auth-change
subscriber. Successful post-login config loading excludes cached cloud timeout
and its five-second retry path. Private exclusive stdio permits only initialize,
one device login, the ordered read checks, and the named thread/turn operations
plus observation/status necessary for recording. No additional auth mutation,
rate-limit read, token import, logout or second login is admitted.

Thread prewarm remains a possible writer, hence closure precedes thread creation.
Closing streams cannot recall a complete token response already delivered to
native. Source reachability conditions and two observed cases do not establish a
global auth-writer barrier. No quiet-time argument substitutes for these limits.

## Bounds, acceptance and ownership

Retain the existing CONNECT parser, two-active-stream, eight-connection, per-stream
and aggregate byte bounds, eight-second tunnel lifetime, stricter serial relay
140,000/20,000 bytes and four seconds, 24 accepted sockets, 18-second native
watchdog/20-second process supervisor. Retain explicit derived AppServerLimits.
Bound endpoint request bodies/responses and native events. Coordinate held
responses within those limits; propose any necessary change to root first.
Unexpected routes/producers, malformed payloads, capture gaps and exhaustion stop
the case. Report counts separately for login RPCs, turns, CONNECT attempts,
issuer requests, provider requests and fixture token generations. Join owned
workers and close sockets. No aggregate CPU/RSS/SQLite quota claim.

**Accepted amendment after the first native pair:** near-expiry login completed
the ordering challenge; the closed-issuer case stopped on an unexpected
`/backend-api/codex/analytics-events/events` request during thread startup.
Preserve that failed attempt. Root reviewed the tagged analytics client: explicit
`analytics.enabled=false` omits its queue and prevents this producer. Pin and
verify it at both config reads before repeating the pair. Do not allow the
analytics route. Record attempted outbound RPCs separately from acknowledged
thread/turn starts; an aborted request is not a confirmed native turn.

**Accepted second amendment after analytics-off refusal:** the tagged binary
unconditionally installs its Git attribution context contributor. It reads
`GET /backend-api/wham/settings/user`, resolves managed auth and can perform its
own 401 recovery. The returned field controls developer-role attribution text;
the reviewed extension does not register tools or grant capabilities. There is no
reviewed disable control. Treat this as supported native-added governance context,
not proof that the selected packet is the complete native context.

Root reviewed the extension, resolver, renderer and backend response shape.
Authorize a further offline repeat admitting exactly one GET to that exact path,
with empty body, exact fixture host and generation-A bearer, returning only
`{"commit_attribution_enabled":false}`. Preserve the analytics-off refusal as
evidence of why the initial route model was incomplete. This is a reviewed new
fixture route on the existing local destination; no new upstream or credential
access. All current quotas remain unchanged; duplicate settings requests or other
routes stop the case. Settings-401 recovery itself remains untested by this case.

Default tests make no native call. Cover exact grants/invalid token fixtures,
phase-specific RPC refusal, notification/login correlation, plan/config rejection,
and source-matched capture limits. Independent socket tests challenge active
issuer closure, parsed-but-not-open races, immutable destination mapping, shared
quotas and continued provider access. The integrator independently reproduces the
opt-in cases after reviewing source and raw evidence.

Owner native_frontier: `/tmp/nema-native-managed-lifecycle`, branch
`codex/native-managed-lifecycle`; only new `scripts/probe_native_managed_lifecycle.py`,
`tests/test_native_managed_lifecycle_probe.py`,
`docs/evidence/NATIVE_MANAGED_LIFECYCLE_EXPERIMENT.md` and
`docs/evidence/NATIVE_MANAGED_LIFECYCLE_0_154_0.json`.
Root owns this packet, the existing shared CONNECT helper, integration and final
commit/push. Accepted shared seams preserve prior defaults: fixed destination
callbacks and irreversible authority closure; extra named fixture certificates
and explicit TLS endpoint/certificate injection; exact synthetic Authorization
values optionally accepted by the bounded HTTP parser (default remains refusal).
Provider dispatch must separately require its expected header, and request
compression is explicitly disabled. No existing no-auth client is relaxed.
history_ui owns independent
`tests/test_native_connect_phase_closure.py` in
`/tmp/nema-managed-auth-acceptance`, plus
`tests/test_native_fixture_auth_headers.py`. gateway_review owns the source-review appendix
in its existing review worktree. No production profile, runtime or UI changes.

Return frozen source, synthetic raw evidence, exact checks and failures. Revise
the candidate when a case falsifies it; do not widen effects to force success.
