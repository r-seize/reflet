from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


@pytest.fixture
def clients_csv(tmp_path: Path) -> Path:
    path = tmp_path / "clients.csv"
    rows = [
        {"id": "1", "name": "Martin", "country": "FR", "price": "10"},
        {"id": "2", "name": "Smith", "country": "UK", "price": "20"},
        {"id": "3", "name": "Durand", "country": "FR", "price": "30"},
        {"id": "4", "name": "Dupont", "country": "FR", "price": "40"},
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "name", "country", "price"])
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def clients_json(tmp_path: Path) -> Path:
    path = tmp_path / "clients.json"
    rows = [
        {"id": 1, "name": "Martin", "country": "FR", "price": 10},
        {"id": 2, "name": "Smith", "country": "UK", "price": 20},
        {"id": 3, "name": "Durand", "country": "FR", "price": 30},
    ]
    path.write_text(json.dumps(rows))
    return path
