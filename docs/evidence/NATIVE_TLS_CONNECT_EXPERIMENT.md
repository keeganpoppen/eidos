# Native HTTPS through an opaque CONNECT fixture

**2026-10-13 · native 0.154.0 · C6 / V1-05/12 · offline synthetic evidence.**
Contract: [accepted task packet](../agents/NATIVE_TLS_CONNECT_TASK.md).
Implementation: [probe](../../scripts/probe_native_tls_connect.py),
[tests](../../tests/test_native_tls_connect_probe.py),
[raw synthetic observation](NATIVE_TLS_CONNECT_0_154_0.json).

The reviewed native provider client honored `HTTPS_PROXY` and
`CODEX_CA_CERTIFICATE` inside the disconnected namespace. One valid-certificate
turn returned the exact authored fixture text and recovered it with
`executionEvidence: synthetic`. A certificate signed by the same trusted CA for
the wrong hostname produced **zero plaintext HTTP requests**. An HTTP 307 caused
a CONNECT attempt to the unapproved destination; the broker rejected that attempt
before creating an endpoint. This establishes the proposed opaque transport
primitive for this client path. It does not establish managed-ChatGPT admission.

## Exact setup and source support

Native remains the reviewed `/usr/bin/codex` binary, SHA-256
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`, with
the unchanged pre-exec process filter (source SHA-256
`274c79ec32bd8ab307a883bbdb74805c1a040c969ca32a3cdc7b514d35910e56`).
The existing runner verifies the recorded pre-exec filter installation,
fresh `account: null` / `requiresOpenaiAuth: false`, and the effective provider,
model and startup catalog before authorizing one `turn/start` per case. It
retains the [paired derived catalog](NATIVE_DERIVED_CATALOG_EXPERIMENT.md): exact
public catalog plus the explicit two-field policy patch, agents disabled and
the previously tested tool controls. No model entitlement is inferred.

The root-owned runner extension supplies explicit `expected_base_url` and a
context-managed fixture factory. Existing default behavior is preserved. This
probe changes only the disposable launcher to set
`HTTPS_PROXY=http://127.0.0.1:<namespace-port>` and
`CODEX_CA_CERTIFICATE=/fixture/ca.pem`. The namespace starts with a cleared
environment. The provider is `https://provider.fixture.invalid/v1`, no auth,
WebSockets disabled; requested request/stream retry settings are zero.

The existing namespace TCP relay carries bytes to a host Unix socket. The
CONNECT broker accepts only the literal `provider.fixture.invalid:443`, maps it
to a local socket pair, and forwards opaque bytes. It has no DNS resolver or TCP
dialer. A separate TLS fixture endpoint owns the private key, validates the
bounded Responses Lite request, and supplies fixed text or the authored redirect.
The public CA is mounted read-only; CA/server private keys are generated in a
temporary directory outside the repo and namespace and removed on exit. The
proxy itself never terminates TLS. This separation is an implementation fact,
not protection from a compromised host that owns both fixtures.

Primary public source at tag `rust-v0.154.0` supports the tested knobs:

