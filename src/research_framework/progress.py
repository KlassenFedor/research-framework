from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """A machine-readable update emitted by a potentially long operation."""

    phase: str
    current: int
    total: int | None
    message: str

    @property
    def completed(self) -> bool:
        return self.total is not None and self.current >= self.total


ProgressCallback = Callable[[ProgressEvent], None]


def notify_progress(
    callback: ProgressCallback | None,
    *,
    phase: str,
    current: int,
    total: int | None,
    message: str,
) -> None:
    if callback is None:
        return
    callback(
        ProgressEvent(
            phase=phase,
            current=current,
            total=total,
            message=message,
        )
    )
