# Investigation Cycle A — acceptance evidence

**2026-10-13; implementation base `b40d9ac4758ac1129fbfe0ab26c00b28f777b3ae`.** This report describes the patch in the commit containing it. The seed audit remains historical. No personal traces, auth material, or provider calls were used.

The delivered loop is two recorded threads → exact evidence selection → saved context revisions and prompt preview → one admitted native attempt → recorded artifact → source return → conclusion adoption. It uses the existing trace/API/UI path. It does not yet connect an Eidos pending inquiry to the outer investigation.

## Reproduce without native account use

From the repository root, choose a fresh database path:

```bash
uv run python scripts/investigation_demo.py --db /tmp/nema-investigation-demo.db --serve
```

In another terminal:

```bash
cd ui
bun run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Both source histories and the specialist are explicitly synthetic. The fixture has 48 turns / 96 records, including unrelated build discussion. In the design thread, select the semantic recovery item and add its two source ranges (12 and 38). In the experiment thread, add the agent message at record 72. Name the investigation and ask which crash window remains unprotected. Save, inspect the exact input, revise the question, compare revisions, start the specialist, reload, follow source links, and adopt or reject its conclusion.

Restart the same synthetic service without reseeding or switching to real Codex:

```bash
uv run python scripts/investigation_demo.py --db /tmp/nema-investigation-demo.db --resume --serve
```

The normal `bash scripts/dev.sh` uses installed native Codex and consumes account resources when explicitly launched through its UI. The demo command above always uses the fake boundary process.

## Checks and observed outcome

- `uv sync`: passed; existing environment reused.
- `uv run pytest`: **176 passed** on the final Python implementation, including the new context, worker, API, lifecycle, and backpressure cases.
- `uv run eidos --help`: passed.
- `cd ui && bun install && bun run check && bun run build`: dependencies available; Svelte check has **0 errors / 0 warnings**, production build passed. Adapter-auto reports no deployment target; no site was deployed.
- `node scripts/check_investigation_ui.mjs`: rendered Chromium acceptance passed against synthetic API/Vite. Requires an isolated Chromium instance with `--remote-debugging-port=9222`. The script drives actual DOM selection, save, revision, dispatch, reload, source return, and adoption; verifies stored provenance and no horizontal overflow; saves the [screenshot](investigation-workbench.png). This is scripted product evidence, not a human speed measurement.
- Installed native interface checked with `codex --version` (**0.154.0**) and `codex app-server generate-json-schema --experimental --out /tmp/nema-native-schema`. These are local schema checks, **not a native model run**. Fixed feature settings were cross-checked against the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Scenario coverage

| Scenario | Evidence established | Still open |
| --- | --- | --- |
| V1-02 | Frozen raw bytes/hash, unknown fields, thread-scoped ranges, immutable historical context after index enrichment/reimport. | General generated-claim sufficiency/entailment. |
| V1-03 | Semantic disjoint support and item selection feed context; citation links restore exact source focus; saved work reloads. | Large real-history ergonomics and richer saved arrangements. |
| V1-04 | Two-thread packet, exact prompt preview, immutable parent-linked revisions, question/range/rationale comparison. | Full instructions/skills/config manifests and per-provider-request observation. |
| V1-05 | Native adapter exists; synthetic app-server verifies exact frozen prompt, fixed launch settings, attributable output. | An actual specialist run, native policy activation, and resource/cost observation. |
| V1-07 | Atomic duplicate claim, uncertain dispatch never replays, completion recovers before artifact commit, missing native mappings recovered, idempotent adoption. | Native history reconciliation after missing local evidence; surviving arbitrary native pending interactions. |
| V1-08 | Separate alternative can copy selected context; conclusion adoption retains baseline/source history. | Named comparison/adoption lineage between investigations and isolated workspace changes. |
| V1-12 | No generic TM endpoint; fixed host executor; reject substituted execution parameters, stale contexts and mismatched evidence; loopback/origin checks; native tool admission refuses known MCP tools. | Authentication between local users, secure remote authority, complete native tool isolation and OS resource accounting. |

V1-01, V1-06, V1-09/10/11 are not claimed delivered. All twelve release scenarios still need their complete acceptance evidence.

## Independent reviews and repairs

Three independent read-only scouts preceded implementation in disjoint worktrees. A context/store implementer separately reviewed API/worker authority and recovery; the worker implementer separately reviewed UI/product usefulness. One root integrator owned API/native-client changes and final acceptance.

The authority review reproduced a closed app-server client restarting with a new PID under the same evidence source. `AppServerClient` now serializes lifecycle operations and makes closure terminal. It also identified stdin backpressure bypassing request timeouts: an independent worker watchdog terminates the owned process before buffered stdin is closed. A synthetic 120,000-character write to a stalled reader ended in about 0.41 seconds with a 0.3-second deadline. The regression asserts a generous upper bound, not exact scheduling.

Recovery originally restored an artifact without its native navigation mapping. The coordinator now reconstructs absent thread/turn mappings from verified output evidence. Product review led to persistent save retry IDs, correct new-work selection, guarded source navigation, and a demo resume mode. Browser inspection led to wrapping long provenance IDs.

## Deliberate limits

This remains a trusted single-owner local service. A Name is not authentication. A read-only native sandbox is not packet-only visibility: native instructions and account configuration remain partly opaque. The worker disables applicable app/shell/delegation/hook/memory/web features, disables environment access, requests no network in its sandbox, and refuses configured or unresolved MCP tools before submitting a turn. Native acceptance of these settings is unverified; no universal isolation claim follows from a fake server.

The deadline bounds the owned process lifecycle with cleanup overhead. It is not an OS CPU/memory cap, total recorder byte quota, token budget, cost guarantee, or exactly-once external-effects guarantee. One worker at a time is enforced by the local controller; do not run multiple controllers as a scheduler. JSON state and listing entire context revisions are intentionally simple and need scaling work for large projects. Adoption records a conclusion and does not apply code or alter persistent instructions.
