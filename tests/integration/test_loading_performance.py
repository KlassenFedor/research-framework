from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import ProgressEvent, Project, RevisionConflict
from tests.conftest import NODE_IDS


@pytest.mark.contract
@pytest.mark.integration
def test_project_open_reads_and_decodes_each_node_only_once(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    markdown_reads = {"bytes": 0, "text": 0}

    def counted_read_bytes(path: Path) -> bytes:
        if path.suffix == ".md":
            markdown_reads["bytes"] += 1
        return original_read_bytes(path)

    def counted_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.suffix == ".md":
            markdown_reads["text"] += 1
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    monkeypatch.setattr(Path, "read_text", counted_read_text)

    project = Project.open(example_project)

    assert len(project.snapshot().list_nodes()) == 11
    assert markdown_reads == {"bytes": 11, "text": 0}


@pytest.mark.contract
@pytest.mark.integration
def test_snapshot_body_is_loaded_once_on_first_access(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])
    original_read_bytes = Path.read_bytes
    reads: list[Path] = []

    def counted_read_bytes(path: Path) -> bytes:
        if path.suffix == ".md":
            reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    assert "body" not in node.to_dict()
    assert project.snapshot().list_nodes(kind="claim") == (node,)
    assert reads == []

    assert "Context cost" in node.body
    assert reads == [node.path]
    assert "Context cost" in node.body
    assert reads == [node.path]


@pytest.mark.contract
@pytest.mark.integration
def test_lazy_body_never_mixes_a_stale_snapshot_with_new_file_content(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])
    node.path.write_text(
        node.path.read_text(encoding="utf-8") + "\nExternal edit.\n",
        encoding="utf-8",
    )

    with pytest.raises(RevisionConflict):
        _ = node.body


@pytest.mark.contract
@pytest.mark.integration
def test_project_open_reports_machine_readable_progress(example_project: Path) -> None:
    events: list[ProgressEvent] = []

    Project.open(example_project, progress=events.append)

    loading = [event for event in events if event.phase == "loading"]
    assert loading[0].current == 0
    assert loading[-1].current == loading[-1].total == 11
    assert any(event.phase == "validating" and event.completed for event in events)
    assert any(event.phase == "indexing" and event.completed for event in events)


@pytest.mark.contract
@pytest.mark.integration
def test_validate_and_format_report_progress(example_project: Path) -> None:
    project = Project.open(example_project)
    validation_events: list[ProgressEvent] = []
    formatting_events: list[ProgressEvent] = []

    assert project.validate(progress=validation_events.append) == ()
    result = project.format(check=True, progress=formatting_events.append)

    assert result.checked_files == 11
    assert any(
        event.phase == "loading" and event.completed for event in validation_events
    )
    assert any(
        event.phase == "formatting" and event.completed for event in formatting_events
    )
