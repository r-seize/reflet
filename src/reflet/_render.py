"""Tiny shared TSV rendering, used by `Pipeline.preview()`, `View.head()`, and the CLI."""

from __future__ import annotations

_MAX_CELL_LENGTH = 60


def _render_cell(value: object) -> str:
    text = str(value)
    # a literal tab or newline would misalign/break the one-row-per-line format
    text = text.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    if len(text) > _MAX_CELL_LENGTH:
        text = text[: _MAX_CELL_LENGTH - 1] + "…"
    return text


def render_table(rows: list[dict[str, object]], limit: int | None = None) -> str:
    """Render rows (as from `View.to_dicts()`) as a tab-separated table.

    Cell values are rendered with `str()`; missing/`None` values render as
    the literal text `"None"`. Tabs/newlines within a value are escaped
    (`\\t`/`\\n`) and values longer than 60 characters are truncated with
    `…`, so one row always stays on one line.
    """
    if not rows:
        return "(empty view)"
    shown = rows if limit is None else rows[:limit]
    fields = list(shown[0].keys())
    lines = ["\t".join(fields)]
    lines.extend("\t".join(_render_cell(row[f]) for f in fields) for row in shown)
    return "\n".join(lines)
