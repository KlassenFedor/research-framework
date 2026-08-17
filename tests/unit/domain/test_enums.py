from __future__ import annotations

import pytest

from research_framework import EdgeKind, NodeKind, NodeStatus


@pytest.mark.contract
def test_mvp_node_kinds_are_fixed() -> None:
    assert {kind.value for kind in NodeKind} == {
        "question",
        "hypothesis",
        "claim",
        "experiment",
        "run",
        "evidence",
        "assessment",
        "source",
        "artifact",
        "decision",
    }


@pytest.mark.contract
def test_node_lifecycle_is_separate_from_epistemic_verdict() -> None:
    assert [status.value for status in NodeStatus] == [
        "draft",
        "active",
        "closed",
        "archived",
    ]
    assert "supported" not in {status.value for status in NodeStatus}


@pytest.mark.contract
def test_mvp_edge_kinds_are_fixed() -> None:
    assert {kind.value for kind in EdgeKind} == {
        "addresses",
        "decomposes",
        "depends_on",
        "tests",
        "instance_of",
        "produces",
        "derived_from",
        "supports",
        "challenges",
        "contradicts",
        "assesses",
        "based_on",
        "supersedes",
        "related_to",
    }
