from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _write_script(tmp_path: Path, csv_path: Path) -> Path:
    script = tmp_path / "pipeline_script.py"
    script.write_text(
        "import reflet as rf\n"
        f"pipeline = rf.Source({str(csv_path)!r}).filter(lambda r: r.country == 'FR')"
        '.rename(customer="name")\n'
    )
    return script


def test_cli_show(tmp_path: Path, clients_csv: Path) -> None:
    script = _write_script(tmp_path, clients_csv)
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "show", str(script)],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    assert "Martin" in result.stdout
    assert "Smith" not in result.stdout  # UK row filtered out


def test_cli_why(tmp_path: Path, clients_csv: Path) -> None:
    script = _write_script(tmp_path, clients_csv)
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "why", str(script), "0", "customer"],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    assert str(clients_csv) in result.stdout
    assert "rename" in result.stdout
