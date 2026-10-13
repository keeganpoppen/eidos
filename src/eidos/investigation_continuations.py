from __future__ import annotations

"""Investigation-scoped admission and reintegration, not a process interpreter.

Only the fixed local evidence-review program is admitted here. All semantic
advancement belongs to ModelProcessRunner / ProcessRuntime. Native execution
is deliberately absent from this adapter.
"""

import json
from typing import Any, Mapping
import uuid

from .investigation import InvestigationError, InvestigationStore, _body, _digest, _json, _text
from .investigation_runtime import InvestigationRuntime


_PROGRESS = (
    "processId", "protocolId", "modelId", "checkpointId", "initialCheckpointId",
    "outcomeId", "contextName", "inquiryId", "openedOccurrenceId", "pending",
)
_PUBLIC_REFS = _PROGRESS[:7]
MAX_RESPONSES = 32


class InvestigationContinuations:
    def __init__(self, store: InvestigationStore) -> None:
        self.store = store
        self.trace = store.trace
        # Schema setup is outside a transaction (SQLite executescript commits).
        self.runtime = InvestigationRuntime(self.trace)
        with self.trace._lock:
            self.trace.db.execute(
                "CREATE TABLE IF NOT EXISTS investigation_runtime_links("
                "investigation_id TEXT PRIMARY KEY REFERENCES investigations(id),"
                "continuation_id TEXT NOT NULL UNIQUE, state_json TEXT NOT NULL)"
            )

    def _linked(self, identifier: str) -> tuple[dict[str, Any], dict[str, Any]]:
        investigation = self.store._load(identifier)
        row = self.trace.db.execute(
            "SELECT continuation_id,state_json FROM investigation_runtime_links WHERE investigation_id=?",
            (identifier,),
        ).fetchone()
        continuation = investigation.get("continuation")
        if row is None or continuation is None:
            raise InvestigationError(409, "investigation has no admitted Eidos continuation")
        link = json.loads(row["state_json"])
        attempt = investigation["attempt"]
        native = investigation.get("nativeArtifact")
        if (
            row["continuation_id"] != continuation["id"]
            or attempt is None or attempt["status"] != "completed"
            or link["attemptId"] != attempt["id"]
            or continuation["attemptId"] != attempt["id"]
            or native is None or link["nativeArtifactId"] != native["id"]
        ):
            raise InvestigationError(409, "continuation does not match its admitted native attempt")
        state = link["runtime"]
        if state is not None and (
            state["key"] != continuation["id"]
            or state["investigationId"] != identifier
            or state["attemptId"] != attempt["id"]
        ):
            raise InvestigationError(409, "runtime does not belong to this investigation admission")
        if state is not None and any(continuation[key] != state.get(key) for key in _PUBLIC_REFS):
            raise InvestigationError(409, "historical continuation does not match its live admission")
        inquiry = continuation["inquiry"]
        if inquiry is not None and (state is None or inquiry["id"] != state.get("inquiryId")):
            raise InvestigationError(409, "inquiry does not match its admitted continuation")
        return investigation, link

    def _save_link(self, identifier: str, link: dict[str, Any]) -> None:
        self.trace.db.execute(
            "UPDATE investigation_runtime_links SET state_json=? WHERE investigation_id=?",
            (_json(link), identifier),
        )

    def _project(self, investigation: dict[str, Any], state: dict[str, Any]) -> None:
        continuation = investigation["continuation"]
        for key in _PUBLIC_REFS:
            continuation[key] = state.get(key)
        if state.get("inquiryId") is not None and continuation["inquiry"] is None:
            continuation["inquiry"] = {
                "id": state["inquiryId"], "question": continuation["question"],
                "status": "pending", "openedOccurrenceId": state["openedOccurrenceId"],
                "responses": [],
            }

    def open(self, identifier: str, body: Mapping[str, Any]) -> dict[str, Any]:
        body = _body(body, {"requestId", "attemptId", "question"})
        attempt_id = _text(body.get("attemptId"), "attemptId", 200)
        question = _text(body.get("question"), "question", 16000)
        with self.store._transaction():
            investigation = self.store._load(identifier)
            request_id, fingerprint, prior = self.store._request(body, "continuation:" + identifier)
            if prior is None:
                attempt = investigation["attempt"]
                if (
                    attempt is None or attempt["id"] != attempt_id or attempt["status"] != "completed"
                    or investigation["status"] != "completed" or investigation["artifact"] is None
                    or investigation["adoption"] is not None or investigation.get("continuation") is not None
                ):
                    raise InvestigationError(409, "review requires this investigation's completed, unadopted native artifact")
                continuation_id = "continuation_" + uuid.uuid4().hex
                investigation["continuation"] = {
                    "schemaVersion": 1, "id": continuation_id, "attemptId": attempt_id,
                    "origin": "synthetic-eidos", "question": question,
                    "status": "preparing", "error": None,
                    **{key: None for key in _PUBLIC_REFS}, "inquiry": None,
                }
                investigation["nativeArtifact"] = investigation["artifact"]
                investigation["artifact"] = None
                investigation["status"] = "resuming"
                link = {"attemptId": attempt_id, "nativeArtifactId": investigation["nativeArtifact"]["id"], "runtime": None}
                self.trace.db.execute(
                    "INSERT INTO investigation_runtime_links VALUES (?,?,?)",
                    (identifier, continuation_id, _json(link)),
                )
                self.store._save(investigation)
                self.store._remember(request_id, fingerprint, identifier)
        return self.resume(identifier)

    def inquiry(self, identifier: str, inquiry_id: str) -> dict[str, Any]:
        with self.trace._lock:
            if self.store._load(identifier).get("continuation") is None:
                raise InvestigationError(404, "inquiry not found in this investigation")
            investigation, _ = self._linked(identifier)
            inquiry = investigation["continuation"]["inquiry"]
            if inquiry is None or inquiry["id"] != inquiry_id:
                raise InvestigationError(404, "inquiry not found in this investigation")
            return inquiry

    def respond(self, identifier: str, inquiry_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        body = _body(body, {"requestId", "decision", "note", "selections"})
        decision = body.get("decision")
        if not isinstance(decision, str) or decision not in {"defer", "offer", "refuse"}:
            raise InvestigationError(400, "decision must be offer, refuse, or defer")
        note = _text(body.get("note", ""), "note", 16000, empty=True)
        if decision != "offer" and "selections" in body:
            raise InvestigationError(400, "only offers may supply evidence selections")
        with self.store._transaction():
            if self.store._load(identifier).get("continuation") is None:
                raise InvestigationError(404, "inquiry not found in this investigation")
            investigation, _ = self._linked(identifier)
            inquiry = investigation["continuation"]["inquiry"]
            if inquiry is None or inquiry["id"] != inquiry_id:
                raise InvestigationError(404, "inquiry not found in this investigation")
            request_id, fingerprint, prior = self.store._request(body, "response:" + identifier + ":" + inquiry_id)
            if prior is None:
                if any(response["decision"] in {"offer", "refuse"} for response in inquiry["responses"]):
                    raise InvestigationError(409, "inquiry already has an admitted terminal response")
                if len(inquiry["responses"]) >= MAX_RESPONSES or (decision == "defer" and len(inquiry["responses"]) >= MAX_RESPONSES - 1):
                    raise InvestigationError(409, "inquiry response budget exhausted")
                evidence = None
                if decision == "offer":
                    evidence = self.store._context(
                        {"question": inquiry["question"], "selections": body.get("selections")},
                        investigation["attempt"]["contextId"],
                    )
                inquiry["responses"].append({
                    "id": "response_" + uuid.uuid4().hex, "requestId": request_id,
                    "decision": decision, "note": note, "status": "admitted",
                    "evidenceContext": evidence, "occurrenceId": None,
                    "disclosureCutId": None, "responseValueId": None,
                })
                investigation["continuation"]["status"] = "resuming"
                investigation["status"] = "resuming"
                self.store._save(investigation)
                self.store._remember(request_id, fingerprint, identifier)
        return self.resume(identifier)

    def resume(self, identifier: str) -> dict[str, Any]:
        # A process-local lock protects the shared connection; SQLite transactions
        # and stable operation keys also serialize/replay independent controllers.
        with self.trace._lock:
            self._linked(identifier)  # Bad/missing admission is an HTTP conflict.
            try:
                return self._resume(identifier)
            except Exception as exc:
                # Retain every admitted response and checkpoint. Recovery is an
                # explicit local retry, never a native resend or inferred refusal.
                with self.store._transaction():
                    investigation, _ = self._linked(identifier)
                    if investigation["continuation"]["status"] == "completed":
                        return investigation
                    investigation["continuation"]["error"] = f"{type(exc).__name__}: {exc}"[:4000]
                    self.store._save(investigation)
                    return investigation

    def _resume(self, identifier: str) -> dict[str, Any]:
        with self.store._transaction():
            investigation, link = self._linked(identifier)
            continuation = investigation["continuation"]
            if continuation["status"] == "completed":
                return investigation
            if link["runtime"] is None:
                context = next(c for c in investigation["contexts"] if c["id"] == investigation["attempt"]["contextId"])
                link["runtime"] = self.runtime.start(
                    key=continuation["id"], investigation_id=identifier,
                    attempt_id=investigation["attempt"]["id"],
                    native_artifact=investigation["nativeArtifact"], context=context,
                    question=continuation["question"],
                )
                self._project(investigation, link["runtime"])
                self._save_link(identifier, link)
                self.store._save(investigation)

        for _ in range(8):  # fixed two-operation Closure, no external calls
            with self.store._transaction():
                investigation, link = self._linked(identifier)
                continuation = investigation["continuation"]
                inquiry = continuation["inquiry"]
                if inquiry is not None:
                    for response in inquiry["responses"]:
                        if response["status"] == "admitted":
                            link["runtime"], fields = self.runtime.respond(link["runtime"], response)
                            response.update(fields)
                            response["status"] = "committed"
                            inquiry["status"] = "deferred" if response["decision"] == "defer" else response["decision"]
                    self._save_link(identifier, link)
                    self.store._save(investigation)
                state = link["runtime"]
            if state.get("outcomeId") is not None:
                return self._complete(identifier)
            # Each runtime commit remains durable even if saving the outer
            # pointer below fails. The old checkpoint recovers the same result.
            advanced = self.runtime.advance(state)
            with self.store._transaction():
                investigation, link = self._linked(identifier)
                current = link["runtime"]
                if current["checkpointId"] != state["checkpointId"] or current.get("outcomeId") != state.get("outcomeId"):
                    continue  # another controller already saved this successor
                for key in _PROGRESS:
                    current[key] = advanced.get(key)
                self._project(investigation, current)
                continuation = investigation["continuation"]
                continuation["error"] = None
                continuation["status"] = "pending" if current.get("pending") else "resuming"
                investigation["status"] = continuation["status"]
                self._save_link(identifier, link)
                self.store._save(investigation)
                if current.get("pending"):
                    # A source decision may have arrived concurrently after the
                    # read that returned Pending; the next explicit resume sees it.
                    return investigation
        raise RuntimeError("evidence review exceeded its local continuation budget")

    def _complete(self, identifier: str) -> dict[str, Any]:
        with self.store._transaction():
            investigation, link = self._linked(identifier)
            continuation = investigation["continuation"]
            if continuation["status"] == "completed":
                return investigation
            inquiry = continuation["inquiry"]
            terminal = next(r for r in inquiry["responses"] if r["decision"] in {"offer", "refuse"} and r["status"] == "committed")
            native = investigation["nativeArtifact"]
            evidence = terminal["evidenceContext"]
            receipt = (
                "Evidence offered and incorporated into the Eidos context."
                if terminal["decision"] == "offer" else
                "Evidence refused; the Eidos context was not expanded."
            )
            content = {
                **{key: value for key, value in native.items() if key != "id"},
                "text": native["text"] + "\n\n[Eidos evidence review — synthetic continuation]\n" + receipt
                    + " This receipt records the evidence decision; it is not a new native analysis.",
                "kind": "eidos-evidence-review", "nativeArtifactId": native["id"],
                "continuationId": continuation["id"], "processId": continuation["processId"],
                "outcomeId": continuation["outcomeId"], "inquiryId": inquiry["id"],
                "responseId": terminal["id"], "decisionOccurrenceId": terminal["occurrenceId"],
                "contextName": continuation["contextName"],
                "evidenceContextId": None if evidence is None else evidence["id"],
            }
            investigation["artifact"] = {**content, "id": "artifact_" + _digest(_json(content))}
            investigation["status"] = continuation["status"] = "completed"
            continuation["error"] = None
            self.store._save(investigation)
            return investigation
