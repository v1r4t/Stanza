"""Deterministic NPCI/RBI routing skeleton.

LLM may help interpret user text, but MUST NOT invent policy.
Each track maps to verified official sources checked at resolution time.
"""
from __future__ import annotations
from .schemas import TransactionType

# Grounded sources — cite the ID + date (verifiable via rbi.org.in /
# npci.org.in search). URLs are section landing pages, not deep links.
SOURCES = {
    "rbi_tat_2019": {
        "cite": "RBI DPSS.CO.PD No.629/02.01.014/2019-20 (20 Sep 2019)",
        "title": "Harmonisation of Turn Around Time (TAT) and customer compensation for failed transactions",
        "note": "Failed UPI auto-reversal T+1; Rs 100/day compensation beyond TAT",
        "url": "https://www.rbi.org.in",
    },
    "rbi_liability_2017": {
        "cite": "RBI DBR.AML.BC.No.81/14.01.001/2016-17 (6 Jul 2017)",
        "title": "Customer Protection — Limiting Liability of Customers in Unauthorised Electronic Banking Transactions",
        "note": "Zero liability if reported within 3 working days; reversal credit within 10 days",
        "url": "https://www.rbi.org.in",
    },
    "npci_dispute": {
        "cite": "NPCI UPI Dispute Redressal Mechanism",
        "title": "UPI dispute / chargeback cycle via PSP",
        "note": "Raise with PSP first; NPCI cycle if PSP unresolved",
        "url": "https://www.npci.org.in/what-we-do/upi/dispute-redressal-mechanism",
    },
}

# Back-compat: short cite strings.
OFFICIAL_SOURCES = {k: v["cite"] for k, v in SOURCES.items()}

TRACK_RULES = {
    "failed_payment": {
        "actions": [
            "check_applicable_reversal_timeline",
            "identify_payment_service_provider",
            "prepare_escalation_if_overdue",
        ],
        "conditions": [
            "debited=True and beneficiary not credited",
            "applies only after official reversal window expires",
        ],
        "escalation": ["PSP/bank complaint with UTR", "NPCI dispute if PSP unresolved"],
        "sources": ["rbi_tat_2019", "npci_dispute"],
        "evidence": [
            "debit proof (SMS alert / statement entry for the UTR)",
            "beneficiary non-credit screenshot (app status page)",
        ],
    },
    "pending_payment": {
        "actions": [
            "do_not_retry_immediately",
            "check_status_window",
            "treat_as_failed_only_after_window",
        ],
        "conditions": ["status is pending/processing per PSP"],
        "escalation": ["wait window, then follow failed_payment track"],
        "sources": ["rbi_tat_2019", "npci_dispute"],
        "evidence": [
            "status screenshot showing pending/processing",
            "recheck time (note when the window expires)",
        ],
    },
    "unauthorised_payment": {
        "actions": [
            "block_channel_immediately",
            "report_to_bank_without_delay",
            "file_cybercrime_report_if_fraud",
        ],
        "conditions": ["user denies transaction / suspected fraud"],
        "escalation": ["home branch + cybercrime.gov.in + 1930 helpline"],
        "sources": ["rbi_liability_2017", "npci_dispute"],
        "evidence": [
            "block confirmation (UPI/cards disabled)",
            "bank acknowledgement / complaint number",
            "1930 helpline or cybercrime.gov.in reference",
        ],
    },
    "unknown": {
        "actions": ["collect_missing_fields"],
        "conditions": ["insufficient data to classify"],
        "escalation": [],
        "sources": ["npci_dispute"],
        "evidence": [],
    },
}


def get_resolution_track(transaction_type: TransactionType) -> dict:
    mapping = {
        TransactionType.FAILED: "failed_payment",
        TransactionType.PENDING: "pending_payment",
        TransactionType.UNAUTHORISED: "unauthorised_payment",
        TransactionType.UNKNOWN: "unknown",
    }
    track = mapping.get(transaction_type, "unknown")
    rules = TRACK_RULES[track]
    return {
        "track": track,
        "actions": rules["actions"],
        "conditions": rules["conditions"],
        "escalation": rules["escalation"],
        "refund_guaranteed": False,  # never promise refunds
        "source_ids": [SOURCES[s]["cite"] for s in rules["sources"]],
        "evidence": list(rules["evidence"]),
    }
