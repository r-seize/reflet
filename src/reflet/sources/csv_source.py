"""CSV source backend."""

from __future__ import annotations

import csv
from typing import IO

from reflet.lens import Cell, Record, RowId, Table
from reflet.provenance import Provenance
from reflet.sources import SourceBackend, atomic_write, infer_scalar, render_scalar


class CsvSource(SourceBackend):
    def read(self) -> Table:
        with open(self.path, newline="", encoding="utf-8") as fh:
            reader                = csv.DictReader(fh)
            self.fieldnames       = list(reader.fieldnames or [])
            table: Table          = []
            seen: set[RowId]      = set()
            order: list[RowId]    = []
            for i, raw_row in enumerate(reader):
                fields = {
                    k: Cell(infer_scalar(v), Provenance(self.path, k)) for k, v in raw_row.items()
                }
                rid: RowId = i
                if self.key is not None:
                    if self.key not in fields:
                        raise ValueError(
                            f"{self.path}: key field {self.key!r} missing on row {i}"
                        )
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
        fieldnames    = self.fieldnames or (list(table[0].fields.keys()) if table else [])
        by_rid        = {r.rid: r for r in table}

        def _write(fh: IO[str]) -> None:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for rid in self._order:
                record = by_rid.get(rid)
                if record is None:
                    continue
                writer.writerow({k: render_scalar(record.fields[k].value) for k in fieldnames})

        atomic_write(self.path, _write)
        self._remember_fingerprint()
