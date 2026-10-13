# Current handoff — bounded native capture and recovery

**NEMA-SEED-1 · 2026-10-13 · integration base `eab1653` on main.**
The continuing mission remains active; [PROGRAM](../PROGRAM.md) owns conjectures and
opportunity ordering. The previous [experiment/catalog integration](../history/RECORDED_EXPERIMENTS_AND_MODEL_CATALOG.md)
is pushed as `eab1653437c77e4f0eb387721a2db13f9d9e1688`; [CI passed](https://github.com/keeganpoppen/eidos/actions/runs/38462571280).
A green milestone does not complete the mission or V1.

## Integrated loop

Native capture now records finite input limits before launch and preserves bounded
exact rejected/partial bytes in a valid internal capture-gap envelope. Accepted
JSON objects retain unknown fields and original text. Events keep their wire-byte
and count reservations through queues, wait_for's skipped list and backlog.
Closure wakes waiters independently of a full event queue and stops the owned child.

A source-scoped trusted capture gap ends recovery interpretation for that native
incarnation. Completion already recorded before it survives; truncated completion
and terminals imported after it cannot manufacture success. A child-authored copy
of the marker grants no authority. There is no automatic retry or invented native
completion. See [contract](../BOUNDED_NATIVE_TRANSPORT_TASK.md) and [independent acceptance](../../evidence/NATIVE_CAPTURE_ACCEPTANCE.md).

Accepted transport: `7f5d4e1`, `be3280d`, `acd6f04`; independent acceptance:
`af51b3f`, `5cdc877`, `32c1e47`, `bbf4269`. Root owns worker cutoff, actual capture
metadata in the three local-provider probes, integration and docs. Review resolved
stderr loss after stdout EOF, post-gap recovery/contradiction, chunk-dependent loss
of a terminal exactly at the byte cap, and non-JSON NaN/Infinity constants.

Defaults per incarnation: stdout frame 4MiB, stderr frame 256KiB, combined receipt
64MiB, retained events 1,024/8MiB, stderr tail 200 lines/256KiB. Frames include their
newline; at most one extra proof byte is read beyond a byte limit. These are wire
budgets, not process memory/CPU, outbound RPC, total SQLite or external-effect quotas.
Storage failure reports diagnosticError without claiming a durable gap exists.

## Verification

- Parent final full Python suite: **947 passed, 41 explicit native checks skipped**.
  Independent acceptance plus context checks: **29 passed**. Diff check passed.
- Independent acceptance: **24 passed** against root transport/worker source,
  using authored local Python processes and real store/worker recovery pathways.
- Parent native opt-in across text, tool and exact-catalog probes: **100 passed**.
  Seven contained native turns / fourteen authored local provider requests;
  **zero real model/upstream requests or credentials**, native 0.154.0. Reported
  capture limits match the actual internal trace record; no capture failure.
  Catalog reproduction: `/tmp/native_bounded_catalog_parent_20261013.json`.
- No frontend change in this wave. Previous eab1653 UI evidence remains **73 Bun
  tests / 385 assertions**, Svelte 0 errors/warnings, build and desktop/mobile
  browser acceptance passed. Those are previous integration results.
- Historical raw probe reports remain unchanged; future reports now include
  actual nativeCapture status and explicitly deny a database byte quota.

## Active work and next move

Root has completed verification and is preparing one coherent main commit/push. Transport
worktree `/tmp/nema-bounded-native-transport` is clean at `acd6f04`; acceptance
`/tmp/nema-native-capture-acceptance` is clean at `bbf4269`. Their patches are applied
on main. No user decision blocks ordinary repository progress.

Two independent read-only scouts continue while integration finishes:
- `history_ui`: identify a useful next product loop from reversible context recipes
  versus returning-person recovery; reuse actual experiment/draft interfaces.
- `native_frontier`: review the aggregate-prefix fix and prepare a narrow paired
  original/derived Astra startup-catalog challenge. No new native turns yet.

**Next runnable action:** commit/push bounded capture, inspect CI, then select the
next coherent product and
native discriminator contracts. Continue the mission; do not stop at green checks.

Native scout direction: prefer a supported narrow ordinary-Responses model if
available to the eventual account. A transparently derived Astra startup catalog
may set only tool_mode=direct and experimental_supported_tools=[]; preserve slug,
Lite mode and other metadata, original hash, exact semantic patch and derived hash.
Supported agents.enabled=false plus multi_agent_v2=false and sleep/current-time
controls need a paired no-credential probe. This is local policy, not authentic
upstream metadata or proof of entitlement. An actual subscription/auth flow remains
a later separate decision; never copy existing auth or impersonate Desktop.

## Limits

Synthetic transport and recovery are verified, not model reasoning or live caller
admission. Internal direction is a trusted-host convention, not authentication of
arbitrary database writers. Native admission remains closed. Catalog presence does
not establish account availability. An absent action item does not establish that
no native handler ran. Same-database scripted UI recovery does not measure human
reorientation benefit. Generic TM remains a trusted-host interface.

Integrated and pushed as `555a3170fd51a2ca20e2e15b82f7a740fa82e4e5`; [CI passed](https://github.com/keeganpoppen/eidos/actions/runs/38464488502).
