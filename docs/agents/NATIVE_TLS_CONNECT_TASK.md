# Offline native HTTPS through opaque CONNECT

**2026-10-13 · base `59bec0d` over `555a317` plus the root-owned config/limits
runner extension · C6 / V1-05/12.** Owner: native_frontier, worktree
`/tmp/nema-native-tls-connect`, branch `codex/native-tls-connect`. Root owns shared
interfaces, independent review and integration. **Root accepted this contract and
the explicit fixture_factory/expected_base_url runner seam.** No managed
authentication or production admission is included.

Integrated contributions `96de975` and `9c0274a`; parent reproduction and limits are
recorded in the [evidence report](../evidence/NATIVE_TLS_CONNECT_EXPERIMENT.md).

## Question and permitted effects

Does reviewed native 0.154.0 honor a namespace-local `HTTPS_PROXY` CONNECT relay
with normal certificate validation? Reuse the disconnected namespace, pre-exec
process filter, fresh no-auth state, derived Astra startup catalog and bounded
recorder. The provider is `https://provider.fixture.invalid/v1`, requires no auth,
has WebSockets disabled and request/stream retry settings zero, and receives only
authored fixture responses. Those settings did not suppress all observed native
retries; the fixture bounds every attempt independently.
The Unix-socket CONNECT broker has an exact host:port-to-local-socket mapping,
no DNS resolver and no real forward route. Its traffic remains encrypted; a
separate local TLS endpoint owns the disposable certificate/key and records
synthetic plaintext. Private keys remain outside the repo and native namespace.

Explicit native opt-in cases: valid certificate completes one text-only authored
turn; a trusted but wrong-host certificate delivers zero plaintext HTTP requests;
a valid endpoint returns a redirect to a disallowed target, which never receives
traffic. Record native refusal to follow a redirect as an observed outcome, not a
proxy denial. Author no tool/code/shell/interaction calls. Count native turns,
CONNECT attempts and actual fixture HTTP requests separately. Zero sign-in,
credentials, existing owner state, upstream requests or real model calls.

## Bounds and rejection checks

CONNECT header content: 8 KiB plus the four-byte CRLFCRLF delimiter and at most
one refusal proof byte / 2 seconds. At most two concurrent tunnels and eight
connections per case. Fixed buffers; per-tunnel outbound 256 KiB / inbound 512 KiB;
aggregate tunnel bytes 2 MiB; idle 4 seconds / absolute lifetime 8 seconds.
Retain native watchdog 18 seconds/helper 20 seconds and explicit AppServerLimits:
stdout frame 1 MiB, stderr 64 KiB, aggregate receipt 4 MiB, retained events 128/2 MiB,
stderr tail 64 KiB/100 lines. Preserve existing HTTP fixture body 128 KiB,
response 16 KiB and completion consumer 100 events/8 seconds. No aggregate CPU/RSS
or database quota claim. Shutdown closes active sockets and joins owned workers.

Default tests launch no native process. Test fragmented/oversized/truncated
headers, unknown destinations, scheme/userinfo/IP/port/suffix/trailing-dot/escape
ambiguities, mismatched Host, non-CONNECT methods, unsupported headers, declared
body and already-coalesced post-header bytes,
pre-admission requests, exhausted budgets, concurrent clients and shutdown.
Reject before opening the mapped endpoint. Never treat relay PID, content matching
or an in-process token as logical caller authentication. Post-200 stream bytes
are opaque: future bytes cannot be classified as an illegal CONNECT body versus
legitimate TLS by this broker. Ciphertext quotas count received bytes, including
at most one non-forwarded proof byte past a direction/shared aggregate limit;
they do not promise delivery of every byte received within the quota.

Acceptance: valid TLS returns/reconstructs exact authored text labelled synthetic;
wrong-host TLS fails before HTTP; disallowed redirect destination gets no traffic;
configured/recorded limits agree, no reported capture gap, and all threads/sockets
are closed. Explicit close does not prove no unreceived tail existed. TLS opacity
means CONNECT evidence contains only authority/counts/lifetime; endpoint plaintext
is separate fixture evidence. Actual managed auth, refresh/plan changes,
cloud-config lifecycle and model entitlement remain untested; production gate stays
closed regardless of this result.

The reused native runner/namespace relay serves serially and retains its stricter
140,000/20,000-byte and 4-second connection bounds. Exercise the CONNECT broker's
two-stream concurrency independently with local socket pairs; do not claim the
native fixture demonstrated concurrent provider requests.

## Ownership and integration

New owned files: this packet, `scripts/probe_native_tls_connect.py`,
`tests/test_native_tls_connect_probe.py`,
`docs/evidence/NATIVE_TLS_CONNECT_EXPERIMENT.md`, and
`docs/evidence/NATIVE_TLS_CONNECT_0_154_0.json`. Reuse existing client, packet,
parser/SSE, catalog validation and process helpers. Propose a minimal explicit
runner injection to root before touching shared code; do not copy the full runner.
Return frozen source, raw synthetic evidence, exact default/opt-in commands and
counterexamples. Root independently reviews and reproduces before integration.
