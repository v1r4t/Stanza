from core.resolution import triage_text, policy_for, build_pack
from core.security import redact


def test_pack_has_draft_and_sources():
    t = triage_text("Failed UPI Rs 2000, UTR 123456789012, debited not credited")
    p = policy_for(t)
    pack = build_pack(t, p)
    assert pack.complaint_draft
    assert pack.official_sources
    assert p.refund_guaranteed is False


def test_redaction():
    assert "[REDACTED" in redact("my card 4111111111111111 and otp 123456")
    assert "4111111111111111" not in redact("my card 4111111111111111")
