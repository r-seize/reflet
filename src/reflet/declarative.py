"""Build a Pipeline from a JSON spec, without writing Python.

Only the lenses expressible without an arbitrary callable are supported:
`rename`, `select`, `sort`, `constant`, `aggregate` (with a named agg
function), `filter` (a single field/comparison/value), and `map` (a named
numeric transform: scale or offset). `compute`/`validate`, and a `map` with
custom logic, need real Python — build those with `reflet.Source(...)`
directly and treat the declarative spec as a starting point, not the whole
pipeline.

There's no reverse (Pipeline -> spec): a Pipeline built the normal way holds
arbitrary Python closures for filter/map/compute, which have no general
serialization. This module only builds pipelines from specs, not the other
way around.

Spec shape:

    {
      "source": {"path": "clients.csv", "key": "id"},
      "steps": [
        {"op": "filter", "field": "country", "cmp": "==", "value": "FR"},
        {"op": "rename", "mapping": {"customer": "name"}},
        {"op": "map", "field": "price", "transform": "scale", "factor": 1.2},
        {"op": "sort", "field": "customer"}
      ]
    }
"""

from __future__ import annotations

import json
import operator
from collections.abc import Callable
from typing import Any

from reflet.lens import ConflictPolicy
from reflet.lenses import RowView
from reflet.pipeline import Pipeline, Source

_CMP_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
}

_AGG_FNS: dict[str, Callable[[list[Any]], Any]] = {
    "sum": sum,
    "min": min,
    "max": max,
    "count": len,
    "avg": lambda xs: sum(xs) / len(xs),
}


def _compile_predicate(step: dict[str, Any]) -> Callable[[RowView], bool]:
    field = step["field"]
    try:
        cmp = _CMP_OPS[step["cmp"]]
    except KeyError as exc:
        raise ValueError(f"declarative filter: unknown cmp {step['cmp']!r}") from exc
    value = step["value"]

    def predicate(row: RowView) -> bool:
        return cmp(getattr(row, field), value)

    return predicate


def _compile_map(step: dict[str, Any]) -> tuple[Callable[[Any], Any], Callable[[Any], Any]]:
    transform = step["transform"]
    if transform == "scale":
        factor = step["factor"]
        return (lambda x, factor=factor: x * factor, lambda x, factor=factor: x / factor)
    if transform == "offset":
        amount = step["amount"]
        return (lambda x, amount=amount: x + amount, lambda x, amount=amount: x - amount)
    raise ValueError(f"declarative map: unknown transform {transform!r}")


def pipeline_from_dict(spec: dict[str, Any]) -> Pipeline:
    """Build a `Pipeline` from an already-parsed declarative spec dict."""
    src = spec["source"]
    pipeline = Source(
        src["path"],
        key                = src.get("key"),
        tombstone_field    = src.get("tombstone_field"),
        table              = src.get("table"),
        rows_at            = src.get("rows_at"),
    )

    for step in spec.get("steps", []):
        op = step["op"]
        if op == "filter":
            pipeline = pipeline.filter(_compile_predicate(step), defaults=step.get("defaults"))
        elif op == "rename":
            pipeline = pipeline.rename(**step["mapping"])
        elif op == "select":
            pipeline = pipeline.select(*step["fields"])
        elif op == "sort":
            pipeline = pipeline.sort(step["field"], reverse=step.get("reverse", False))
        elif op == "constant":
            pipeline = pipeline.constant(step["field"], step["value"])
        elif op == "map":
            fwd, bwd    = _compile_map(step)
            pipeline    = pipeline.map(step["field"], fwd=fwd, bwd=bwd)
        elif op == "aggregate":
            try:
                agg_fn = _AGG_FNS[step["agg_fn"]]
            except KeyError as exc:
                name = step["agg_fn"]
                raise ValueError(f"declarative aggregate: unknown agg_fn {name!r}") from exc
            pipeline = pipeline.aggregate(
                step["group_by"],
                step["agg_field"],
                agg_fn,
                source_field    = step.get("source_field"),
                policy          = ConflictPolicy(step.get("policy", "error")),
            )
        else:
            raise ValueError(f"unknown declarative step: {op!r}")

    return pipeline


def pipeline_from_json(path: str) -> Pipeline:
    """Build a `Pipeline` from a declarative spec file."""
    with open(path, encoding="utf-8") as fh:
        return pipeline_from_dict(json.load(fh))
