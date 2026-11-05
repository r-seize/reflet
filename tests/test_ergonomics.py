"""Pipeline/View __repr__, context manager, to_dicts(), rows, preview()."""

from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf


def test_pipeline_repr_lists_lens_names(clients_csv: Path) -> None:
    pipeline = rf.Source(str(clients_csv)).filter(lambda r: r.country == "FR").rename(
        customer="name"
    )
    text = repr(pipeline)
    assert str(clients_csv) in text
    assert "filter" in text
    assert "rename" in text


def test_pipeline_repr_with_no_lenses(clients_csv: Path) -> None:
    text = repr(rf.Source(str(clients_csv)))
    assert "none" in text


def test_view_repr_shows_row_count_and_fields(clients_csv: Path) -> None:
    view    = rf.Source(str(clients_csv)).run()
    text    = repr(view)
    assert "4 rows" in text
    assert "name" in text


def test_view_context_manager_syncs_on_clean_exit(clients_csv: Path) -> None:
    with rf.Source(str(clients_csv), key="id").run() as view:
        view[0].name = "Changed"
    assert "Changed" in clients_csv.read_text()


def test_view_context_manager_does_not_sync_on_exception(clients_csv: Path) -> None:
    before = clients_csv.read_text()
    try:
        with rf.Source(str(clients_csv), key="id").run() as view:
            view[0].name = "Changed"
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert clients_csv.read_text() == before


def test_view_rows_property(clients_csv: Path) -> None:
    view    = rf.Source(str(clients_csv)).run()
    rows    = view.rows
    assert len(rows) == len(view)
    assert str(rows[0].name) == str(view[0].name)


def test_view_to_dicts(clients_csv: Path) -> None:
    view     = rf.Source(str(clients_csv)).run()
    dicts    = view.to_dicts()
    assert len(dicts) == len(view)
    assert dicts[0] == {"id": 1, "name": "Martin", "country": "FR", "price": 10}


def test_pipeline_preview_prints_limited_rows(
    clients_csv: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pipeline = rf.Source(str(clients_csv))
    pipeline.preview(2)
    out      = capsys.readouterr().out
    lines    = out.strip().splitlines()
    assert len(lines) == 3  # header + 2 rows
