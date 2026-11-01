"""Stable row identity via `key=`."""

from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf


def test_key_identity_used_as_rid_in_diff_and_journal(clients_csv: Path) -> None:
    """With `key=`, Change/JournalEntry.rid is the business key (e.g. the id),
    not an opaque file position — directly readable in a diff or audit log."""
    view               = rf.Source(str(clients_csv), key="id").run()
    martin_row         = next(row for row in view if str(row.name) == "Martin")
    martin_row.name    = "Martin2"

    changes = view.diff()
    assert len(changes) == 1
    assert changes[0].rid == 1  # the "id" column's value, not a position

    view.sync()
    assert view.journal[0].rid == 1


def test_without_key_rid_is_positional_index(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv)).run()  # no key: identity = position
    view[2].name    = "Changed"  # third row, Durand

    changes = view.diff()
    assert len(changes) == 1
    assert changes[0].rid == 2  # position, not the "id" column's value (3)


def test_duplicate_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "dupes.csv"
    path.write_text("id,name\n1,A\n1,B\n")
    with pytest.raises(ValueError, match="duplicate key"):
        rf.Source(str(path), key="id").run()


def test_missing_key_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "nokey.csv"
    path.write_text("name\nA\n")
    with pytest.raises(ValueError, match="missing"):
        rf.Source(str(path), key="id").run()


def test_key_based_writeback_targets_the_right_row_regardless_of_position(
    clients_csv: Path,
) -> None:
    """The write-back lookup is by key value, so it's immune to whatever
    position the row happens to occupy in the in-memory table."""
    view                = rf.Source(str(clients_csv), key="id").run()
    dupont_row          = next(row for row in view if str(row.name) == "Dupont")
    dupont_row.price    = 999
    view.sync()

    content = clients_csv.read_text()
    assert "4,Dupont,FR,999" in content
    assert "1,Martin,FR,10" in content  # other rows untouched
