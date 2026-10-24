"""Redaction + evidence helpers. Never log full PAN/account/UPI PIN/OTP."""
from __future__ import annotations
import re

_PATTERNS = [
    # NOTE: exactly-12-digit runs are UPI UTRs — leave them intact so triage
    # and complaint drafts keep the reference. Real PANs are 13-19 digits.
    (re.compile(r"\b\d{13,19}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b\d{13,18}\b"), "[REDACTED_ID]"),
    (re.compile(r"\b\d{9,11}\b"), "[REDACTED_ID]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[REDACTED_CARD]"),
    (re.compile(r"(?i)(upi\s*pin|otp|password|pwd)\s*[:=]?\s*\S+"), r"\1=[REDACTED]"),
]


def redact(text: str) -> str:
    if not text:
        return ""
    out = text
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


def build_complaint_draft(utr: str | None, amount: float | None, ttype: str, timeline: list[str]) -> str:
    lines = [
        "To: Grievance Officer, [Your Bank/PSP]",
        f"Subject: Dispute — {ttype} UPI transaction UTR {utr or '[UTR]'}",
        "",
        f"Transaction amount: {amount if amount is not None else '[AMOUNT]'}",
        f"Type assessed: {ttype}",
        "",
        "Timeline:",
    ]
    lines += [f"- {t}" for t in timeline] if timeline else ["- [date/time + app screenshots]"]
    lines += [
        "",
        "Request: investigate and confirm reversal/status per RBI/NPCI TAT.",
        "Attachments: masked statement, screenshots (no PIN/OTP).",
        "",
        "[Name, masked account, contact]",
    ]
    return "\n".join(lines)
