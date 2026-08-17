from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import Actor, ClaimDraft, Project, StorageError
from tests.conftest import NODE_IDS


def _node_file(root: Path, folder: str) -> Path:
    return next((root / "research" / folder).glob("*.md"))


@pytest.mark.contract
@pytest.mark.integration
def test_update_follows_discovered_file_not_filename_convention(
    example_project: Path,
) -> None:
    original = _node_file(example_project, "claims")
    moved = example_project / "research" / "notes" / "human-name.md"
    moved.parent.mkdir()
    original.rename(moved)
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])

    updated = project.update_node(
        node.id,
        patch={"summary": "Updated after a manual move"},
        expected_revision=node.revision,
        actor=Actor.human("fedor"),
    )

    assert updated.path == moved
    assert moved.exists()
    assert not original.exists()


@pytest.mark.contract
@pytest.mark.integration
def test_generated_slug_cannot_escape_vault(example_project: Path) -> None:
    project = Project.open(example_project)

    node = project.create_node(
        ClaimDraft(
            title="../../outside/../../danger",
            statement="Path-like titles are still plain titles.",
        ),
        actor=Actor.human("fedor"),
    )

    assert node.path.resolve().is_relative_to((example_project / "research").resolve())
    assert node.path.parent == example_project / "research" / "claims"
    assert "/" not in node.path.name


@pytest.mark.contract
@pytest.mark.integration
def test_symlink_swap_cannot_redirect_atomic_update_outside_vault(
    example_project: Path, tmp_path: Path
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])
    outside = tmp_path / "outside.md"
    outside.write_text("must remain unchanged", encoding="utf-8")
    node.path.unlink()
    try:
        node.path.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(StorageError, match="symlink"):
        project.update_node(
            node.id,
            patch={"summary": "Redirected write"},
            expected_revision=node.revision,
            actor=Actor.human("attacker"),
        )

    assert outside.read_text(encoding="utf-8") == "must remain unchanged"


@pytest.mark.contract
@pytest.mark.integration
def test_revision_hash_covers_body_as_well_as_metadata(example_project: Path) -> None:
    first = Project.open(example_project).snapshot().get_node(NODE_IDS["claim"])
    first.path.write_text(
        first.path.read_text(encoding="utf-8") + "\nA manual body edit.\n",
        encoding="utf-8",
    )
    second = Project.open(example_project).snapshot().get_node(NODE_IDS["claim"])

    assert second.revision != first.revision


@pytest.mark.contract
@pytest.mark.integration
def test_namespaced_extensions_round_trip_without_unknown_field_error(
    example_project: Path,
) -> None:
    path = _node_file(example_project, "questions")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "relations: []",
        "extensions:\n"
        "  example.plugin:\n"
        "    external_id: 42\n"
        "    enabled: true\n"
        "relations: []",
    )
    path.write_text(text, encoding="utf-8")
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["question"])

    updated = project.update_node(
        node.id,
        patch={"summary": "Keep extensions"},
        expected_revision=node.revision,
        actor=Actor.human("fedor"),
    )

    assert updated.extensions["example.plugin"] == {
        "external_id": 42,
        "enabled": True,
    }
    assert "example.plugin:" in path.read_text(encoding="utf-8")


@pytest.mark.contract
@pytest.mark.integration
def test_successful_write_leaves_no_temporary_files(example_project: Path) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])

    project.update_node(
        node.id,
        patch={"summary": "Atomic update"},
        expected_revision=node.revision,
        actor=Actor.human("fedor"),
    )

    leftovers = [
        path
        for path in (example_project / "research").rglob("*")
        if path.is_file()
        and (path.name.endswith(".tmp") or path.name.startswith(".rf-"))
    ]
    assert leftovers == []
