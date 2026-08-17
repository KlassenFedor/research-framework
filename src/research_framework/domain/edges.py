from __future__ import annotations

from dataclasses import dataclass

from .enums import EdgeKind, NodeKind


@dataclass(frozen=True, slots=True)
class RelationDraft:
    """Caller-owned fields for an outgoing relation created with a new node."""

    kind: EdgeKind
    target: str
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EdgeKind(self.kind))
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("relation target must not be blank")
        if self.rationale is not None and (
            not isinstance(self.rationale, str) or not self.rationale.strip()
        ):
            raise ValueError("relation rationale must not be blank")


_ALLOWED: dict[EdgeKind, tuple[set[NodeKind], set[NodeKind]]] = {
    EdgeKind.ADDRESSES: (
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
        {NodeKind.QUESTION},
    ),
    EdgeKind.DECOMPOSES: (
        {NodeKind.QUESTION, NodeKind.HYPOTHESIS},
        {NodeKind.QUESTION, NodeKind.HYPOTHESIS},
    ),
    EdgeKind.DEPENDS_ON: (
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM, NodeKind.EXPERIMENT},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.TESTS: (
        {NodeKind.EXPERIMENT},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.INSTANCE_OF: ({NodeKind.RUN}, {NodeKind.EXPERIMENT}),
    EdgeKind.PRODUCES: ({NodeKind.RUN}, {NodeKind.EVIDENCE, NodeKind.ARTIFACT}),
    EdgeKind.DERIVED_FROM: (
        {NodeKind.EVIDENCE, NodeKind.CLAIM},
        {
            NodeKind.RUN,
            NodeKind.SOURCE,
            NodeKind.ARTIFACT,
            NodeKind.EVIDENCE,
        },
    ),
    EdgeKind.SUPPORTS: (
        {NodeKind.EVIDENCE},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.CHALLENGES: (
        {NodeKind.EVIDENCE},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.CONTRADICTS: (
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.ASSESSES: (
        {NodeKind.ASSESSMENT},
        {NodeKind.HYPOTHESIS, NodeKind.CLAIM},
    ),
    EdgeKind.BASED_ON: (
        {NodeKind.ASSESSMENT, NodeKind.DECISION},
        {NodeKind.EVIDENCE, NodeKind.ASSESSMENT, NodeKind.CLAIM},
    ),
}


def relation_is_allowed(
    source: NodeKind,
    edge: EdgeKind,
    target: NodeKind,
) -> bool:
    if edge is EdgeKind.RELATED_TO:
        return True
    if edge is EdgeKind.SUPERSEDES:
        return source is target
    sources, targets = _ALLOWED[edge]
    if edge is EdgeKind.DECOMPOSES:
        return source in sources and target in targets and source is target
    return source in sources and target in targets
