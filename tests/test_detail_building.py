"""Regression guard: a card selection must never discard the user's sentence.

Bug this prevents: parse_selection infers a track from keywords ("debit"),
which made the orchestrator treat the message as a card submission and build
detail from empty sel fields — silently losing UTR, amount and date.
"""
from core.cards import parse_selection, build_detail
from core.resolution import triage_text


MESSAGE = "Rs 2500 debited 3 days ago, merchant not credited, UTR 897543239485"


def test_keyword_track_keeps_full_message():
    sel = parse_selection(MESSAGE)
    assert sel.get("track") == "failed"  # keyword-inferred, not a real card
    detail = build_detail(sel, MESSAGE)
    assert "897543239485" in detail
    assert "2500" in detail
    assert "3 days ago" in detail


def test_pipeline_recovers_utr_amount_and_day():
    detail = build_detail(parse_selection(MESSAGE), MESSAGE)
    t = triage_text(detail)
    assert t.utr == "897543239485"
    assert t.amount == 2500.0
    assert t.days_elapsed == 3


def test_form_submission_merges_fields_and_message():
    sel = {"action": "intake_submit", "status": "pending", "amount": "500", "utr": "", "details": "swiggy"}
    detail = build_detail(sel, '{"action":"intake_submit"}')
    assert "pending" in detail and "500" in detail and "swiggy" in detail


def test_plain_message_passthrough():
    assert build_detail({}, MESSAGE) == MESSAGE
