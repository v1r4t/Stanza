from __future__ import annotations
from .schemas import TriageResult, PolicyFinding, EvidencePack, TransactionType
from .policy_rules import get_resolution_track, OFFICIAL_SOURCES
from .security import redact, build_complaint_draft
from .langchain_triage import llm_triage


def triage_text(text: str) -> TriageResult:
    # Extract from raw text FIRST — redaction would destroy the 12-digit UTR.
    # Callers redact separately for logs/LLM prompts via security.redact.
    return llm_triage(text or "")


def _decide_escalation(triage: TriageResult) -> tuple[bool, str | None]:
    """Computed decision, not advice text. (escalate_now, tat_note)."""
    t = triage.transaction_type
    d = triage.days_elapsed
    if t == TransactionType.UNAUTHORISED:
        return True, "report immediately — zero-liability clock runs from discovery"
    if t == TransactionType.FAILED:
        if d is None:
            return False, "date unknown — assume within T+1 auto-reversal window"
        if d > 1:
            return True, f"day {d + 1} — T+1 auto-reversal window passed"
        return False, f"day {d + 1} of T+1 auto-reversal window — hold"
    if t == TransactionType.PENDING:
        if d is None:
            return False, "recheck after the processing window"
        if d > 2:
            return True, f"day {d + 1} pending — treat as failed, escalate"
        return False, f"day {d + 1} — still in window"
    return False, None


def policy_for(triage: TriageResult) -> PolicyFinding:
    route = get_resolution_track(triage.transaction_type)
    escalate_now, tat_note = _decide_escalation(triage)
    uncertainty = []
    if triage.transaction_type.value == "unknown":
        uncertainty.append("insufficient data — collected via intake form")
    if not triage.utr:
        uncertainty.append("UTR missing — timelines conditional on PSP lookup")
    if tat_note:
        uncertainty.append(tat_note)
    return PolicyFinding(
        track=route["track"],
        source_ids=route["source_ids"],
        conditions=route["conditions"],
        timelines=route["actions"],
        escalation=route["escalation"],
        refund_guaranteed=False,
        uncertainty=uncertainty,
        escalate_now=escalate_now,
        evidence=list(route.get("evidence", [])),
    )


