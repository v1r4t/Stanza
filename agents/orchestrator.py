"""PayResolve orchestrator — public ACP entry point.

Docs used:
- uagent-creation (mailbox=True, publish_agent_details, Python 3.10-13, uagents>=0.25.5)
- asi-interactive-cards (MetadataContent card wire protocol)
- asione quickstart (ASI1 via OpenAI-compatible API, model asi1-mini default)
- uagents-adapter-guide (LangChain inside handler + optional Adapter publish)
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
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

load_dotenv()
SEED = os.getenv("AGENT_SEED", "payresolve-dev-seed-do-not-use-in-prod")

agent = Agent(
    name="PayResolve",
    seed=SEED,
    port=8001,
    mailbox=True,
    publish_agent_details=True,
    network="testnet",
)

fund_agent_if_low(str(agent.wallet.address()))

chat_proto = Protocol(spec=chat_protocol_spec)


def _text(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


_MISSING_LABEL = {
    "utr": "the 12-digit UTR from your payment history",
    "amount": "the amount in INR",
    "details": "a one-line description (date, app, merchant)",
    "status": "what your app shows (failed, pending, or processing)",
    "utr_or_date": "the UTR or transaction date",
    "bank acknowledgement + cybercrime ref (1930 / cybercrime.gov.in)": "your bank's acknowledgement / cybercrime reference (call 1930)",
}


def _asi1_reply(prompt: str) -> str | None:
    key = os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=key)
        r = client.chat.completions.create(
            model=os.getenv("ASI1_MODEL", "asi1-mini"),
            messages=[
                {"role": "system", "content": "You are PayResolve intake. Be concise. Never promise refunds. Preserve failed/pending/unauthorised distinction."},
                {"role": "user", "content": prompt[:2000]},
            ],
            max_tokens=300,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception:
        return None


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

    if not last or last.strip().lower() in {"hi", "hello", "start", "help"}:
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
        draft = saved.get("draft") if isinstance(saved, dict) else None
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
    if sel.get("action") in {"intake_submit", "pick_track"} or "track" in sel:
        detail = f"{sel.get('track','')} amount={sel.get('amount','')} utr={sel.get('utr','')} {sel.get('details','')} {last}"
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

    triage = triage_text(detail)
    # explicit track override from card
    if sel.get("track") in {"failed", "pending", "unauthorised"}:
        from core.schemas import TransactionType
        triage.transaction_type = TransactionType(sel["track"])
        triage.urgency = "high" if sel["track"] == "unauthorised" else triage.urgency

    policy = policy_for(triage)
    pack = build_pack(triage, policy)

    # Step 1: show classification carousel for confirmation if unknown/low-confidence.
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
            "I couldn't tell which situation this is — pick the closest one below.",
            "carousel", track_carousel(),
        ))
        return

    narration, rows = elaborate_assessment(triage, policy)
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
        })
    except Exception:
        pass
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
