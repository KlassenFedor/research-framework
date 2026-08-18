from __future__ import annotations

from io import StringIO

from research_framework.presentation.progress import (
    TerminalProgressBar,
    terminal_progress,
)
from research_framework.progress import ProgressEvent


def event(phase: str, current: int, total: int | None) -> ProgressEvent:
    return ProgressEvent(
        phase=phase,
        current=current,
        total=total,
        message=phase.replace("_", " ").title(),
    )


def test_terminal_progress_renders_counts_and_finishes_each_phase() -> None:
    stream = StringIO()
    progress = TerminalProgressBar(stream, enabled=True, min_interval=0)

    progress(event("loading", 0, 2))
    progress(event("loading", 1, 2))
    progress(event("loading", 2, 2))
    progress(event("validating", 0, None))
    progress.close()

    output = stream.getvalue()
    assert "50.0% Loading (1/2)" in output
    assert "100.0% Loading (2/2)" in output
    assert "Validating" in output
    assert output.endswith("\n")


def test_terminal_progress_can_be_forced_for_machine_output() -> None:
    stream = StringIO()

    with terminal_progress("always", machine_output=True, stream=stream) as progress:
        assert progress is not None
        progress(event("loading", 1, 1))

    assert "Loading" in stream.getvalue()


def test_terminal_progress_auto_mode_is_silent_for_non_tty_stream() -> None:
    stream = StringIO()

    with terminal_progress("auto", machine_output=False, stream=stream) as progress:
        assert progress is None

    assert stream.getvalue() == ""
