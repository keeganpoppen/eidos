# Managed native text and durable recovery

**2026-10-13 · base `6ea405a` · C6 / V1-05/07/12.** One wholly local,
synthetic managed-auth native turn completed and produced a persisted artifact
that recovered identically after SQLite was closed and reopened. This is an
operational native transport/recovery result, **not subscription execution or
production admission**. No real issuer, provider, model or owner credentials
were used.

The [accepted contract](../agents/NATIVE_MANAGED_TEXT_TASK.md) extends the
[managed lifecycle experiment](NATIVE_MANAGED_LIFECYCLE_EXPERIMENT.md), which
established login ordering and a challenged issuer denial. This positive case
asks whether that candidate can complete useful text transport rather than only
stop work. It reuses the same driver, process filter, TLS broker, fixed local
endpoints and limits. The default negative pair and its committed evidence are
unchanged; the positive case requires explicit `managedText` selection.

## Observed result

The hash-pinned 0.154.0 native executable completed one device-code login against
an authored issuer. Its own fresh Ephemeral store held invalid-signature,
fixture-only JWT-shaped tokens. Matching login completion, the following account
update, ordered `account/read(refreshToken=false)` and successful managed config
read acknowledged Plus and all required controls. The issuer destination and its
active tunnels were closed before `thread/start`.

Native acknowledged read-only/never approval and empty environments, accepted
one exact selected-context input, and completed one turn. The final text was:

> SYNTHETIC FIXTURE: both selected records survived [evidence:1] [evidence:2].

That text was authored by the fixture. Its appearance is evidence of native
protocol completion and recovery, not model reasoning or citation entailment.
The native terminal had status `completed`, no error, and the same turn identity
as its acknowledgement. The recovered output refers to native record **33**;
matching terminal record **37** followed it. The artifact cites selected records
**1 and 2**, with no unsupported citations.

Exactly six CONNECTs opened exactly six local TLS endpoints, carrying six HTTP
requests. No cap refusal, unexpected route, extra response request or issuer
reopening occurred:

| Order | Fixed endpoint request | Authored response |
| --- | --- | --- |
| 1 | Issuer POST device user-code | 200, synthetic device code |
| 2 | Issuer POST device token poll | 200, synthetic authorization code |
| 3 | Issuer POST OAuth code exchange | 200, generation A, far-expiry Plus |
| 4 | Provider WebSocket GET Responses | 426, explicitly induced HTTP fallback |
| 5 | Provider GET Git-attribution settings | 200, `commit_attribution_enabled=false` |
| 6 | Provider POST Responses Lite | 200, fixed 2,769-byte text SSE |

The builtin provider remained enabled with its native WebSocket behavior. The
426 was a deliberate fixture response, not proof that WebSockets are disabled.
The settings request is the mandatory native context contributor identified in
the prior experiment; it was not silently removed or relabelled as model traffic.
There were **one native login RPC, one recorded/acknowledged native turn, three
issuer HTTP requests and three provider HTTP requests**. Real auth, upstream and
model calls were zero. A final non-refreshing account read still reported Plus.
An `account/rateLimits/updated` notification was observed; the driver sent no
rate-limit-read RPC.

## Native context and durable classification

The one observed provider POST contained the exact selected prompt once. The
native-added content included the fixture base instructions, permission and
collaboration instructions, and environment context. Responses Lite used the
reviewed header and an empty `additional_tools.tools` array; top-level tools and
function-call outputs were absent. The selected packet is therefore an exact
observed input, not the whole native/provider context.

Before turn request record **25**, the host wrote record **24** on the exact
native source:

```json
{"method":"$native/profile","params":{"admission":"custom-command-trusted-host","executionEvidence":"synthetic","fixture":"offline-managed-text","liveAdmitted":false}}
```

Unmodified `NativeInvestigationWorker.recover` derived `synthetic` from that
preceding internal record. The probe did not overwrite the recovered
classification. `InvestigationStore.complete` persisted the recovered artifact
against the exact attempt. After closing SQLite, a new store read matched the
saved work and a second recovery returned the same text, output references,
citations and synthetic classification without launching another process.
Default evidence checks independently reconstruct the raw recorder history in
memory and run that same recovery code.

This internal marker is a trusted host fixture convention. It is not a production
profile admission, capability grant or authenticator against arbitrary database
writers. Default mutations verify that a missing marker, a marker from another
source, native-emitted marker or marker after the request cannot establish this
synthetic classification. Other mutations reject missing/cross-ID terminal or
acknowledgement, changed packet/selected records, capture loss, duplicate provider
requests, altered reopened output and classification inflation.

Selected records retain their exact raw text, source, sequence and SHA-256,
including `futureFixtureField`. The raw authored SSE retains its unknown
`futureSyntheticField`; this does not claim that native propagated that field
into its app-server events. The [raw evidence](NATIVE_MANAGED_TEXT_0_154_0.json)
keeps the selected packet, effective config, HTTP payloads, app-server records,
native terminal, artifact and reopened recovery separately inspectable.

