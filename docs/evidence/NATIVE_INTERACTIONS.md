# Installed native interaction inspection — NEMA-SEED-1

**2026-10-13 · base `50d1bc91870b9118a84706606d6a06008dffcdf7` · branch
`codex/native-specialist-v2`.** This supplements the earlier
[boundary verification](NATIVE_VERIFICATION_INTEGRATED.md). It establishes
registration and empty-thread control behavior, with **zero model turns**.
Model-emitted interaction, answer delivery, interruption of a running turn,
and preservation of pending requests across restart remain **UNVERIFIED**.

The installed binary is `codex-cli 0.154.0`, Linux/aarch64, SHA-256
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.
The [versioned observation artifact](NATIVE_INTERACTIONS_0_154_0.json) preserves
returned native fields, errors, drained notifications, exact tool specifications,
and generated experimental schema hashes. Only the purpose-created temporary
directory prefix is normalized to `<probe>`. Schema entries are excerpts for
inspection, not standalone schemas; referenced definitions can be regenerated.

The probe uses temporary HOME/CODEX_HOME/cwd, an empty child environment except
four fixed variables, and an unauthenticated synthetic provider at loopback
port 9. It does not read account state, copy credentials, attach to another
process, or send a native request response. Its method allowlist rejects
`turn/start`, `turn/steer`, execution APIs, and server-request names before
launch. Generated schemas are inspected locally; no-model native results take
precedence over advertised contracts. Disposable user state does not certify
every machine-level configuration source, or establish an equivalent profile
for the owner's subscription-backed configuration.

| Interaction or context observation | Evidence on 0.154.0 | Integration consequence |
| --- | --- | --- |
| Function and namespaced dynamic tools on `thread/start` | **OBSERVED / TESTED:** canonical forms accepted; duplicate function names and invalid names rejected with `-32600`. | A controller evidence tool has a real registration path. Its invocation and reply lifecycle still require an authorized model test. |
| Dynamic tool schema validation | **OBSERVED:** legacy missing-type form and a string input schema are also accepted. | Registration acceptance is not a guarantee of model exposure or usable arguments. Supply the canonical locally validated specification. |
| Disabled environment access and empty workspace roots | **OBSERVED / TESTED:** `environments=[]`, `runtimeWorkspaceRoots=[]`, read-only/no-network, approval `never`; `instructionSources=[]`. | These are returned context/policy observations, not a complete provider input manifest or filesystem confidentiality boundary. |
| Collaboration presets | **OBSERVED:** `collaborationMode/list` returns Plan and Default. | Listing a preset does not establish which model tools are available in that mode. |
| Elicitation counters | **OBSERVED / TESTED:** increment returns `{count:1,paused:true}` on an empty thread; metadata still reports `idle`; decrement returns `{count:0,paused:false}`. No request envelope appeared in the bounded observation windows. | A host-incremented counter is not evidence that native requested information. Do not synthesize a pending request from it. |
| Interrupt with no active turn | **OBSERVED rejection:** `-32600`, `no active turn to interrupt`. | Advertised interrupt is not unconditional success. Running-turn cancellation remains unverified. |
| Request user input | **INSTALLED SCHEMA:** server request `item/tool/requestUserInput` includes `threadId`, `turnId`, `itemId`, `questions`, required `isBlocking`; deprecated `autoResolutionMs` is optional. | Recognize an actual request envelope with RPC `id` plus method and matching identities. Do not infer blocking from a timer field. |
| User-input response | **INSTALLED SCHEMA:** `answers` maps question IDs to `{answers:[string]}`. No cancellation discriminator is defined. | Respond to the original RPC identity only after controller admission. Do not invent a cancellation response shape. |
| Dynamic evidence request | **INSTALLED SCHEMA:** `item/tool/call` includes `threadId`, `turnId`, `callId`, `tool`, `arguments`, optional `namespace`; response includes `contentItems` and `success`. | Match incarnation, original RPC ID, registered tool, and native identities. A call's arguments are a proposal for context, not permission to inspect evidence. |
| Request resolution | **INSTALLED SCHEMA:** `serverRequest/resolved` contains `threadId` and `requestId`, without a turn ID. | Correlate to the existing pending record. Resolution alone does not prove an answer was delivered or that work succeeded. |
| MCP elicitation | **INSTALLED SCHEMA:** `mcpServer/elicitation/request` exists separately from direct user-input and dynamic-tool requests. | Keep unsupported under a specialist profile that excludes MCP. Schema presence does not establish safe startup or elicitation handling. |
| Terminal states | **INSTALLED SCHEMA:** `completed`, `interrupted`, `failed`, `inProgress`. | Only coherent, correlated recorded completion can become an artifact. This probe produces no model terminal evidence. |

The [official App Server documentation](https://learn.chatgpt.com/docs/app-server)
describes dynamic registration and server-originated tool calls, and explains
that `serverRequest/resolved` can follow an answer or cleanup on turn completion
or interruption. Those are advertised lifecycle semantics, not live observations
from this run. The installed schema's `isBlocking` requirement is more specific
than the page's timer discussion. Neither documentation nor a generated schema
proves the installed implementation will emit or accept a live interaction.

Reproduction (explicit no-model native opt-in):

```bash
NEMA_NATIVE_PROBE=1 \
  NEMA_INTERACTIONS_PROBE_OUTPUT=/tmp/nema-native-interactions.json \
  uv run pytest tests/test_native_interactions_probe.py
```

Verified result: **10 passed in 0.43 seconds**. This invocation captured the
observation artifact directly, without a second native run for serialization.
Default pytest runs the nine safety checks and skips the installed-native test.
The standalone equivalent is:

```bash
uv run python scripts/probe_native_interactions.py \
  --output /tmp/nema-native-interactions.json
```

Before promoting interaction support, the separate live gate must observe a
real request, controller response, and correlated terminal outcome using one
reviewed synthetic packet and a defensible pre-launch profile. That test needs
explicit user authorization for subscription usage. Reconnection/resume must
not revive pending authority from copied historical descriptions; no restart
or automatic retransmission of a native interaction is established here.
