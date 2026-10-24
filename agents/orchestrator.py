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
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from core.cards import card_message, intake_form, track_carousel, review_pack, parse_selection
from core.resolution import triage_text, policy_for, build_pack
from core.security import redact

load_dotenv()
SEED = os.getenv("AGENT_SEED", "payresolve-dev-seed-do-not-use-in-prod")

agent = Agent(
    name="PayResolve",
    seed=SEED,
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)

chat_proto = Protocol(spec=chat_protocol_spec)


def _text(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


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
    # intake form submit or track pick carries JSON
    if sel.get("action") in {"intake_submit", "pick_track"} or "track" in sel:
        detail = f"{sel.get('track','')} amount={sel.get('amount','')} utr={sel.get('utr','')} {sel.get('details','')} {last}"
    else:
        detail = last

    triage = triage_text(redact(detail))
    # explicit track override from card
    if sel.get("track") in {"failed", "pending", "unauthorised"}:
        from core.schemas import TransactionType
        triage.transaction_type = TransactionType(sel["track"])
        triage.urgency = "high" if sel["track"] == "unauthorised" else triage.urgency

    policy = policy_for(triage)
    pack = build_pack(triage, policy)

    # Step 1: show classification carousel for confirmation if unknown/low-confidence
    if triage.transaction_type.value == "unknown":
        await ctx.send(sender, card_message(
            "I couldn't classify this yet — which matches? (failed / pending / unauthorised are different tracks)",
            "carousel", track_carousel(),
        ))
        return

    llm_note = _asi1_reply(f"Summarise in 2 lines: track={triage.transaction_type.value}, urgency={triage.urgency}, report={redact(detail)[:500]}")
    summary = llm_note or f"Track: {triage.transaction_type.value} | Urgency: {triage.urgency} | Refund guaranteed: False"

    rows = [
        {"label": "Track", "value": triage.transaction_type.value},
        {"label": "UTR", "value": triage.utr or "missing"},
        {"label": "Amount", "value": str(triage.amount) if triage.amount is not None else "missing"},
        {"label": "Next", "value": ", ".join(policy.timelines[:2])},
        {"label": "Note", "value": summary[:120]},
    ]
    await ctx.send(sender, card_message(
        f"Assessment: {summary}. Review the pack — I cite official sources, never promise refunds.",
        "review",
        review_pack(rows, {"action": "confirm_pack"}, {"action": "cancel"}),
    ))
    # store pack in storage for confirm step
    try:
        ctx.storage.set(sender, {"draft": pack.complaint_draft, "track": triage.transaction_type.value})
    except Exception:
        pass


@chat_proto.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"ACK from {sender} for {msg.acknowledged_msg_id}")


# Confirm/cancel follow-up is handled via generic text path above.


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
