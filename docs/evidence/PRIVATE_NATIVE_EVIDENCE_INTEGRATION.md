# Private recording and inspectable result publication

**2026-10-13 · integration base `6ea405a` · C6 / V1-02/05/06/07/12.**
The existing investigation loop now records each new incarnation privately and
publishes an attributable derived result into the workbench. Inquiry, refusal,
restart, grounded result reuse and comparison continue to use the same canonical
investigation/context/attempt/artifact identities. Production native admission
remains closed. All API/browser examples here use authored subprocesses; the
[separate positive native experiment](NATIVE_MANAGED_TEXT_EXPERIMENT.md) proves
managed-login text transport, not this complete product flow against a real account.

[Contract](../agents/PRIVATE_NATIVE_EVIDENCE_TASK.md),
[decision D30](../roadmap/DECISIONS.md#d30--preserve-private-native-evidence-publish-attributable-results).

## Implemented boundary

An annotation in the main store did not prevent direct raw selection. The new
adapter instead records the entire owned incarnation in a separate private
SQLite database, including unknown fields, late account/control events, errors,
stderr bytes and capture-gap payloads. The native worker still owns execution
and recovery. The adapter introduces no second agent loop or provider.

A persistent application-id marker makes ordinary TraceStore opening reject a
private database before SQLite opens it, including copied databases. Explicit
private-role access is a trusted-host interface. API/render/investigation entry
points also reject an already open private-role store. Private directories/files
are created with 0700/0600 permissions. These protect against accidental exposure;
they are not authentication against code running as the filesystem owner.

After closed-source validation, a main transaction appends `$capsule/result` and
its unique attempt/publication ledger entry together. Result outputSeqs contain
only main-store publication sequences. An additive outputEvidence envelope records
private-capsule publication provenance. Retrying publication returns the same
record; contradictory evidence conflicts. Child-shaped messages cannot mint the
host ledger. Existing public native recordings remain recoverable unchanged.

Private native inquiry admission resolves original request/output records through
the owner adapter and retains existing exact prompt, request pin, phase, terminal
and incarnation checks. Version 2 causes use capsule-scoped sequence/digest refs;
version 1 public causes retain their old format. Missing private proof cannot
create a new inquiry. Previously admitted continuations retain their causal host
ledger; copied history does not recreate execution authority.

Public context lineage observes a local derived publication. It does not invent
native RPC acknowledgements or expose private traffic as provider context. The
UI labels published results separately from their execution classification,
provides public fields/provenance, and retains exact result/context pins in reused
inputs and comparison. The original private recording may later be unavailable;
the past-tense notice does not promise current proof availability.

## Counterexamples that changed implementation

- Independent authored subprocesses sent a failed terminal after initial artifact
  calculation but during recorder cleanup. A second adapter could also publish
  while that capture was live. Both now fail without publication: a Unix advisory
  writer exclusion spans capture, reader termination, final recovery and commit.
  Busy recovery returns no artifact. A lingering reader retains exclusion until
  it terminates; recorder-host crash releases it for evidence-only recovery.
- A lost public completion callback recovers the exact already-published result
  after reopen without another native request. Publication/ledger rollback is
  atomic. Numeric private and public sequence collisions remain distinct.
- Inquiry refusal changes the Eidos receipt text. Lineage must select the original
  native artifact rather than validate that amended receipt as the publication.
- Actual browser inspection initially opened an empty source pane because the
  derived record had no native item ID. Explicit privateResultPublication
  projection now exposes the public record without fabricating item/completed.
- The earlier Round 3 demonstration counted only main turn/start records. Its
  owner-side report now counts scoped private requests through the resolver;
  reopen still proves two authored requests and no resend.

## Verification

Parent default suite: **1,244 passed / 53 explicit native skips in 24.51s**,
`/tmp/nema-private-parent-suite.log`. Focused final backend run: **168 passed**,
including 24 adapter cases, 12 store-role cases, 18 typed inquiry cases and five
actual API cases; `/tmp/nema-private-parent-focused.log`. The API cases preserve
raw private records on reopen, exclude control canaries from ordinary JSON/HTML,
SQL export and context manifests, reuse exact artifacts, refuse an inquiry,
recover a lost completion reply and reject new admission after private proof loss.

Independent final review re-ran the original owner-only and second-adapter
late-terminal schedules: zero publication in both, with the late failure privately
retained. Its 133 default checks passed, including the recorder-host crash test.
The accepted adapter SHA-256 was
`cd86288da8c2c668b5cc1421da31c1c29a4575de02ce1e61be95dd6a1b3567fd`.

Parent UI: **78 Bun tests / 416 assertions**, Svelte **0 errors / 0 warnings**,
build passed. Real-backend browser inspected conclusion and pending inquiry,
exact reload identity, unknown error/malformed outcomes, public source sequences
and result comparison at 1600px and 390px. All **56 GET responses** were captured
and free of the private canaries; no browser exceptions or private-capsule routes.
Root inspected desktop source/provenance and mobile comparison screenshots.

Browser report `/tmp/nema-private-evidence-real-browser.json`, SHA-256
`f8aa63b3a2567408416138fbd53fb9136821d9ba719c69ff8d34cac033cd7502`.
The failed pre-projection run remains separately retained locally. The successful
script is preserved as [private_native_evidence_browser.mjs](../../scripts/private_native_evidence_browser.mjs),
with configurable fixture paths/endpoints and mandatory publication checks.
Its portable adaptation was syntax-checked and reviewed against the successful
run; it was not represented as another browser execution.

Reproduce the API fixture without native/model calls:

```sh
uv run python scripts/private_native_evidence_demo.py --db /tmp/private-demo.db --output /tmp/private-demo.json
uv run python scripts/private_native_evidence_demo.py --db /tmp/private-demo.db --resume
uv run pytest tests/test_private_investigation.py tests/test_private_trace_role.py tests/test_private_inquiry_resolution.py tests/test_private_investigation_api.py
```

The browser script documents the isolated Chromium/Vite/API setup. Use a fresh
database for seeding; --resume requires its exact synthetic marker.

## Limits and next discriminator

The default retention ceiling is 32 capsules; each has logical record, byte,
outbound and diagnostic reserves. Those are not CPU/RSS, WAL or whole-disk quotas.
No retention/export UI is supplied. The deliberately published result text is not
guaranteed secret-free; this boundary separates raw control traffic, not semantic
content classification. Private metadata names remain identification, not grants.

The underlying legacy worker may calculate a result before its own cleanup;
new private publications explicitly revalidate after capture closes. Evidence
cannot establish bytes never received after bounded close. Cross-user access,
portable non-Unix locking and hostile owner code are outside the claim.

Next connect pinned attempt preparation, pending sign-in, exact owned cancellation
and reload recovery through the existing controller. No real-account usability,
complete auth-writer barrier, subscription execution or production readiness is
inferred from the offline native and authored-process evidence.
