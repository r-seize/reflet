from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import reflet as rf


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


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "--version"],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    assert f"reflet {rf.__version__}" in result.stdout


def test_cli_fields(tmp_path: Path, clients_csv: Path) -> None:
    script = _write_script(tmp_path, clients_csv)
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "fields", str(script)],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    assert result.stdout.splitlines() == ["id", "country", "price", "customer"]


def test_cli_show_json(tmp_path: Path, clients_csv: Path) -> None:
    script = _write_script(tmp_path, clients_csv)
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "show", str(script), "--json"],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    rows = json.loads(result.stdout)
    assert len(rows) == 3
    assert {row["customer"] for row in rows} == {"Martin", "Durand", "Dupont"}
