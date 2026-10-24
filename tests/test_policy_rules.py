from core.policy_rules import get_resolution_track
from core.schemas import TransactionType


def test_tracks_are_distinct():
    assert get_resolution_track(TransactionType.FAILED)["track"] == "failed_payment"
    assert get_resolution_track(TransactionType.PENDING)["track"] == "pending_payment"
    assert get_resolution_track(TransactionType.UNAUTHORISED)["track"] == "unauthorised_payment"
    assert get_resolution_track(TransactionType.UNKNOWN)["track"] == "unknown"


def test_never_guarantees_refund():
    for t in TransactionType:
        assert get_resolution_track(t)["refund_guaranteed"] is False


def test_unauthorised_escalates_to_bank():
    r = get_resolution_track(TransactionType.UNAUTHORISED)
    joined = " ".join(r["escalation"] + r["actions"]).lower()
    assert "bank" in joined or "cybercrime" in joined
