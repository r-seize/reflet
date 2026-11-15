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


def test_render_table_escapes_tabs_and_newlines() -> None:
    rows = [{"note": "line1\nline2", "tabbed": "a\tb"}]
    text = render_table(rows)
    lines = text.splitlines()
    assert len(lines) == 2  # header + exactly one data row, despite the embedded "\n"
    assert "\\n" in lines[1]
    assert "\\t" in lines[1]


def test_render_table_truncates_long_values() -> None:
    rows = [{"text": "x" * 200}]
    text = render_table(rows)
    data_line = text.splitlines()[1]
    assert len(data_line) == 60
    assert data_line.endswith("…")


def test_render_table_renders_none() -> None:
    rows = [{"value": None}]
    assert render_table(rows) == "value\nNone"
