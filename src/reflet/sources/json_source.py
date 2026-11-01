"""JSON source backend: a file containing a list of flat objects."""

from __future__ import annotations

import json
from typing import IO

from reflet.lens import Cell, Record, RowId, Table
from reflet.provenance import Provenance
from reflet.sources import SourceBackend, atomic_write


class JsonSource(SourceBackend):
    def read(self) -> Table:
        with open(self.path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, list):
            raise ValueError(f"{self.path}: expected a JSON array of objects")
        if raw:
            self.fieldnames = list(raw[0].keys())

        table: Table          = []
        seen: set[RowId]      = set()
        order: list[RowId]    = []
        for i, raw_row in enumerate(raw):
            fields        = {k: Cell(v, Provenance(self.path, k)) for k, v in raw_row.items()}
            rid: RowId    = i
            if self.key is not None:
                if self.key not in fields:
                    raise ValueError(f"{self.path}: key field {self.key!r} missing on row {i}")
                rid = fields[self.key].value
                if rid in seen:
                    raise ValueError(f"{self.path}: duplicate key {self.key}={rid!r}")
            seen.add(rid)
            order.append(rid)
            table.append(Record(rid, fields))
        self._order = order
        self._remember_fingerprint()
        return table

    def write(self, table: Table) -> None:
        by_rid = {r.rid: r for r in table}

        def _write(fh: IO[str]) -> None:
            rows = []
            for rid in self._order:
                record = by_rid.get(rid)
                if record is None:
                    continue
                keys = self.fieldnames or list(record.fields.keys())
                rows.append({k: record.fields[k].value for k in keys})
            json.dump(rows, fh, indent=2)
            fh.write("\n")

        atomic_write(self.path, _write)
        self._remember_fingerprint()
