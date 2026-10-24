"""LangChain + ASI1 for triage interpretation.

Yes — you can use LangChain for uAgents two ways:
1. Lightweight (used here): ChatOpenAI pointed at ASI1 inside the uAgent handler.
   Deterministic policy_rules remain the guardrail.
2. Full adapter: uagents-adapter[langchain] LangchainRegisterTool to publish
   a LangChain agent to Agentverse (see docs agent-creation/uagents-adapter-guide).

This module tries LangChain/ASI1 when ASI1_API_KEY is set, else falls back
to keyword triage so tests run offline.
"""
from __future__ import annotations
import os
import re
from .schemas import TriageResult, TransactionType

_KEYWORDS = {
    TransactionType.UNAUTHORISED: ["unauthor", "fraud", "did not", "didn't", "not me", "hacked", "otp", "1930"],
    TransactionType.PENDING: ["pending", "processing", "waiting", "in progress", "not confirmed"],
    TransactionType.FAILED: ["failed", "failure", "debited", "not credited", "not received", "reversed"],
}


def keyword_triage(text: str) -> TriageResult:
    low = (text or "").lower()
    for ttype, words in _KEYWORDS.items():
        if any(w in low for w in words):
            urgency = "high" if ttype == TransactionType.UNAUTHORISED else "normal"
            return TriageResult(
                transaction_type=ttype,
                debited=("debit" in low or "paid" in low or "deduct" in low),
                merchant_status="as_reported",
                missing_fields=_missing(text),
                urgency=urgency,
                utr=_find_utr(text),
                amount=_find_amount(text),
                raw_text=text or "",
            )
    return TriageResult(transaction_type=TransactionType.UNKNOWN, missing_fields=["status", "utr_or_date", "amount"], raw_text=text or "")


def _missing(text: str) -> list[str]:
    m = []
    if not _find_utr(text):
        m.append("utr")
    if not _find_amount(text):
        m.append("amount")
    if not text or len(text) < 20:
        m.append("details")
    return m


def _find_utr(text: str) -> str | None:
    mt = re.search(r"\b\d{12}\b", text or "")
    return mt.group(0) if mt else None


def _find_amount(text: str) -> float | None:
    mt = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)", (text or "").lower())
    if not mt:
        mt = re.search(r"\b([\d,]+(?:\.\d+)?)\b", text or "")
    if mt:
        try:
            return float(mt.group(1).replace(",", ""))
        except Exception:
            return None
    return None


def llm_triage(text: str) -> TriageResult:
    """Use LangChain ChatOpenAI -> ASI1 if configured, else keyword fallback."""
    api_key = os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")
    if not api_key:
        return keyword_triage(text)
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            base_url="https://api.asi1.ai/v1",
            api_key=api_key,
            model=os.getenv("ASI1_MODEL", "asi1-mini"),
            temperature=0,
        )
        prompt = (
            "Classify UPI dispute into exactly one: failed, pending, unauthorised, unknown. "
            "failed=debited but beneficiary not credited. pending=processing. "
            "unauthorised=user denies/fraud. Reply with one word.\nText: " + (text or "")
        )
        out = llm.invoke(prompt)
        label = str(getattr(out, "content", "") or "").lower()
        base = keyword_triage(text)
        for t in TransactionType:
            if t.value in label:
                base.transaction_type = t
                base.urgency = "high" if t == TransactionType.UNAUTHORISED else base.urgency
                break
        return base
    except Exception:
        return keyword_triage(text)
