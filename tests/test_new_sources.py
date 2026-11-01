"""SqliteSource and JsonPathSource."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import reflet as rf


@pytest.fixture
def clients_db(tmp_path: Path) -> Path:
    path    = tmp_path / "clients.sqlite"
    conn    = sqlite3.connect(path)
    conn.execute("CREATE TABLE clients (id INTEGER, name TEXT, country TEXT)")
    conn.execute("INSERT INTO clients VALUES (1, 'Martin', 'FR')")
    conn.execute("INSERT INTO clients VALUES (2, 'Smith', 'UK')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def nested_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    doc = {
        "meta": {"version": 1},
        "servers": [
            {"id": 1, "host": "a", "port": 80},
            {"id": 2, "host": "b", "port": 443},
        ],
    }
    path.write_text(json.dumps(doc))
    return path


def test_sqlite_source_requires_table() -> None:
    with pytest.raises(ValueError, match="table="):
        rf.Source("db.sqlite")


def test_sqlite_source_read_and_write(clients_db: Path) -> None:
    view = rf.Source(str(clients_db), table="clients", key="id").run()
    assert len(view) == 2
    assert str(view[0].name) == "Martin"

    view[0].name = "Dupont"
    view.sync()

    conn    = sqlite3.connect(clients_db)
    rows    = conn.execute("SELECT id, name, country FROM clients ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, "Dupont", "FR"), (2, "Smith", "UK")]


def test_json_path_source_reads_nested_rows(nested_config: Path) -> None:
    view = rf.Source(str(nested_config), rows_at="servers", key="id").run()
    assert len(view) == 2
    assert str(view[0].host) == "a"
    assert view[0].port.value == 80


def test_json_path_source_write_preserves_rest_of_document(nested_config: Path) -> None:
    view            = rf.Source(str(nested_config), rows_at="servers", key="id").run()
    view[0].port    = 8080
    view.sync()

    doc = json.loads(nested_config.read_text())
    assert doc["meta"] == {"version": 1}  # untouched
    assert doc["servers"][0]["port"] == 8080
    assert doc["servers"][1]["port"] == 443


def test_json_path_source_rejects_non_list_path(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"meta": {"version": 1}}))
    with pytest.raises(ValueError, match="doesn't resolve to a list"):
        rf.Source(str(path), rows_at="meta").run()
