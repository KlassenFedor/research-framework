from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    Actor,
    ArtifactDraft,
    AssessmentDraft,
    ClaimDraft,
    DecisionDraft,
    EdgeKind,
    EvidenceDraft,
    ExperimentDraft,
    HypothesisDraft,
    NodeKind,
    Project,
    QuestionDraft,
    RelationDraft,
    RunDraft,
    SourceDraft,
    ValidationFailed,
)
from tests.conftest import NODE_IDS


def _node_files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in (root / "research").rglob("*.md")
    }


def _creation_cases() -> list[tuple[object, tuple[RelationDraft, ...], NodeKind]]:
    return [
        (
            QuestionDraft(title="New question", question="What changed?"),
            (),
            NodeKind.QUESTION,
        ),
        (
            HypothesisDraft(
                title="New hypothesis",
                statement="The change improves recall.",
                falsification_criteria="Recall does not improve.",
            ),
            (),
            NodeKind.HYPOTHESIS,
        ),
        (
            ClaimDraft(title="New claim", statement="Recall improved."),
            (),
            NodeKind.CLAIM,
        ),
        (
            ExperimentDraft(
                title="New experiment",
                objective="Measure recall.",
                method="Run a benchmark.",
                success_criteria="Recall improves by 10%.",
                protocol_version=1,
            ),
            (),
            NodeKind.EXPERIMENT,
        ),
        (
            RunDraft(
                title="New run",
                started_at="2026-08-17T12:00:00+07:00",
                outcome="running",
            ),
            (
                RelationDraft(
                    kind=EdgeKind.INSTANCE_OF,
                    target=NODE_IDS["experiment"],
                ),
            ),
            NodeKind.RUN,
        ),
        (
            EvidenceDraft(
                title="New evidence",
                observation="Recall improved by 12%.",
                evidence_kind="quantitative",
            ),
            (
                RelationDraft(
                    kind=EdgeKind.DERIVED_FROM,
                    target=NODE_IDS["source"],
                ),
            ),
            NodeKind.EVIDENCE,
        ),
        (
            AssessmentDraft(
                title="New assessment",
                verdict="supported",
                confidence="medium",
                review_state="proposed",
            ),
            (
                RelationDraft(
                    kind=EdgeKind.ASSESSES,
                    target=NODE_IDS["hypothesis"],
                ),
                RelationDraft(
                    kind=EdgeKind.BASED_ON,
                    target=NODE_IDS["evidence"],
                ),
            ),
            NodeKind.ASSESSMENT,
        ),
        (
            SourceDraft(
                title="New source",
                source_kind="paper",
                locator="https://example.test/new-paper",
            ),
            (),
            NodeKind.SOURCE,
        ),
        (
            ArtifactDraft(title="New artifact", locator="artifacts/new.json"),
            (),
            NodeKind.ARTIFACT,
        ),
        (
            DecisionDraft(
                title="New decision",
                outcome="Repeat the benchmark.",
                rationale="More observations are required.",
            ),
            (),
            NodeKind.DECISION,
        ),
    ]


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(("draft", "relations", "expected_kind"), _creation_cases())
def test_every_node_kind_can_be_created_in_a_valid_state(
    example_project: Path,
    draft: object,
    relations: tuple[RelationDraft, ...],
    expected_kind: NodeKind,
) -> None:
    project = Project.open(example_project)

    node = project.create_node(
        draft,  # type: ignore[arg-type]
        actor=Actor.human("creator"),
        initial_relations=relations,
    )

    assert node.kind is expected_kind
    assert len(project.snapshot().outgoing(node.id)) == len(relations)
    assert project.validate() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_initial_relations_are_canonical_and_share_creation_audit_context(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    actor = Actor.agent("assessor", run_id="agent-run-42")
    before = _node_files(example_project)

    node = project.create_node(
        AssessmentDraft(
            title="Alias-based assessment",
            verdict="supported",
            confidence="high",
            review_state="proposed",
        ),
        actor=actor,
        initial_relations=(
            RelationDraft(
                kind=EdgeKind.ASSESSES,
                target="H-context",
                rationale="The assessment evaluates this hypothesis.",
            ),
            RelationDraft(
                kind=EdgeKind.BASED_ON,
                target=NODE_IDS["claim"][:12],
            ),
        ),
    )

    edges = {edge.kind: edge for edge in project.snapshot().outgoing(node.id)}
    after = _node_files(example_project)
    assert set(after) - set(before) == {node.path.relative_to(example_project)}
    assert all(before[path] == after[path] for path in before)
    assert edges[EdgeKind.ASSESSES].target == NODE_IDS["hypothesis"]
    assert edges[EdgeKind.BASED_ON].target == NODE_IDS["claim"]
    assert edges[EdgeKind.ASSESSES].rationale == (
        "The assessment evaluates this hypothesis."
    )
    assert all(
        edge.id.startswith("rel-") and len(edge.id) == 30 for edge in edges.values()
    )
    assert all(edge.source == node.id for edge in edges.values())
    assert all(edge.created_at == node.created_at for edge in edges.values())
    assert all(edge.created_by == actor for edge in edges.values())


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("draft", "expected_code"),
    [
        (
            RunDraft(
                title="Disconnected run",
                started_at="2026-08-17T12:00:00+07:00",
                outcome="running",
            ),
            "invalid_instance_of_count",
        ),
        (
            EvidenceDraft(
                title="Unprovenanced evidence",
                observation="An observation.",
                evidence_kind="qualitative",
            ),
            "evidence_provenance_required",
        ),
        (
            AssessmentDraft(
                title="Unconnected assessment",
                verdict="inconclusive",
                confidence="low",
                review_state="proposed",
            ),
            "assessment_target_required",
        ),
    ],
)
def test_missing_required_initial_relations_leave_project_unchanged(
    example_project: Path,
    draft: object,
    expected_code: str,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.create_node(draft, actor=Actor.human("creator"))  # type: ignore[arg-type]

    assert expected_code in {item.code for item in raised.value.diagnostics}
    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot
    assert not list((example_project / "research").rglob(".rf-*.tmp"))


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("relations", "expected_code"),
    [
        (
            (
                RelationDraft(
                    kind=EdgeKind.SUPPORTS,
                    target=NODE_IDS["hypothesis"],
                ),
            ),
            "relation_kind_mismatch",
        ),
        (
            (
                RelationDraft(
                    kind=EdgeKind.INSTANCE_OF,
                    target=NODE_IDS["experiment"],
                ),
                RelationDraft(
                    kind=EdgeKind.INSTANCE_OF,
                    target=NODE_IDS["experiment"],
                ),
            ),
            "invalid_instance_of_count",
        ),
    ],
)
def test_invalid_initial_relation_sets_are_rejected_before_writing(
    example_project: Path,
    relations: tuple[RelationDraft, ...],
    expected_code: str,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.create_node(
            RunDraft(
                title="Invalid run",
                started_at="2026-08-17T12:00:00+07:00",
                outcome="running",
            ),
            actor=Actor.human("creator"),
            initial_relations=relations,
        )

    assert expected_code in {item.code for item in raised.value.diagnostics}
    assert _node_files(example_project) == before


@pytest.mark.contract
@pytest.mark.integration
def test_initial_relations_reject_raw_persistence_metadata_before_writing(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.create_node(
            RunDraft(
                title="Caller-authored relation metadata",
                started_at="2026-08-17T12:00:00+07:00",
                outcome="running",
            ),
            actor=Actor.human("creator"),
            initial_relations=(
                {  # type: ignore[arg-type]
                    "id": "rel-01J000000000000000000ZZZZZ",
                    "kind": "instance_of",
                    "target": NODE_IDS["experiment"],
                    "created_by": {"kind": "human", "id": "spoofed"},
                },
            ),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "invalid_relation_draft"
    assert diagnostic.field == "initial_relations[0]"
    assert _node_files(example_project) == before


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize(
    ("target", "expected_code"),
    [
        ("exp-01J000000000000000000ZZZZZZ", "relation_target_not_found"),
        ("evd-01J00000", "ambiguous_relation_target"),
    ],
)
def test_unresolved_initial_relation_target_is_a_validation_error_without_a_write(
    example_project: Path,
    target: str,
    expected_code: str,
) -> None:
    project = Project.open(example_project)
    before = _node_files(example_project)

    with pytest.raises(ValidationFailed) as raised:
        project.create_node(
            RunDraft(
                title="Run with missing experiment",
                started_at="2026-08-17T12:00:00+07:00",
                outcome="running",
            ),
            actor=Actor.human("creator"),
            initial_relations=(
                RelationDraft(
                    kind=EdgeKind.INSTANCE_OF,
                    target=target,
                ),
            ),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == expected_code
    assert diagnostic.field == "initial_relations[0].target"
    assert diagnostic.details["target"] == target
    if expected_code == "ambiguous_relation_target":
        assert diagnostic.details["candidates"] == sorted(
            [NODE_IDS["evidence"], NODE_IDS["challenging_evidence"]]
        )
    assert _node_files(example_project) == before


@pytest.mark.contract
@pytest.mark.integration
def test_evidence_can_be_created_without_provenance_when_policy_is_disabled(
    example_project: Path,
) -> None:
    config = example_project / "research.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "require_evidence_provenance: true",
            "require_evidence_provenance: false",
        ),
        encoding="utf-8",
    )
    project = Project.open(example_project)

    node = project.create_node(
        EvidenceDraft(
            title="Policy-independent evidence",
            observation="An observation without recorded provenance.",
            evidence_kind="other",
        ),
        actor=Actor.human("creator"),
    )

    assert project.snapshot().outgoing(node.id) == ()
    assert project.validate() == ()


@pytest.mark.contract
@pytest.mark.integration
def test_create_node_rolls_back_its_file_when_snapshot_publish_fails(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    snapshot = project.snapshot()
    before = _node_files(example_project)

    def fail_publish(*args: object) -> None:
        del args
        raise RuntimeError("simulated snapshot publish failure")

    monkeypatch.setattr(project, "_publish_document", fail_publish)

    with pytest.raises(RuntimeError, match="simulated snapshot publish failure"):
        project.create_node(
            ClaimDraft(title="Rolled back claim", statement="Never becomes visible."),
            actor=Actor.human("creator"),
        )

    assert _node_files(example_project) == before
    assert project.snapshot() is snapshot
    assert not list((example_project / "research").rglob(".rf-*.tmp"))
