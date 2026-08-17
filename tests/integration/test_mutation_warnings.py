from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    Actor,
    ClaimDraft,
    DiagnosticSeverity,
    EdgeKind,
    ExperimentDraft,
    Project,
    RelationDraft,
    RunDraft,
    ValidationFailed,
)
from tests.conftest import NODE_IDS


def _create_archived_claim(project: Project) -> str:
    claim = project.create_node(
        ClaimDraft(title="Archived target", statement="A historical claim."),
        actor=Actor.human("author"),
    )
    archived = project.archive_node(
        claim.id,
        expected_revision=claim.revision,
        actor=Actor.human("archivist"),
    )
    assert project.last_diagnostics() == ()
    return archived.id


@pytest.mark.contract
@pytest.mark.integration
def test_add_edge_exposes_warning_without_changing_edge_return_type(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    archived_claim = _create_archived_claim(project)

    edge = project.add_edge(
        source=NODE_IDS["question"],
        kind=EdgeKind.RELATED_TO,
        target=archived_claim,
        actor=Actor.human("editor"),
    )

    warnings = project.last_diagnostics()
    assert project.snapshot().get_edge(edge.id) == edge
    assert len(warnings) == 1
    assert warnings[0].severity is DiagnosticSeverity.WARNING
    assert warnings[0].code == "archived_target"
    assert warnings[0].edge_id == edge.id
    assert warnings[0].node_id == NODE_IDS["question"]


@pytest.mark.contract
@pytest.mark.integration
def test_create_node_exposes_initial_relation_warning(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    experiment = project.create_node(
        ExperimentDraft(
            title="Historical experiment",
            objective="Preserve an old protocol.",
            method="Run the historical benchmark.",
            success_criteria="The benchmark completes.",
            protocol_version=1,
        ),
        actor=Actor.human("author"),
    )
    archived = project.archive_node(
        experiment.id,
        expected_revision=experiment.revision,
        actor=Actor.human("archivist"),
    )

    run = project.create_node(
        RunDraft(
            title="Historical protocol run",
            started_at="2026-08-17T12:00:00+07:00",
            outcome="running",
        ),
        actor=Actor.human("runner"),
        initial_relations=(RelationDraft(EdgeKind.INSTANCE_OF, archived.id),),
    )

    warnings = project.last_diagnostics()
    assert run.id in {node.id for node in project.snapshot().list_nodes()}
    assert len(warnings) == 1
    assert warnings[0].code == "archived_target"
    assert warnings[0].node_id == run.id


@pytest.mark.contract
@pytest.mark.integration
def test_clean_mutation_replaces_previous_operation_warnings(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    archived_claim = _create_archived_claim(project)
    edge = project.add_edge(
        source=NODE_IDS["question"],
        kind=EdgeKind.RELATED_TO,
        target=archived_claim,
        actor=Actor.human("editor"),
    )
    assert project.last_diagnostics()

    project.remove_edge(edge.id, actor=Actor.human("editor"))

    assert project.last_diagnostics() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_archiving_target_exposes_warnings_for_incoming_relations(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    claim = project.create_node(
        ClaimDraft(title="Soon archived", statement="A temporary claim."),
        actor=Actor.human("author"),
    )
    edge = project.add_edge(
        source=NODE_IDS["question"],
        kind=EdgeKind.RELATED_TO,
        target=claim.id,
        actor=Actor.human("editor"),
    )
    assert project.last_diagnostics() == ()

    project.archive_node(
        claim.id,
        expected_revision=claim.revision,
        actor=Actor.human("archivist"),
    )

    warnings = project.last_diagnostics()
    assert len(warnings) == 1
    assert warnings[0].code == "archived_target"
    assert warnings[0].edge_id == edge.id
    assert warnings[0].node_id == NODE_IDS["question"]


@pytest.mark.contract
@pytest.mark.integration
def test_failed_mutation_does_not_leave_candidate_warnings(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    archived_claim = _create_archived_claim(project)
    project.add_edge(
        source=NODE_IDS["question"],
        kind=EdgeKind.RELATED_TO,
        target=archived_claim,
        actor=Actor.human("editor"),
    )
    assert project.last_diagnostics()

    with pytest.raises(ValidationFailed):
        project.add_edge(
            source=NODE_IDS["question"],
            kind=EdgeKind.SUPPORTS,
            target=archived_claim,
            actor=Actor.human("editor"),
        )

    assert project.last_diagnostics() == ()