- [`http-client/src/custom_ca.rs`, lines 61–63 and 164–182](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/http-client/src/custom_ca.rs#L164): custom CA loading; `CODEX_CA_CERTIFICATE` precedes `SSL_CERT_FILE`.
- [`http-client/src/outbound_proxy.rs`, lines 351–374](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/http-client/src/outbound_proxy.rs#L351): HTTPS environment-proxy selection and `NO_PROXY` handling.
- [`http-client/src/client_builder.rs`, lines 268–289](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/http-client/src/client_builder.rs#L268): default proxy routing, direct-mode override and redirect policy.
- [`core/src/config/mod.rs`, lines 1636–1647 and 2995–3007](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/config/mod.rs#L1636): runtime/bootstrap factory policy selection.

The four inspected source hashes are retained in `sourceProvenance` in the raw
JSON. The local read-only source cache was `/tmp/nema-codex-0.154-source`.
These spans explain the intended route; observed CONNECT requests, successful
custom-root TLS and the hostname-negative control establish the narrower actual
behavior. No assertion covers every native HTTP client, auth refresh, WebSockets,
macOS proxy routing or arbitrary plugin HTTP code.

## Observation

| Case | Native turns | CONNECT attempts / mapped endpoints | Plaintext HTTP | Result |
| --- | ---: | ---: | ---: | --- |
| Valid certificate | 1 | 1 / 1 | 1 | Exact authored text, accepted terminal recovered as synthetic |
| Trusted wrong-host certificate | 1 | 2 / 2 | 0 | Both TLS handshakes failed; event consumer timed out before any terminal was observed |
| Redirect to unapproved host | 1 | 3 / 2 | 2 | Authored 307, refused destination CONNECT, retry to original endpoint refused with 409; failed native terminal |

Total: **3 native turn RPCs, 6 CONNECT attempts, 3 fixture HTTP requests,
zero real model calls and zero upstream requests**. `acceptedProviderRequests`
counts the one permitted fixture request per valid/redirect case, including the
307; it does not count real provider executions. All six attempts were retained;
no over-cap refusals occurred. General reporting distinguishes all observed
`connectAttempts`, retained/processed `connectCount` (at most eight), and
`unrecordedConnectRefusals` after that cap or close.

The redirect was followed, not refused by native. The recorded refused authority
is exactly `disallowed.fixture.invalid:443`, status 403, with zero tunnel bytes
and no mapped endpoint. Native then retried the original provider, despite the
requested zero request/stream retry settings. The fixture consumed its single
permit on the 307 and returned 409 to the retry. Likewise, wrong-host TLS tried
twice. The byte/time/request bounds remain necessary; zero configured retries
does not mean one observed network attempt.

The valid request uses the actual Responses Lite envelope and an empty
`additional_tools.tools` declaration with an opaque native ID. Raw endpoint
evidence preserves the complete prompt, additional native messages, request
headers/body and authored SSE; source-context correlation is retained in the
same case. Proxy evidence contains only CONNECT headers, byte counts, timings
and outcomes. No tool call was authored. Earlier tool-policy experiments remain
the evidence for tool rejection; this text-only fixture does not repeat them.

Ciphertext received was 15,297 bytes (valid), 8,082 (wrong host), and 25,111
(redirect), including TLS overhead in both directions. Native stdout receipt was
23,483 / 21,781 / 22,372 bytes, stderr zero, with 30 / 25 / 27 trace records.
All endpoint workers joined and all tunnel reservations returned to zero. The
bounded recorder reported no capture gap. Only the valid case recovered an
accepted successful terminal; explicit close and a gap-free received prefix do
not prove that no unreceived tail existed. The wrong-host timeout is an incomplete
turn observation, not a successful failed-terminal recovery.

## Rejection and resource scope

Default tests use local sockets, disposable certificates and authored inputs;
they never start Codex. Counterexamples include early requests, duplicate and
mismatched Host, non-CONNECT methods, credentials/transfer headers, declared
nonempty bodies, coalesced post-header bytes, oversized/truncated/slow headers,
scheme/userinfo/IP/port/suffix/trailing-dot/escape ambiguities, concurrent tunnel
overflow, aggregate quota races, nonreading peers and shutdown during TLS setup.
All parser/policy refusals precede endpoint creation. Once 200 is sent, stream
bytes are opaque; the broker cannot classify future bytes as illegal CONNECT
bodies versus TLS.

Header content is bounded to 8,192 bytes plus CRLFCRLF and one refusal proof byte,
with a two-second parse deadline. At most eight exchanges are processed and two
tunnels active; later exchanges receive an unrecorded 429 with a separate counter.
Each direction has an 8,192-byte pending buffer. Ciphertext receipt is limited to
262,144 outbound / 524,288 inbound per tunnel and 2,097,152 aggregate, plus at most
one non-forwarded proof byte past a direction/shared aggregate cap. Concurrent
receive/accounting is serialized. These are received-byte quotas, not promises to
forward every allowed prefix. Idle timeout is four seconds; the absolute
eight-second tunnel lifetime starts after CONNECT acceptance, with separate parse
and CONNECT-response socket timeouts.

The reused namespace relay and native fixture server are serial. Their stricter
140,000 outbound / 20,000 inbound bytes and four-second connection limit dominate
actual native cases; the relay accepts at most 24 sockets and has an 18-second
lifetime. Two-tunnel behavior is exercised independently through socket pairs,
not claimed as observed concurrent native requests. Native watchdog, completion
consumer and frame/event/receipt limits remain in the task packet and raw JSON.
There is no aggregate CPU, RSS or trace-database disk quota. Shutdown interrupts
active sockets before joining the native fixture server and joins TLS workers.

## Reproduction and next decision

From the repository root, with dependencies already synced:

```sh
uv run pytest -o addopts='' tests/test_native_tls_connect_probe.py tests/test_native_model_catalog_probe.py tests/test_native_derived_catalog_probe.py tests/test_native_synthetic_turn_probe.py tests/test_native_tool_boundary_probe.py
NEMA_NATIVE_TLS_CONNECT_PROBE=1 NEMA_NATIVE_TLS_CONNECT_EVIDENCE=/tmp/native-tls-connect.json uv run pytest -o addopts='' tests/test_native_tls_connect_probe.py
```

The frozen native run passed **53 checks** before the final two pure evidence /
header-boundary tests were added. Root review then added exact capture-limit,
diagnostic and source-matching recorded-policy assertions plus three pure
counterexamples. Final combined default checks passed **163**, with
**19 explicit opt-in tests skipped**. The first development run exposed two overly
strict test assumptions (an extra native tool-envelope ID and redirect retries);
the corrected frozen run retains both observations and adds refused-authority
diagnostics. No allowance was broadened to obtain success.

The parent independently reproduced the final **58 checks** on integrated main:
three contained native turns, six CONNECT attempts, three authored fixture HTTP
requests and zero real model/upstream/auth calls. The same valid result,
wrong-host timeout with zero HTTP and denied-redirect/original-host retry were
observed. Actual capture status and the source-matched trusted limit record agree;
there was no reported capture gap or diagnostic error. Every endpoint worker joined
and every tunnel reservation returned to zero. Parent report:
`/tmp/native_tls_connect_parent_20261013.json`. This reproduction is separate from
the committed raw development observation.

Parent combined verification: **1,026 Python passed / 50 explicit native checks
skipped**. Independent code and prose review found no blocking counterexample.
No frontend changed in this wave; the prior UI checks remain separate evidence.

Proceed with this transport primitive as a candidate for a Nema-owned managed
session; keep production admission closed. TLS can remain opaque to a
destination-limited broker when the reviewed native executable/configuration is
the trust boundary. A same-process token or matching request body is still not
caller authentication, and CONNECT cannot distinguish allowed-host model traffic
from cloud configuration or another path on that host.

The next indispensable discriminator is a separate offline managed-auth lifecycle
fixture: prove a barrier between fresh native-owned ephemeral login/refresh and
post-login admission, including a successful issuer response buffered before
destination closure that attempts to commit after closure. Observe exact plan,
effective config and native credential-generation changes without treating
`login/completed` or cached `account/read` as that barrier. The managed-account
writer analysis is source inference; this no-auth provider run does not exercise
login, account refresh, plan transitions, cloud configuration, plugin bootstrap,
subscription availability or a real account. No credential copying, Desktop
ownership claim or paid API fallback has been introduced.
