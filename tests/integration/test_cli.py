"""The command line: exit codes, actionable error messages, and that real bugs are
not hidden behind a friendly message."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import PROJECT_ROOT, CsvFactory

from ticket_pipeline import cli

pytestmark = pytest.mark.integration


def run_cli(*args: str) -> int:
    return cli.main(list(args))


def test_successful_run_exits_0_prints_json_and_writes_files(
    real_sample_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"

    code = run_cli("--input", str(real_sample_csv), "--output-dir", str(out))

    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert json.loads(captured.out)["duplicate_ticket_ids"] == ["T-002"]
    assert sorted(path.name for path in out.iterdir()) == [
        "analytics.json",
        "cleaned_tickets.csv",
        "quality_issues.csv",
    ]
    assert "pipeline_finished tickets=23" in captured.err  # logs go to stderr, data to stdout


@pytest.mark.parametrize(
    ("body", "header", "expected"),
    [
        (None, None, "does not exist. Check the spelling"),
        ("T-1,billing,high\n", None, "line 2: expected 7 fields, found 3"),
        ("", "id,category\n", "missing required column(s): ticket_id"),
        ("", None, "header row but no ticket records"),
    ],
    ids=["missing-file", "malformed-row", "schema-mismatch", "header-only"],
)
def test_input_problems_exit_2_with_an_actionable_message(
    csv_factory: CsvFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    body: str | None,
    header: str | None,
    expected: str,
) -> None:
    if body is None:
        path = tmp_path / "missing.csv"
    elif header is None:
        path = csv_factory(body)
    else:
        path = csv_factory(body, header=header)

    code = run_cli("--input", str(path), "--output-dir", str(tmp_path / "out"))

    err = capsys.readouterr().err
    assert code == cli.EXIT_PIPELINE_ERROR
    assert expected in err
    assert "Traceback" not in err
    assert "pipeline_failed" in err


def test_duplicate_policy_raise_exits_2(
    real_sample_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_cli(
        "--input", str(real_sample_csv), "--output-dir", str(tmp_path / "o"),
        "--duplicate-policy", "raise",
    )  # fmt: skip

    assert code == cli.EXIT_PIPELINE_ERROR
    assert "T-002 appears in record 2 and again in record 23" in capsys.readouterr().err


def test_output_that_would_overwrite_the_input_is_refused(
    csv_factory: CsvFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = csv_factory("T-1,billing,high,x,2,5,open\n", name="cleaned_tickets.csv")
    original = raw.read_bytes()

    code = run_cli("--input", str(raw), "--output-dir", str(raw.parent))

    assert code == cli.EXIT_PIPELINE_ERROR
    assert "it is the input file" in capsys.readouterr().err
    assert raw.read_bytes() == original


def test_invalid_option_value_is_rejected_by_argparse(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_cli("--log-level", "loud")

    assert caught.value.code == 2
    assert "invalid choice: 'loud'" in capsys.readouterr().err


def test_unexpected_bugs_are_not_hidden(
    monkeypatch: pytest.MonkeyPatch, real_sample_csv: Path, tmp_path: Path
) -> None:
    # Simulates a programming error inside the pipeline: the CLI must not turn it
    # into a friendly exit code, or the bug would be silently masked.
    def broken(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError("bug")

    monkeypatch.setattr(cli, "run_pipeline", broken)

    with pytest.raises(ZeroDivisionError):
        run_cli("--input", str(real_sample_csv), "--output-dir", str(tmp_path))


def test_module_entry_point_runs_as_a_real_process(real_sample_csv: Path, tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
    command = [sys.executable, "-m", "ticket_pipeline", "--input", str(real_sample_csv),
               "--output-dir", str(tmp_path / "out"), "--log-level", "WARNING"]  # fmt: skip

    completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["unresolved_ticket_count"] == 10
