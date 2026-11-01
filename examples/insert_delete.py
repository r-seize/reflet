"""Inserting and deleting rows, with each on_delete policy.

Run it directly:

    python examples/insert_delete.py
"""

import csv
import tempfile
from pathlib import Path

import reflet as rf


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scratch_csv = Path(tmp) / "clients.csv"
        rows = [
            {"id": 1, "name": "Martin", "country": "FR", "price": 10, "deleted": ""},
            {"id": 2, "name": "Smith", "country": "UK", "price": 20, "deleted": ""},
            {"id": 3, "name": "Durand", "country": "FR", "price": 30, "deleted": ""},
        ]
        with scratch_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["id", "name", "country", "price", "deleted"])
            writer.writeheader()
            writer.writerows(rows)
        _run_demo(str(scratch_csv))


def _run_demo(scratch_csv: str) -> None:
    view = rf.Source(scratch_csv, key="id", tombstone_field="deleted").run()

    print("-- insert(): add a new row, in view-level field names --")
    row = view.insert(id=4, name="Lefevre", country="BE", price=5, deleted="")
    print(f"  inserted: {row}")
    print(f"  diff before sync: {view.diff()}")
    view.sync()
    print(f"  {scratch_csv} now has {len(view)} rows")

    print()
    print("-- delete(..., on_delete='delete'): removes the source row entirely --")
    idx = next(i for i, r in enumerate(view) if str(r.name) == "Lefevre")
    view.delete(idx)
    view.sync()
    print(f"  back to {len(view)} rows")

    print()
    print("-- delete(..., on_delete='tombstone'): marks instead of removing --")
    idx = next(i for i, r in enumerate(view) if str(r.name) == "Martin")
    view.delete(idx, on_delete="tombstone")
    view.sync()
    print("  " + Path(scratch_csv).read_text().replace("\n", "\n  "))

    print("-- delete(..., on_delete='ignore'): view-only, source untouched --")
    view2 = rf.Source(scratch_csv, key="id").run()
    before = Path(scratch_csv).read_text()
    view2.delete(0, on_delete="ignore")
    view2.sync()
    assert Path(scratch_csv).read_text() == before
    print("  source file unchanged, confirmed")


if __name__ == "__main__":
    main()
