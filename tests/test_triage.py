from core.resolution import triage_text, policy_for, build_pack
from core.policy_rules import get_resolution_track
from core.schemas import TransactionType


def test_failed_distinct_from_pending():
    f = triage_text("My UPI payment failed, Rs 1200 debited but merchant not credited")
    p = triage_text("UPI payment pending, processing since morning, Rs 500")
    assert f.transaction_type == TransactionType.FAILED
    assert p.transaction_type == TransactionType.PENDING
    assert f.transaction_type != p.transaction_type


def test_unauthorised_high_urgency():
    u = triage_text("I did not authorise this Rs 9999 txn, possible fraud, please help")
    assert u.transaction_type == TransactionType.UNAUTHORISED
    assert u.urgency == "high"


def test_unknown_when_vague():
    u = triage_text("hi")
    assert u.transaction_type == TransactionType.UNKNOWN
    assert "status" in u.missing_fields or len(u.missing_fields) > 0
