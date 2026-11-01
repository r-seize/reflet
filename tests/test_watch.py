"""View.watch(): polling auto-sync, bounded by max_iterations for tests."""

from __future__ import annotations

from pathlib import Path

import reflet as rf


def test_watch_flushes_pending_edits(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Watched"
    view.watch(interval=0.001, max_iterations=1)
    assert "Watched" in clients_csv.read_text()


def test_watch_calls_on_change_for_external_edit(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    with open(clients_csv, "a") as fh:
        fh.write("5,External,BE,1\n")

    calls: list[int] = []
    view.watch(interval=0.001, max_iterations=1, on_change=lambda: calls.append(1))
    assert len(calls) == 1


def test_watch_no_op_when_nothing_pending_or_changed(clients_csv: Path) -> None:
    view                = rf.Source(str(clients_csv), key="id").run()
    calls: list[int]    = []
    view.watch(interval=0.001, max_iterations=3, on_change=lambda: calls.append(1))
    assert calls == []


def test_watch_reports_conflict_via_on_change_instead_of_raising(clients_csv: Path) -> None:
    view            = rf.Source(str(clients_csv), key="id").run()
    view[0].name    = "Changed"
    with open(clients_csv, "a") as fh:
        fh.write("5,External,BE,1\n")

    calls = []
    view.watch(interval=0.001, max_iterations=1, on_change=lambda: calls.append(1))
    assert calls == [1]
    assert "Changed" not in clients_csv.read_text()  # sync() didn't force through
