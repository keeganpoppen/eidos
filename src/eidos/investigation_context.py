from __future__ import annotations

"""Manifest projections of the existing investigation, never a second controller.

The frozen investigation packet owns input meaning. Manifests give its ingredients
addressable versions, and an attempt pins one projection before native dispatch.
Later recorder evidence adds correlations without changing that pin.
"""

import json
from typing import Any, Mapping

from .context_manifest import Boundary, ContextManifestStore, ContextObject, KnowledgeState, RuntimeIdentity
from .trace import TraceStore


THREAD_CONFIG = {
    "features.apps": False, "features.shell_tool": False,
    "features.multi_agent": False, "features.hooks": False,
    "features.memories": False, "web_search": "disabled",
}
TURN_SANDBOX = {"type": "readOnly", "networkAccess": False}


def _object(value: ContextObject) -> dict[str, Any]:
    return {"id": value.cid, "kind": value.kind, "data": value.data, "refs": dict(value.refs)}


class InvestigationContexts:
    def __init__(self, trace: TraceStore) -> None:
        self.trace = trace
        self.store = ContextManifestStore(trace)

    def _slot(self, kind: str, value: Any, *, projected: bool = False) -> str:
        content = self.store.put_content(kind, value)
        claim = self.store.claim(
            content, state=KnowledgeState.PROJECTED if projected else KnowledgeState.SELECTED,
            boundary=Boundary.APP_SERVER if projected else Boundary.LOCAL,
            rationale="Derived from the immutable investigation packet; does not establish native loading.",
        )
        return self.store.slot(claim)

    def attach(self, context: dict[str, Any]) -> None:
        """Project frozen data, never re-read current source indexes or files."""
        selection = {
            "question": context["question"], "selections": context["selections"],
            "coverage": context["coverage"], "builderVersion": "investigation-context-v1",
        }
        if context.get("artifactInputs"):
            selection.update(builderVersion="investigation-context-v2", artifactInputs=[
                {key: artifact[key] for key in ("investigationId", "artifactId", "rationale")}
                for artifact in context["artifactInputs"]
            ])
        entries = {
            "builder/selection": self._slot("investigation.selection.v1", selection),
            "input/user": self._slot("investigation.user-input.v1", {
                "text": context["projectedPrompt"],
            }, projected=True),
            "native/unknown": self.store.slot(
                self.store.unknown("Other native instructions, skills, integrations, model defaults and loading are not fully captured.", boundary=Boundary.APP_SERVER),
                self.store.unknown("Provider input, hidden instructions and request retries are not observed.", boundary=Boundary.PROVIDER),
            ),
        }
        if "inputOrigin" in context:
            entries["input/origin"] = self._slot("investigation.input-origin.v1", context["inputOrigin"])
        for record in context["records"]:
            entries[f"evidence/{record['seq']}"] = self._slot("investigation.frozen-record.v1", record)
        for artifact in context.get("artifactInputs", []):
            entries[f"artifact/{artifact['investigationId']}/{artifact['artifactId']}"] = self._slot(
                "investigation.frozen-artifact.v1", artifact)
        manifest = self.store.manifest(entries)
        if context.get("manifestId") not in (None, manifest.cid):
            raise ValueError("context manifest does not match its frozen packet")
        context["manifestId"] = manifest.cid

    def revision(self, context: Mapping[str, Any], parent: Mapping[str, Any] | None) -> None:
        self.store.record_event(
            context["id"] + "/preview", kind="revision", manifest=context["manifestId"],
            previous_manifest=parent.get("manifestId") if parent else None,
            details={"contextId": context["id"], "parentContextId": context["parentContextId"],
                     "interpretation": "Frozen packet projection; no activation or native delivery."},
        )

    def pin(self, investigation_id: str, attempt: dict[str, Any], context: dict[str, Any]) -> None:
        self.attach(context)  # also supports an unattempted legacy frozen packet
        policy = self._slot("investigation.native-policy.v1", {
            "threadConfig": THREAD_CONFIG, "approvalPolicy": "never",
            "sandboxPolicy": TURN_SANDBOX, "environments": [],
            "workingDirectory": "fresh temporary directory; path assigned by worker",
            "timeoutSeconds": attempt["timeoutSeconds"], "turnLimit": 1,
            "limits": "Native startup integrations are not contained; no token/cost cap.",
        }, projected=True)
        manifest = self.store.replace(context["manifestId"], "runtime/requested-policy", policy)
        name = attempt["id"] + "/app-server-input"
        self.store.pin_request(name, manifest, identity=RuntimeIdentity(
            process_name=investigation_id, attempt_id=attempt["id"],
        ))
        attempt.update(manifestId=manifest.cid, contextRequestName=name)

    def correlate(self, investigation: Mapping[str, Any]) -> None:
        """Record observed transport bytes; never infer delivery from a send log.

        Called after work/recovery inside a local transaction. No native calls.
        Each event's coordinates come from its own raw record, so later mapping
        hydration cannot rewrite the old claim or make exact replay conflict.
        """
        attempt = investigation["attempt"]
        if not attempt or not attempt.get("contextRequestName") or not attempt.get("source"):
            return
        pin = self.store.get_request(attempt["contextRequestName"])
        if (pin.ref("manifest") != attempt["manifestId"]
                or pin.data["identity"]["attempt_id"] != attempt["id"]
                or pin.data["identity"]["process_name"] != investigation["id"]):
            raise ValueError("request pin does not belong to this investigation attempt")
        context = next(c for c in investigation["contexts"] if c["id"] == attempt["contextId"])
        artifacts = [investigation.get("nativeArtifact"), investigation.get("artifact"),
                     *investigation.get("artifactHistory", [])]
        publication = next((value for value in artifacts if isinstance(value, dict)
                            and value.get("attemptId") == attempt["id"]
                            and value.get("kind") != "eidos-evidence-review"
                            and value.get("outputEvidence") is not None), None)
        if publication is not None:
            # This is an observation of a host publication. The original RPCs
            # remain private; copying them here would defeat that boundary.
            from .private_investigation import validate_publication
            validate_publication(self.trace, attempt, context, publication)
            seq = publication["outputSeqs"][0]
            identity = RuntimeIdentity(
                process_name=investigation["id"], incarnation_id=attempt["source"],
                thread_id=attempt.get("threadId"), turn_id=attempt.get("turnId"),
                attempt_id=attempt["id"],
            )
            evidence = self.store.freeze_trace(seq)
            receipt = {"version": 1, "attemptId": attempt["id"], "contextId": context["id"],
                       "publicationSeq": seq, "outputEvidence": publication["outputEvidence"],
                       "coverage": "Derived result publication. Original native traffic is retained privately; provider input remains unknown."}
            content = self.store.put_content("investigation.private-result-publication.v1", receipt)
            claim = self.store.claim(
                content, state=KnowledgeState.OBSERVED, boundary=Boundary.LOCAL,
                facet="derived-result-publication", evidence=(evidence,), scope=identity,
                rationale="Observed host publication after private native evidence validation; not a public raw RPC or provider-input observation.",
            )
            supplemental = self.store.replace(attempt["manifestId"], "native/result-publication", self.store.slot(claim))
            self.store.record_event(
                attempt["contextRequestName"] + f"/publication/{seq}", kind="correlation",
                manifest=attempt["manifestId"], request_name=attempt["contextRequestName"],
                identity=identity, boundary=Boundary.LOCAL, evidence=(evidence,),
                supplemental_manifest=supplemental,
                details={"observation": "derived-result-publication", "seq": seq,
                         "outputEvidence": publication["outputEvidence"], "providerContext": "unknown"},
            )
            return
        rows = self.trace.db.execute(
            "SELECT seq,direction,raw_text FROM trace_records WHERE source=? ORDER BY seq",
            (attempt["source"],),
        ).fetchall()
        messages = []
        for row in rows:
            try:
                payload = json.loads(row["raw_text"])
            except (ValueError, TypeError):
                continue
            if isinstance(payload, dict):
                messages.append((row, payload))
        requests = [(r, p) for r, p in messages if r["direction"] == "client_to_appserver"
                    and p.get("method") == "turn/start"]
        if len(requests) > 1:
            raise ValueError("native incarnation has multiple turn requests; context correlation is ambiguous")
        if not requests:
            return
        request_row, request = requests[0]
        if (not isinstance(request.get("params"), dict)
                or request["params"].get("input") != [{"type": "text", "text": context["projectedPrompt"]}]):
            raise ValueError("recorded native input differs from the pinned context")
        if "id" not in request:
            return
        if attempt.get("threadId") and request["params"].get("threadId") != attempt["threadId"]:
            raise ValueError("recorded input names a different native thread")
        observed = [(request_row, request, "recorded-outbound")]
        observed.extend((r, p, "native-acknowledgement") for r, p in messages
                        if r["seq"] > request_row["seq"] and r["direction"] == "appserver_to_client"
                        and type(p.get("id")) is type(request["id"]) and p.get("id") == request["id"]
                        and "method" not in p and ("result" in p or "error" in p))
        for row, payload, label in observed:
            result = payload.get("result")
            turn = result.get("turn") if isinstance(result, dict) else None
            if isinstance(turn, dict) and attempt.get("turnId") and turn.get("id") != attempt["turnId"]:
                raise ValueError("native acknowledgement names a different turn")
            identity = RuntimeIdentity(
                process_name=investigation["id"], incarnation_id=attempt["source"],
                thread_id=request["params"].get("threadId"),
                turn_id=turn.get("id") if isinstance(turn, dict) else None,
                request_id=str(request["id"]), attempt_id=attempt["id"],
            )
            evidence = self.store.freeze_trace(row["seq"])
            content = self.store.put_content("investigation.native-traffic.v1", payload)
            claim = self.store.claim(content, state=KnowledgeState.OBSERVED,
                boundary=Boundary.APP_SERVER, facet=label, evidence=(evidence,), scope=identity,
                rationale="Recorder observation only. Outbound logging precedes writing and does not prove delivery; an acknowledgement does not expose provider input.")
            supplemental = self.store.replace(attempt["manifestId"], "native/" + label, self.store.slot(claim))
            self.store.record_event(
                attempt["contextRequestName"] + f"/trace/{row['seq']}", kind="correlation",
                manifest=attempt["manifestId"], request_name=attempt["contextRequestName"],
                identity=identity, boundary=Boundary.APP_SERVER, evidence=(evidence,),
                supplemental_manifest=supplemental,
                details={"observation": label, "seq": row["seq"], "providerContext": "unknown"},
            )

    def lineage(self, investigation: Mapping[str, Any]) -> dict[str, Any]:
        attempt = investigation["attempt"]
        value = None
        if attempt:
            name, manifest = attempt.get("contextRequestName"), attempt.get("manifestId")
            value = {"id": attempt["id"], "manifestId": manifest, "requestName": name,
                     "pin": _object(self.store.get_request(name)) if name else None,
                     "events": [_object(event) for event in self.store.events(manifest)
                                if event.data["identity"].get("attempt_id") == attempt["id"]] if manifest else []}
        return {"schemaVersion": 1,
                "contexts": [{"contextId": c["id"], "manifestId": c.get("manifestId")} for c in investigation["contexts"]],
                "attempt": value, "error": investigation.get("contextLineageError")}

    def view(self, context: Mapping[str, Any], parent: Mapping[str, Any] | None = None) -> dict[str, Any]:
        manifest = context.get("manifestId")
        slots = []
        if manifest:
            for path, slot_id in self.store.entries(manifest).items():
                claims, gaps = [], []
                for _, ref in self.store.get(slot_id).refs:
                    obj = self.store.get(ref)
                    if obj.kind == "cm.claim":
                        claims.append({"id": obj.cid, **obj.data,
                            "content": _object(self.store.get(obj.ref("content"))),
                            "evidence": [cid for key, cid in obj.refs if key.startswith("evidence:")]})
                    else:
                        gaps.append({"id": obj.cid, **obj.data})
                slots.append({"path": path, "claims": claims, "gaps": gaps, "conflicts": []})
        changes = []
        if manifest and parent and parent.get("manifestId"):
            changes = [{"path": c.path, "before": c.before, "after": c.after, "operation": c.operation}
                       for c in self.store.diff(parent["manifestId"], manifest)]
        return {"contextId": context["id"], "manifestId": manifest, "slots": slots, "changes": changes}
