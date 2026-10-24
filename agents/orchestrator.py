"""PayResolve orchestrator — public ACP entry point.

Docs used:
- uagent-creation (mailbox=True, publish_agent_details, Python 3.10-13, uagents>=0.25.5)
- asi-interactive-cards (MetadataContent card wire protocol)
- asione quickstart (ASI1 via OpenAI-compatible API, model asi1-mini default)
- uagents-adapter-guide (LangChain inside handler + optional Adapter publish)
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()  # must run before any os.getenv below

from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from core.cards import card_message, intake_form, track_carousel, review_pack, parse_selection
from core.resolution import triage_text, policy_for, build_pack, elaborate_assessment
from core.security import redact
from core.schemas import TransactionType, TriageResult, PolicyFinding, EvidencePack
from core.cases import case_id_for, short_ref, save_case, get_case

TRIAGE_AGENT_ADDRESS = os.getenv(
    "TRIAGE_AGENT_ADDRESS",
    "agent1qwd7l7jv9fzpkej7nq4c8wjxfs8vgw9unddst5q08076yn92k5uy5l043dq",
)
POLICY_AGENT_ADDRESS = os.getenv(
    "POLICY_AGENT_ADDRESS",
    "agent1qggnj3j4jvz9su2eefhf7l9rprjsccjphjxdan77wmahe9tgtmz5yxppwr7",
)
EVIDENCE_AGENT_ADDRESS = os.getenv(
    "EVIDENCE_AGENT_ADDRESS",
    "agent1qvnrqea7eflv2my3szqtn2jdq82uu7dspuguzdgvmnpqf2c2nx70qxd5u79",
)
_DELEGATE_TIMEOUT_S = int(os.getenv("DELEGATE_TIMEOUT_S", "10"))

SEED = os.getenv("AGENT_SEED", "payresolve-dev-seed-do-not-use-in-prod")

agent = Agent(
    name="PayResolve",
    seed=SEED,
    port=8001,
    mailbox=True,
    publish_agent_details=True,
    network="testnet",
)

try:
    fund_agent_if_low(str(agent.wallet.address()))
except Exception as _e:  # hosted wrapper may not expose .wallet
    print(f"[setup] skipping testnet funding: {_e}")


@agent.on_event("startup")
async def _log_address(ctx: Context):
    """Print our own address so hosted deployments (where the dashboard
    overrides our seed and wraps the agent object) can be wired from logs.
    getattr guards: the hosted wrapper may not expose .name/.address."""
    _name = getattr(agent, "name", "PayResolve")
    _addr = getattr(agent, "address", "unknown")
    ctx.logger.info(f"[startup] {_name} ADDRESS={_addr}")

chat_proto = Protocol(spec=chat_protocol_spec)


def _text(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


def _normalise(text: str) -> str:
    """Strip @mentions, punctuation and filler so greeting detection works
    even when ASI:One prefixes the message with the agent handle."""
    import re
    s = re.sub(r"@[\w\-\.]+", " ", text or "")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _is_greeting(text: str) -> bool:
    norm = _normalise(text)
    if not norm:
        return True
    words = set(norm.split())
    return len(words) <= 3 and bool(words & {"hi", "hello", "hey", "start", "help", "namaste", "yo"})


_MISSING_LABEL = {
    "utr": "the 12-digit UTR from your payment history",
    "amount": "the amount in INR",
    "details": "a one-line description (date, app, merchant)",
    "status": "what your app shows (failed, pending, or processing)",
    "utr_or_date": "the UTR or transaction date",
    "bank acknowledgement + cybercrime ref (1930 / cybercrime.gov.in)": "your bank's acknowledgement / cybercrime reference (call 1930)",
}


async def _delegate_triage(ctx: Context, detail: str) -> tuple[TriageResult, bool]:
    """Ask the triage specialist over ACP; fall back to local logic."""
    try:
        from core.messages import TriageRequest, TriageResponse
        resp, _status = await ctx.send_and_receive(
            TRIAGE_AGENT_ADDRESS, TriageRequest(text=detail), TriageResponse,
            timeout=_DELEGATE_TIMEOUT_S,
        )
        if resp is None:
            raise TimeoutError("triage specialist did not reply")
        try:
            ttype = TransactionType(resp.transaction_type)
        except Exception:
            ttype = TransactionType.UNKNOWN
        ctx.logger.info(f"[delegate] triage via agent: {ttype.value}")
        return TriageResult(
            transaction_type=ttype, debited=resp.debited, utr=resp.utr,
            amount=resp.amount, missing_fields=list(resp.missing_fields),
            urgency=resp.urgency, occurred_on=resp.occurred_on,
            days_elapsed=resp.days_elapsed, raw_text=detail,
        ), True
    except Exception as e:
        ctx.logger.warning(f"[delegate] triage fallback to local: {e}")
        return triage_text(detail), False


async def _delegate_policy(ctx: Context, triage: TriageResult) -> tuple[PolicyFinding, bool]:
    """Ask the policy specialist over ACP; fall back to local logic."""
    try:
        from core.messages import PolicyRequest, PolicyResponse
        resp, _status = await ctx.send_and_receive(
            POLICY_AGENT_ADDRESS,
            PolicyRequest(
                transaction_type=triage.transaction_type.value, utr=triage.utr,
                occurred_on=triage.occurred_on, days_elapsed=triage.days_elapsed,
            ),
            PolicyResponse, timeout=_DELEGATE_TIMEOUT_S,
        )
        if resp is None:
            raise TimeoutError("policy specialist did not reply")
        ctx.logger.info(f"[delegate] policy via agent: {resp.track}")
        return PolicyFinding(
            track=resp.track, source_ids=list(resp.source_ids),
            conditions=list(resp.conditions), timelines=list(resp.timelines),
            escalation=list(resp.escalation), refund_guaranteed=False,
            uncertainty=list(resp.uncertainty), escalate_now=resp.escalate_now,
            evidence=list(resp.evidence),
        ), True
    except Exception as e:
        ctx.logger.warning(f"[delegate] policy fallback to local: {e}")
        return policy_for(triage), False


async def _delegate_evidence(ctx: Context, triage: TriageResult, detail: str,
                             policy: PolicyFinding):
    """Ask the evidence specialist over ACP; returns EvidencePack or (None, False)."""
    try:
        from core.messages import EvidenceRequest, EvidenceResponse
        resp, _status = await ctx.send_and_receive(
            EVIDENCE_AGENT_ADDRESS,
            EvidenceRequest(
                transaction_type=triage.transaction_type.value, utr=triage.utr,
                amount=triage.amount, report=detail,
                occurred_on=triage.occurred_on, days_elapsed=triage.days_elapsed,
            ),
            EvidenceResponse, timeout=_DELEGATE_TIMEOUT_S,
        )
        if resp is None:
            raise TimeoutError("evidence specialist did not reply")
        ctx.logger.info("[delegate] evidence via agent")
        return EvidencePack(
            timeline=list(resp.timeline), missing_evidence=list(resp.missing_evidence),
            official_sources=policy.source_ids, complaint_draft=resp.complaint_draft,
            verified_facts=[f"classification={triage.transaction_type.value}"],
            user_reported=[redact(detail)[:300]], unresolved=policy.uncertainty,
        ), True
    except Exception as e:
        ctx.logger.warning(f"[delegate] evidence fallback to local: {e}")
        return None, False


@chat_proto.on_message(ChatMessage)
async def on_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id),
    )
    texts = [c.text for c in msg.content if isinstance(c, TextContent)]
    last = texts[-1] if texts else ""

    # session lifecycle
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")
        elif isinstance(item, EndSessionContent):
            ctx.logger.info(f"Session ended with {sender}")

    if not last or _is_greeting(last):
        await ctx.send(sender, card_message(
            "Welcome to PayResolve. Tell me what happened, or fill the intake form.",
            "form", intake_form(),
        ))
        await ctx.send(sender, _text("Tip: failed ≠ pending ≠ unauthorised. I check policy before recommending."))
        return

    sel = parse_selection(last)
    # Confirm / cancel from the review pack card
    if sel.get("action") == "confirm":
        try:
            saved = ctx.storage.get(sender) or {}
        except Exception:
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        draft = saved.get("draft")
        report = saved.get("report")
        # Prefer the persisted SQLite case (survives restarts).
        try:
            if saved.get("case_id"):
                try:
                    row = await asyncio.to_thread(get_case, saved["case_id"])
                except Exception:
                    row = None
                if row:
                    draft = row.get("draft") or draft
                    report = row.get("report") or report
        except Exception:
            pass
        # Rebuild fresh from stored report so template upgrades and any
        # merged details always apply — never serve a stale stored draft.
        try:
            if report:
                fresh = triage_text(report)
                if fresh.transaction_type.value == "unknown" and saved.get("track") in {"failed", "pending", "unauthorised"}:
                    fresh.transaction_type = TransactionType(saved["track"])
                fresh_pack = build_pack(fresh, policy_for(fresh))
                draft = fresh_pack.complaint_draft
                saved["draft"] = draft
                ctx.storage.set(sender, saved)
                try:
                    save_case(saved.get("case_id") or case_id_for(fresh.utr, fresh.occurred_on),
                              sender, fresh.transaction_type.value, fresh.utr, fresh.amount, draft, report)
                except Exception:
                    pass
        except Exception:
            pass
        if draft:
            await ctx.send(sender, _text(
                "Here is your complaint draft — copy, fill the [brackets], and send it to your bank/PSP:\n\n" + draft
            ))
        else:
            await ctx.send(sender, _text(
                "No active case pack in this session. Describe the transaction (UTR, amount, what happened) and I'll build one."
            ))
        return
    if sel.get("action") == "cancel":
        try:
            ctx.storage.set(sender, {})
        except Exception:
            pass
        await ctx.send(sender, card_message(
            "Started over. Tell me what happened, or fill the intake form.",
            "form", intake_form(),
        ))
        return
    # intake form submit or track pick carries JSON
    if sel.get("action") in {"intake_submit", "pick_track"} or "track" in sel or "status" in sel:
        _track = sel.get("track") or sel.get("status") or ""
        detail = (
            f"{_track} amount={sel.get('amount','')} utr={sel.get('utr','')} "
            f"{sel.get('details','')} {_track}"
        )
        if _track in {"failed", "pending", "unauthorised"}:
            sel.setdefault("track", _track)
    else:
        detail = last

    # Merge follow-up details into the pending case (one-shot): if the last
    # turn asked for missing fields, combine rather than starting over.
    try:
        prev = ctx.storage.get(sender) or {}
    except Exception:
        prev = {}
    if isinstance(prev, dict) and prev.get("awaiting_details") and sel.get("action") not in {"confirm", "cancel"}:
        detail = f"{prev.get('report', '')} {detail}"
        try:
            prev["awaiting_details"] = False
            ctx.storage.set(sender, prev)
        except Exception:
            pass

    # Real multi-agent path: coordinator delegates to specialists over ACP,
    # with local fallbacks so the demo never dies on a hung handoff.
    triage, _triage_live = await _delegate_triage(ctx, detail)
    # explicit track override from card
    if sel.get("track") in {"failed", "pending", "unauthorised"}:
        triage.transaction_type = TransactionType(sel["track"])
        triage.urgency = "high" if sel["track"] == "unauthorised" else triage.urgency

    policy, _policy_live = await _delegate_policy(ctx, triage)

    # Unknown → ask which track before paying for evidence assembly.
    # But if a case is already open and this message carries no NEW UTR, it is
    # a follow-up on that case — recap instead of restarting from step 1.
    if triage.transaction_type.value == "unknown":
        try:
            saved = ctx.storage.get(sender) or {}
        except Exception:
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        if triage.utr and saved.get("utr") and triage.utr != saved.get("utr"):
            try:
                ctx.storage.set(sender, {})
            except Exception:
                pass
            saved = {}
        if saved.get("track") in {"failed", "pending", "unauthorised"}:
            utr_bit = f" (UTR …{saved['utr'][-4:]})" if saved.get("utr") else ""
            amt_bit = ""
            try:
                amt_bit = f" of Rs {saved['amount']:g}" if saved.get("amount") is not None else ""
            except Exception:
                pass
            await ctx.send(sender, _text(
                f"Still on your {saved['track']} case{utr_bit}{amt_bit}. "
                "Ask me anything about it — tap Generate complaint draft on the review card "
                "when ready, or say 'start over' for a new case."
            ))
            return
        await ctx.send(sender, card_message(
            "I need a bit more detail to place this correctly. Fill what you know below "
            "(or just describe it in a sentence, e.g. \"Rs 2500 debited yesterday, merchant not credited\").",
            "form", intake_form(),
        ))
        return

    pack, _evidence_live = await _delegate_evidence(ctx, triage, detail, policy)
    if pack is None:
        pack = build_pack(triage, policy)

    cid = case_id_for(triage.utr, triage.occurred_on, detail)
    day_n = triage.days_elapsed + 1 if triage.days_elapsed is not None else None
    case_label = f"Case {short_ref(triage.utr, triage.occurred_on)}" + (f" · Day {day_n}" if day_n else "")
    narration, rows = elaborate_assessment(triage, policy, case_ref=case_label)
    await ctx.send(sender, card_message(
        narration + " I cite official sources and never promise refunds.",
        "review",
        review_pack(rows, {"action": "confirm_pack"}, {"action": "cancel"}),
    ))
    # store pack in storage for confirm step (+ merge state for follow-ups)
    missing = list(triage.missing_fields)
    try:
        ctx.storage.set(sender, {
            "draft": pack.complaint_draft,
            "track": triage.transaction_type.value,
            "report": detail,
            "utr": triage.utr,
            "amount": triage.amount,
            "awaiting_details": bool(missing),
            "case_id": cid,
        })
    except Exception:
        pass
    try:
        await asyncio.to_thread(
            save_case, cid, sender, triage.transaction_type.value, triage.utr,
            triage.amount, pack.complaint_draft, detail,
        )
    except Exception as e:
        ctx.logger.warning(f"[cases] persist failed: {e}")
    if missing:
        need = ", ".join(_MISSING_LABEL.get(m, m) for m in missing)
        await ctx.send(sender, _text(
            "To complete this case I still need: " + need
            + ". Reply with it and I'll update the pack — anything you already gave is kept."
        ))


@chat_proto.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"ACK from {sender} for {msg.acknowledged_msg_id}")


# Confirm/cancel follow-up is handled via generic text path above.


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