def _human_report(raw: str) -> str:
    """Strip card-selection JSON, @mentions and key= fragments so the timeline
    reads like a user report, not protocol exhaust."""
    import re as _re
    s = _re.sub(r"\{.*?\}", " ", raw or "")
    s = _re.sub(r"@\w+", " ", s)
    s = _re.sub(r"\b(amount|utr|details|track|action)\s*=", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s[:200]


def build_pack(triage: TriageResult, policy: PolicyFinding) -> EvidencePack:
    t = _human_report(triage.raw_text)
    timeline = [f"User report: {redact(t)}"] if t else ["User report: (see intake details)"]
    if triage.utr:
        timeline.append(f"UTR provided: {triage.utr}")
    if triage.amount is not None:
        timeline.append(f"Amount: INR {triage.amount:g}")
    timeline.append(f"Track: {triage.transaction_type.value} — resolution per official RBI/NPCI timelines (no refund promised)")
    missing = list(dict.fromkeys(triage.missing_fields))
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


_ACTION_PLAIN = {
    "check_applicable_reversal_timeline": "Wait out the auto-reversal window — most failed debits reverse on their own",
    "identify_payment_service_provider": "Quote the UTR to your PSP/bank if the window passes with no reversal",
    "prepare_escalation_if_overdue": "Escalate with the generated complaint draft if still unresolved",
    "do_not_retry_immediately": "Do NOT retry or pay again — a duplicate payment is the main risk right now",
    "check_status_window": "Recheck the status in your UPI app after the processing window",
    "treat_as_failed_only_after_window": "Treat it as failed (and escalate) only once the window expires",
    "block_channel_immediately": "Block the channel now — disable UPI/cards linked to this account",
    "report_to_bank_without_delay": "Report to your bank without delay, then file at cybercrime.gov.in / 1930",
    "file_cybercrime_report_if_fraud": "File a cybercrime report quoting the transaction details",
    "collect_missing_fields": "Share the missing details so the case can be assessed",
}

_VERDICT_SHORT = {
    "failed": "Failed debit — auto-reversal window applies",
    "pending": "Pending — wait, do not retry",
    "unauthorised": "Unauthorised — block + report today",
    "unknown": "Unclassified — pick a track",
}

_VERDICT_LONG = {
    "failed": "This is a FAILED debit: money left your account but the merchant was not credited.",
    "pending": "This payment is PENDING: nothing is confirmed yet — patience, not a retry, is the move.",
    "unauthorised": "This looks UNAUTHORISED: treat it as time-critical.",
    "unknown": "This could not be classified yet.",
}

_WHERE = {
    "failed": "Your PSP/bank grievance channel (quote the UTR)",
    "pending": "Your UPI app status page first — PSP only after the window",
    "unauthorised": "Home branch + 1930 helpline / cybercrime.gov.in",
    "unknown": "—",
}

_DEADLINE = {
    "failed": "Escalate if no reversal within your PSP's stated window",
    "pending": "Recheck after the processing window; escalate only if it flips to failed",
    "unauthorised": "Today — immediately",
    "unknown": "—",
}


def _deadline_row(triage: TriageResult, policy: PolicyFinding) -> str:
    prefix = "ESCALATE NOW — " if policy.escalate_now else ""
    t = triage.transaction_type.value
    d = triage.days_elapsed
    if t == "failed":
        if d is None:
            return prefix + "Within T+1 auto-reversal window — escalate if no credit (date unknown)"
        if d > 1:
            return prefix + f"Day {d + 1} — T+1 window passed, escalate with UTR"
        return prefix + f"Day {d + 1} of T+1 window — hold, do not escalate yet"
    if t == "pending":
        if d is None:
            return prefix + "Recheck after the processing window; escalate only if it flips to failed"
        if d > 2:
            return prefix + f"Day {d + 1} — treat as failed, escalate"
        return prefix + f"Day {d + 1} — still in window"
    if t == "unauthorised":
        return prefix + "Today — immediately (liability clock runs from discovery)"
    return "—"


def elaborate_assessment(triage: TriageResult, policy: PolicyFinding, case_ref: str | None = None) -> tuple[str, list[dict]]:
    """Glanceable verdict + card rows. Deterministic — no LLM, no invented timelines."""
    t = triage.transaction_type.value
    amt = f"Rs {triage.amount:g}" if triage.amount is not None else "the amount"
    utr_bit = f" (UTR …{triage.utr[-4:]})" if triage.utr else " (UTR missing — timelines stay conditional)"
    steps = [_ACTION_PLAIN.get(a, a) for a in policy.timelines]
    narration = f"{_VERDICT_LONG.get(t, _VERDICT_LONG['unknown'])} {amt}{utr_bit} " + " ".join(steps)
    if case_ref:
        narration = f"[{case_ref}] " + narration
    rows = [
        {"label": "Verdict", "value": _VERDICT_SHORT.get(t, _VERDICT_SHORT["unknown"])},
        {"label": "UTR", "value": triage.utr or "missing"},
        {"label": "Amount", "value": f"{triage.amount:g}" if triage.amount is not None else "missing"},
        {"label": "Deadline", "value": _deadline_row(triage, policy)},
        {"label": "Where", "value": _WHERE.get(t, "—")},
        {"label": "Next", "value": "; ".join(steps[:3])},
        {"label": "Attach", "value": "; ".join(policy.evidence[:3]) or "—"},
        {"label": "Sources", "value": "; ".join(policy.source_ids) or "—"},
    ]
    if case_ref:
        rows.insert(0, {"label": "Case", "value": case_ref})
    return narration, rows
