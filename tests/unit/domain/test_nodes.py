from __future__ import annotations

from collections.abc import Callable

import pytest

from research_framework import (
    Actor,
    ArtifactDraft,
    AssessmentDraft,
    ClaimDraft,
    DecisionDraft,
    EvidenceDraft,
    ExperimentDraft,
    HypothesisDraft,
    NodeKind,
    QuestionDraft,
    RunDraft,
    SourceDraft,
)

DraftFactory = Callable[[], object]


CASES: list[tuple[NodeKind, DraftFactory]] = [
    (
        NodeKind.QUESTION,
        lambda: QuestionDraft(title="Question", question="What changed?"),
    ),
    (
        NodeKind.HYPOTHESIS,
        lambda: HypothesisDraft(
            title="Hypothesis",
            statement="The intervention improves recall.",
            falsification_criteria="Recall improves by less than 10%.",
        ),
    ),
    (
        NodeKind.CLAIM,
        lambda: ClaimDraft(title="Claim", statement="Recall increased."),
    ),
    (
        NodeKind.EXPERIMENT,
        lambda: ExperimentDraft(
            title="Experiment",
            objective="Measure recall.",
            method="Run a fixed benchmark.",
            success_criteria="At least 10% improvement.",
            protocol_version=1,
        ),
    ),
    (
        NodeKind.RUN,
        lambda: RunDraft(
            title="Run",
            started_at="2026-08-17T10:00:00+07:00",
            outcome="running",
        ),
    ),
    (
        NodeKind.EVIDENCE,
        lambda: EvidenceDraft(
            title="Evidence",
            observation="Recall improved by 13%.",
            evidence_kind="quantitative",
        ),
    ),
    (
        NodeKind.ASSESSMENT,
        lambda: AssessmentDraft(
            title="Assessment",
            verdict="supported",
            confidence="medium",
            review_state="proposed",
        ),
    ),
    (
        NodeKind.SOURCE,
        lambda: SourceDraft(
            title="Source",
            source_kind="paper",
            locator="https://example.test/paper",
        ),
    ),
    (
        NodeKind.ARTIFACT,
        lambda: ArtifactDraft(title="Artifact", locator="artifacts/result.json"),
    ),
    (
        NodeKind.DECISION,
        lambda: DecisionDraft(
            title="Decision",
            outcome="Repeat the benchmark.",
            rationale="One run is insufficient.",
        ),
    ),
]


@pytest.mark.contract
@pytest.mark.parametrize(
    ("kind", "factory"),
    CASES,
    ids=[kind.value for kind, _factory in CASES],
)
def test_each_mvp_kind_has_a_typed_draft(kind: NodeKind, factory: DraftFactory) -> None:
    draft = factory()

    assert draft.kind is kind  # type: ignore[attr-defined]


@pytest.mark.contract
def test_draft_normalizes_user_classification_without_losing_ordered_aliases() -> None:
    draft = HypothesisDraft(
        title="Hypothesis",
        statement="Statement",
        falsification_criteria="Criterion",
        tags={"retrieval", "context"},
        aliases=["H-1", "old-name"],
    )

    assert draft.tags == frozenset({"retrieval", "context"})
    assert draft.aliases == ("H-1", "old-name")


@pytest.mark.contract
def test_draft_rejects_blank_required_text() -> None:
    with pytest.raises(ValueError, match="title"):
        QuestionDraft(title=" ", question="What changed?")


@pytest.mark.contract
@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (lambda: QuestionDraft(title="Question", question=" "), "question"),
        (
            lambda: HypothesisDraft(
                title="Hypothesis",
                statement=" ",
                falsification_criteria="Criterion",
            ),
            "statement",
        ),
        (
            lambda: HypothesisDraft(
                title="Hypothesis",
                statement="Statement",
                falsification_criteria=" ",
            ),
            "falsification_criteria",
        ),
        (lambda: ClaimDraft(title="Claim", statement=" "), "statement"),
        (
            lambda: ExperimentDraft(
                title="Experiment",
                objective=" ",
                method="Method",
                success_criteria="Criterion",
                protocol_version=1,
            ),
            "objective",
        ),
        (
            lambda: EvidenceDraft(
                title="Evidence", observation=" ", evidence_kind="quantitative"
            ),
            "observation",
        ),
        (
            lambda: SourceDraft(title="Source", source_kind="paper", locator=" "),
            "locator",
        ),
        (lambda: ArtifactDraft(title="Artifact", locator=" "), "locator"),
        (
            lambda: DecisionDraft(title="Decision", outcome=" ", rationale="Rationale"),
            "outcome",
        ),
        (
            lambda: DecisionDraft(title="Decision", outcome="Outcome", rationale=" "),
            "rationale",
        ),
    ],
    ids=[
        "question",
        "hypothesis-statement",
        "hypothesis-falsification",
        "claim",
        "experiment",
        "evidence",
        "source",
        "artifact",
        "decision-outcome",
        "decision-rationale",
    ],
)
def test_each_kind_rejects_blank_required_text(
    factory: DraftFactory, field: str
) -> None:
    with pytest.raises(ValueError, match=field):
        factory()


@pytest.mark.contract
@pytest.mark.parametrize(
    "factory",
    [
        lambda: RunDraft(
            title="Run",
            started_at="2026-08-17T10:00:00+07:00",
            outcome="succeeded",
        ),
        lambda: EvidenceDraft(
            title="Evidence", observation="Observed", evidence_kind="anecdotal"
        ),
        lambda: AssessmentDraft(
            title="Assessment",
            verdict="true",
            confidence="medium",
            review_state="approved",
        ),
        lambda: AssessmentDraft(
            title="Assessment",
            verdict="supported",
            confidence="certain",
            review_state="approved",
        ),
        lambda: AssessmentDraft(
            title="Assessment",
            verdict="supported",
            confidence="medium",
            review_state="final",
        ),
        lambda: SourceDraft(
            title="Source", source_kind="tweet", locator="https://example.test"
        ),
    ],
    ids=[
        "run-outcome",
        "evidence-kind",
        "assessment-verdict",
        "assessment-confidence",
        "assessment-review-state",
        "source-kind",
    ],
)
def test_draft_enums_are_strict(factory: DraftFactory) -> None:
    with pytest.raises(ValueError):
        factory()


@pytest.mark.contract
def test_draft_rejects_blank_tags_and_duplicate_aliases() -> None:
    with pytest.raises(ValueError, match="tag"):
        ClaimDraft(title="Claim", statement="Statement", tags={""})
    with pytest.raises(ValueError, match="alias"):
        ClaimDraft(
            title="Claim",
            statement="Statement",
            aliases=["C-1", "C-1"],
        )


@pytest.mark.contract
def test_draft_rejects_unknown_fields_instead_of_silently_discarding_them() -> None:
    with pytest.raises((TypeError, ValueError), match="typo_field"):
        QuestionDraft(  # type: ignore[call-arg]
            title="Question",
            question="What changed?",
            typo_field="must not be ignored",
        )


@pytest.mark.contract
def test_agent_can_be_attached_to_mutation_without_becoming_draft_metadata() -> None:
    draft = ClaimDraft(title="Claim", statement="A statement")
    actor = Actor.agent("claim-writer", run_id="agent-run-1")

    assert not hasattr(draft, "created_by")
    assert actor.run_id == "agent-run-1"
