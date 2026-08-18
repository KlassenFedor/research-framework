from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    Actor,
    ClaimDraft,
    EdgeKind,
    HypothesisDraft,
    NodeStatus,
    Project,
    RevisionConflict,
    StorageError,
    ValidationFailed,
)
from tests.conftest import NODE_IDS, RELATION_IDS


def _node_files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in (root / "research").rglob("*.md")
    }


@pytest.mark.contract
@pytest.mark.integration
def test_project_open_uses_ancestor_discovery_and_returns_clean_snapshot(
    example_project: Path,
) -> None:
    project = Project.open(example_project / "research" / "runs")

    assert project.root == example_project.resolve()
    assert len(project.snapshot().list_nodes()) == 11
    assert project.validate() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_init_creates_text_only_project_without_database_or_cache(
    tmp_path: Path,
) -> None:
    target = tmp_path / "new-research"

    project = Project.init(
        target,
        title="New research",
        default_language="ru",
    )

    assert project.root == target.resolve()
    assert (target / "research.yaml").is_file()
    assert (target / "research" / "PROJECT.md").is_file()
    assert (target / "research" / "questions").is_dir()
    assert (target / "research" / "decisions").is_dir()
    assert project.snapshot().list_nodes() == ()
    assert not list(target.rglob("*.sqlite"))
    assert not (target / ".research-cache").exists()