## Bounds and limits of the result

All startup pins remain in force: the exact derived static catalog, disabled
analytics, both OTEL exporters `none`, disabled tools/MCP/agents and other reviewed
producer controls. Existing fixed no-DNS/no-upstream endpoint factories, opaque
CONNECT transport, fresh disconnected namespace and pre-exec process filter were
reused. TLS keys stayed outside native and git; no existing credentials/state,
token-import/export RPC, browser or paid API was used.

No quota increased. Inherited bounds include eight processed CONNECTs, two active
tunnels, two MiB aggregate receipts plus the existing proof byte, 256/512-KiB
per-direction limits, eight-KiB buffers/responses, eight-second tunnels and
four-second idle time. The serial namespace relay is stricter: 140,000 outgoing
and 20,000 incoming bytes per connection, four seconds and 24 accepted sockets.
Native watchdog/supervisor remain 18/20 seconds. HTTP body receipt is at most
128 KiB, with a separate 16-KiB issuer acceptance limit; native events remain
bounded and use the exact source-matched derived `AppServerLimits`. There is no
aggregate CPU, RSS or SQLite quota claim.

All owned workers joined and active tunnels returned to zero. Capture reported
no gap or diagnostic error, with 34,890 stdout bytes, 239 stderr bytes and 25
accepted stdout frames. The stderr line records the deliberately rejected
WebSocket handshake. Absence of a reported gap does not prove absence of an
unreceived tail after bounded client close. The accepted terminal was recovered
from the recorded prefix.

`account/updated` has no login ID: correlation uses the matching login-completion
ID plus the exclusive fresh single-login flow and expected ordered account
fields. Local timeline timestamps represent host construction/consumption,
not a universal native clock. Issuer closure cannot recall already delivered or
buffered token bytes. This case did not challenge settings-401 recovery or prove
a global auth-writer barrier. Its auth-file check concerns only `auth.json`, not
all possible native state persistence.

## Reproduction and provenance

Default checks launch no native process:

```sh
uv run pytest -o addopts='' tests/test_native_managed_lifecycle_probe.py
```

Explicit positive case, with the older negative opt-in disabled:

```sh
NEMA_NATIVE_MANAGED_LIFECYCLE_PROBE=0 NEMA_NATIVE_MANAGED_TEXT_PROBE=1 \
  NEMA_NATIVE_MANAGED_TEXT_OUTPUT=/tmp/native-managed-text.json \
  uv run pytest -o addopts='' tests/test_native_managed_lifecycle_probe.py
```

The direct probe also supports
`uv run python scripts/probe_native_managed_lifecycle.py --mode managedText --output /tmp/native-managed-text.json`.
Omitting `--mode` retains the prior negative pair.

The native run passed **86 checks, 2 negative opt-in skips in 0.84 seconds** before
additional pure artifact tests. Current default file checks: **102 passed,
3 explicit native skips**. The reviewed binary hash remains
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
Native reported 0.154.0 through contained initialization. Raw artifact SHA-256:
`71c390f2f5faa34f2d5df033078f1ea65c623d18c3ec354a2aa3e9ef5b637a20`.

Executed script SHA-256 was
`8453a7312174a3381c6d215b1c56b771c74bb72357e8c267e7949f7f48d5753b`.
Only pure assessor checks for exact selected records and completed saved-attempt
state changed after that run; final script SHA-256 is
`5b5d2c7e527f5b0f6b22bd2d1884d6f5354453c9ca90eea7a0b77102ff996973`.
The raw artifact retains the executed-source hash and all helper hashes. Tagged
native protocol/control provenance remains in the preceding lifecycle report;
this change used the already reviewed tagged fixed-text SSE and existing
production recovery logic.

## Independent parent reproduction

The integrator ran the final `5b5d2c7e…ff996973` source against the combined tree:
**103 passed, 2 negative opt-in checks skipped in 0.86 seconds**. The report is
`/tmp/native_managed_text_parent_20261013.json`, SHA-256
`a0c865b3b329cefdd3d844648c5c6c8974c513a7740b42dbac016c41001153a5`.
It reproduces six CONNECT/HTTP requests, one login and one acknowledged/completed
turn, exact output record 33, citations 1 and 2, and identical synthetic recovery
after SQLite reopen. All workers joined, active tunnels returned to zero, and
both assessments and reported capture failures were empty. No real auth, upstream
or model call. The original development artifact and its source hash stay intact.

## Decision

The candidate can complete a managed synthetic native turn and return a durable,
correctly classified artifact under the reviewed containment and closed-issuer
policy. This removes a concrete offline compatibility uncertainty. It does not
establish subscription availability, live account admission, caller authentication
against compromised native code or complete provider-context control.

The next integration decision belongs to the separate private owned-lifecycle
controller: express this supported sequence through the existing investigation
without manufacturing live authority from the synthetic report. No real sign-in
or upstream request is authorized by this result.
