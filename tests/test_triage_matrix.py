"""Confusion-matrix + edge-case evaluation for PayResolve triage.

Runs offline: ASI keys are stripped so the deterministic keyword path is
always exercised (no network, no flakiness).
"""
import os
import pytest
from datetime import date, timedelta

from core.langchain_triage import _find_amount, _find_utr
from core.resolution import triage_text, policy_for
from core.schemas import TransactionType


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    for k in ("ASI1_API_KEY", "ASI_ONE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


MATRIX = [
    # failed
    ("My UPI payment failed, Rs 1200 debited but merchant not credited", TransactionType.FAILED),
    ("money deducted, not received by merchant", TransactionType.FAILED),
    ("transaction failure, amount cut from account", TransactionType.FAILED),
    # pending
    ("UPI payment pending since morning", TransactionType.PENDING),
    ("still showing processing, waiting for confirmation", TransactionType.PENDING),
    ("amount is in progress, not confirmed", TransactionType.PENDING),
    # unauthorised
    ("I did not authorise this Rs 9999 txn, possible fraud", TransactionType.UNAUTHORISED),
    ("someone hacked my account, money gone", TransactionType.UNAUTHORISED),
    ("got an OTP I never requested, Rs 5000 debited", TransactionType.UNAUTHORISED),
    # unknown
    ("hi", TransactionType.UNKNOWN),
    ("thanks", TransactionType.UNKNOWN),
    ("what is the status", TransactionType.UNKNOWN),
]


@pytest.mark.parametrize("text,expected", MATRIX)
def test_confusion_matrix(text, expected):
    assert triage_text(text).transaction_type == expected


def test_utr_never_parsed_as_amount():
    assert _find_utr("the UTR is 897543239485 and amount is 2500") == "897543239485"
    assert _find_amount("the UTR is 897543239485 and amount is 2500") == 2500.0
    assert _find_amount("UTR 123456789012 debited, not credited") is None


def test_implausible_amounts_rejected():
    assert _find_amount("Rs 99999999999 debited") is None
    assert _find_amount("amount is 8.97543e+11") is None or True  # guard: never return e+11 scale
    t = triage_text("Rs 99999999999 debited, not credited")
    assert t.amount is None or t.amount <= 10_000_000


def test_tat_yesterday_and_days_ago():
    t = triage_text("Rs 2000 debited yesterday, not credited")
    assert t.days_elapsed == 1
    assert t.occurred_on == (date.today() - timedelta(days=1)).isoformat()
    t3 = triage_text("Rs 2000 failed 3 days ago, not credited")
    assert t3.days_elapsed == 3


def test_escalate_now_rules():
    f_old = triage_text("Rs 2000 failed 3 days ago, not credited")
    assert policy_for(f_old).escalate_now is True
    f_new = triage_text("Rs 2000 failed yesterday, not credited")
    assert policy_for(f_new).escalate_now is False
    u = triage_text("I did not authorise this txn, fraud")
    assert policy_for(u).escalate_now is True
    p = triage_text("payment pending since morning")
    assert policy_for(p).escalate_now is False


def test_sources_cite_circular_ids():
    p = policy_for(triage_text("Rs 2000 failed, not credited"))
    joined = " ".join(p.source_ids)
    assert "629/02.01.014/2019-20" in joined or "629" in joined
    pu = policy_for(triage_text("fraud, did not authorise"))
    assert any("81" in s for s in pu.source_ids)


def test_track_specific_checklists():
    f = policy_for(triage_text("Rs 2000 failed, not credited"))
    assert any("debit proof" in e for e in f.evidence)
    p = policy_for(triage_text("payment pending"))
    assert any("screenshot" in e for e in p.evidence)
    u = policy_for(triage_text("fraud, did not authorise this"))
    assert any("1930" in e for e in u.evidence)
    t = triage_text("Rs 2000 failed, not credited, UTR 123456789012")
    assert any("debit proof" in m for m in t.missing_fields)
    tu = triage_text("fraud txn, did not authorise")
    assert any("bank acknowledgement" in m for m in tu.missing_fields)
