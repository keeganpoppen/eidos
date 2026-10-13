# Authorized no-model verification of the integrated worker

**2026-10-13 · tested implementation `ebcead9a3d05b5ea2da7a066300d057ea304ac8b` on main.**
The owner explicitly authorized the two disposable, unauthenticated no-model probes.
This follow-up closes the pending preflight action in the integration handoff. It does
not authorize or establish an account-backed model turn.

## Execution and retained evidence

The opt-in suites ran once each through pytest:

```bash
NEMA_NATIVE_PROBE=1 uv run pytest tests/test_native_boundary_probe.py tests/test_native_mcp_probe.py
```

Result: **13 passed in 0.62 seconds; zero failures or skips**. A temporary pytest
capture hook wrote the unchanged return objects from the two probe functions, avoiding
a second native run merely to collect JSON. Its output and JUnit XML stayed under
`/tmp/nema-native-verified-20261013/`. The [sanitized combined observation artifact](NATIVE_BOUNDARY_INTEGRATED_0_154_0.json)
retains all returned fields and labels the tested revision and authorization scope.
Only purpose-created temporary path prefixes are normalized. The raw XML's host name
is not published. The [earlier branch artifact](NATIVE_BOUNDARY_0_154_0.json) is unchanged.

Installed native version: **codex-cli 0.154.0**, Linux/aarch64. Binary SHA-256:
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
Both child environments use temporary HOME/CODEX_HOME/work directories, no copied
credentials or personal history, and a synthetic provider at loopback port 9. RPC
allowlists exclude model operations. The actual investigation worker reaches a guard
that rejects `turn/start` before transport/recording; recorded model turns remain zero.
The MCP probe only handshakes, starts a synthetic thread, and inspects discovery.

## Observations and comparison

| Boundary | Fresh observation |
| --- | --- |
| Worker admission | Thread acknowledged; `readOnly`, network disabled, approval `never`, requested temporary cwd, empty environments; empty inventory accepted; pre-turn guard reached. |
| Standalone sandbox | Cwd write, outside-file overwrite and symlink overwrite denied with errno 30; loopback connection denied with errno 1. Host confirmed sentinels unchanged. Reading the synthetic outside file still succeeded. |
| Native configuration | Invalid feature type and conflicting permissions/sandbox rejected; unknown feature key accepted. Global config remains unsuitable as per-thread attestation. |
| MCP startup | Tools/resource/failed fixture processes wrote startup markers before inventory. Disabled fixture never launched. No tool invocation or resource read occurred. |
| MCP visibility | Compact tool inventory hides resource capabilities; full inventory exposes them. An empty tool map does not establish absent MCP capability. |
| Empty-thread lifecycle | Metadata read/fork acknowledged. Full-history methods and same-process resume still rejected on this tested path. Restart resume changes environment/root reporting despite supplied read-only policy. |

An independent reviewer compared complete reports: the native report is structurally
identical to the prior artifact; the MCP report differs only in the ordering of
`resources/list` and `resources/templates/list` discovery calls. No policy or recovery
implementation changed. The stricter worker gate remains appropriate.

## Limits and next step

This is fresh native compatibility evidence for the integrated code, not model
entitlement, a returned specialist answer, model-tool enforcement, provider context
capture, native-stack recovery, or complete containment. In particular, a post-start
MCP check cannot undo startup effects, and read-only does not mean packet-only reads.
These limitations remain visible in STATE and the workbench.

Only documentation/evidence changed after the probe. `uv run pytest tests/test_seed_context.py`
and whitespace/link checks validate that update; the integration's 361-test default
suite and frontend acceptance remain the evidence for the unchanged implementation.

The next meaningful gate is one separately authorized subscription-backed run of the
same synthetic packet in an audited configuration. Stage that packet using the exact
command in CURRENT_HANDOFF. Do not weaken admission, copy credentials into a test home,
silently use a paid API, or interpret this no-model authorization as model permission.
