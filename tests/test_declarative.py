"""reflet.declarative: build a Pipeline from a JSON spec."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reflet.declarative import pipeline_from_dict, pipeline_from_json


def test_declarative_filter_rename_map(clients_csv: Path) -> None:
    pipeline = pipeline_from_dict(
        {
            "source": {"path": str(clients_csv), "key": "id"},
            "steps": [
                {"op": "filter", "field": "country", "cmp": "==", "value": "FR"},
                {"op": "rename", "mapping": {"customer": "name"}},
                {"op": "map", "field": "price", "transform": "scale", "factor": 1.2},
            ],
        }
    )
    view     = pipeline.run()
    names    = sorted(str(r.customer) for r in view)
    assert names == ["Dupont", "Durand", "Martin"]
    assert view[0].price.value == pytest.approx(12.0)


def test_declarative_sort_select_constant(clients_csv: Path) -> None:
    pipeline = pipeline_from_dict(
        {
            "source": {"path": str(clients_csv)},
            "steps": [
                {"op": "select", "fields": ["name", "price"]},
                {"op": "sort", "field": "name"},
                {"op": "constant", "field": "currency", "value": "EUR"},
            ],
        }
    )
    view     = pipeline.run()
    names    = [str(r.name) for r in view]
    assert names == sorted(names)
    assert str(view[0].currency) == "EUR"


def test_declarative_aggregate(clients_csv: Path) -> None:
    pipeline = pipeline_from_dict(
        {
            "source": {"path": str(clients_csv)},
            "steps": [
                {
                    "op": "aggregate",
                    "group_by": "country",
                    "agg_field": "total",
                    "agg_fn": "sum",
                    "source_field": "price",
                }
            ],
        }
    )
    view      = pipeline.run()
    totals    = {str(r.country): r.total.value for r in view}
    assert totals["FR"] == 80


def test_declarative_unknown_op_raises(clients_csv: Path) -> None:
    with pytest.raises(ValueError, match="unknown declarative step"):
        pipeline_from_dict(
            {"source": {"path": str(clients_csv)}, "steps": [{"op": "bogus"}]}
        )


def test_declarative_unknown_cmp_raises(clients_csv: Path) -> None:
    with pytest.raises(ValueError, match="unknown cmp"):
        pipeline_from_dict(
            {
                "source": {"path": str(clients_csv)},
                "steps": [{"op": "filter", "field": "country", "cmp": "~=", "value": "FR"}],
            }
        )


def test_pipeline_from_json_file(clients_csv: Path, tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "source": {"path": str(clients_csv)},
                "steps": [{"op": "filter", "field": "country", "cmp": "==", "value": "UK"}],
            }
        )
    )
    view = pipeline_from_json(str(spec_path)).run()
    assert len(view) == 1
    assert str(view[0].name) == "Smith"


def test_cli_show_accepts_declarative_json(clients_csv: Path, tmp_path: Path) -> None:
    import subprocess
    import sys

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "source": {"path": str(clients_csv)},
                "steps": [{"op": "filter", "field": "country", "cmp": "==", "value": "UK"}],
            }
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "reflet", "show", str(spec_path)],
        capture_output    = True,
        text              = True,
        check             = True,
    )
    assert "Smith" in result.stdout
