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


def test_view_head_shows_current_state_including_pending_edits(
    clients_csv: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unlike preview() (which re-runs the pipeline fresh), head() reflects
    whatever the view currently holds — edited or not, synced or not."""
    view = rf.Source(str(clients_csv)).run()
    view[0].name = "Pending"
    view.head(1)
    out = capsys.readouterr().out
    assert "Pending" in out
    assert "Pending" not in clients_csv.read_text()  # not synced yet


def test_view_to_dicts_with_fields_selects_and_orders_columns(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv)).run()
    dicts = view.to_dicts(fields=["price", "name"])
    assert list(dicts[0].keys()) == ["price", "name"]
    assert dicts[0] == {"price": 10, "name": "Martin"}


def test_view_context_manager_syncs_on_early_return(clients_csv: Path) -> None:
    """`with ... as view: ...; return` still runs __exit__, same as falling
    off the end of the block — Python guarantees this regardless of how
    control leaves."""

    def edit_and_return() -> None:
        with rf.Source(str(clients_csv), key="id").run() as view:
            view[0].name = "Changed"
            return

    edit_and_return()
    assert "Changed" in clients_csv.read_text()


def test_undo_redo_inside_context_manager_then_sync_on_exit(clients_csv: Path) -> None:
    with rf.Source(str(clients_csv), key="id").run() as view:
        view[0].name = "Changed"
        view.undo()
        view[0].name = "FinalValue"
    content = clients_csv.read_text()
    assert "FinalValue" in content
    assert "Changed" not in content


def test_context_manager_propagates_sync_conflict_on_exit(clients_csv: Path) -> None:
    from reflet.errors import SourceConflictError

    with pytest.raises(SourceConflictError):
        with rf.Source(str(clients_csv), key="id").run() as view:
            view[0].name = "Changed"
            with open(clients_csv, "a") as fh:
                fh.write("5,External,BE,1\n")
    # the conflicting edit never got written
    assert "Changed" not in clients_csv.read_text()
