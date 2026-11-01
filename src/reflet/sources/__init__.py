"""Source backends: read a table from storage, and write edits back."""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import IO, Any

from reflet.lens import RowId, Table


class SourceBackend(ABC):
    """Reads/writes a table to a concrete storage format.

    `key`, when given, is the source field whose value uniquely identifies a
    row (its `RowId`); rows keep that identity across reads, so write-back
    survives reordering or insertion done outside reflet. With no key, a
    row's identity is its position in the file.
    """

    def __init__(self, path: str, key: str | None = None) -> None:
        self.path                        = path
        self.key                         = key
        self.fieldnames: list[str]       = []
        self._order: list[RowId]         = []
        self._fingerprint: str | None    = None

    @abstractmethod
    def read(self) -> Table: ...

    @abstractmethod
    def write(self, table: Table) -> None: ...

    def changed_since_read(self) -> bool:
        """Whether the file on disk differs from what was last read/written."""
        if self._fingerprint is None:
            return False
        return self._file_hash() != self._fingerprint

    def _file_hash(self) -> str:
        with open(self.path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def _remember_fingerprint(self) -> None:
        self._fingerprint = self._file_hash()


def atomic_write(path: str, write_fn: Callable[[IO[str]], None]) -> None:
    """Write via a temp file + os.replace so readers never see a partial file."""
    directory       = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path    = tempfile.mkstemp(dir=directory, prefix=".reflet-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            write_fn(fh)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


def infer_scalar(raw: str) -> Any:
    """Best-effort conversion of a CSV string cell to int/float/bool/str."""
    if raw == "":
        return raw
    if raw in ("True", "False"):
        return raw == "True"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def render_scalar(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float | int):
        return str(value)
    return "" if value is None else str(value)
