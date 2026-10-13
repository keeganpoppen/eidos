# Bounded capture and recovery acceptance

2026-10-13 · independent acceptance from `2c447e4` · synthetic subprocesses only.

The user-visible invariant is recoverable evidence: a native stream that cannot
be captured must leave an inspectable gap, without erasing an earlier accepted
completion or inventing completion from a partial frame. No native Codex process,
real model, credential, external service or production profile is used here.

## Verified result

The independent [acceptance tests](../../tests/test_native_capture_acceptance.py)
pass **24 tests** against integrated root source: transport contributions
`7f5d4e1`, `be3280d` and `acd6f04`
and the integrator's worker recovery cutoff. The source base is `eab1653` plus
those reviewed changes; the parent owns final integration and broader checks.

```sh
PYTHONPATH=/home/elkeegano.guest/eidos/src UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync pytest -o addopts='' -o pythonpath=/home/elkeegano.guest/eidos/src -q tests/test_native_capture_acceptance.py
```

Run that command from the acceptance worktree when reviewing isolated source;
after integration, ordinary `uv run pytest tests/test_native_capture_acceptance.py`
uses the repository implementation. Tests use real local Python subprocesses,
AppServerClient, TraceStore, InvestigationStore claim/update/complete pathways and
NativeInvestigationWorker run/recover. Only the worker client constructor is
replaced to inject small explicit transport limits; parsing, recording, attempt
mapping and recovery are the production implementations.

- Previously accepted whitespace, multibyte UTF-8 and unknown fields remain exact
  through invalid JSON, invalid UTF-8, non-object JSON, nonfinite timestamp and
  surrogate projection failures, then SQLite reopen. Nonstandard NaN and positive/
  negative Infinity literals are refused even though Python accepts them by default.
  Rejected bytes live inside
  valid internal JSON as exact base64; all retained raw records remain parseable.
- An unterminated deeply nested frame stops at its frame budget before decode.
  Combined stdout/stderr receipt stops at the aggregate limit plus one sentinel
  byte. Wire-byte event limits include whitespace and UTF-8 bytes, independently
  of the smaller reserialized object.
- Repeated unmatched wait_for timeouts retain event reservations. Subsequent
  pressure closes out of band; draining releases each reservation once and
  delivers the accepted queued events in order.
- A stderr frame breach preserves an already received incomplete UTF-8 stdout
  frame exactly in the same diagnostic. Clean stdout EOF wakes consumers while
  stderr remains observed until EOF, a limit, or explicit bounded cancellation.
- Real worker attempts distinguish a fully accepted terminal followed by capture
  loss from a truncated terminal or valid JSON lacking its JSONL delimiter.
  An accepted terminal whose delimiter exactly fills the aggregate budget also
  survives an extra byte in the same child write. Reopen recovers accepted
  terminals; incomplete ones stay unknown and cannot be reclaimed as
  a new dispatch. A child-authored captureGap object cannot establish host capture
  status or manufacture successful completion.
- Explicit trusted-import counterexamples place an actual host diagnostic before
  a later terminal, or append conflicting terminal evidence after a captured gap.
  Recovery stops at the first matching trusted gap. Earlier completion and an
  already saved artifact remain unchanged. Child-direction copies and unrelated
  source incarnations do not impose that cutoff. These imports test historical
  interpretation; the bounded reader itself admits no frames after its gap.

## Counterexamples resolved

The initial transport implementation closed its input reader on stdout EOF before
reading ready stderr. Three independent runs of a child that closed stdout and
wrote 4,096 stderr bytes reported zero stderr receipt and no failure. The transport
owner separated RPC closure from input-reader cancellation; the new regression
passes without waiting indefinitely for inherited pipes.

The initial worker recovery ignored capture diagnostics. An explicitly reordered
trusted fixture therefore recovered a terminal after a host gap, and a later
conflicting imported terminal could invalidate earlier accepted completion. The
integrator added a source-scoped, internal-direction, versioned capture cutoff
and a corresponding specialist event. Both counterexamples and their child-copy/
other-incarnation controls pass.

An independent reviewer also found that an aggregate breach discarded complete
allowed-prefix frames when they arrived in the same read as the excess byte.
The acceptance lane reproduced the resulting product consequence: a terminal
ending exactly at byte 32,768, followed by one extra byte, could not be recovered
after reopen. The transport follow-up parses only complete frames ending inside
the allowed prefix, then records the remaining fragment and proof byte. The
independent worker-level regression now retains the accepted completion and the
separate received-byte diagnostic.

A final parser counterexample delivered and stored a child object containing the
literal `NaN` as ordinary native evidence. Python's permissive decoder accepts
`NaN`, `Infinity` and `-Infinity`; these tokens are not JSON. The transport owner
added explicit constant rejection. All three acceptance cases preserve the prior
frame and store the rejected bytes inside a valid capture diagnostic after reopen.
This does not add a policy rejecting every large but syntactically valid number.

## Parent native compatibility check

On the integrated source, the parent ran the three existing disconnected native
probes with explicit opt-ins: **100 checks passed**, seven native turns and fourteen
authored local provider requests. Native 0.154.0 completed text, tool and exact-model
catalog cases under the existing namespace/process restrictions. No real model,
upstream request, credential, production admission or profile change occurred.

```sh
NEMA_NATIVE_SYNTHETIC_TURN_PROBE=1 NEMA_NATIVE_TOOL_BOUNDARY_PROBE=1 NEMA_NATIVE_MODEL_CATALOG_PROBE=1 NEMA_NATIVE_MODEL_CATALOG_EVIDENCE=/tmp/native-bounded-catalog.json uv run pytest tests/test_native_synthetic_turn_probe.py tests/test_native_tool_boundary_probe.py tests/test_native_model_catalog_probe.py
```

Future probe reports include the actual per-case nativeCapture status; checks
require its configured limits to match the internal trace record and capture to
finish without a gap. Historical committed raw reports retain their original
unbounded-transport classification. The parent catalog reproduction is
`/tmp/native_bounded_catalog_parent_20261013.json`; this local artifact is not a
requirement for default tests. The containing integration's full verification is
recorded in the [handoff](../agents/CURRENT_HANDOFF.md).

## Scope

These are received-wire and retained-event budgets, not child CPU/RSS, filesystem,
total SQLite size or external-effect quotas. Explicit cancellation can stop
observation of bytes the reader has not received. Stderr tail eviction remains a
bounded display policy. A database write failure cannot promise a durable gap;
the client reports diagnosticError separately.

The `internal` direction is a trusted-host recording convention. It does not
authenticate arbitrary database writers or convert copied descriptions into live
authority. Synthetic successful completion proves recovery of these authored
records, not model reasoning, caller admission or subscription compatibility.
Production native admission remains a separate closed gate.
