# Bounded native recording and honest capture gaps

**2026-10-13 · active implementation from `2c447e4` · V1-02/07/12, C6.**
The integrator is finishing recorded-experiment composition and the model-catalog
challenge. Their changes do not modify the transport files owned here.

## User loop and observed failure

A native specialist or live reader must preserve what it observed and leave an
inspectable unknown outcome when its stream cannot be captured. AppServerClient
currently iterates unbounded text lines, records before the downstream worker's
limits, and retains unbounded event/backlog queues. Malformed JSON, invalid UTF-8
and a deeply nested approximately 600KiB object each reproduced failure with no
preserved record. A wait_for timeout moved all 20 queued events into its backlog;
a queue-size-only limit would miss that retained memory.

## Contract

Use one explicit configurable, reported input-budget contract in AppServerClient.
Read bounded binary chunks before decode. Bound a stdout frame, stderr frame/tail,
aggregate received stdout+stderr bytes, and retained event count/bytes. Defaults
must be finite and generous enough for existing fixtures; report actual limits.
These are transport limits, not a process CPU/RSS/disk quota or a mission budget.
Do not conflate received bytes with total database size including indexing/overhead.

Preserve accepted native JSON objects and unknown fields exactly through the
existing trace convention. On malformed, truncated or over-limit input, write a
valid host-internal capture diagnostic with stream, reason, configured limits,
counters, bounded exact captured bytes/base64 and explicit completeness. Never
store invalid JSON as an ordinary raw_text record: recovery reparses it. Guard
UTF-8 decode, JSON recursion/type errors and trace projection errors. Do not let
child-supplied diagnostic-looking JSON establish host capture status.

All retained events, including wait_for's local skipped list and _backlog, keep
count/byte reservations until delivered to the external consumer. Release once.
Close out of band so a full event queue cannot prevent pending requests waking.
Latch the reason once, stop only the owned child and preserve existing bounded
cancellation behavior when a descendant retains a pipe. No automatic retry or
synthetic native completion. An earlier accepted terminal event remains evidence;
a truncated terminal or gap before required completion remains unknown. Later
capture loss must remain separately inspectable and cannot rewrite prior artifacts.

## Ownership and integration

- history_ui agent: `/tmp/nema-bounded-native-transport`, branch
  `codex/bounded-native-transport`; owns `src/eidos/codex.py`, existing
  `tests/test_codex.py` and a unique new transport test file if clearer. No worker,
  API, trace schema, shared docs or native profile changes without coordination.
- Root: shared contract, worker/recovery integration only if needed, source review,
  full-suite verification, docs, final main commit. One integrator owns merging.
- Independent acceptance: separate contract/worktree follows implementation shape;
  focus on capture trust and reopen/unknown outcome counterexamples.
- Native lane: model-catalog evidence review is separate; no credentials, upstream
  traffic, real model calls or production admission are authorized by this packet.

Use only local authored subprocesses for this implementation and default tests.
Keep nonblocking writes, RPC correlation and native incarnation terminality intact.

## Discriminating checks

Endless unterminated stdout/stderr; fragmented UTF-8; malformed/deep JSON; bounded
small-message floods; repeated wait_for timeouts; closure with a full queue;
stderr breach while stdout holds a partial frame; exact unknown-field retention;
accepted terminal versus truncated terminal followed by database reopen; and a
child-authored fake capture marker. Verify pending RPC waiters wake promptly,
limits apply before allocation/recording grows without bound, prior frames remain
readable, and no capture diagnostic is interpreted as successful native work.
