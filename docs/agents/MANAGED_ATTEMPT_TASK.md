# One user-operated managed attempt

**2026-10-13 · accepted implementation contract · base `8ed2f0a` · C6 / V1-05/07/12.**
The [owned native join](../evidence/NATIVE_OWNED_WORKER_EXPERIMENT.md) passed through
the actual private worker. Build its first concrete opt-in product path now. This
packet authorizes code, authored local tests and rendered UI acceptance. It does
not authorize real sign-in, account state access, upstream connections or model
calls. A new contained native experiment requires review of its concrete code and
effects before execution; do not silently rerun an expanded fixture.

## User-visible loop

An owner deliberately enables managed native work when starting the loopback
server, pins an investigation and chooses its ordinary Start action. A fresh
contained process offers a device sign-in URL/code with this attempt's deadline.
The existing Stop action cancels that exact attempt. Ordered native readiness
checks permit one bounded thread/turn; its private evidence supports the existing
typed public result. Reopen shows historical work without credentials, challenge,
admission, owner or automatic resend. Default server behavior remains closed.

Reuse PrivateInvestigationWorker, NativePreparation, AppServerClient and the
current turn loop. NativeLaunch.live_admitted stays false for the old profile.
No second event pump or agent loop. Custom commands remain synthetic/unverified.
Do not claim one provider request per turn, hidden-context completeness, permanent
entitlement, a global credential-writer barrier or exactly-once external effects.

## Shared interfaces and ownership

Root owns `native_managed_contract.py`, worker/private/API/serve/CLI integration,
correlated historical classification, integration tests, docs and final commit.
The shared contract defines immutable identity from attempt ID, context ID,
canonical context SHA256, projected prompt SHA256 and exact native source. The
globally unique attempt already binds its investigation; do not invent another
owner identity the worker cannot receive. Hashes identify selected bytes, not
caller authority. Root supplies the identity before any process launch.

- **native_frontier:** isolated worktree; new `native_connect.py`,
  `native_containment.py`, packaged `resources/native_guard.c` and
  `resources/native_runtime.py`, their tests, resource packaging in pyproject.
  Promote reviewed process/TLS code; production never imports scripts. Own low
  level containment, dial/relay lifecycle and public root provisioning.
- **history_ui:** isolated worktree; new `native_managed.py`, its tests, packaged
  original public catalog plus explicit patch/provenance/license. Own per-attempt
  managed preparation, configuration validation, challenge and admission state.
  Use containment interface below; no edits to worker/API/UI or transport files.
- **gateway_review:** isolated worktree; existing attempt-control/types/pane and
  UI tests only. Present ephemeral challenge through exact existing control reads,
  stop/reload/navigation. Root provides API and authored browser fixture. After
  UI delivery, review runtime/integration independently and inspect actual UI.

Minimal interface (agents may propose a concrete improvement before changing it):

```python
profile.prepare(cwd, *, identity: ManagedAttemptIdentity) -> ManagedLaunch
launch.command; launch.env; launch.evidence; launch.limits
launch.require_contained_startup()  # one consumption by actual Popen guard
launch.prepare_native(preparation: NativePreparation)
launch.consume_turn_admission(identity) -> dict  # immediately before thread/start
launch.read_challenge(identity) -> dict | None
launch.bind_abort(close_owned_client)
launch.close(reason="closed") -> dict

ContainedRuntime(cwd, *, config_toml, catalog_bytes, policy, binary="codex")
runtime.command; runtime.env; runtime.evidence
runtime.require_contained_startup()
runtime.activate_provider()  # close all issuer paths first; irreversible
runtime.bind_abort(close_owned_client)
runtime.close(reason="closed", *, wait=True) -> dict
runtime.remaining_preparation(); runtime.remaining_turn()
```

ManagedExecutionProfile is a reusable factory with no sticky admission/challenge;
every prepare creates fresh live state. Preparation requires empty initial account,
the fixed configuration, one device login, matching completion and subsequent
account update, then non-refreshing Plus/Pro account and successful config checks.
Close issuer access before opening provider access or returning readiness. The
receipt records exact identity, reviewed manifest and actual correlated readiness
evidence privately before thread/start. Recovery may classify historical evidence;
it must never manufacture a ManagedLaunch. Root retains native thread/turn policy
and MCP checks and binds subsequent request/acknowledgements to that receipt.

Root adds an explicit `managed_profile` constructor seam mutually exclusive with
custom preparation/commands. The CLI switch is the deliberate resource choice;
an HTTP request cannot choose a binary, profile, endpoint, budget or live exemption.
Implement and test the switch, but do not enable it against real endpoints here.

## Ephemeral UI contract

