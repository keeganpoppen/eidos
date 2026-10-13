from __future__ import annotations

"""Host placement of the existing Eidos process for an investigation review.

The public API admits identities and response intents separately. This module
accepts only that host-owned state; possessing one of these descriptive Values
does not admit a continuation. There are no native calls or executor callbacks.
"""

from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator
from uuid import uuid4

from .authority import ProjectionGrant
from .core import (
    Closure, Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore,
    Record, RecordValue, Var, content_id,
)
from .discovery import (
    accept_inquiry, decide_inquiry, discover_request, discovery_provider_value,
)
from .epistemics import context_value, model_value
from .model_execution import model_input
from .model_process import AWAIT_DISCOVERY, DISCOVER, PROCESS_SOCKET_ROLE, ModelProcessRunner
from .process_runtime import ProcessRuntime
from .semantic_values import projection_value
from .trace import TraceStore
from .trusted import TrustedMachinery


class _TraceTrustedMachinery(TrustedMachinery):
    """Private local placement sharing TraceStore's connection and transaction.

    Savepoints preserve an enclosing admission/response transaction. Without
    one, each existing TM operation commits durably before outer reintegration.
    The caller owns the connection; closing this adapter cannot close it.
    """

    def __init__(self, trace: TraceStore) -> None:
        self.trace = trace
        self.db = trace.db
        with trace._lock:
            if self.db.in_transaction:
                raise RuntimeError("initialize investigation runtime before opening a transaction")
            self._schema()

    @contextmanager
    def _tx(self) -> Iterator[Any]:
        with self.trace._lock:
            nested = self.db.in_transaction
            savepoint = "investigation_tm_" + uuid4().hex
            self.db.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
            try:
                yield self.db
            except BaseException:
                if nested:
                    self.db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.db.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute(f"RELEASE SAVEPOINT {savepoint}" if nested else "COMMIT")

    def close(self) -> None:
        pass


def _program(provider: str, question: str) -> Closure:
    realized = PraxisCore().realize(Lambda(
        ("request",),
        Perform(
            socket=Need(PROCESS_SOCKET_ROLE),
            operation=DISCOVER,
            argument=Lit(discover_request(provider, question)),
            result_as="opened",
            successor_as="after_discover",
            then=Perform(
                socket=Var("after_discover"),
                operation=AWAIT_DISCOVERY,
                argument=Record.from_mapping({
                    "$kind": Lit("AwaitDiscoveryRequest"),
                    "inquiry": Get(Var("opened"), "inquiry"),
                }),
                result_as="answer",
                successor_as="after_answer",
                then=Record.from_mapping({
                    "$kind": Lit("ModelProposal"),
                    "context": Get(Var("answer"), "context"),
                    "claims": Lit(()),
                    "receipt": Var("answer"),
                }),
            ),
        ),
    ))
    if not isinstance(realized, Done) or not isinstance(realized.value, Closure):
        raise RuntimeError("investigation review program did not realize a Closure")
    return realized.value


