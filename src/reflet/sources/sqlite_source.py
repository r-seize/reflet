"""SQLite source backend, via the stdlib `sqlite3` module."""

from __future__ import annotations

import sqlite3

from reflet.lens import Cell, Record, RowId, Table
from reflet.provenance import Provenance
from reflet.sources import SourceBackend


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class SqliteSource(SourceBackend):
    """Reads/writes one table of a SQLite database file.

    Write-back replaces the table's contents wholesale (delete + reinsert,
    in one transaction) rather than diffing individual rows, same as the
    CSV/JSON backends: only the columns seen on read are written back.
    """

    def __init__(self, path: str, table: str, key: str | None = None) -> None:
        super().__init__(path, key)
        self.table = table

    def read(self) -> Table:
        conn = sqlite3.connect(self.path)
        try:
            conn.row_factory    = sqlite3.Row
            cur                 = conn.execute(f"SELECT * FROM {_quote_identifier(self.table)}")
            rows                = cur.fetchall()
            self.fieldnames     = [d[0] for d in cur.description]
        finally:
            conn.close()

        table: Table          = []
        seen: set[RowId]      = set()
        order: list[RowId]    = []
        source_name           = f"{self.path}#{self.table}"
        for i, raw_row in enumerate(rows):
            fields = {
                k: Cell(v, Provenance(source_name, k)) for k, v in dict(raw_row).items()
            }
            rid: RowId = i
            if self.key is not None:
                if self.key not in fields:
                    raise ValueError(
                        f"{self.path}#{self.table}: key field {self.key!r} missing on row {i}"
                    )
                rid = fields[self.key].value
                if rid in seen:
                    raise ValueError(f"{self.path}#{self.table}: duplicate key {self.key}={rid!r}")
            seen.add(rid)
            order.append(rid)
            table.append(Record(rid, fields))
        self._order = order
        self._remember_fingerprint()
        return table

    def write(self, table: Table) -> None:
        by_rid          = {r.rid: r for r in table}
        cols            = self.fieldnames or (list(table[0].fields.keys()) if table else [])
        qtable          = _quote_identifier(self.table)
        qcols           = ", ".join(_quote_identifier(c) for c in cols)
        placeholders    = ", ".join("?" for _ in cols)

        conn = sqlite3.connect(self.path)
        try:
            with conn:
                conn.execute(f"DELETE FROM {qtable}")
                for rid in self._order:
                    record = by_rid.get(rid)
                    if record is None:
                        continue
                    conn.execute(
                        f"INSERT INTO {qtable} ({qcols}) VALUES ({placeholders})",
                        [record.fields[c].value for c in cols],
                    )
        finally:
            conn.close()
        self._remember_fingerprint()
