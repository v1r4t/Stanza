"""Deterministic NPCI/RBI routing skeleton.

LLM may help interpret user text, but MUST NOT invent policy.
Each track maps to verified official sources checked at resolution time.
"""
from __future__ import annotations
from .schemas import TransactionType

# Curated official sources — verify dates before submission.
OFFICIAL_SOURCES = {
    "rbi_failed_credits": "https://www.rbi.org.in — Customer Protection: zero liability / failed transaction reversal TAT",
    "npci_upi_dispute": "https://www.npci.org.in — UPI dispute / chargeback cycle",
    "npci_cyber": "https://www.npci.org.in + https://cybercrime.gov.in — unauthorised transaction reporting",
}

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
    },
    "pending_payment": {
        "actions": [
            "do_not_retry_immediately",
            "check_status_window",
            "treat_as_failed_only_after_window",
        ],
        "conditions": ["status is pending/processing per PSP"],
        "escalation": ["wait window, then follow failed_payment track"],
    },
    "unauthorised_payment": {
        "actions": [
            "block_channel_immediately",
            "report_to_bank_without_delay",
            "file_cybercrime_report_if_fraud",
        ],
        "conditions": ["user denies transaction / suspected fraud"],
        "escalation": ["home branch + cybercrime.gov.in + 1930 helpline"],
    },
    "unknown": {
        "actions": ["collect_missing_fields"],
        "conditions": ["insufficient data to classify"],
        "escalation": [],
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
        "source_ids": list(OFFICIAL_SOURCES.values()),
    }
