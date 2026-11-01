from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf
from reflet.errors import UnknownFieldError


def test_full_pipeline_edit_and_sync(clients_csv: Path) -> None:
    pipeline = (
        rf.Source(str(clients_csv))
        .filter(lambda r: r.country == "FR")
        .rename(customer="name")
        .map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
    )
    view = pipeline.run()
    assert len(view) == 3  # Martin, Durand, Dupont are FR; Smith (UK) is filtered out

    names = [str(row.customer) for row in view]
    assert names == ["Martin", "Durand", "Dupont"]
    assert view[0].price.value == 12.0  # 10 * 1.2

    view[0].customer = "Dupont"
    view.sync()

    content = clients_csv.read_text()
    assert "Dupont" in content
    assert "Martin" not in content
    # UK row untouched
    assert "Smith,UK,20" in content


def test_sync_without_edits_is_noop(clients_csv: Path) -> None:
    pipeline    = rf.Source(str(clients_csv)).filter(lambda r: r.country == "FR")
    view        = pipeline.run()
    before      = clients_csv.read_text()
    view.sync()
    assert clients_csv.read_text() == before


def test_select_pipeline(clients_csv: Path) -> None:
    pipeline    = rf.Source(str(clients_csv)).select("name", "price")
    view        = pipeline.run()
    assert len(view) == 4
    row = view[0]
    assert str(row.name) == "Martin"
    with pytest.raises(UnknownFieldError):
        _ = row.country
