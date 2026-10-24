"""ASI Interactive Cards helpers (docs: asi-interactive-cards)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from uuid import uuid4
from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

OPT_FAILED = {"value": "failed", "label": "Failed / debited, not credited"}
OPT_PENDING = {"value": "pending", "label": "Pending / processing"}
OPT_UNAUTH = {"value": "unauthorised", "label": "Did not authorise this"}


def card_message(narration, card_kind, card_payload, terminal=False):
    meta = {
        "card_protocol_version": "1",
        "requires_card_interaction": "true" if not terminal else "false",
        "card_kind": card_kind,
        "card_payload": json.dumps(card_payload)[:64512],
        "preferred_drawer_width_px": "540",
    }
    if terminal:
        meta["is_terminal"] = "true"
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=narration),
            MetadataContent(type="metadata", metadata=meta),
        ],
    )


def intake_form():
    opts = [OPT_FAILED, OPT_PENDING, OPT_UNAUTH]
    return {
        "title": "PayResolve - dispute intake",
        "fields": [
            {"name": "utr", "kind": "text", "label": "UTR / Txn ID", "required": False},
            {"name": "amount", "kind": "number", "label": "Amount (INR)", "required": True},
            {"name": "status", "kind": "select", "label": "Status", "options": opts},
            {"name": "details", "kind": "text", "label": "What happened?", "required": True},
        ],
        "submit_cta": {"label": "Analyse", "selection": {"action": "intake_submit"}},
    }


def track_carousel():
    return {
        "title": "Which one matches your situation?",
        "subtitle": "Pick the closest — each path handles your money differently",
        "items": [
            {"id": "failed", "title": "I paid, but they didn't get it", "subtitle": "Money left my account; merchant not credited", "badges": [{"label": "Usually auto-refunds", "variant": "success"}], "secondary_text": "No need to panic yet", "primary_cta": {"label": "This is my case", "selection": {"action": "pick_track", "track": "failed"}}},
            {"id": "pending", "title": "Still showing 'processing'", "subtitle": "App hasn't confirmed success or failure", "badges": [{"label": "Wait — don't pay again", "variant": "warning"}], "secondary_text": "A second payment can double-charge you", "primary_cta": {"label": "This is my case", "selection": {"action": "pick_track", "track": "pending"}}},
            {"id": "unauthorised", "title": "I didn't make this payment", "subtitle": "Someone else may have used my account", "badges": [{"label": "Act today", "variant": "warning"}], "secondary_text": "Block the account, then report", "primary_cta": {"label": "This is my case", "selection": {"action": "pick_track", "track": "unauthorised"}}},
        ],
    }


def review_pack(summary_rows, approve_sel, reject_sel):
    return {
        "title": "Resolution pack - review",
        "summary_rows": summary_rows,
        "approve_cta": {"label": "Generate complaint draft", "selection": approve_sel, "primary": True},
        "reject_cta": {"label": "Start over", "selection": reject_sel},
    }


def parse_selection(text):
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    low = (text or "").lower()
    sel = {}
    if "unauthor" in low or "fraud" in low:
        sel["track"] = "unauthorised"
    elif "pending" in low or "processing" in low:
        sel["track"] = "pending"
    elif "fail" in low or "debit" in low:
        sel["track"] = "failed"
    for key in ("confirm", "cancel", "back", "intake_submit", "pick_track"):
        if key in low:
            sel["action"] = key
    return sel
