from __future__ import annotations

"""Interpret recorded specialist output; this module never admits native work.

The terminal protocol is a fallback for a worker that cannot service an interactive
request. Its result describes a need for evidence, not a suspended native stack.
Only the controller may use this evidence to admit an Eidos continuation. Returning
or copying an envelope from this module does not grant response or execution authority.
"""

import hashlib
import json
from typing import Any, Literal, Mapping, NotRequired, Protocol, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .investigation import InvestigationStore


INQUIRY_INSTRUCTION = """If missing evidence prevents a supported conclusion, end this native attempt with exactly one final message containing only this JSON object (no Markdown fences or surrounding prose):
{"schemaVersion":1,"kind":"nema-needs-evidence","question":"The specific question requiring additional evidence","cause":"Why the selected evidence cannot answer it"}
Use exactly those four fields; question and cause must be nonempty strings. Do not include investigation, attempt, context, event, authority, or continuation identifiers. This terminal result asks Eidos to record an inquiry. It does not keep this native turn waiting, and any later specialist work requires a separately admitted new attempt. An offered source is evidence to assess, not automatically factual truth. If the evidence is sufficient, return your ordinary supported conclusion instead."""


class NativeInquiryEvent(TypedDict):
    seq: int
    source: str
    threadId: str
    turnId: str
    method: Literal["item/completed", "turn/completed"]
    sha256: str


class PrivateNativeRecord(TypedDict):
    kind: Literal["private-capsule-record"]
    capsuleId: str
    seq: int
    sha256: str


class PrivateNativeInquiryEvent(TypedDict):
    source: str
    threadId: str
    turnId: str
    method: Literal["item/completed", "turn/completed"]
    evidence: PrivateNativeRecord


class NativeInquiryAdmission(TypedDict):
    schemaVersion: Literal[1, 2]
    origin: Literal["native-specialist"]
    mode: Literal["terminal-needs-evidence"]
    investigationId: str
    attemptId: str
    contextId: str
    nativeArtifactId: str
    question: str
    cause: str
    nativeEvent: NativeInquiryEvent | PrivateNativeInquiryEvent
    requestSeq: NotRequired[int]
    request: NotRequired[PrivateNativeRecord]


class SpecialistContinueRequest(TypedDict):
    """POST /api/investigations/:id/continue; admits one new native attempt."""

    requestId: str
    continuationId: str
    contextId: str


class InquiryCancelRequest(TypedDict):
    """Owner cancellation intent; identifiers never supply live authority."""

    requestId: str
    note: NotRequired[str]


class NativeEvidenceRecovery(Protocol):
    def recover(
        self, attempt: Mapping[str, Any], context: Mapping[str, Any],
    ) -> dict[str, Any] | None: ...


