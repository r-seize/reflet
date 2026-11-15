# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-11-15

A reliability/consolidation release — no breaking changes.

### Fixed

- CSV sources now strip a leading BOM on read (`utf-8-sig`); previously a
  BOM leaked into the first fieldname, breaking `key=`/field lookups on
  files from Excel/Windows.
- `python -m reflet` now reports expected failures (missing script,
  unknown field, out-of-range row, ...) as a one-line `error: ...` message
  on stderr with exit status 1, instead of a raw Python traceback.
  Unexpected bugs still show their full traceback.
- `show --json` emits literal UTF-8 characters (`ensure_ascii=False`)
  instead of escaped `\uXXXX` sequences.
- Clarified `SourceConflictError`'s message to spell out the three ways
  to resolve it (`force=True`, reload, or do nothing for now).

### Added

- `Source(path, delimiter=",")` for CSV files that use a different field
  separator (e.g. `;` or tab).
- `View.head(n=5)`: prints the first `n` rows of the view as it currently
  stands (including unsynced edits) — the counterpart to
  `Pipeline.preview()`, which re-runs the pipeline fresh.
- `View.to_dicts(fields=None)`: an optional `fields` argument to select
  and order which columns are returned.
- `Pipeline.preview()`/CLI `show`/`View.head()` now escape embedded
  tabs/newlines and truncate cell values over 60 characters, so one row
  always stays on one line.
- Expanded test coverage: CSV BOM and custom delimiters, nested-JSON
  sources with an empty row list, SQLite `NULL`/boolean-like values,
  `dry_run=True` under an external conflict, and context-manager edge
  cases (early `return`, `undo()`/`redo()` inside the block, `sync()`
  raising on exit).
- README: a condensed "read -> edit -> diff -> sync" walkthrough, and a
  "Common mistakes" section next to the error reference.

## [0.1.1] - 2026-11-05

### Added

- `Pipeline`/`View.__repr__`: a readable summary (lens chain; row count and
  fields) instead of the default object repr.
- `Pipeline.preview(n=5)`: run the pipeline and print the first `n` rows as
  a table, without writing a loop.
- `View` is now a context manager: `with pipeline.run() as view: ...` calls
  `sync()` on a clean exit, and leaves edits unsynced if the block raises.
- `View.rows`: all rows as a tuple, instead of iterating.
- `View.to_dicts()`: the current view as plain `list[dict]`, for quick
  inspection or interop with other libraries.
- CLI: `python -m reflet --version`; `show --json` for scriptable output
  alongside the existing tab-separated table; new `fields` subcommand to
  list a view's available field names.
- `reflet._render`: small shared TSV-rendering helper behind `preview()`
  and the CLI's `show`, replacing duplicated formatting logic.

## [0.1.0] - 2026-11-01

Initial public release.

### Added

- Core bidirectional lens engine: `Lens.get`/`put`, composition via `>>`,
  `Pipeline`, `View`, `Row` with attribute access, and per-cell `Provenance`
  exposed through `.why()`.
- Lenses: `rename`, `select`, `filter` (with `defaults=` for `insert()`),
  `map`, `cast`, `split`, `merge`, `constant`, `compute`, `aggregate` (with
  `ConflictPolicy`), `sort`, and `join` (inner join against another
  pipeline; right-hand fields read-only).
- Sources: CSV, JSON (flat or nested via `rows_at=`), and SQLite
  (`table=`), each with read and atomic write-back, and an optional
  stable `key=` for row identity.
- `View.diff()` and `sync(dry_run=True)` to preview pending changes before
  writing.
- `SourceConflictError`: `sync()` detects if the source file changed on
  disk since it was read, and refuses unless `force=True`.
- `View.undo()`/`redo()` and `View.journal` for edit history and audit.
- `Pipeline.validate()`: field-level constraints checked at edit time,
  with the field's provenance in the error message.
- `View.why_not(rid)` and `View.impact(rid, field)` for tracing why a row
  is absent from a view, and what a source cell produced.
- `View.insert()`/`delete()` with `on_delete` policies (`delete`,
  `tombstone`, `ignore`).
- `View.watch()`: a polling loop that auto-syncs pending edits and flags
  external source changes via a callback.
- `reflet.declarative`: build a `Pipeline` from a JSON spec, for the
  lenses that don't need arbitrary Python.
- CLI: `python -m reflet show|why`, accepting either a `.py` script or a
  declarative `.json` spec.
- Zero runtime dependencies; typed, `mypy --strict` clean; tested on
  Python 3.10–3.13.

[Unreleased]: https://github.com/r-seize/reflet/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/r-seize/reflet/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/r-seize/reflet/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/r-seize/reflet/releases/tag/v0.1.0
