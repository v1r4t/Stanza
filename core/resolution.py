from __future__ import annotations
from .schemas import TriageResult, PolicyFinding, EvidencePack
from .policy_rules import get_resolution_track, OFFICIAL_SOURCES
from .security import redact, build_complaint_draft
from .langchain_triage import llm_triage


def triage_text(text: str) -> TriageResult:
    return llm_triage(redact(text))


def policy_for(triage: TriageResult) -> PolicyFinding:
    route = get_resolution_track(triage.transaction_type)
    uncertainty = []
    if triage.transaction_type.value == "unknown":
        uncertainty.append("insufficient data — collected via intake form")
    if not triage.utr:
        uncertainty.append("UTR missing — timelines conditional on PSP lookup")
    return PolicyFinding(
        track=route["track"],
        source_ids=route["source_ids"],
        conditions=route["conditions"],
        timelines=route["actions"],
        escalation=route["escalation"],
        refund_guaranteed=False,
        uncertainty=uncertainty,
    )


def build_pack(triage: TriageResult, policy: PolicyFinding) -> EvidencePack:
    t = (triage.raw_text or "")[:200]
    timeline = [f"User report: {redact(t)}"]
    if triage.utr:
        timeline.append(f"UTR provided: {triage.utr}")
    if triage.amount is not None:
        timeline.append(f"Amount: INR {triage.amount}")
    timeline.append(f"Track: {policy.track} (refund_guaranteed=False)")
    missing = list(triage.missing_fields)
    if triage.transaction_type.value == "unauthorised":
        missing.append("bank acknowledgement + cybercrime ref (1930 / cybercrime.gov.in)")
    draft = build_complaint_draft(triage.utr, triage.amount, triage.transaction_type.value, timeline)
    return EvidencePack(
        timeline=timeline,
        missing_evidence=missing,
        official_sources=policy.source_ids,
        complaint_draft=draft,
        verified_facts=[f"classification={triage.transaction_type.value}"],
        user_reported=[redact(triage.raw_text or "")[:300]],
        unresolved=policy.uncertainty,
    )
