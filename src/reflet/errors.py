"""Exceptions raised by reflet."""

from __future__ import annotations


class RefletError(Exception):
    """Base class for all reflet errors."""


class ReadOnlyFieldError(RefletError):
    """Raised when attempting to write to a field produced by a non-invertible lens."""

    def __init__(self, field: str) -> None:
        super().__init__(
            f"field {field!r} is read-only: it was produced by a non-invertible "
            "operation (e.g. compute/constant/aggregate/join) and has no inverse "
            "to propagate through"
        )
        self.field = field


class ConflictError(RefletError):
    """Raised when an output row maps back to several source rows under the 'error' policy."""

    def __init__(self, count: int) -> None:
        super().__init__(
            f"ambiguous write-back: output row maps to {count} source rows; "
            "pass a conflict policy ('first', 'last') to resolve this explicitly"
        )
        self.count = count


class UnknownFieldError(RefletError):
    """Raised when referencing a field that does not exist on a row."""

    def __init__(self, field: str) -> None:
        super().__init__(f"no such field: {field!r}")
        self.field = field


class SourceConflictError(RefletError):
    """Raised when the source file changed on disk since it was read."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path!r} changed on disk since it was read; pass force=True to "
            "sync() to overwrite it anyway, or re-run the pipeline to pick up "
            "the external changes first"
        )
        self.path = path


class ValidationError(RefletError):
    """Raised when an edit fails a `.validate()` constraint, before it touches the source."""

    def __init__(
        self, field: str, value: object, message: str | None = None, why: str | None = None
    ) -> None:
        text = message or f"{field}={value!r} failed validation"
        if why:
            text = f"{text} ({why})"
        super().__init__(text)
        self.field    = field
        self.value    = value


class InsertError(RefletError):
    """Raised when `View.insert()` can't be resolved back to a valid source row."""


class UnsupportedOperationError(RefletError):
    """Raised when an operation isn't supported for the current lens chain."""
