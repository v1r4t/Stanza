"""Guard: the committed hosted bundles must match a fresh build.

If this fails, someone edited sources (or a bundle) without rerunning
`python scripts/build_hosted.py` — the Agentverse pastes would be stale.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLES = [
    "hosted_payresolve.py",
    "hosted_triage.py",
    "hosted_policy.py",
    "hosted_evidence.py",
]


def test_hosted_bundles_present():
    for name in BUNDLES:
        assert (ROOT / name).is_file(), f"missing {name} — run scripts/build_hosted.py"


def test_hosted_bundles_have_no_local_imports():
    for name in BUNDLES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "load_dotenv" not in text, f"{name} still imports dotenv"
        for line in text.splitlines():
            s = line.strip()
            assert not s.startswith("from core"), f"{name}: {s}"
            assert not s.startswith("from ."), f"{name}: {s}"


def test_hosted_bundles_up_to_date():
    before = {n: (ROOT / n).read_text(encoding="utf-8") for n in BUNDLES}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_hosted.py")],
        cwd=ROOT, check=True, capture_output=True,
    )
    for name in BUNDLES:
        after = (ROOT / name).read_text(encoding="utf-8")
        assert before[name] == after, f"{name} stale — rerun build_hosted.py and commit"
