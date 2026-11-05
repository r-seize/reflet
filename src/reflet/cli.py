"""Command-line interface: `python -m reflet show|why|fields ...`."""

from __future__ import annotations

import argparse
import json
import runpy
import sys

from reflet import __version__
from reflet._render import render_table
from reflet.declarative import pipeline_from_json
from reflet.pipeline import Pipeline
from reflet.view import View


def _load_pipeline(script: str) -> Pipeline:
    if script.endswith(".json"):
        return pipeline_from_json(script)
    namespace    = runpy.run_path(script)
    pipeline     = namespace.get("pipeline")
    if pipeline is None or not isinstance(pipeline, Pipeline):
        raise SystemExit(f"{script}: no module-level `pipeline = rf.Source(...)...` found")
    return pipeline


def _run(script: str) -> View:
    return _load_pipeline(script).run()


def cmd_show(args: argparse.Namespace) -> None:
    rows = _run(args.script).to_dicts()
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        print(render_table(rows))


def cmd_why(args: argparse.Namespace) -> None:
    view     = _run(args.script)
    row      = view[args.row]
    field    = getattr(row, args.field)
    print(field.why())


def cmd_fields(args: argparse.Namespace) -> None:
    rows = _run(args.script).to_dicts()
    if not rows:
        print("(empty view)")
        return
    for name in rows[0]:
        print(name)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m reflet")
    parser.add_argument(
        "--version", action="version", version=f"reflet {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    script_help = "path to a .py file defining `pipeline`, or a declarative .json spec"

    show_parser = subparsers.add_parser("show", help="run a pipeline and print its view")
    show_parser.add_argument("script", help=script_help)
    show_parser.add_argument(
        "--json", action="store_true", help="print as JSON instead of a tab-separated table"
    )
    show_parser.set_defaults(func=cmd_show)

    why_parser = subparsers.add_parser("why", help="print a field's provenance")
    why_parser.add_argument("script", help=script_help)
    why_parser.add_argument("row", type=int, help="row index in the view")
    why_parser.add_argument("field", help="field name")
    why_parser.set_defaults(func=cmd_why)

    fields_parser = subparsers.add_parser("fields", help="list a view's available fields")
    fields_parser.add_argument("script", help=script_help)
    fields_parser.set_defaults(func=cmd_fields)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
