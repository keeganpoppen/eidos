# Synthetic gateway: transport works; caller admission fails

**2026-10-13 · implementation base `dc9767c` · C6 / V1-05 / V1-12.**
This implements steps 1–2 from the
[outer-boundary experiment](NATIVE_OUTER_ADMISSION_EXPERIMENT.md). The proposed
shared relay must **not** become the production native admission mechanism: a
same-namespace sibling can consume a permit intended for another caller by sending
identical approved content. The experiment produced this counterexample while
preserving the earlier filesystem/network negative controls.

The [sanitized artifact](NATIVE_GATEWAY_0_154_0.json) contains both schedules, native
configuration acknowledgements, synthetic HTTP results, broker events, version/hash
and launch commands. There are zero model turns, account credentials, real upstream
requests or production-gate changes. Both HTTP callers are fixture processes;
neither is a native model-provider request.

## What ran

On Codex **0.154.0**, bubblewrap **0.12.0**, Linux
**7.2.4-1-aarch64-ARCH**, the native app-server started inside the same disconnected
namespace boundary as the prior experiment. A loopback HTTP relay in that namespace
could reach exactly one host-mounted Unix socket. The host broker has **no upstream
network client or real forwarding route**. It returns fixed synthetic responses.

The native executable accepted the following candidate provider settings through
its normal configuration loader; `config/read` returned them and `account/read`
returned a null account with `requiresOpenaiAuth=true`:

```toml
model_provider = "synthetic_gateway"
forced_login_method = "chatgpt"
[model_providers.synthetic_gateway]
name = "Synthetic ChatGPT gateway"
base_url = "http://127.0.0.1:<namespace-port>/backend-api/codex"
requires_openai_auth = true
wire_api = "responses"
```

OpenAI documents a ChatGPT-sign-in gateway with `requires_openai_auth=true`, forwarding
native authorization/account headers to the ChatGPT Codex backend's model and
response routes. This is a supported contract to investigate without silently
switching to API-key billing. Its enterprise setup and other authentication,
managed-policy and integration routes still need separate verification.
[Official native gateway recipe](https://learn.chatgpt.com/docs/enterprise/sign-in-with-chatgpt-through-a-gateway).

Native configuration acceptance is the only provider-routing claim established
here. The RPC transcript contains `initialize`, `account/read`, `config/read`,
`thread/start`, and `mcpServerStatus/list`. It contains no model request. Synthetic
HTTP actors exercise the route independently of native provider execution.

## Counterexample and surviving controls

The intended fixture actor and a child of the unexpected startup MCP both know the
same public request body and send the same claimed caller header. No secret is
invented to distinguish them. The host controller opens one in-memory admission,
then releases the actors in a deliberately chosen order. These release files are
fixture scheduling controls, not an authority mechanism.

| Schedule | First exact-content request | Other actor's request | Repeated requests |
| --- | --- | --- | --- |
| Intended fixture first | Accepted, HTTP 200 | Rival refused, HTTP 409 | Refused, HTTP 409 |
| MCP sibling first | **Rival accepted, HTTP 200** | **Intended fixture refused, HTTP 409** | Refused, HTTP 409 |

Each case admitted exactly one synthetic response. Exact content and a count limit
held, but they did not establish which process was authorized to request it or
receive the result. This is a deterministic adversarial schedule, not a measured
probability of winning a timing race.

The broker observed the same Unix peer credentials for both actor attempts: those
of the relay that connected to it. Linux authenticates that Unix peer; it does not
recover the original TCP caller. A claimed caller header or body digest cannot
restore the lost distinction. The sibling also connected directly to the mounted
Unix socket despite its read-only bind mount. The direct peer differed from the
relay, but its early request was still denied by the closed permit.
[Linux Unix-socket credentials and pathname permissions](https://man7.org/linux/man-pages/man7/unix.7.html).

Other observations in **both** cases:

- An absolute unapproved URL was refused (403), wrong content was refused (422),
  an oversized body was refused (413), and an exact request before admission was
  refused (403). Duplicate requests could not consume another permit.
- The broker's fake service response supplied status 307 and a Location pointing
  at an unapproved domain. The broker returned 502 without a Location. This tests
  a **synthetic redirect-denial branch**, not receipt of a real upstream redirect
  or live redirect containment.
- The unchanged outer MCP fixture ran before inventory. Outside/symlink/parent-root
  reads, outside/packet writes, host-loopback/external connections, nested user
  namespace creation and packet remounting all failed as before. The selected
  packet remained readable. Host canary, packet and listener remained unchanged;
  the detached descendant heartbeat stopped after closing the owned worker.

## Bounded implementation and verification

The broker handles one connection at a time and stops accepting after 24 handled
connections per case, including refused requests. Each request has an absolute
two-second parsing deadline, an 8 KiB header limit and a 4 KiB body limit. Synthetic
response bodies are at most 4 KiB. The relay limits each direction's bytes, has
bounded socket operations including connection establishment, and handles at most
24 connections. A 20-second watchdog closes the owned namespace for each case.
These are experiment bounds; they do not provide aggregate CPU, memory, PID or disk
quotas, provider token/cost bounds, durable admission, or exactly-once external
effects. A fresh broker starts with fresh in-memory state.

Reproduce from the repository root:

```sh
uv run python scripts/probe_native_gateway.py --output /tmp/nema-native-gateway.json
NEMA_NATIVE_GATEWAY_PROBE=1 uv run pytest tests/test_native_gateway_probe.py
```

Observed: **26 passed** with native opt-in, including both real native startups.
The parent integrator independently reran the same opt-in suite on the integrated
tree: **26 passed**. This reproduces the rejected caller-admission mechanism as
well as the surviving containment controls.
Default tests run the 25 local guard/parser/concurrency/deadline checks and skip the
single native experiment. The direct script produced the committed artifact.
The combined gateway/outer/account/profile/worker/round-3/seed default suite passed
**191 tests**, with **3 explicit native experiments skipped**.
Malformed/duplicate framing, oversized headers/body, coalesced body/header counting,
concurrent permit consumption, exact-content replay, and incomplete-input timeout
have dedicated local tests. Independent review identified the caller confusion and
prompted stronger connection bounds, direct-socket evidence and precise redirect
labelling; the parent integrator owns final combined verification.

## Consequence and next discriminating experiment

Reject this shared-relay permit as a native caller-authentication boundary. Do not
repair it with another public Name, random URL, environment secret, process label,
or post-start reassignment: descendants in the admitted environment may learn or
inherit those resources, and the relay still loses the original caller identity.
The current worker remains closed and the earlier account acknowledgement remains
necessary.

The next no-credential experiment must establish a **kernel-enforced distinction
before startup** between native service execution and any untrusted MCP/tool
process. A concrete narrow candidate is a tools-disabled specialist launch whose
outer policy permits native threads but denies new non-thread processes and
unreviewed executables before configuration loads. Test that native initialization
and configuration inspection still work, that the unexpected startup MCP cannot
start a process or gain service egress, and that an intended service request can be
admitted without exposing its authority to a sibling. Whether this can be composed
with supported native execution on this host is unverified; no such filter was
implemented here. A supported separately authenticated native service channel is
another possible route, but has not been established.

Any later credential use must also protect authentication state from descendant
reads and honor applicable managed policy. Native sign-in/refresh, authenticated
provider routing, a real useful specialist answer, provider-context capture and
complete resource admission remain open. This negative result narrows the design;
it is not a new release gate or a claim that useful native execution is impossible.
