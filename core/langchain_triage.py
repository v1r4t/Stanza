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
from datetime import date
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
            occurred = _find_date(text)
            return TriageResult(
                transaction_type=ttype,
                debited=("debit" in low or "paid" in low or "deduct" in low),
                merchant_status="as_reported",
                missing_fields=_missing(text, ttype),
                urgency=urgency,
                utr=_find_utr(text),
                amount=_find_amount(text),
                raw_text=text or "",
                occurred_on=occurred.isoformat() if occurred else None,
                days_elapsed=(date.today() - occurred).days if occurred else None,
            )
    return TriageResult(transaction_type=TransactionType.UNKNOWN, missing_fields=["status", "utr_or_date", "amount"], raw_text=text or "")


def _missing(text: str, ttype: TransactionType | None = None) -> list[str]:
    m = []
    if not _find_utr(text):
        m.append("utr")
    if not _find_amount(text):
        m.append("amount")
    if not text or len(text) < 20:
        m.append("details")
    if ttype == TransactionType.FAILED:
        m.append("debit proof (SMS/statement screenshot)")
    elif ttype == TransactionType.PENDING:
        m.append("status screenshot (for recheck)")
    elif ttype == TransactionType.UNAUTHORISED:
        m += [
            "block confirmation (UPI/cards disabled)",
            "bank acknowledgement / complaint number",
            "1930 helpline or cybercrime.gov.in reference",
        ]
    return m


def _find_date(text: str):
    """Parse an explicit date or relative day reference. Returns date | None."""
    from datetime import date as _date, timedelta as _td
    low = (text or "").lower()
    today = _date.today()
    if "today" in low:
        return today
    if "yesterday" in low:
        return today - _td(days=1)
    mt = re.search(r"(\d+)\s+days?\s+ago", low)
    if mt:
        try:
            return today - _td(days=min(int(mt.group(1)), 3650))
        except Exception:
            pass
    mt = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text or "")
    if mt:
        try:
            d, mo, y = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
            if y < 100:
                y += 2000
            return _date(y, mo, d)
        except Exception:
            return None
    return None


def _find_utr(text: str) -> str | None:
    mt = re.search(r"\b\d{12}\b", text or "")
    return mt.group(0) if mt else None


def _find_amount(text: str) -> float | None:
    low = (text or "").lower()
    # 1. Explicitly marked amounts win: Rs 2000, INR 2000, ₹2000, amount is 2500.
    mt = re.search(r"(?:rs\.?|inr|₹|amount(?:\s+is|\s+of|\s*:)?|paid|price|total)\s*([\d,]+(?:\.\d+)?)", low)
    if mt:
        try:
            return _sane_amount(float(mt.group(1).replace(",", "")))
        except Exception:
            pass
    # 2. Fallback: first bare number that is neither a 12-digit UTR nor a
    #    duration ("3 days ago") nor a count of attempts ("paid 2 times").
    for m in re.finditer(r"\b([\d,]+(?:\.\d+)?)\b", text or ""):
        raw = m.group(1).replace(",", "")
        if re.fullmatch(r"\d{12}", raw):
            continue  # UTR, not an amount
        tail = (text or "")[m.end():m.end() + 12].lower()
        if re.match(r"\s*(days?|hours?|hrs?|mins?|minutes?|weeks?|months?|years?|times?|attempts?)\b", tail):
            continue  # duration / count, not money
        try:
            return _sane_amount(float(raw))
        except Exception:
            continue
    return None


def _sane_amount(v: float | None) -> float | None:
    """Discard implausible UPI amounts (above Rs 1 crore) — misparsed IDs, not money."""
    if v is None:
        return None
    if v > 10_000_000:
        return None
    return v


def llm_triage(text: str) -> TriageResult:
    """Keyword-first for speed; ASI1 only for genuinely ambiguous input.

    Keyword triage is deterministic and instant, and the 3-track rules are
    deterministic anyway. Calling the LLM on every message added seconds of
    latency for no accuracy gain — it now runs only when keywords find nothing.
    """
    base = keyword_triage(text)
    if base.transaction_type != TransactionType.UNKNOWN:
        return base
    api_key = os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")
    if not api_key or os.getenv("USE_LLM_TRIAGE", "true").strip().lower() == "false":
        return base
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            base_url="https://api.asi1.ai/v1",
            api_key=api_key,
            model=os.getenv("ASI1_MODEL", "asi1-mini"),
            temperature=0,
            timeout=float(os.getenv("LLM_TIMEOUT_S", "6")),
            max_retries=0,
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
