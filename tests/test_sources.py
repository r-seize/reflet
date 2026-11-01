from __future__ import annotations

import json
from pathlib import Path

import pytest

import reflet as rf


def test_csv_roundtrip_types(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv)).run()
    assert view[0].id.value == 1  # inferred int
    assert view[0].price.value == 10  # inferred int
    view[0].name = "Changed"
    view.sync()
    assert "Changed,FR,10" in clients_csv.read_text()


def test_json_source_roundtrip(clients_json: Path) -> None:
    view = rf.Source(str(clients_json)).run()
    assert len(view) == 3
    view[0].name = "Changed"
    view.sync()

    data = json.loads(clients_json.read_text())
    assert data[0]["name"] == "Changed"
    assert data[1]["name"] == "Smith"


def test_unsupported_extension_raises() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        rf.Source("data.txt")


def test_atomic_write_leaves_no_temp_file_on_success(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv)).run()
    view[0].name    = "Changed"
    view.sync()
    leftovers = list(clients_csv.parent.glob(".reflet-*"))
    assert leftovers == []


def test_atomic_write_cleans_up_on_failure(clients_csv: Path) -> None:
    from reflet.sources import atomic_write

    before = clients_csv.read_text()

    def _boom(fh: object) -> None:
        raise RuntimeError("simulated failure mid-write")

    with pytest.raises(RuntimeError, match="simulated failure"):
        atomic_write(str(clients_csv), _boom)

    assert clients_csv.read_text() == before  # original file untouched
    assert list(clients_csv.parent.glob(".reflet-*")) == []  # temp file cleaned up