class NativeInquiryError(ValueError):
    """A claimed inquiry cannot be bound to the required recorded evidence."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NativeInquiryError("native inquiry contains a duplicate JSON field")
        result[key] = value
    return result


def parse_terminal_inquiry(text: Any) -> dict[str, Any] | None:
    """Recognize the reserved protocol; parsing supplies no admission authority."""
    if not isinstance(text, str):
        return None
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "nema-needs-evidence":
        return None
    # Ordinary output may be JSON. Only this exact protocol marker activates its
    # strict versioned parser; unknown fields remain in the untouched artifact.
    payload = json.loads(text, object_pairs_hook=_unique_object)
    if set(payload) != {"schemaVersion", "kind", "question", "cause"}:
        raise NativeInquiryError("native inquiry has unsupported or missing protocol fields")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise NativeInquiryError("native inquiry schemaVersion is unsupported")
    for field in ("question", "cause"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 16000:
            raise NativeInquiryError(f"native inquiry {field} must be a nonempty bounded string")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise NativeInquiryError(f"native inquiry {field} must be valid UTF-8") from None
    return payload


def terminal_inquiry(
    store: InvestigationStore, identifier: str, worker: NativeEvidenceRecovery,
) -> NativeInquiryAdmission | None:
    """Read a completed attempt's exact terminal inquiry, without side effects.

    The worker's evidence-only recovery validates terminal coherence and the frozen
    input. This adapter additionally binds the strict output interpretation to one
    original final event. Admission must recheck these identities transactionally:
    this returned description is not a lock, an authority token, or a live handle.
    """
    investigation = store.get(identifier)
    attempt = investigation.get("attempt")
    if not isinstance(attempt, dict) or attempt.get("status") != "completed":
        return None
    candidates = [investigation.get("nativeArtifact"), investigation.get("artifact")]
    artifact = next((
        value for value in candidates
        if isinstance(value, dict) and value.get("attemptId") == attempt.get("id")
        and value.get("kind") != "eidos-evidence-review"
    ), None)
    if artifact is None:
        return None
    payload = parse_terminal_inquiry(artifact.get("text"))
    if payload is None:
        return None
    if artifact.get("contextId") != attempt.get("contextId"):
        raise NativeInquiryError("native inquiry artifact belongs to a different context")
    # A copied Investigation/attempt/event description cannot claim the original
    # host's pre-send association. This protocol requires the immutable pin from
    # claim(); legacy unpinned native results remain readable, not executable.
    request_name = attempt.get("contextRequestName")
    if not isinstance(request_name, str):
        raise NativeInquiryError("native inquiry requires its admitted request pin")
    try:
        pin = store.contexts.store.get_request(request_name)
    except (KeyError, ValueError) as exc:
        raise NativeInquiryError("native inquiry request pin is unavailable") from exc
    if (pin.data["identity"].get("process_name") != identifier
            or pin.data["identity"].get("attempt_id") != attempt["id"]
            or pin.ref("manifest") != attempt.get("manifestId")):
        raise NativeInquiryError("native inquiry request pin belongs to another investigation or attempt")
    contexts = [value for value in investigation["contexts"] if value.get("id") == attempt.get("contextId")]
    if len(contexts) != 1:
        raise NativeInquiryError("native inquiry requires one frozen attempt context")
    for field in ("id", "contextId", "source", "threadId", "turnId"):
        if not isinstance(attempt.get(field), str) or not attempt[field]:
            raise NativeInquiryError(f"native inquiry requires a recorded attempt {field}")
    if not isinstance(artifact.get("id"), str) or not artifact["id"]:
        raise NativeInquiryError("native inquiry requires an attributable native artifact")

    try:
        recovered = worker.recover(attempt, contexts[0])
    except Exception as exc:
        if artifact.get("outputEvidence") is not None:
            raise NativeInquiryError("Private inquiry evidence recovery failed.") from None
        raise NativeInquiryError(f"native inquiry evidence recovery failed: {exc}") from exc
    if recovered is None or any(
        recovered.get(field) != artifact.get(field) for field in ("text", "outputSeqs")
    ):
        raise NativeInquiryError("native inquiry does not match the recovered native result")
    evidence_trace = store.trace
    evidence_artifact = artifact
    capsule_id = None
    if artifact.get("outputEvidence") is not None:
        try:
            resolver = getattr(worker, "resolve_result_evidence", None)
            if not callable(resolver):
                raise ValueError("private resolver unavailable")
            resolved = resolver(attempt, contexts[0], artifact)
            envelope = artifact["outputEvidence"]
            if (resolved["kind"] != "private-capsule"
                    or resolved["capsuleId"] != envelope["capsuleId"]
                    or resolved["trace"].role != "private-control"
                    or any(resolved["attempt"].get(key) != attempt.get(key)
                           for key in ("id", "contextId", "source", "threadId", "turnId"))
                    or any(resolved["artifact"].get(key) != artifact.get(key)
                           for key in ("text", "executionEvidence"))):
                raise ValueError("private evidence binding differs")
            capsule_id = resolved["capsuleId"]
            evidence_trace = resolved["trace"]
            evidence_artifact = resolved["artifact"]
        except Exception:
            raise NativeInquiryError("Private inquiry evidence is unavailable or invalid.") from None
    seqs = evidence_artifact.get("outputSeqs")
    if not isinstance(seqs, list) or len(seqs) != 1 or type(seqs[0]) is not int or seqs[0] < 1:
        raise NativeInquiryError("native inquiry requires exactly one recorded final output event")

    event = evidence_trace.get(seqs[0])
    message = event.message
    params = message.get("params")
    if not isinstance(params, dict):
        raise NativeInquiryError("native inquiry output has no native event parameters")
    method = message.get("method")
    if method == "item/completed":
        items = [params.get("item")]
        turn_id = params.get("turnId")
    elif method == "turn/completed":
        turn = params.get("turn")
        if not isinstance(turn, dict) or turn.get("status") != "completed":
            raise NativeInquiryError("native inquiry output is not a completed turn")
        items = turn.get("items", [])
        turn_id = turn.get("id")
    else:
        raise NativeInquiryError("native inquiry output is not a completed native message")
    if (
        event.direction != "appserver_to_client" or "id" in message
        or event.source != attempt["source"]
        or params.get("threadId") != attempt["threadId"] or turn_id != attempt["turnId"]
    ):
        raise NativeInquiryError("native inquiry event does not belong to the recorded attempt")
    if not isinstance(items, list) or not any(
        isinstance(item, dict) and isinstance(item.get("id"), str)
        and item.get("type") == "agentMessage" and item.get("phase") in ("final", "final_answer")
        and item.get("text") == artifact["text"] for item in items
    ):
        raise NativeInquiryError("native inquiry must be an explicit final agent message")
    requests = [
        record for record in evidence_trace.records()
        if record.source == attempt["source"] and record.direction == "client_to_appserver"
        and record.message.get("method") == "turn/start"
    ]
    if len(requests) != 1 or requests[0].seq >= event.seq:
        raise NativeInquiryError("native inquiry requires one preceding turn request")
    request = requests[0]
    request_params = request.message.get("params", {})
    if (
        not isinstance(request_params, dict) or request_params.get("threadId") != attempt["threadId"]
        or request_params.get("input") != [{"type": "text", "text": contexts[0]["projectedPrompt"]}]
    ):
        raise NativeInquiryError("native inquiry request contradicts its frozen context")
    result = {
        "schemaVersion": 1, "origin": "native-specialist", "mode": "terminal-needs-evidence",
        "investigationId": investigation["id"], "attemptId": attempt["id"],
        "contextId": attempt["contextId"], "nativeArtifactId": artifact["id"],
        "question": payload["question"], "cause": payload["cause"], "requestSeq": request.seq,
        "nativeEvent": {
            "seq": event.seq, "source": event.source, "threadId": attempt["threadId"],
            "turnId": attempt["turnId"], "method": method,
            "sha256": hashlib.sha256(event.raw_text.encode("utf-8")).hexdigest(),
        },
    }
    if capsule_id is not None:
        def reference(record):
            return {"kind": "private-capsule-record", "capsuleId": capsule_id,
                    "seq": record.seq, "sha256": hashlib.sha256(record.raw_text.encode("utf-8")).hexdigest()}
        result["schemaVersion"] = 2
        result.pop("requestSeq")
        result["request"] = reference(request)
        result["nativeEvent"] = {
            "source": event.source, "threadId": attempt["threadId"], "turnId": attempt["turnId"],
            "method": method, "evidence": reference(event),
        }
    return result
