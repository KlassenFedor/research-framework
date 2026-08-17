from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    DiagnosticSeverity,
    FormatResult,
    Project,
    RevisionConflict,
    StorageError,
    ValidationFailed,
)


def _node_files(root: Path) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in (root / "research").rglob("*.md")
        if path.name != "PROJECT.md"
    }


def _body(raw: bytes) -> bytes:
    closing = raw.index(b"\n---\n", 4)
    return raw[closing + len(b"\n---\n") :]


@pytest.mark.contract
@pytest.mark.integration
def test_format_check_reports_every_noncanonical_node_without_writing(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    result = project.format(check=True)

    assert isinstance(result, FormatResult)
    assert result.checked_files == 11
    assert result.applied is False
    assert result.changed_paths == tuple(sorted(before))
    assert _node_files(example_project) == before


@pytest.mark.contract
@pytest.mark.integration
def test_format_canonicalizes_only_front_matter_and_is_idempotent(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)
    project_readme = example_project / "research" / "PROJECT.md"
    readme_before = project_readme.read_bytes()

    applied = project.format()

    after = _node_files(example_project)
    assert applied.checked_files == 11
    assert applied.applied is True
    assert applied.changed_paths == tuple(sorted(before))
    assert {path: _body(raw) for path, raw in after.items()} == {
        path: _body(raw) for path, raw in before.items()
    }
    assert project_readme.read_bytes() == readme_before
    assert project.validate() == ()

    canonical = after.copy()
    checked = project.format(check=True)
    assert checked.checked_files == 11
    assert checked.changed_paths == ()
    assert checked.applied is False
    assert _node_files(example_project) == canonical

    noop = project.format()
    assert noop.changed_paths == ()
    assert noop.applied is False
    assert _node_files(example_project) == canonical


@pytest.mark.contract
@pytest.mark.integration
def test_format_validates_the_whole_project_before_any_write(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    hypothesis.write_text(
        hypothesis.read_text(encoding="utf-8").replace(
            "que-01J00000000000000000000001",
            "que-01J00000000000000000MISSING",
        ),
        encoding="utf-8",
    )
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed):
        project.format()

    assert _node_files(example_project) == before
    assert project.last_diagnostics() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_format_rolls_back_all_files_if_refresh_fails(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    def fail_refresh() -> None:
        raise StorageError("simulated refresh failure")

    monkeypatch.setattr(project, "_refresh", fail_refresh)

    with pytest.raises(StorageError, match="refresh failure"):
        project.format()

    assert _node_files(example_project) == before
    assert project.last_diagnostics() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_format_detects_concurrent_edit_and_preserves_it_while_rolling_back(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)
    ordered = tuple(sorted(before))
    second = ordered[1]
    external = before[second] + b"\nExternal edit.\n"
    original_write = project._atomic_write_bytes
    calls = 0

    def edit_second_after_first_write(target: Path, content: bytes) -> None:
        nonlocal calls
        original_write(target, content)
        calls += 1
        if calls == 1:
            second.write_bytes(external)

    monkeypatch.setattr(project, "_atomic_write_bytes", edit_second_after_first_write)

    with pytest.raises(RevisionConflict):
        project.format()

    after = _node_files(example_project)
    assert after[second] == external
    assert {path: raw for path, raw in after.items() if path != second} == {
        path: raw for path, raw in before.items() if path != second
    }
    assert project.last_diagnostics() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_successful_format_exposes_validation_warnings(example_project: Path) -> None:
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    hypothesis.write_text(
        hypothesis.read_text(encoding="utf-8").replace(
            "status: active", "status: archived"
        ),
        encoding="utf-8",
    )
    project = Project.open(example_project)

    project.format(check=True)

    warnings = project.last_diagnostics()
    assert warnings
    assert all(item.severity is DiagnosticSeverity.WARNING for item in warnings)
