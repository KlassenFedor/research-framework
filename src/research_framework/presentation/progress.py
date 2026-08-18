from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

from research_framework.progress import ProgressCallback, ProgressEvent


class TerminalProgressBar:
    """Small dependency-free progress renderer for interactive CLI use."""

    def __init__(
        self,
        stream: TextIO,
        *,
        enabled: bool,
        width: int = 24,
        min_interval: float = 0.08,
    ) -> None:
        self._stream = stream
        self._enabled = enabled
        self._width = width
        self._min_interval = min_interval
        self._last_phase: str | None = None
        self._last_rendered_at = 0.0
        self._line_length = 0
        self._open_line = False

    def __call__(self, event: ProgressEvent) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        phase_changed = self._last_phase not in {None, event.phase}
        if phase_changed:
            self._finish_line()
        if (
            not phase_changed
            and event.current != 0
            and not event.completed
            and now - self._last_rendered_at < self._min_interval
        ):
            return

        line = self._render(event)
        padding = " " * max(0, self._line_length - len(line))
        self._stream.write(f"\r{line}{padding}")
        self._stream.flush()
        self._line_length = len(line)
        self._open_line = True
        self._last_phase = event.phase
        self._last_rendered_at = now

    def _render(self, event: ProgressEvent) -> str:
        if event.total is None:
            spinner = "|/-\\"[event.current % 4]
            return f"[{spinner}] {event.message}"
        total = max(0, event.total)
        current = min(max(0, event.current), total)
        ratio = 1.0 if total == 0 else current / total
        filled = min(self._width, int(ratio * self._width))
        bar = "#" * filled + "-" * (self._width - filled)
        return f"[{bar}] {ratio:6.1%} {event.message} ({current}/{total})"

    def _finish_line(self) -> None:
        if not self._open_line:
            return
        self._stream.write("\n")
        self._stream.flush()
        self._open_line = False
        self._line_length = 0

    def close(self) -> None:
        self._finish_line()


@contextmanager
def terminal_progress(
    mode: str,
    *,
    machine_output: bool,
    stream: TextIO | None = None,
) -> Iterator[ProgressCallback | None]:
    output = stream or sys.stderr
    enabled = mode == "always" or (
        mode == "auto" and not machine_output and output.isatty()
    )
    renderer = TerminalProgressBar(output, enabled=enabled)
    try:
        yield renderer if enabled else None
    finally:
        renderer.close()
