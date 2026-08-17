from __future__ import annotations

import pytest

from research_framework import EdgeKind, NodeKind
from research_framework.domain.edges import relation_is_allowed

ALLOWED = [
    ("hypothesis", "addresses", "question"),
    ("claim", "addresses", "question"),
    ("question", "decomposes", "question"),
    ("hypothesis", "decomposes", "hypothesis"),
    ("hypothesis", "depends_on", "claim"),
    ("claim", "depends_on", "hypothesis"),
    ("experiment", "depends_on", "claim"),
    ("experiment", "tests", "hypothesis"),
    ("experiment", "tests", "claim"),
    ("run", "instance_of", "experiment"),
    ("run", "produces", "evidence"),
    ("run", "produces", "artifact"),
    ("evidence", "derived_from", "run"),
    ("evidence", "derived_from", "source"),
    ("evidence", "derived_from", "artifact"),
    ("evidence", "derived_from", "evidence"),
    ("claim", "derived_from", "source"),
    ("evidence", "supports", "hypothesis"),
    ("evidence", "supports", "claim"),
    ("evidence", "challenges", "hypothesis"),
    ("evidence", "challenges", "claim"),
    ("hypothesis", "contradicts", "claim"),
    ("claim", "contradicts", "hypothesis"),
    ("assessment", "assesses", "hypothesis"),
    ("assessment", "assesses", "claim"),
    ("assessment", "based_on", "evidence"),
    ("assessment", "based_on", "assessment"),
    ("assessment", "based_on", "claim"),
    ("decision", "based_on", "evidence"),
    ("decision", "based_on", "assessment"),
    ("decision", "based_on", "claim"),
    ("source", "supersedes", "source"),
    ("artifact", "related_to", "question"),
]


@pytest.mark.contract
@pytest.mark.parametrize(("source", "edge", "target"), ALLOWED)
def test_allowed_relation_matrix(source: str, edge: str, target: str) -> None:
    assert relation_is_allowed(NodeKind(source), EdgeKind(edge), NodeKind(target))


@pytest.mark.contract
@pytest.mark.parametrize(
    ("source", "edge", "target"),
    [
        ("question", "supports", "hypothesis"),
        ("hypothesis", "tests", "claim"),
        ("evidence", "produces", "artifact"),
        ("run", "instance_of", "claim"),
        ("assessment", "assesses", "evidence"),
        ("source", "supersedes", "artifact"),
    ],
)
def test_disallowed_relation_matrix(source: str, edge: str, target: str) -> None:
    assert not relation_is_allowed(NodeKind(source), EdgeKind(edge), NodeKind(target))


@pytest.mark.contract
@pytest.mark.parametrize("kind", list(NodeKind))
def test_related_to_is_escape_hatch_for_every_node_kind(kind: NodeKind) -> None:
    for target in NodeKind:
        assert relation_is_allowed(kind, EdgeKind.RELATED_TO, target)


@pytest.mark.contract
@pytest.mark.parametrize("kind", list(NodeKind))
def test_supersedes_requires_matching_kinds(kind: NodeKind) -> None:
    for target in NodeKind:
        assert relation_is_allowed(kind, EdgeKind.SUPERSEDES, target) is (
            kind is target
        )