Existing exact-attempt GET control may add:
`signIn:{verificationUrl,userCode,expiresAtMs}` only while this controller owns
that current challenge. Expiry is Nema's preparation deadline, not a claimed
issuer expiry. Production URL must be exactly `https://auth.openai.com/codex/device`;
render as an explicit new-tab link with no automatic navigation. Keep URL/code
out of public history, saved views, draft/retry storage, result publications and
browser local/session storage. Private raw native capture remains attributable.
Clear on sign-in completion, cancellation, expiry, lost ownership and navigation.
Delayed responses for A cannot populate B or revive a cancelled/expired challenge.
Existing control snapshots without signIn remain compatible. Show bounded text
and the attempt deadline; no native implementation internals in ordinary UI copy.

## Containment and limits

Initial support is reviewed Linux/aarch64 only. Require bwrap namespaces,
seccomp-notification ABI, stdlib Python and a bounded C compiler invocation. No
fallback, downloaded helper, host credentials/config, token import/export or paid
API provider. Compile only packaged guard code into disposable state. Fix the
fork-to-parent-death registration race and preserve one exec/listener closure.
Copy/hash the pinned native executable into a read-only asset snapshot with a
fixed size cap. Fresh writable native state and empty tmpfs retain only cwd
spelling; mount no owner workspace contents. Read-only /usr remains a declared
trusted runtime dependency. Snapshot only public system certificate roots into
a standard namespace path, with hash. No inherited custom CA or fixture override.

Production destinations are fixed `auth.openai.com:443` and `chatgpt.com:443`.
Irreversible states: prepared → issuer-only → provider-only → closed. DNS runs in
a killable finite resolver process, never under the broker lock; bounded public
address results are frozen for nonblocking TCP dialing. Register pending sockets;
phase/generation recheck rejects completion after closure before 200 CONNECT.
Two bounded concurrent opaque streams permit WebSocket plus settings traffic.
The broker observes ciphertext and endpoint/budget outcomes, not HTTP/model bodies.

Initial policy choices: preparation180s (including setup/sign-in), turn120s,
hard lifetime305s from resource creation; resolver3s/TCP5s/header2s; two active
tunnels,256 total accepted connections; idle60s; tunnel lifetime bounded by the
remaining phase; shared received TLS8MiB plus one proof byte, directional pending
buffers8KiB. Private app-server capture retains the existing production8MiB
received cap and other PrivateEvidenceLimits capture bounds. These are new reviewed
product choices, not a silent change to old probes or a promise of service success.
Device polling may need a fresh connection each second; counters remain finite.
No CPU/RSS/disk quota or exact provider-request-count claim.

All clocks derive from one launch lifetime. Cleanup invalidates challenge/admission
first, interrupts pending dials/tunnels, calls owned-client abort outside locks,
joins workers, then removes disposable files. Repeated/concurrent close is safe;
failed shutdown retains diagnostic evidence and cannot grant reuse. A writable
policy.json is diagnostic evidence, never the dispatch authorization itself.
Only startup-exception unwind uses `wait=False` to avoid waiting for a concurrent
closer whose owned-client callback needs the current startup lock. It invalidates
managed readiness immediately and may return cleanup-in-progress, never a success
claim. Final worker cleanup uses the normal joined close report after startup
has unwound. Test this through ManagedLaunch and the actual AppServerClient lock,
not just the low-level runtime guard in isolation.

Managed publication and later recovery require one successful private
`$native/managedClose` with the exact attempt/context/source identity after all
native protocol records. A missing close record (including storage failure or a
host interruption after completion) leaves the attempt uncertain and its terminal
evidence private. Failed, duplicate, foreign or premature closure refuses recovery.
This deliberately narrows managed crash recovery; absent evidence cannot establish
that disposable native/network resources closed. Legacy completed-prefix recovery
is unchanged. Neither copied closure records nor historical classification grant
live ownership.

## Acceptance and integration

Use authored local processes/TLS endpoints; no real DNS/account/provider. Test
pending login beyond the old20s cap, cancellation/deadline before thread, exact
completion with publication/reopen, successful opaque WebSocket with concurrent
settings, fragmented/stalled/quota traffic, issuer closure during resolve/dial/
forwarding, parent death/startup failures and joined cleanup. The decisive identity
case is sign-in A→cancel→new B/reopen: no borrowed challenge, receipt or dispatch.
Wrong config/account/source/context, replayed readiness and missing resources
must refuse. Native package tests inspect an installed wheel outside checkout.

Root reviews actual UI at desktop and390px with private canaries, dirty draft,
pending save/retry, lost stop reply and delayed stale control. Full Python and
appropriate UI checks follow integration. Independently review authority/evidence/
cleanup boundaries before a separately scoped real-native local acceptance run.
Only after concrete reviewable code can a deliberate user-operated live attempt
answer account/model availability and login usefulness. Do not ask for that first.
