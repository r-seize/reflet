"""SQLite and nested-JSON sources.

Run it directly:

    python examples/sources_example.py
"""

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

import reflet as rf

CONFIG_JSON = str(Path(__file__).parent / "config.json")


def _demo_sqlite(tmp: Path) -> None:
    db_path = tmp / "clients.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE clients (id INTEGER, name TEXT, country TEXT)")
    conn.execute("INSERT INTO clients VALUES (1, 'Martin', 'FR')")
    conn.execute("INSERT INTO clients VALUES (2, 'Smith', 'UK')")
    conn.commit()
    conn.close()

    print("-- SQLite source: table=..., via the stdlib sqlite3 module --")
    view = rf.Source(str(db_path), table="clients", key="id").run()
    for row in view:
        print(f"  {row.name} ({row.country})")

    view[0].name = "Dupont"
    view.sync()

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT * FROM clients ORDER BY id").fetchall()
    conn.close()
    print(f"  after edit + sync: {rows}")


def _demo_nested_json(tmp: Path) -> None:
    scratch_config = tmp / "config.json"
    shutil.copy(CONFIG_JSON, scratch_config)

    print()
    print("-- Nested JSON source: rows_at='servers' --")
    view = rf.Source(str(scratch_config), rows_at="servers", key="id").run()
    for row in view:
        print(f"  {row.host}:{row.port}")

    view[0].port = 8080
    view.sync()

    doc = json.loads(scratch_config.read_text())
    print(f"  everything else in the document is preserved: {doc['meta']}")
    print(f"  only the matching row changed: {doc['servers'][0]}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _demo_sqlite(tmp_path)
        _demo_nested_json(tmp_path)


if __name__ == "__main__":
    main()
