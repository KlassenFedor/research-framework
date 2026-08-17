from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .enums import NodeKind


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeDraft:
    title: str
    summary: str | None = None
    tags: frozenset[str] = frozenset()
    aliases: tuple[str, ...] = ()
    body: str = ""

    kind: ClassVar[NodeKind]

    def __post_init__(self) -> None:
        _require_text(self.title, "title")
        object.__setattr__(self, "tags", frozenset(self.tags))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("tags must contain non-blank strings")
        if any(
            not isinstance(alias, str) or not alias.strip() for alias in self.aliases
        ):
            raise ValueError("aliases must contain non-blank strings")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("aliases must not contain duplicates")


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionDraft(NodeDraft):
    question: str
    scope: str | None = None

    kind: ClassVar[NodeKind] = NodeKind.QUESTION

    def __post_init__(self) -> None:
        super(QuestionDraft, self).__post_init__()
        _require_text(self.question, "question")


@dataclass(frozen=True, slots=True, kw_only=True)
class HypothesisDraft(NodeDraft):
    statement: str
    falsification_criteria: str
    assumptions: tuple[str, ...] = ()

    kind: ClassVar[NodeKind] = NodeKind.HYPOTHESIS

    def __post_init__(self) -> None:
        super(HypothesisDraft, self).__post_init__()
        _require_text(self.statement, "statement")
        _require_text(self.falsification_criteria, "falsification_criteria")
        object.__setattr__(self, "assumptions", tuple(self.assumptions))


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimDraft(NodeDraft):
    statement: str

    kind: ClassVar[NodeKind] = NodeKind.CLAIM

    def __post_init__(self) -> None:
        super(ClaimDraft, self).__post_init__()
        _require_text(self.statement, "statement")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentDraft(NodeDraft):
    objective: str
    method: str
    success_criteria: str
    protocol_version: int | str

    kind: ClassVar[NodeKind] = NodeKind.EXPERIMENT

    def __post_init__(self) -> None:
        super(ExperimentDraft, self).__post_init__()
        _require_text(self.objective, "objective")
        _require_text(self.method, "method")
        _require_text(self.success_criteria, "success_criteria")


@dataclass(frozen=True, slots=True, kw_only=True)
class RunDraft(NodeDraft):
    started_at: str
    outcome: str
    finished_at: str | None = None
    environment: dict[str, object] | None = None

    kind: ClassVar[NodeKind] = NodeKind.RUN

    def __post_init__(self) -> None:
        super(RunDraft, self).__post_init__()
        _require_text(self.started_at, "started_at")
        if self.outcome not in {"running", "completed", "failed", "cancelled"}:
            raise ValueError("invalid run outcome")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceDraft(NodeDraft):
    observation: str
    evidence_kind: str
    collected_at: str | None = None

    kind: ClassVar[NodeKind] = NodeKind.EVIDENCE

    def __post_init__(self) -> None:
        super(EvidenceDraft, self).__post_init__()
        _require_text(self.observation, "observation")
        if self.evidence_kind not in {
            "quantitative",
            "qualitative",
            "citation",
            "derived",
            "other",
        }:
            raise ValueError("invalid evidence_kind")


@dataclass(frozen=True, slots=True, kw_only=True)
class AssessmentDraft(NodeDraft):
    verdict: str
    confidence: str
    review_state: str
    limitations: tuple[str, ...] = ()

    kind: ClassVar[NodeKind] = NodeKind.ASSESSMENT

    def __post_init__(self) -> None:
        super(AssessmentDraft, self).__post_init__()
        if self.verdict not in {"supported", "challenged", "refuted", "inconclusive"}:
            raise ValueError("invalid assessment verdict")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValueError("invalid assessment confidence")
        if self.review_state not in {"proposed", "approved", "rejected"}:
            raise ValueError("invalid assessment review_state")
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceDraft(NodeDraft):
    source_kind: str
    locator: str
    citation: str | None = None
    accessed_at: str | None = None

    kind: ClassVar[NodeKind] = NodeKind.SOURCE

    def __post_init__(self) -> None:
        super(SourceDraft, self).__post_init__()
        _require_text(self.locator, "locator")
        if self.source_kind not in {
            "paper",
            "book",
            "dataset",
            "web",
            "interview",
            "other",
        }:
            raise ValueError("invalid source_kind")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactDraft(NodeDraft):
    locator: str
    media_type: str | None = None
    sha256: str | None = None
    size: int | None = None

    kind: ClassVar[NodeKind] = NodeKind.ARTIFACT

    def __post_init__(self) -> None:
        super(ArtifactDraft, self).__post_init__()
        _require_text(self.locator, "locator")
        if self.size is not None and self.size < 0:
            raise ValueError("size must not be negative")
        if self.sha256 is not None and (
            len(self.sha256) != 64
            or any(
                character not in "0123456789abcdefABCDEF" for character in self.sha256
            )
        ):
            raise ValueError("sha256 must contain 64 hexadecimal characters")


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionDraft(NodeDraft):
    outcome: str
    rationale: str

    kind: ClassVar[NodeKind] = NodeKind.DECISION

    def __post_init__(self) -> None:
        super(DecisionDraft, self).__post_init__()
        _require_text(self.outcome, "outcome")
        _require_text(self.rationale, "rationale")
