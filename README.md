# reflet

[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![Runtime dependencies: zero](https://img.shields.io/badge/runtime%20deps-zero-brightgreen.svg)](pyproject.toml)
[![Type checked: mypy --strict](https://img.shields.io/badge/types-mypy%20strict-blue.svg)](pyproject.toml)
[![Linted with ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](pyproject.toml)

A bidirectional data transformation engine.

Pipelines are built from **lenses** — each with a forward (`get`) and backward
(`put`) function. Editing the output view propagates the change back to the
source. Every value carries **provenance**: where it came from, and through
which steps.

```python
import reflet as rf

pipeline = (
    rf.Source("clients.csv")
    .filter(lambda r: r.country == "FR")
    .rename(customer="name")
    .map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
)
view = pipeline.run()
view[0].customer = "Dupont"       # view[0]: first row of the *view*, not row 0 of the source
view.sync()                  # writes back to clients.csv
view[0].customer.why()            # provenance chain
```

## Table of contents

- [Why](#why)
- [Install](#install)
- [Quickstart](#quickstart)
- [Concepts](#concepts)
  - [Lenses](#lenses)
  - [Pipeline and View](#pipeline-and-view)
  - [Provenance: `.why()`](#provenance-why)
- [Lens reference](#lens-reference)
  - [`rename`](#rename)
  - [`select`](#select)
  - [`filter`](#filter)
  - [`map`](#map)
  - [`constant`](#constant)
  - [`compute`](#compute)
  - [`aggregate`](#aggregate)
  - [`sort`](#sort)
  - [`cast`](#cast)
  - [`split` and `merge`](#split-and-merge)
  - [`join`](#join)
- [Conflict policies](#conflict-policies)
- [Row identity: `key=`](#row-identity-key)
- [Dry-run, diff, and incremental sync](#dry-run-diff-and-incremental-sync)
- [Conflict detection](#conflict-detection)
- [Undo, redo, and the journal](#undo-redo-and-the-journal)
- [Validation](#validation)
- [Explaining the view: `why_not()` and `impact()`](#explaining-the-view-why_not-and-impact)
- [Inserting and deleting rows](#inserting-and-deleting-rows)
- [Watch mode](#watch-mode)
- [Declarative pipelines](#declarative-pipelines)
- [Sources](#sources)
- [Errors](#errors)
- [CLI](#cli)
- [Development](#development)
- [Compatibility](#compatibility)
- [Scope](#scope)
- [License](#license)

## Why

Most data pipelines are one-way: source → transformation → result. Fix a
mistake in the result and you're on your own to figure out where, in the
source, that value actually came from — and re-applying the fix upstream
means re-deriving, by hand, the inverse of every transformation in between.

reflet makes transformations invertible. Each lens is defined with its
inverse, so editing a value in the output view propagates the edit back
through every step to the original row and field it came from. Every cell
also remembers its lineage, so you can always ask `.why()` a value looks the
way it does.

Operations that have no sensible inverse (`compute`, `aggregate`) produce
read-only fields instead of a silent, wrong guess: editing them raises
`ReadOnlyFieldError`. When an aggregated field maps back to several source
rows, you choose how to resolve it (`first`, `last`, or the default,
`error`).

## Install

```bash
pip install reflet
```

Zero runtime dependencies — only the standard library. Requires Python 3.10+.

## Quickstart

```python
import reflet as rf

pipeline = (
    rf.Source("clients.csv")
    .filter(lambda r: r.country == "FR")
    .rename(customer="name")
    .map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
)

view = pipeline.run()
for row in view:
    print(row.customer, row.price)

view[0].customer = "Dupont"   # index is into the *view* (post-filter), not the source file
view.sync()              # edit the view, then write the change back to clients.csv

print(view[0].customer.why()) # clients.csv:name -> rename name->customer -> edit
```

A runnable, slightly more detailed version of this lives in
[`examples/example_pipeline.py`](examples/example_pipeline.py). Every other
feature below has its own runnable example too:

| Example | Covers |
| --- | --- |
| [`example_pipeline.py`](examples/example_pipeline.py) | `filter`/`rename`/`map`, edit + `sync()`, `.why()` |
| [`provenance_and_validation.py`](examples/provenance_and_validation.py) | `.why()`, `.validate()`, `why_not()`, `impact()` |
| [`insert_delete.py`](examples/insert_delete.py) | `insert()`, all three `on_delete` policies |
| [`join_example.py`](examples/join_example.py) | `join()`, read-only right-hand fields |
| [`sources_example.py`](examples/sources_example.py) | SQLite (`table=`) and nested-JSON (`rows_at=`) sources |
| [`watch_example.py`](examples/watch_example.py) | `view.watch()` (blocking, polling), `on_change` |
| [`declarative_pipeline.py`](examples/declarative_pipeline.py) + [`.json`](examples/declarative_pipeline.json) | building a pipeline from a JSON spec, and running it via the CLI |

Each is self-contained and safe to run as-is: `python examples/<name>.py`
(the declarative one from the repo root, since its spec's path is relative).

## Concepts

### Lenses

A `Lens` is the atomic unit of a pipeline: a pair of functions, `get` (source
→ view) and `put` (edited view + original source → updated source). Lenses
compose with `>>`, and a `Pipeline` is just a chain of them in front of a
`Source`. Composition follows the standard bidirectional-lens law:

```
(l1 >> l2).get(s)    == l2.get(l1.get(s))
(l1 >> l2).put(a, s) == l1.put(l2.put(a, l1.get(s)), s)
```

Every lens in reflet is tested against the two **round-trip laws** that make
this kind of transformation trustworthy:

```
get(put(a, s)) == a      # an edit survives a round trip through the source
put(get(s), s) == s      # reading without editing changes nothing
```

### Pipeline and View

`rf.Source(path)` returns a `Pipeline`. Each method (`.filter`, `.rename`,
`.map`, ...) appends a lens and returns a new `Pipeline` — the chain is built
up functionally, nothing runs yet. `.run()` reads the source once and applies
every lens, producing a `View`: a list-like, editable result.

```python
view = pipeline.run()
len(view)             # number of rows in the view
view[2]                # a Row
for row in view: ...   # iterate all rows
```

### Provenance: `.why()`

Every field you read off a `Row` is a `FieldProxy`: it behaves like the
underlying value (compares equal, prints, formats), but also carries its
lineage. Call `.why()` to render it:

```python
view[0].customer.why()
# -> "clients.csv:name -> rename name->customer"
```

Editing a field appends an `"edit"` step to its lineage, so after
`view[0].customer = "Dupont"` the chain reads
`"clients.csv:name -> rename name->customer -> edit"`.

## Lens reference

### `rename`

Renames fields. Keyword is the new name, value is the source field name.
Fully invertible — a no-op on every other field.

```python
.rename(customer="name")   # source field "name" is exposed as "customer"
```

### `select`

Projects down to a subset of fields. Dropped fields pass straight through
on write-back, untouched.

```python
.select("name", "price")
```

### `filter`

Keeps only rows matching a predicate. Rows that don't match are left
completely untouched on write-back — reflet never deletes a source row.

```python
.filter(lambda r: r.country == "FR")
```

### `map`

Transforms a single field with an explicit forward/backward pair. You own
the inverse, so make sure `bwd(fwd(x)) == x` (that's exactly what the law
tests in `tests/test_lens_laws.py` check for the built-in lenses, and what
you should check for your own `fwd`/`bwd`).

```python
.map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
```

This particular pair isn't bit-exact — `x / 1.2 * 1.2` can differ from `x`
in the last float digit, like any floating-point division that isn't a
power of two. Harmless for display/editing, but if you need an exact
round trip, pick a `fwd`/`bwd` where that holds (integer arithmetic,
`Decimal`, or a scale factor that's a power of two).

### `constant`

Adds a fixed value as a new, **read-only** field. There's no source cell to
write back to, so editing it raises `ReadOnlyFieldError`.

```python
.constant("currency", "EUR")
```

### `compute`

Adds a field derived from the rest of the row via an arbitrary function.
Also **read-only** — same reasoning as `constant`: a derived value has no
unique inverse.

```python
.compute("total", lambda r: r.price * r.qty)
```

### `aggregate`

Groups rows by a key, producing one output row per group with a read-only
aggregate field. The group key itself stays **writable**, but an edit to it
maps back to every source row in that group — see
[Conflict policies](#conflict-policies).

```python
.aggregate(
    group_by        = "country",
    agg_field       = "total_price",
    agg_fn          = sum,
    source_field    = "price",
    policy          = rf.ConflictPolicy.FIRST,
)
```

### `sort`

Orders the view by a field. Purely a view-level concern: write-back ignores
the view's order entirely and merges each row back by its identity, so the
source file's row order is untouched.

```python
.sort("price", reverse=True)
```

### `cast`

Sugar for `.map()` when the transform is just a type conversion. `back` is
required rather than guessed — reflet won't silently assume how to undo a
cast.

```python
.cast("price", to=float, back=str)
```

### `split` and `merge`

Duals of each other: `split` turns one source field into several view
fields (e.g. a full name into first/last); `merge` turns several source
fields into one view field.

```python
.split(
    "full_name",
    into    = ("first", "last"),
    fwd     = lambda v: tuple(v.split(" ", 1)),
    bwd     = lambda parts: " ".join(parts),
)

.merge(
    fields    = ("first", "last"),
    into      = "full_name",
    fwd       = lambda parts: " ".join(parts),
    bwd       = lambda v: tuple(v.split(" ", 1)),
)
```

### `join`

Inner-joins against another `Pipeline`'s rows by key. Rows with no match on
the right are dropped, like `filter`.

```python
orders = rf.Source("orders.csv", key="order_id")
view = (
    rf.Source("clients.csv", key="id")
    .join(orders, on="id", other_on="client_id", prefix="order_")
    .run()
)
```

**Right-hand fields are read-only** — editing one raises `ReadOnlyFieldError`.
A genuine two-way join (editing a joined-in field writes back to the *other*
file) would need a `View` that spans two backends at once, which reflet's
single-source `View` doesn't support yet; this is the one place the library
falls short of the "everything is bidirectional" goal, and it's called out
here rather than faked. Left-hand fields stay fully writable. `other` is
re-read on every `get()`, so edits made to its file are picked up on the next
`run()`/`sync()`.

## Conflict policies

When an edited field maps back to more than one source row (currently: the
`group_by` key of `aggregate`), reflet refuses to guess silently. You choose
a `rf.ConflictPolicy`:

| Policy | Behavior |
| --- | --- |
| `ConflictPolicy.ERROR` (default) | editing the field raises `ConflictError` immediately |
| `ConflictPolicy.FIRST` | the edit is written to the first source row in the group |
| `ConflictPolicy.LAST` | the edit is written to the last source row in the group |

A no-op write (setting the field to the value it already has) never raises,
regardless of policy.

## Row identity: `key=`

By default, a row's identity is its position in the source file. That's
fragile the moment anything else touches the file between `run()` and
`sync()` — a reorder or an insert shifts positions and your edit lands on
the wrong row. Pass `key=` to pin identity to a field instead:

```python
view = rf.Source("clients.csv", key="id").run()
```

Write-back then looks up each row by its key value, not its position, so it
keeps targeting the right row regardless of where it sits in the in-memory
table. The key field must be present and unique on every row — reflet
raises `ValueError` at read time otherwise. It also makes `Change` and
`JournalEntry` read naturally: `rid` is the key value (e.g. `1`) instead of
an opaque position.

## Dry-run, diff, and incremental sync

Editing a `Row` mutates the view in place — nothing is written yet.
`view.diff()` previews exactly what a sync would write, without touching
anything:

```python
view[0].name = "Dupont"
view.diff()
# [Change(clients.csv[1].name: 'Durand' -> 'Dupont')]
```

`view.sync(dry_run=True)` does the same thing (it's `diff()` under the
hood) if you'd rather branch on the one call. A real `view.sync()` applies
the changes, writes the source, and returns that same list of `Change`.

Only rows actually touched by an edit are replayed through the lens
chain's `put`; untouched rows are copied through as-is, not reprocessed.
Calling `sync()` with no pending edits is a no-op — the source file isn't
even reopened.

## Conflict detection

reflet fingerprints the source file at read time (a content hash). If the
file changed on disk by the time you call `sync()` — another process wrote
to it, a script ran in parallel — `sync()` raises `SourceConflictError`
instead of silently overwriting those changes:

```python
view.sync()                 # SourceConflictError if clients.csv changed underneath
view.sync(force=True)       # overwrite anyway
```

`force=True` overwrites unconditionally; reflet doesn't attempt to merge
the external change with your edits (recognize that as a known limitation
for now, not a silent guess).

Writes themselves are atomic: reflet writes to a temp file in the same
directory and `os.replace()`s it into place, so a crash or a concurrent
reader never sees a half-written source file.

## Undo, redo, and the journal

```python
view.undo()   # revert the most recent edit, or the most recent sync()
view.redo()   # reapply what undo() just reverted
view.journal  # tuple[JournalEntry, ...]: every field write actually committed
```

`undo()`/`redo()` work one step at a time and interleave edits and syncs:
undoing right after a `sync()` reverts the file to its pre-sync state (and
writes that reversion back out); undoing an uncommitted edit just restores
the in-memory value. Both return `False` if there's nothing to do.
`view.journal` only records writes that were actually committed by
`sync()` — previews via `diff()`/`dry_run=True` never appear in it.
`undo()`/`redo()` don't (yet) cover `insert()`/`delete()`.

## Validation

```python
.validate("price", lambda x: x > 0, "price must be positive")
```

Checked at **edit time** (`row.price = -5`), not at `sync()` — a failing
edit raises `ValidationError` immediately, before it ever becomes a pending
change, with the field's provenance appended to the message so you can see
where the value came from. A field can have more than one `.validate()`
call; all of them must pass.

## Explaining the view: `why_not()` and `impact()`

```python
view.why_not(5)
# -> "excluded by filter(...)"     (row id=5 didn't match a filter())
# -> "no source row with id 5"     (id=5 doesn't exist at all)
# -> "row 5 is present in the view (it wasn't filtered out)"

view.impact(5, "price")
# -> [(5, "total"), (5, "price")]  # view fields derived from source[5]["price"]
```

`why_not(rid)` replays the source row with that id through each lens in
order and reports the first one that drops it — handy when a row you
expected in the view just isn't there. `impact(rid, field)` is the reverse
question: which view fields (row, field name) trace their provenance back
to that source cell — useful before editing a field whose value a
`compute()` elsewhere depends on.

## Inserting and deleting rows

```python
view.insert(customer="Lefevre", price=99)   # add a new row, in view-level field names
view.delete(0)                          # remove the row at this index
view.delete(0, on_delete="tombstone")   # mark it instead of removing it
view.delete(0, on_delete="ignore")      # drop it from the view only
```

`insert()` takes the row's fields exactly as you'd write them through
`Row` — reflet works backward through `rename`/`map` to recover the
source-level values, fills in anything `filter(..., defaults=...)`
requires, and rejects `constant`/`compute` fields (they have no inverse).
It isn't supported through `select()` (hidden fields would have no value)
or `aggregate()` (a group has no single source row to invent) — both raise
`UnsupportedOperationError`. Every source column needs a value one way or
another; a missing or unrecognized one raises `InsertError`.

`delete()` removes the row from the view immediately; what happens to the
source on the next `sync()` depends on `on_delete`:

| Policy | Behavior |
| --- | --- |
| `"delete"` (default) | the source row(s) are removed entirely |
| `"tombstone"` | `tombstone_field` (from `Source(..., tombstone_field=...)`) is set instead; it must already be a source column |
| `"ignore"` | the view drops it, but the source is left untouched |

Deleting an `aggregate()` group row applies the policy to every source row
in that group.

## Watch mode

**`view.watch()` blocks the calling thread and polls** — it is not an
OS-level file-watch (zero dependencies, and no stdlib API for that which is
cross-platform). Run it in a thread/process of its own, or pass
`max_iterations=` to bound it; otherwise it only returns when interrupted.

```python
view.watch(interval=1.0, on_change=lambda: print("source changed externally"))
```

Each tick, pending edits are flushed via `sync()`; if that hits a conflict
(or the source changed with nothing pending), `on_change()` is called
instead of silently overwriting or ignoring it — by default a no-op, so
pass one to actually reload.

## Declarative pipelines

Most of a pipeline can be described as data instead of Python — enough to
share, version, and run from the CLI without writing code:

```json
{
  "source": {"path": "clients.csv", "key": "id"},
  "steps": [
    {"op": "filter", "field": "country", "cmp": "==", "value": "FR"},
    {"op": "rename", "mapping": {"customer": "name"}},
    {"op": "map", "field": "price", "transform": "scale", "factor": 1.2},
    {"op": "sort", "field": "customer"}
  ]
}
```

```python
from reflet.declarative import pipeline_from_json
view = pipeline_from_json("pipeline.json").run()
```

```bash
python -m reflet show pipeline.json    # the CLI also accepts a spec directly
```

Supported steps: `filter` (one field/`cmp`/`value` — `==`, `!=`, `<`, `<=`,
`>`, `>=`, `in`, `not in`), `rename`, `select`, `sort`, `constant`,
`aggregate` (`agg_fn` is a name: `sum`/`min`/`max`/`count`/`avg`), and `map`
(`transform`: `scale`/`offset`). `compute`, `validate`, and any custom
`map`/`filter` logic need real Python — build those with `reflet.Source(...)`
directly; there's deliberately no `eval()` of arbitrary expressions here.
There's also no reverse direction: a normally-built `Pipeline` holds Python
closures for its callables, which have no general way back to a spec.

## Sources

| Format | Extension / option | Notes |
| --- | --- | --- |
| CSV | `.csv` | Values are best-effort type-inferred (`int`/`float`/`bool`/`str`) on read |
| JSON | `.json` | A flat JSON array of objects |
| Nested JSON | `.json`, `rows_at="servers"` | A list nested inside a larger document; everything else in the document is preserved byte-for-byte on write-back |
| SQLite | `.sqlite`/`.sqlite3`/`.db`, `table="clients"` | Via the stdlib `sqlite3` module; write-back replaces the table's rows in one transaction |

All support read and write-back, atomic writes (SQLite via its own
transactions), and an optional `key=`. `rf.Source(path, key=None, table=None,
rows_at=None, tombstone_field=None)` picks the backend from the file
extension and these options. Not supported (zero-dependency constraint):
YAML (no parser in the standard library) and TOML write-back (`tomllib` is
read-only).

## Errors

| Exception | Raised when |
| --- | --- |
| `ReadOnlyFieldError` | writing to a field with no inverse (`constant`/`compute`/`aggregate`'s derived field/a `join()`-ed right-hand field) |
| `ConflictError` | writing to a field shared by several source rows under `ConflictPolicy.ERROR` |
| `UnknownFieldError` | reading or writing a field that doesn't exist on the row |
| `SourceConflictError` | the source file changed on disk since it was read, and `sync()` wasn't called with `force=True` |
| `ValidationError` | an edit fails a `.validate()` constraint |
| `InsertError` | `insert()` is missing a required field, got an unrecognized one, reused an id, or produced a row the pipeline's filter(s) reject |
| `UnsupportedOperationError` | `insert()` through a `select()` or `aggregate()` |

All inherit from `reflet.RefletError`.

## CLI

```bash
python -m reflet show examples/example_pipeline.py
python -m reflet why examples/example_pipeline.py 0 customer
```

Both expect the script to define a module-level `pipeline = rf.Source(...)...`.
`show` prints the resulting view as a table; `why` prints one field's
provenance chain.

## Development

Zero *runtime* dependencies, but contributing needs the dev extras —
`pytest`, `ruff`, and `mypy`:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/pytest           # tests, including property-style round-trip law tests
.venv/bin/ruff check .     # lint
.venv/bin/mypy src         # strict type checking
```

## Compatibility

Zero runtime dependencies, stdlib only. Tested on Python 3.10, 3.11, 3.12,
and 3.13 — matching Debian Bookworm (3.11) and Trixie (3.13), among others.

## Scope

In scope today: the core lens/pipeline/view engine; `rename`/`select`/
`filter`/`map`/`cast`/`split`/`merge`/`constant`/`compute`/`aggregate`/
`sort`/`join`; CSV, JSON (flat or nested via `rows_at=`), and SQLite
sources, all with atomic writes and an optional stable `key=`; per-cell
provenance; conflict policies; incremental sync with dry-run/diff;
source-conflict detection; undo/redo with an edit journal; field-level
`.validate()`; `why_not()`/`impact()` for tracing the view;
`insert()`/`delete()` with `on_delete` policies; a polling `watch()` mode; a
declarative JSON pipeline format for the lenses that don't need arbitrary
Python; and a CLI that runs either kind of pipeline.

Out of scope, with why:

- **Merging external changes**: conflict detection refuses or
  force-overwrites; it doesn't attempt to merge your edits with someone
  else's.
- **Two-way `join()`**: right-hand fields are read-only — writing to the
  joined-in table would need a `View` spanning two backends, which the
  current single-source `View` doesn't support.
- **`pivot`/`unpivot`**: not yet implemented; `split`/`merge` cover the
  common column-reshape cases, reshaping between row-shaped and
  column-shaped data doesn't fit the current row-identity model without
  more design.
- **YAML sources**: no parser in the standard library, and zero
  dependencies is a hard constraint.
- **TOML write-back**: the stdlib's `tomllib` is read-only; a source would
  need its own hand-rolled writer to round-trip, which doesn't exist yet.
- **A declarative `compute`/`validate`/custom `map`/`filter`**: would need
  either arbitrary code execution (`eval()`, a security liability) or a
  constrained expression language (not built); write these with
  `reflet.Source(...)` directly.
- **A TUI/HTML UI and a constraint solver**: not attempted.

## License

BSD-3-Clause — see [LICENSE](LICENSE). See [CHANGELOG.md](CHANGELOG.md) for
release history.