@pytest.mark.contract
@pytest.mark.integration
def test_init_refuses_to_overwrite_existing_project(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("important", encoding="utf-8")

    with pytest.raises(StorageError, match="not empty"):
        Project.init(target, title="Must not overwrite")

    assert marker.read_text(encoding="utf-8") == "important"


@pytest.mark.contract
@pytest.mark.integration
def test_create_node_generates_typed_ulid_and_one_markdown_file(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    before = set((example_project / "research").rglob("*.md"))

    node = project.create_node(
        ClaimDraft(
            title="Replication improves confidence",
            statement="Three consistent runs improve assessment confidence.",
            tags={"replication"},
            aliases=["C-replication"],
        ),
        actor=Actor.human("fedor"),
    )

    after = set((example_project / "research").rglob("*.md"))
    assert node.id.startswith("clm-")
    assert len(node.id) == 30
    assert node.status is NodeStatus.DRAFT
    assert node.created_by == Actor.human("fedor")
    assert node.path.parent.name == "claims"
    assert node.path.name.startswith(f"{node.id}--replication-improves-confidence")
    assert after - before == {node.path}
    assert project.snapshot().get_node("C-replication").id == node.id


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("title", "expected_slug"),
    [
        ("Тестовый вопрос", "тестовый-вопрос"),
        ("研究问题", "研究问题"),
        ("Résumé / NAÏVE", "résumé-naïve"),
    ],
)
def test_create_node_preserves_unicode_in_human_readable_slug(
    example_project: Path,
    title: str,
    expected_slug: str,
) -> None:
    project = Project.open(example_project)

    node = project.create_node(
        ClaimDraft(title=title, statement="Unicode titles remain readable."),
        actor=Actor.human("fedor"),
    )

    assert node.path.name == f"{node.id}--{expected_slug}.md"


@pytest.mark.contract
@pytest.mark.integration
def test_old_snapshot_remains_immutable_after_project_mutation(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    before = project.snapshot()

    node = project.create_node(
        ClaimDraft(title="New claim", statement="A new statement."),
        actor=Actor.human("fedor"),
    )

    assert node.id not in {item.id for item in before.list_nodes()}
    assert project.snapshot().get_node(node.id).id == node.id


@pytest.mark.contract
@pytest.mark.integration
def test_update_node_preserves_markdown_body_and_refreshes_audit_fields(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["hypothesis"])
    original = node.path.read_text(encoding="utf-8")
    original_body = original[original.index("\n---\n", 4) + len("\n---\n") :]

    updated = project.update_node(
        node.id,
        patch={"summary": "Updated summary", "tags": ["retrieval", "updated"]},
        expected_revision=node.revision,
        actor=Actor.agent("editor", run_id="agent-run-42"),
    )

    rewritten = updated.path.read_text(encoding="utf-8")
    rewritten_body = rewritten[rewritten.index("\n---\n", 4) + len("\n---\n") :]
    assert updated.summary == "Updated summary"
    assert updated.updated_by == Actor.agent("editor", run_id="agent-run-42")
    assert updated.revision != node.revision
    assert rewritten_body == original_body


@pytest.mark.contract
@pytest.mark.integration
def test_update_detects_external_change_and_never_overwrites_it(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["hypothesis"])
    externally_edited = node.path.read_text(encoding="utf-8") + "\nExternal note.\n"
    node.path.write_text(externally_edited, encoding="utf-8")

    with pytest.raises(RevisionConflict) as raised:
        project.update_node(
            node.id,
            patch={"summary": "Stale update"},
            expected_revision=node.revision,
            actor=Actor.human("fedor"),
        )

    assert raised.value.node_id == node.id
    assert raised.value.expected_revision == node.revision
    assert node.path.read_text(encoding="utf-8") == externally_edited


@pytest.mark.contract
@pytest.mark.integration
def test_invalid_patch_leaves_file_byte_for_byte_unchanged(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["hypothesis"])
    before = node.path.read_bytes()

    with pytest.raises(ValidationFailed):
        project.update_node(
            node.id,
            patch={"status": "believed"},
            expected_revision=node.revision,
            actor=Actor.human("fedor"),
        )

    assert node.path.read_bytes() == before
    assert not list(node.path.parent.glob("*.tmp"))


@pytest.mark.contract
@pytest.mark.integration
def test_archive_changes_status_without_deleting_node(example_project: Path) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node(NODE_IDS["claim"])

    archived = project.archive_node(
        node.id,
        expected_revision=node.revision,
        actor=Actor.human("reviewer"),
    )

    assert archived.status is NodeStatus.ARCHIVED
    assert archived.path.exists()
    assert project.snapshot().get_node(node.id).status is NodeStatus.ARCHIVED


@pytest.mark.contract
@pytest.mark.integration
def test_add_edge_changes_only_source_file(example_project: Path) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    edge = project.add_edge(
        source=NODE_IDS["evidence"],
        kind=EdgeKind.SUPPORTS,
        target=NODE_IDS["claim"],
        rationale="The measurement supports the related cost claim.",
        actor=Actor.human("reviewer"),
    )

    after = _node_files(example_project)
    changed = {path for path in before if before[path] != after[path]}
    source_path = project.snapshot().get_node(NODE_IDS["evidence"]).path
    assert edge.source == NODE_IDS["evidence"]
    assert edge.target == NODE_IDS["claim"]
    assert changed == {source_path.relative_to(example_project)}
    assert project.snapshot().get_edge(edge.id) == edge


@pytest.mark.contract
@pytest.mark.integration
def test_invalid_edge_does_not_modify_any_file(example_project: Path) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed):
        project.add_edge(
            source=NODE_IDS["question"],
            kind=EdgeKind.SUPPORTS,
            target=NODE_IDS["hypothesis"],
            actor=Actor.human("reviewer"),
        )

    assert _node_files(example_project) == before


@pytest.mark.contract
@pytest.mark.integration
def test_remove_edge_changes_only_owner_file_and_refreshes_snapshot(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    edge = project.snapshot().get_edge(RELATION_IDS["supports"])
    source_path = project.snapshot().get_node(edge.source).path
    before = _node_files(example_project)

    project.remove_edge(edge.id, actor=Actor.human("reviewer"))

    after = _node_files(example_project)
    changed = {path for path in before if before[path] != after[path]}
    assert changed == {source_path.relative_to(example_project)}
    assert all(item.id != edge.id for item in project.snapshot().outgoing(edge.source))


@pytest.mark.contract
@pytest.mark.integration
def test_alias_can_be_used_as_mutation_reference(example_project: Path) -> None:
    project = Project.open(example_project)
    node = project.snapshot().get_node("H-context")

    updated = project.update_node(
        "H-context",
        patch={"summary": "Changed through alias"},
        expected_revision=node.revision,
        actor=Actor.human("fedor"),
    )

    assert updated.id == NODE_IDS["hypothesis"]


@pytest.mark.contract
@pytest.mark.integration
def test_create_hypothesis_respects_falsification_policy(example_project: Path) -> None:
    project = Project.open(example_project)

    with pytest.raises((TypeError, ValueError, ValidationFailed)):
        project.create_node(
            HypothesisDraft(  # type: ignore[call-arg]
                title="Unfalsifiable hypothesis",
                statement="This cannot be disproved.",
            ),
            actor=Actor.human("fedor"),
        )
