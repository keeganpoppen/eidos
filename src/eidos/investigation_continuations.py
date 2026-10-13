from __future__ import annotations

"""Investigation-scoped admission and reintegration, not a process interpreter.

Only the fixed local evidence-review program is admitted here. All semantic
advancement belongs to ModelProcessRunner / ProcessRuntime. Native execution
is deliberately absent from this adapter.
"""

import json
from copy import deepcopy
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

    @staticmethod
    def _origin_attempt(investigation: dict[str, Any], attempt_id: str) -> dict[str, Any] | None:
        attempts = [investigation.get("attempt"), *investigation.get("attemptHistory", [])]
        return next((attempt for attempt in attempts if attempt is not None and attempt["id"] == attempt_id), None)

    @staticmethod
    def _require_active(link: dict[str, Any]) -> None:
        if link.get("cancelled") or link.get("cancellation") is not None:
            raise InvestigationError(409, "inquiry admission was cancelled; historical state cannot resume it")

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
        attempt = self._origin_attempt(investigation, link["attemptId"])
        native = investigation.get("nativeArtifact")
        if (
            row["continuation_id"] != continuation["id"]
            or attempt is None or attempt["status"] != "completed"
            or link["attemptId"] != attempt["id"]
            or continuation["attemptId"] != attempt["id"]
            or native is None or link["nativeArtifactId"] != native["id"]
        ):
            raise InvestigationError(409, "continuation does not match its admitted native attempt")
        observation = link.get("cause")
        if (continuation.get("origin") == "native-specialist") != (observation is not None):
            raise InvestigationError(409, "specialist provenance is not admitted by this host link")
        if observation is not None and (
            continuation.get("cause") != observation
            or continuation.get("origin") != "native-specialist"
            or continuation["question"] != observation["question"]
            or observation["investigationId"] != identifier
            or observation["attemptId"] != attempt["id"]
            or observation["contextId"] != attempt["contextId"]
            or observation["nativeArtifactId"] != native["id"]
        ):
            raise InvestigationError(409, "specialist question does not match its admitted native cause")
        state = link["runtime"]
        if state is not None and (
            state["key"] != continuation["id"]
            or state["investigationId"] != identifier
            or state["attemptId"] != attempt["id"]
            or (observation is not None and state.get("originMetadata") != observation)
        ):
            raise InvestigationError(409, "runtime does not belong to this investigation admission")
        if state is not None and any(continuation[key] != state.get(key) for key in _PUBLIC_REFS):
            raise InvestigationError(409, "historical continuation does not match its live admission")
        inquiry = continuation["inquiry"]
        if inquiry is not None and (state is None or inquiry["id"] != state.get("inquiryId")):
            raise InvestigationError(409, "inquiry does not match its admitted continuation")
        if observation is not None and inquiry is not None and (
            inquiry.get("cause") != observation or inquiry["question"] != observation["question"]
        ):
            raise InvestigationError(409, "inquiry does not match its admitted specialist cause")
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
            if continuation["origin"] == "native-specialist":
                continuation["inquiry"]["cause"] = deepcopy(continuation["cause"])

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

    def open_specialist(self, identifier: str, observation: dict[str, Any]) -> dict[str, Any]:
        """Admit a host-validated terminal native question, never an HTTP claim.

        The adapter validates recorded native evidence before calling here. This
        admission freezes that observation and checks its exact outer identities;
        copying it alone is not a live responder or continuation capability.
        """
        observation = deepcopy(observation)
        if (
            observation.get("schemaVersion") != 1
            or observation.get("origin") != "native-specialist"
            or observation.get("mode") != "terminal-needs-evidence"
            or observation.get("investigationId") != identifier
        ):
            raise InvestigationError(409, "unsupported specialist observation")
        attempt_id = _text(observation.get("attemptId"), "attemptId", 200)
        artifact_id = _text(observation.get("nativeArtifactId"), "nativeArtifactId", 200)
        question = _text(observation.get("question"), "question", 16000)
        body = {
            "requestId": "specialist-inquiry:" + _digest(_json([attempt_id, artifact_id])),
            "observation": observation,
        }
        with self.store._transaction():
            investigation = self.store._load(identifier)
            request_id, fingerprint, prior = self.store._request(body, "specialist-inquiry:" + identifier)
            if prior is None:
                attempt = investigation["attempt"]
                native = investigation["artifact"]
                if (
                    attempt is None or attempt["id"] != attempt_id or attempt["status"] != "completed"
                    or attempt["contextId"] != observation.get("contextId")
                    or investigation["status"] not in {"completed", "needs-evidence"} or native is None
                    or native["id"] != artifact_id or native["attemptId"] != attempt_id
                    or investigation["adoption"] is not None or investigation.get("continuation") is not None
                ):
                    raise InvestigationError(409, "specialist inquiry requires its completed, unadopted native result")
                continuation_id = "continuation_" + uuid.uuid4().hex
                investigation["continuation"] = {
                    "schemaVersion": 1, "id": continuation_id, "attemptId": attempt_id,
                    "origin": "native-specialist", "question": question,
                    "cause": observation, "status": "preparing", "error": None,
                    "realizationStatus": "ready",
                    **{key: None for key in _PUBLIC_REFS}, "inquiry": None,
                }
                investigation["nativeArtifact"] = native
                investigation["artifact"] = None
                investigation["status"] = "resuming"
                link = {
                    "attemptId": attempt_id, "nativeArtifactId": artifact_id,
                    "cause": observation, "runtime": None,
                }
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
            investigation, link = self._linked(identifier)
            self._require_active(link)
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
                        self._origin_attempt(investigation, link["attemptId"])["contextId"],
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

    def cancel(self, identifier: str, inquiry_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Revoke this host admission without fabricating a Discovery refusal.

        Cancellation competes with terminal response admission in one SQLite
        transaction. Once a terminal response is admitted it must be realized;
        otherwise an in-flight pending check cannot consume the requester.
        """
        body = _body(body, {"requestId", "note"})
        note = _text(body.get("note", ""), "note", 16000, empty=True)
        with self.store._transaction():
            investigation, link = self._linked(identifier)
            continuation = investigation["continuation"]
            inquiry = continuation["inquiry"]
            if inquiry is None or inquiry["id"] != inquiry_id:
                raise InvestigationError(404, "inquiry not found in this investigation")
            request_id, fingerprint, prior = self.store._request(body, "cancel-inquiry:" + identifier + ":" + inquiry_id)
            if prior is not None:
                return investigation
            self._require_active(link)
            if continuation["status"] == "completed" or any(
                response["decision"] in {"offer", "refuse"} for response in inquiry["responses"]
            ):
                raise InvestigationError(409, "inquiry already has an admitted terminal response")
            cancellation = {"requestId": request_id, "note": note, "inquiryId": inquiry_id}
            link["cancelled"] = True
            link["cancellation"] = cancellation
            continuation["cancellation"] = deepcopy(cancellation)
            continuation["status"] = inquiry["status"] = investigation["status"] = "cancelled"
            continuation["error"] = None
            continuation["realizationStatus"] = "cancelled"
            self._save_link(identifier, link)
            self.store._save(investigation)
            self.store._remember(request_id, fingerprint, identifier)
            return investigation

    def resume(self, identifier: str) -> dict[str, Any]:
        # A process-local lock protects the shared connection; SQLite transactions
        # and stable operation keys also serialize/replay independent controllers.
        with self.trace._lock:
            _, link = self._linked(identifier)  # Bad/missing admission is an HTTP conflict.
            self._require_active(link)
            try:
                return self._resume(identifier)
            except Exception as exc:
                # Retain every admitted response and checkpoint. Recovery is an
                # explicit local retry, never a native resend or inferred refusal.
                with self.store._transaction():
                    investigation, link = self._linked(identifier)
                    self._require_active(link)
                    if investigation["continuation"]["status"] == "completed":
                        return investigation
                    investigation["continuation"]["error"] = f"{type(exc).__name__}: {exc}"[:4000]
                    investigation["continuation"]["realizationStatus"] = "failed"
                    self.store._save(investigation)
                    return investigation

    def _resume(self, identifier: str) -> dict[str, Any]:
        with self.store._transaction():
            investigation, link = self._linked(identifier)
            self._require_active(link)
            continuation = investigation["continuation"]
            if continuation["status"] == "completed":
                return investigation
            if link["runtime"] is None:
                attempt = self._origin_attempt(investigation, link["attemptId"])
                context = next(c for c in investigation["contexts"] if c["id"] == attempt["contextId"])
                link["runtime"] = self.runtime.start(
                    key=continuation["id"], investigation_id=identifier,
                    attempt_id=attempt["id"],
                    native_artifact=investigation["nativeArtifact"], context=context,
                    question=continuation["question"],
                    origin_metadata=link.get("cause"),
                )
                self._project(investigation, link["runtime"])
                self._save_link(identifier, link)
                self.store._save(investigation)

        for _ in range(8):  # fixed two-operation Closure, no external calls
            with self.store._transaction():
                investigation, link = self._linked(identifier)
                self._require_active(link)
                continuation = investigation["continuation"]
                if continuation["status"] == "completed":
                    return investigation
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
                self._require_active(link)
                current = link["runtime"]
                if current["checkpointId"] != state["checkpointId"] or current.get("outcomeId") != state.get("outcomeId"):
                    continue  # another controller already saved this successor
                for key in _PROGRESS:
                    current[key] = advanced.get(key)
                self._project(investigation, current)
                continuation = investigation["continuation"]
                continuation["error"] = None
                continuation["realizationStatus"] = "ready"
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
            self._require_active(link)
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
            native_question = continuation["origin"] == "native-specialist"
            label = "Eidos specialist inquiry receipt" if native_question else "Eidos evidence review — synthetic continuation"
            content = {
                **{key: value for key, value in native.items() if key != "id"},
                "text": native["text"] + f"\n\n[{label}]\n" + receipt
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
            continuation["realizationStatus"] = "completed"
            if native_question:
                inquiry["status"] = "answered" if terminal["decision"] == "offer" else "refused"
                continuation["nativeNext"] = {
                    "status": "awaiting-admission", "contextId": None, "attemptId": None,
                }
            self.store._save(investigation)
            return investigation
