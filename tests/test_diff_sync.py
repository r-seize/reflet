"""diff()/dry-run, conflict detection, atomic write, undo/redo, journal."""

from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf
from reflet.errors import SourceConflictError


def test_diff_previews_without_writing(clients_csv: Path) -> None:
    view      = rf.Source(str(clients_csv), key="id").run()
    before    = clients_csv.read_text()

    view[0].name    = "Changed"
    changes         = view.diff()

    assert len(changes) == 1
    assert changes[0].field == "name"
    assert changes[0].before == "Martin"
    assert changes[0].after == "Changed"
    assert clients_csv.read_text() == before  # nothing written


def test_sync_dry_run_matches_diff_and_does_not_write(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    before          = clients_csv.read_text()
    view[0].name    = "Changed"

    assert view.sync(dry_run=True) == view.diff()
    assert clients_csv.read_text() == before


def test_sync_returns_committed_changes(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    changes         = view.sync()
    assert len(changes) == 1
    assert "Changed" in clients_csv.read_text()


def test_sync_raises_on_external_conflict(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    clients_csv.write_text(clients_csv.read_text() + "")  # touch: unrelated external write
    with open(clients_csv, "a") as fh:
        fh.write("5,Extra,BE,99\n")

    with pytest.raises(SourceConflictError):
        view.sync()


def test_sync_force_bypasses_conflict(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    with open(clients_csv, "a") as fh:
        fh.write("5,Extra,BE,99\n")

    view.sync(force=True)
    assert "Changed" in clients_csv.read_text()


def test_undo_reverts_uncommitted_edit(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    assert view.undo() is True
    assert str(view[0].name) == "Martin"
    assert view.diff() == []  # edit fully reverted, nothing pending


def test_undo_reverts_a_committed_sync(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    view.sync()
    assert "Changed" in clients_csv.read_text()

    assert view.undo() is True
    assert "Changed" not in clients_csv.read_text()
    assert "Martin" in clients_csv.read_text()


def test_redo_reapplies_undone_sync(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    view.sync()
    view.undo()
    assert view.redo() is True
    assert "Changed" in clients_csv.read_text()


def test_undo_with_nothing_to_undo_returns_false(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    assert view.undo() is False
    assert view.redo() is False


def test_journal_records_committed_writes_only(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    view.diff()  # preview: must not journal
    assert view.journal == ()

    view.sync()
    assert len(view.journal) == 1
    entry = view.journal[0]
    assert entry.field == "name"
    assert entry.before == "Martin"
    assert entry.after == "Changed"


def test_identity_pipeline_view_is_not_aliased_to_source(clients_csv: Path) -> None:
    """Regression: a zero-lens pipeline used to share the view's list object
    with the source table, so editing the view silently mutated the source
    before sync() ever ran, breaking diff()/undo()."""
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    assert view.diff() != []  # if aliased, the "before" value would already be "Changed"
