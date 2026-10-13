# Native startup inside an outer Linux boundary

**2026-10-13 · implementation base `86b3767`, descending from `ad73408`.**
This C6 / V1-05 / V1-12 research lane independently reviewed the account-admission
patch and then ran a new **real-native, no-model, synthetic** experiment. It does
not admit the production worker. No existing credentials, personal configuration,
conversation, repository workspace, or system policy were mounted or inspected.

## Result that changes the next action

Codex 0.154.0 started successfully inside bubblewrap 0.12.0 on Linux
7.2.4-1-aarch64-ARCH. Its intentionally enabled, previously unknown synthetic MCP
started **before** the inventory request. Nevertheless, the outer mount, network,
PID and user namespaces contained every tested startup effect. This is a concrete
alternative to discovering all MCP names before launch. It establishes these
fixture observations, not general arbitrary-code security or authenticated cloud
containment. The complete sanitized observation and command are in
[NATIVE_OUTER_BOUNDARY_0_154_0.json](NATIVE_OUTER_BOUNDARY_0_154_0.json).

| Attempt by the startup fixture | Native/host observation |
| --- | --- |
| Read an unmounted host canary, directly, through a selected-packet symlink, or through `/proc/1/root` | All failed with ENOENT. |
| Overwrite that canary | Failed with ENOENT; host verified unchanged. |
| Read the selected packet | Succeeded. |
| Modify or remount the packet | Write failed with EROFS; remount refused; host verified unchanged. |
| Connect to a real host loopback listener | Refused; host listener received no connection. |
| Open a connection to a documentation-only external address | No route; no external packet delivery was needed. |
| Acquire a nested user namespace | Refused; effective Linux capabilities were zero. |
| Leave a detached descendant alive after closing the worker | Its heartbeat changed before close and stopped after close. |

The experiment uses a fresh root with read-only `/usr`, synthetic read-only packet
and fixture mounts, writable disposable native state, fresh `/proc` and `/dev`,
and no external network route. `--unshare-user` is explicit: on this installed
bubblewrap, `--unshare-all --disable-userns` alone failed because the latter requires
the former's strict user-namespace option. There is no fallback to an uncontained
launch. `account/read` acknowledged no account and builtin authentication required.
The RPC allowlist excludes login, model turns, shell/process calls and interactive
responses. The native binary hash matches the earlier admission report.

This probe deliberately exercises a local unknown startup process; it does not
simulate a signed cloud bundle or show that cloud policy was fetched. The outer
boundary is in place before native startup regardless of the fixture's name, but
the behavior of actual authenticated policy remains a separate observation.

## Independent account-patch review

The 13-line worker change in `86b3767` repairs a real omission: the profile already
had `check_account`, but the worker had never called it. A profiled worker now
records `account/read(refreshToken=false)` after initialization and validates its
reply before `thread/start`. Refusal/error cannot create a thread or model turn.
Unknown account-response fields remain in raw evidence. Trusted-host fake commands
remain compatible, and test-only profiles cannot establish native provenance.
The focused suite passed independently in this worktree.

