"""Redaction + evidence helpers. Never log full PAN/account/UPI PIN/OTP."""
from __future__ import annotations
import re
from datetime import date

_PATTERNS = [
    # NOTE: exactly-12-digit runs are UPI UTRs — leave them intact so triage
    # and complaint drafts keep the reference. Real PANs are 13-19 digits.
    (re.compile(r"\b\d{13,19}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b\d{13,18}\b"), "[REDACTED_ID]"),
    (re.compile(r"\b\d{9,11}\b"), "[REDACTED_ID]"),
    # Spaced groups (e.g. "1234 5678 9012") are card-shaped — require real
    # separators so contiguous 12-digit UTRs are never touched.
    (re.compile(r"\b\d{4} \d{4} \d{4}( \d{4})?\b"), "[REDACTED_CARD]"),
    (re.compile(r"(?i)(upi\s*pin|otp|password|pwd)\s*[:=]?\s*\S+"), r"\1=[REDACTED]"),
]


def redact(text: str) -> str:
    if not text:
        return ""
    out = text
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


_TRACK_EXPLAIN = {
    "failed": (
        "A failed debit: money left the account but the beneficiary was not credited. "
        "Such credits are normally auto-reversed within the PSP's stated window; "
        "a formal dispute applies only after that window passes with no credit."
    ),
    "pending": (
        "A pending transaction: neither success nor failure is confirmed yet. "
        "No retry should be made until the status settles — a duplicate payment "
        "is the main risk, not the delay itself."
    ),
    "unauthorised": (
        "An unauthorised transaction the account holder denies. Time-critical: "
        "channels must be blocked and a fraud dispute registered without delay."
    ),
    "unknown": (
        "A transaction dispute awaiting classification. Please confirm which track applies."
    ),
}

_TRACK_ACTIONS = {
    "failed": [
        "Confirm whether auto-reversal was processed for this UTR, with the credit date.",
        "If the reversal window has passed with no credit, register a formal dispute and share the complaint/reference number.",
        "If unresolved, the holder may escalate via RBI CMS (cms.rbi.org.in) quoting this complaint number.",
    ],
    "pending": [
        "Confirm the current status of this UTR (success/failed) in writing.",
        "If it settles as failed with no credit, process the reversal and share confirmation.",
        "If the holder is asked to retry, confirm in writing that no duplicate will be debited.",
    ],
    "unauthorised": [
        "Block all channels linked to this account immediately and confirm the block in writing.",
        "Register a fraud dispute and share the complaint/reference number.",
        "Advise on zero-liability eligibility; the holder is separately reporting at cybercrime.gov.in / 1930.",
    ],
    "unknown": [
        "Confirm the status of this transaction and advise the correct dispute channel.",
    ],
}


def build_complaint_draft(utr: str | None, amount: float | None, ttype: str, timeline: list[str]) -> str:
    reported = next(
        (t.split("User report:", 1)[1].strip() for t in (timeline or []) if t.startswith("User report:")),
        "",
    )
    lines = [
        "To: Grievance Officer, [Your Bank/PSP]",
        f"Subject: Dispute — {ttype} UPI transaction UTR {utr or '[UTR]'}",
        "",
        f"Date filed: {date.today().isoformat()}",
        f"Transaction amount: {f'{amount:g}' if amount is not None else '[AMOUNT — fill from statement]'}",
        f"Type assessed: {ttype}",
        "",
        "What happened:",
        reported or "[one line: date, app used, merchant, what the app shows]",
        "",
        "Why this track applies:",
        _TRACK_EXPLAIN.get(ttype, _TRACK_EXPLAIN["unknown"]),
        "",
        "Action requested:",
    ]
    lines += [f"{i}. {a}" for i, a in enumerate(_TRACK_ACTIONS.get(ttype, _TRACK_ACTIONS["unknown"]), 1)]
    lines += [
        "",
        "Timeline:",
    ]
    lines += [f"- {t}" for t in timeline] if timeline else ["- [date/time + app screenshots]"]
    lines += [
        "",
        "Attachments to include:",
        "- Screenshot of the debit SMS / alert",
        "- Bank statement entry for this UTR",
        "- Screenshot of the app transaction page showing status",
        "- (Unauthorised only) cybercrime acknowledgement, if already filed",
        "",
        "My details:",
        "Name: [Name]",
        "Account (masked, last 4 digits only): [XXXX]",
        "Contact: [phone/email]",
    ]
    return "\n".join(lines)
