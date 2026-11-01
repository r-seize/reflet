"""JSON source addressing a list nested inside a larger document, by path.

`rows_at="servers"` (or the more explicit "servers[*]") treats
`doc["servers"]` as the table; everything else in the document is kept
byte-for-byte except for that one list on write-back. Only a single,
non-wildcard-in-the-middle dotted path is supported (e.g. "a.b.servers");
a path like "a[*].b" addressing more than one list isn't.
"""

from __future__ import annotations

import json
from typing import IO, Any

from reflet.lens import Cell, Record, RowId, Table
from reflet.provenance import Provenance
from reflet.sources import SourceBackend, atomic_write


def _path_parts(path: str) -> list[str]:
    cleaned = path[:-3] if path.endswith("[*]") else path
    return [p for p in cleaned.split(".") if p]


def _get_path(doc: Any, path: str) -> Any:
    node = doc
    for part in _path_parts(path):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"path {path!r}: no key {part!r}")
        node = node[part]
    return node


def _set_path(doc: Any, path: str, value: Any) -> None:
    parts    = _path_parts(path)
    node     = doc
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


class JsonPathSource(SourceBackend):
    def __init__(self, path: str, row_path: str, key: str | None = None) -> None:
        super().__init__(path, key)
        self.row_path         = row_path
        self._raw_doc: Any    = None

    def read(self) -> Table:
        with open(self.path, encoding="utf-8") as fh:
            self._raw_doc = json.load(fh)
        rows = _get_path(self._raw_doc, self.row_path)
        if not isinstance(rows, list):
            raise ValueError(f"{self.path}: path {self.row_path!r} doesn't resolve to a list")
        if rows:
            self.fieldnames = list(rows[0].keys())

        table: Table          = []
        seen: set[RowId]      = set()
        order: list[RowId]    = []
        source_name           = f"{self.path}#{self.row_path}"
        for i, raw_row in enumerate(rows):
            fields        = {k: Cell(v, Provenance(source_name, k)) for k, v in raw_row.items()}
            rid: RowId    = i
            if self.key is not None:
                if self.key not in fields:
                    raise ValueError(f"{source_name}: key field {self.key!r} missing on row {i}")
                rid = fields[self.key].value
                if rid in seen:
                    raise ValueError(f"{source_name}: duplicate key {self.key}={rid!r}")
            seen.add(rid)
            order.append(rid)
            table.append(Record(rid, fields))
        self._order = order
        self._remember_fingerprint()
        return table

    def write(self, table: Table) -> None:
        by_rid      = {r.rid: r for r in table}
        new_rows    = []
        for rid in self._order:
            record = by_rid.get(rid)
            if record is None:
                continue
            keys = self.fieldnames or list(record.fields.keys())
            new_rows.append({k: record.fields[k].value for k in keys})
        _set_path(self._raw_doc, self.row_path, new_rows)

        def _write(fh: IO[str]) -> None:
            json.dump(self._raw_doc, fh, indent=2)
            fh.write("\n")

        atomic_write(self.path, _write)
        self._remember_fingerprint()
