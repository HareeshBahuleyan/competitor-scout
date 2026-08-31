from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_live_evals.py"


def run_script(*args: str, allow_paid: bool = False) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if allow_paid:
        environment["ALLOW_PAID_OTARI_EVALS"] = "true"
    else:
        environment.pop("ALLOW_PAID_OTARI_EVALS", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


def test_live_eval_requires_environment_opt_in() -> None:
    result = run_script("--confirm-paid-run")

    assert result.returncode == 2
    assert "ALLOW_PAID_OTARI_EVALS=true" in result.stderr


def test_live_eval_requires_second_confirmation_flag() -> None:
    result = run_script(allow_paid=True)

    assert result.returncode == 2
    assert "--confirm-paid-run" in result.stderr
