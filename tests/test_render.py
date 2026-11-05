from __future__ import annotations

from reflet._render import render_table


def test_render_table_empty() -> None:
    assert render_table([]) == "(empty view)"


def test_render_table_basic() -> None:
    rows = [{"id": 1, "name": "Martin"}, {"id": 2, "name": "Smith"}]
    assert render_table(rows) == "id\tname\n1\tMartin\n2\tSmith"


def test_render_table_limit() -> None:
    rows = [{"id": i} for i in range(5)]
    text = render_table(rows, limit=2)
    assert text == "id\n0\n1"
