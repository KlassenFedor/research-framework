from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import Actor, EdgeKind, Project, ValidationFailed
from tests.conftest import NODE_IDS, RELATION_IDS


def _node_files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in (root / "research").rglob("*.md")
    }


def _codes(error: ValidationFailed) -> set[str]:
    return {diagnostic.code for diagnostic in error.diagnostics}


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("node_key", "patch", "expected_code"),
    [
        ("run", {"outcome": "succeeded"}, "invalid_run_outcome"),
        ("artifact", {"size": -1}, "invalid_artifact_size"),
        ("claim", {"aliases": ["H-context"]}, "duplicate_alias"),
    ],
)
def test_update_rejects_invalid_candidate_before_writing(
    example_project: Path,
    node_key: str,
    patch: dict[str, object],
    expected_code: str,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    node = snapshot.get_node(NODE_IDS[node_key])
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.update_node(
            node.id,
            patch=patch,
            expected_revision=node.revision,
            actor=Actor.human("editor"),
        )

    assert expected_code in _codes(raised.value)
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot
    assert not list((example_project / "research").rglob(".rf-*.tmp"))


@pytest.mark.contract
@pytest.mark.integration
def test_add_edge_rejects_second_instance_of_before_writing(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.add_edge(
            source=NODE_IDS["run"],
            kind=EdgeKind.INSTANCE_OF,
            target=NODE_IDS["experiment"],
            actor=Actor.human("editor"),
        )

    assert "invalid_instance_of_count" in _codes(raised.value)
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot


@pytest.mark.contract
@pytest.mark.integration
def test_add_edge_rejects_dependency_cycle_before_writing(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    project.add_edge(
        source=NODE_IDS["claim"],
        kind=EdgeKind.DEPENDS_ON,
        target=NODE_IDS["hypothesis"],
        actor=Actor.human("editor"),
    )
    snapshot = project.snapshot()
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.add_edge(
            source=NODE_IDS["hypothesis"],
            kind=EdgeKind.DEPENDS_ON,
            target=NODE_IDS["claim"],
            actor=Actor.human("editor"),
        )

    assert "dependency_cycle" in _codes(raised.value)
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("edge_key", "expected_code"),
    [
        ("instance_of", "invalid_instance_of_count"),
        ("derived_from_run", "evidence_provenance_required"),
        ("assesses", "assessment_target_required"),
    ],
)
def test_remove_edge_rejects_removing_required_relation_before_writing(
    example_project: Path,
    edge_key: str,
    expected_code: str,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.remove_edge(
            RELATION_IDS[edge_key],
            actor=Actor.human("editor"),
        )

    assert expected_code in _codes(raised.value)
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot


@pytest.mark.contract
@pytest.mark.integration
def test_remove_edge_rejects_removing_last_assessment_basis(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    project.remove_edge(
        RELATION_IDS["based_on_support"],
        actor=Actor.human("editor"),
    )
    snapshot = project.snapshot()
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.remove_edge(
            RELATION_IDS["based_on_challenge"],
            actor=Actor.human("editor"),
        )

    assert "assessment_basis_required" in _codes(raised.value)
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot


@pytest.mark.contract
@pytest.mark.integration
def test_replacement_rolls_back_exact_bytes_when_refresh_fails(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    node = snapshot.get_node(NODE_IDS["claim"])
    before = _node_files(example_project)

    def fail_refresh() -> None:
        raise RuntimeError("simulated refresh failure")

    monkeypatch.setattr(project, "_refresh", fail_refresh)

    with pytest.raises(RuntimeError, match="simulated refresh failure"):
        project.update_node(
            node.id,
            patch={"summary": "Must be rolled back"},
            expected_revision=node.revision,
            actor=Actor.human("editor"),
        )

    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot
    assert not list((example_project / "research").rglob(".rf-*.tmp"))