That acknowledgement is necessary but insufficient: it is neither an entitlement
check nor a durable account lock. The production gate still refuses before process
creation; this experiment adds no gate override. The supported account contract is
documented in [OpenAI's app-server reference](https://learn.chatgpt.com/docs/app-server#account-endpoints).

## Next bounded experiment: controlled subscription traffic

The next implementation should extend this runnable outer-boundary probe with a
**synthetic service gateway**, not give the namespace the host network. A dedicated
Unix socket mount and a loopback relay inside the namespace can expose one broker
without exposing other host services. First verify that transport with fake
responses and no credential mount or model RPC. Keep direct host/external network
attempts in the startup fixture as negative controls.

There is a supported native transport to investigate: OpenAI documents keeping
ChatGPT sign-in while routing a selected provider through a gateway with
`requires_openai_auth=true`. The gateway forwards the native ChatGPT authorization
and account headers to `https://chatgpt.com/backend-api/codex`, including `/models`
and `/responses`. It is distinct from API-key billing. The documentation cautions
that sign-in, MCP and plugins can use other paths and that installed-build support
must be checked. This is an enterprise gateway recipe, not evidence that every
personal-account deployment or this executable has been validated for it.
[Official gateway contract](https://learn.chatgpt.com/docs/enterprise/sign-in-with-chatgpt-through-a-gateway).

The concrete experiment contract is:

1. Keep the outer namespace disconnected and the gateway unable to forward any
   real request. Point only the candidate provider at the synthetic relay using
   supported configuration; verify effective provider/auth requirements and record
   exact requested methods/paths without logging authorization header values.
2. Require the injected startup MCP to try an unapproved URL, a redirect, an early
   `/responses` request, and a second request after a one-use synthetic admission.
   All must be denied. The intended synthetic request must pass exactly once.
   Bound request/response bytes, wall time and total forwarded requests. A proxy
   host allowlist alone is insufficient, and a shared relay does not authenticate
   a native caller against another process in the namespace. Bind any future
   admission to reviewed request content and an owned attempt, and falsify that
   binding with a competing descendant before using credentials.
3. For the eventual real-account phase, choose and review one native credential
   lifecycle: an owner-performed [native sign-in](https://learn.chatgpt.com/docs/auth)
   into Nema-owned state, or a narrow
   read-only mount of an existing native credential file at its expected native
   path. The latter has not been attempted and may fail on token refresh; failure
   must not trigger credential extraction, copying or host-state edits. Neither
   route uses externally managed tokens owned by Desktop.
4. Auth and managed policy require their own native traffic. Native OAuth uses
   `auth.openai.com`; model forwarding targets the ChatGPT backend above. Enumerate
   the installed version's actual routes with synthetic credentials before enabling
   any real forwarding. Preserve applicable system/cloud policy: the probe's blank
   synthetic system view is not a production policy bypass. Do not silently allow
   all traffic to either host, suppress failed managed-policy loading, or switch to
   API-key authentication. If the required account/managed routes cannot be bounded,
   this candidate remains unadmitted.
5. Only after those checks, attach the worker's existing durable attempt/manifest
   pin and account acknowledgement to one approved, short subscription turn. An
   appropriate first task is to identify the controlling decision in a small frozen
   synthetic evidence packet and cite its stable source IDs. Preserve the native
   request/result and acknowledge provider-context gaps. One HTTP request is not a
   token/cost guarantee; use provider-enforced limits where available and state the
   remaining budget uncertainty.

Steps 1–2 are runnable development work without credentials; steps 3–5 are a
deliberate future mechanism decision. None ran in this lane. This candidate changes
the current builtin-only provider policy, so it needs an explicit reviewed profile,
not a reinterpretation of the current gate. The earlier
[frontier report](NATIVE_ADMISSION_FRONTIER.md) remains the source for local/cloud
configuration findings and alternatives. Native command-network proxy settings do
not automatically constrain app-server, MCP or service traffic; the outer boundary
must continue to carry that obligation.
[Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Reproduction, scope and continuation

From the repository root, with this Linux executable and bubblewrap installed:

```sh
uv run python scripts/probe_native_outer_boundary.py --output /tmp/nema-native-outer.json
NEMA_NATIVE_OUTER_PROBE=1 uv run pytest tests/test_native_outer_boundary_probe.py
```

The direct script ran and produced the committed artifact. The opt-in test ran
successfully: **8 passed**, including the actual native experiment. The default
suite skips that one native test and runs seven transport guards. The combined
account/probe opt-in run passed **23 tests**. The account, outer-probe, profile,
worker, round-3 review and seed-context default suite passed **166 tests**, with
**2 explicit native probes skipped**. No authenticated model call ran.

The watchdog closes the owned process after 25 seconds; the fixture produces small,
finite observations. This is not an aggregate CPU, memory, PID or disk quota and is
not yet a production launcher. `/usr` is a broad read-only runtime mount, and the
test does not audit its entire contents. Packet-only provider visibility, real
credential refresh, real cloud-policy composition, allowed inference egress, kernel
escape resistance and provider expenditure remain unverified.

The parent integrator owns main, canonical STATE/handoff and the final combined
verification. This worktree owns only the account patch and this independent
experiment. Next entry point: extend
[probe_native_outer_boundary.py](../../scripts/probe_native_outer_boundary.py)
with the synthetic broker contract above, preserving the existing negative controls.