class InvestigationRuntime:
    """A fixed evidence-review protocol realized by ModelProcessRunner."""

    def __init__(self, trace: TraceStore) -> None:
        self.trace = trace
        self.trusted = _TraceTrustedMachinery(trace)
        self.machine = ProcessRuntime(self.trusted)

    def _persist(self, key: str, kind: str, **fields: Any) -> str:
        return self.machine.persist(
            kind=kind,
            request_id=key,
            value=RecordValue.from_mapping(fields),
        )

    def start(
        self, *, key: str, investigation_id: str, attempt_id: str,
        native_artifact: dict[str, Any], context: dict[str, Any], question: str,
    ) -> dict[str, Any]:
        """Admit a fixed process with exact immutable outer provenance."""
        with self.trace._lock:
            prefix = f"investigation-continuation:{key}"
            origin = self._persist(
                prefix + ":origin", "investigation-origin",
                **{
                    "$kind": "InvestigationReviewOrigin",
                    "investigation_id": investigation_id,
                    "attempt_id": attempt_id,
                    "continuation_id": key,
                    "native_artifact": deepcopy(native_artifact),
                    "context": deepcopy(context),
                    "question": question,
                    "origin": "synthetic-eidos",
                },
            )
            observer = f"investigation-owner:{investigation_id}"
            source_description = RecordValue.from_mapping({
                "$kind": "InvestigationEvidenceSource",
                "origin": Name(origin),
                "observer": observer,
            })
            source = self.trusted.admit_authority_domain(
                description=source_description,
                establishes=(
                    ProjectionGrant(
                        key="discloser", holder=observer,
                        description=projection_value(
                            key="review:discloser", role="Discloser", state="available",
                        ),
                    ),
                    ProjectionGrant(
                        key="evidence", holder=observer,
                        description=RecordValue.from_mapping({
                            "$kind": "Projection", "key": "review:evidence",
                            "role": "InvestigationEvidence", "state": "initial",
                            "origin": Name(origin),
                        }),
                    ),
                ),
                request_id=prefix + ":source",
            )
            protocol_cid = content_id(source_description)
            initial_cut = self.trusted.create_observed_cut(
                instance=source["domain"], observer=observer,
                protocol_cid=protocol_cid,
                projections=[source["projections"]["evidence"]],
                request_id=prefix + ":initial-cut",
            )["cut"]
            provider = self.machine.persist(
                kind="discovery-provider", request_id=prefix + ":provider",
                value=discovery_provider_value(
                    label="Investigation owner evidence review",
                    source_domain=source["domain"], observer=observer,
                ),
            )
            program = _program(provider, question)
            model = self.machine.persist(
                kind="model", request_id=prefix + ":model",
                value=model_value(
                    "Synthetic investigation evidence review", implementation=program,
                    process=True, sources=(origin,),
                ),
            )
            context_name = self.machine.persist(
                kind="context", request_id=prefix + ":context",
                value=context_value(cuts=(initial_cut,), models=(model,)),
            )
            request = model_input(
                context=Name(context_name), model=Name(model),
                cuts=(Name(initial_cut),), facts=(), knowledge=(), remaining_budget=0,
            )
            request = RecordValue.from_mapping({
                **dict(request.fields), "source": Name(origin),
            })
            runner = ModelProcessRunner(self.trusted, machine=self.machine)
            runner.authorize_discovery(model=model, provider=provider)
            progress = runner.start(
                name=model, program=program, request=request, request_id=prefix + ":process",
            )
            descriptor = self.trusted.named_eidos_value(progress.run)["value"]
            return {
                "key": key,
                "investigationId": investigation_id,
                "attemptId": attempt_id,
                "originValueId": origin,
                "processId": progress.run,
                "protocolId": descriptor.get("protocol").value,
                "modelId": model,
                "checkpointId": progress.checkpoint,
                "initialCheckpointId": progress.checkpoint,
                "outcomeId": progress.outcome,
                "pending": False,
                "contextName": context_name,
                "inquiryId": None,
                "openedOccurrenceId": None,
                "sourceDomainId": source["domain"],
                "sourceProtocolCid": protocol_cid,
                "sourceObserver": observer,
                "providerId": provider,
                "discloserId": source["projections"]["discloser"],
                "evidenceProjectionId": source["projections"]["evidence"],
                "responderId": None,
                "acceptanceId": None,
            }

    def advance(self, state: dict[str, Any]) -> dict[str, Any]:
        """Advance one existing process operation; pending creates no event."""
        result = deepcopy(state)
        if result["outcomeId"] is not None:
            return result
        with self.trace._lock:
            loaded = self.machine.load(result["checkpointId"])
            if loaded.process != result["processId"]:
                raise ValueError("checkpoint belongs to another investigation process")
            runner = ModelProcessRunner(self.trusted, machine=self.machine)
            progress = runner.advance(result["checkpointId"])
            if progress.checkpoint is not None:
                result["checkpointId"] = progress.checkpoint
            result["outcomeId"] = progress.outcome
            result["pending"] = progress.pending is not None
            if progress.occurrence is not None:
                occurred = self.trusted.named_eidos_value(progress.occurrence)["value"]
                if occurred.get("$kind") == "ModelInteraction":
                    answer = occurred.get("response")
                    if answer.get("$kind") == "DiscoveryOpened":
                        result["inquiryId"] = answer.get("inquiry").value
                        result["openedOccurrenceId"] = progress.occurrence
            if progress.pending is not None:
                result["inquiryId"] = progress.pending
            current = progress.outcome or progress.checkpoint
            if current is not None:
                value = self.trusted.named_eidos_value(current)["value"]
                result["contextName"] = value.get("context").value
            return result

    def respond(
        self, state: dict[str, Any], response: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Commit one admitted owner decision in its source authority domain."""
        result = deepcopy(state)
        inquiry = result["inquiryId"]
        if inquiry is None:
            raise ValueError("investigation has not issued an inquiry")
        decision = response["decision"]
        evidence = response.get("evidenceContext")
        if decision not in {"offer", "refuse", "defer"}:
            raise ValueError("decision must be offer, refuse, or defer")
        if (decision == "offer") != (evidence is not None):
            raise ValueError("only an offer must carry an evidence context")
        prefix = f"investigation-continuation:{result['key']}:response:{response['id']}"
        with self.trace._lock:
            if result["acceptanceId"] is None:
                accepted = accept_inquiry(
                    self.trusted, inquiry=inquiry,
                    discloser_projection=result["discloserId"],
                    request_id=f"investigation-continuation:{result['key']}:accept",
                )
                result.update({
                    "acceptanceId": accepted["acceptance"],
                    "discloserId": accepted["next_discloser"],
                    "responderId": accepted["responder"],
                })
            cut = None
            evidence_name = None
            selected_occurrence = None
            if evidence is not None:
                evidence_name = self._persist(
                    prefix + ":evidence", "investigation-evidence",
                    **{
                        "$kind": "InvestigationDisclosureEvidence",
                        "origin": Name(result["originValueId"]),
                        "inquiry": Name(inquiry), "response_id": response["id"],
                        "evidence_context": deepcopy(evidence),
                    },
                )
                selected = self.trusted.commit_projection_occurrence(
                    kind="InvestigationEvidenceSelected",
                    consumes=(result["evidenceProjectionId"],),
                    establishes=(ProjectionGrant(
                        key="evidence", holder=result["sourceObserver"],
                        description=RecordValue.from_mapping({
                            "$kind": "Projection", "key": "review:evidence",
                            "role": "InvestigationEvidence", "state": "selected",
                            "origin": Name(result["originValueId"]),
                            "evidence": Name(evidence_name),
                        }),
                    ),),
                    fact={"inquiry": inquiry, "evidence": evidence_name, "response_id": response["id"]},
                    request_id=prefix + ":select-evidence",
                )
                result["evidenceProjectionId"] = selected["established"]["evidence"]
                selected_occurrence = selected["occurrence"]
                cut = self.trusted.create_observed_cut(
                    instance=result["sourceDomainId"], observer=result["sourceObserver"],
                    protocol_cid=result["sourceProtocolCid"],
                    projections=[result["evidenceProjectionId"]],
                    parent_occurrence=selected_occurrence,
                    request_id=prefix + ":cut",
                )["cut"]
            decided = decide_inquiry(
                self.trusted, inquiry=inquiry, responder_projection=result["responderId"],
                decision=decision, cut=cut, request_id=prefix + ":decision",
            )
            result["responderId"] = decided["responder"]
            response_name = self._persist(
                prefix + ":receipt", "investigation-response",
                **{
                    "$kind": "InvestigationInquiryResponse",
                    "origin": Name(result["originValueId"]),
                    "inquiry": Name(inquiry), "response_id": response["id"],
                    "request_id": response["requestId"], "decision": decision,
                    "note": response.get("note", ""),
                    "occurrence": Name(decided["occurrence"]),
                    "cut": None if cut is None else Name(cut),
                    "evidence": None if evidence_name is None else Name(evidence_name),
                    "selection_occurrence": None if selected_occurrence is None else Name(selected_occurrence),
                },
            )
            return result, {
                "occurrenceId": decided["occurrence"],
                "disclosureCutId": cut,
                "responseValueId": response_name,
            }
