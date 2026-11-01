"""Command-line interface: `python -m reflet show|why ...`."""

from __future__ import annotations

import argparse
import runpy
import sys

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
    view = _run(args.script)
    if len(view) == 0:
        print("(empty view)")
        return
    fields = list(view._table[0].fields.keys())
    print("\t".join(fields))
    for row in view:
        print("\t".join(str(getattr(row, f)) for f in fields))


def cmd_why(args: argparse.Namespace) -> None:
    view     = _run(args.script)
    row      = view[args.row]
    field    = getattr(row, args.field)
    print(field.why())


def main(argv: list[str] | None = None) -> None:
    parser        = argparse.ArgumentParser(prog="python -m reflet")
    subparsers    = parser.add_subparsers(dest="command", required=True)

    script_help = "path to a .py file defining `pipeline`, or a declarative .json spec"

    show_parser = subparsers.add_parser("show", help="run a pipeline and print its view")
    show_parser.add_argument("script", help=script_help)
    show_parser.set_defaults(func=cmd_show)

    why_parser = subparsers.add_parser("why", help="print a field's provenance")
    why_parser.add_argument("script", help=script_help)
    why_parser.add_argument("row", type=int, help="row index in the view")
    why_parser.add_argument("field", help="field name")
    why_parser.set_defaults(func=cmd_why)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
