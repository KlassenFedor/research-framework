from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_framework import (
    AmbiguousReference,
    EdgeKind,
    NodeKind,
    NodeNotFound,
    Project,
)
from tests.conftest import NODE_IDS, RELATION_IDS


@pytest.mark.contract
def test_snapshot_resolves_exact_id_alias_and_unambiguous_prefix(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()

    exact = graph.get_node(NODE_IDS["hypothesis"])
    alias = graph.get_node("H-context")
    prefix = graph.get_node("hyp-01J000")

    assert exact is alias is prefix


@pytest.mark.contract
def test_snapshot_reports_ambiguous_prefix_with_candidates(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    with pytest.raises(AmbiguousReference) as raised:
        graph.get_node("evd-01J000")

    assert set(raised.value.candidates) == {
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
    }


@pytest.mark.contract
def test_snapshot_reports_missing_reference(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    with pytest.raises(NodeNotFound) as raised:
        graph.get_node("hyp-missing")

    assert raised.value.reference == "hyp-missing"


@pytest.mark.contract
def test_get_edge_uses_global_relation_id(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    edge = graph.get_edge(RELATION_IDS["supports"])

    assert edge.source == NODE_IDS["evidence"]
    assert edge.target == NODE_IDS["hypothesis"]
    assert edge.kind is EdgeKind.SUPPORTS


@pytest.mark.contract
def test_list_nodes_filters_by_kind_status_and_all_requested_tags(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()

    assert [node.id for node in graph.list_nodes(kind=NodeKind.HYPOTHESIS)] == [
        NODE_IDS["hypothesis"]
    ]
    assert {node.id for node in graph.list_nodes(status="closed")} == {
        NODE_IDS["run"],
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
        NODE_IDS["assessment"],
    }
    assert [node.id for node in graph.list_nodes(tags={"retrieval", "context"})] == [
        NODE_IDS["hypothesis"]
    ]


@pytest.mark.contract
def test_public_collections_are_deterministically_sorted(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    nodes = graph.list_nodes()
    assert list(nodes) == sorted(nodes, key=lambda node: (node.created_at, node.id))

    edges = graph.outgoing(NODE_IDS["run"])
    assert list(edges) == sorted(edges, key=lambda edge: edge.id)


@pytest.mark.contract
def test_outgoing_and_incoming_indexes_do_not_write_backlinks(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    outgoing = graph.outgoing(NODE_IDS["evidence"])
    incoming = graph.incoming(NODE_IDS["hypothesis"])

    assert {edge.kind for edge in outgoing} == {
        EdgeKind.DERIVED_FROM,
        EdgeKind.SUPPORTS,
    }
    assert {edge.kind for edge in incoming} == {
        EdgeKind.TESTS,
        EdgeKind.SUPPORTS,
        EdgeKind.CHALLENGES,
        EdgeKind.ASSESSES,
    }


@pytest.mark.contract
def test_edge_queries_can_be_filtered_by_kind(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    incoming = graph.incoming(
        NODE_IDS["hypothesis"],
        kinds={EdgeKind.SUPPORTS, EdgeKind.CHALLENGES},
    )

    assert {edge.source for edge in incoming} == {
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
    }


@pytest.mark.contract
def test_neighbors_returns_nodes_in_both_directions_without_duplicates(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()

    neighbors = graph.neighbors(NODE_IDS["hypothesis"])

    assert {node.id for node in neighbors} == {
        NODE_IDS["question"],
        NODE_IDS["experiment"],
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
        NODE_IDS["assessment"],
    }


@pytest.mark.contract
def test_symmetric_relation_is_read_from_either_endpoint_but_stored_once(
    example_project: Path,
) -> None:
    question_path = next((example_project / "research" / "questions").glob("*.md"))
    text = question_path.read_text(encoding="utf-8").replace(
        "relations: []",
        f"""relations:
  - id: rel-01J0000000000000000000000X
    kind: related_to
    target: {NODE_IDS["source"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )
    question_path.write_text(text, encoding="utf-8")
    graph = Project.open(example_project).snapshot()

    assert [
        node.id
        for node in graph.neighbors(NODE_IDS["source"], kinds={EdgeKind.RELATED_TO})
    ] == [NODE_IDS["question"]]
    exported = json.loads(graph.export_json())
    assert sum(edge["kind"] == "related_to" for edge in exported["edges"]) == 1


@pytest.mark.contract
def test_breadth_first_traversal_honors_depth_and_direction(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    assert graph.traverse(NODE_IDS["hypothesis"], depth=0) == ()
    depth_one = graph.traverse(NODE_IDS["hypothesis"], depth=1, direction="incoming")

    assert {node.id for node in depth_one} == {
        NODE_IDS["experiment"],
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
        NODE_IDS["assessment"],
    }


@pytest.mark.contract
def test_find_path_returns_ordered_edges_for_shortest_directed_path(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()

    path = graph.find_path(NODE_IDS["run"], NODE_IDS["hypothesis"])

    assert path is not None
    assert [edge.kind for edge in path] == [EdgeKind.INSTANCE_OF, EdgeKind.TESTS]
    assert path[0].source == NODE_IDS["run"]
    assert path[-1].target == NODE_IDS["hypothesis"]
    assert graph.find_path(NODE_IDS["question"], NODE_IDS["run"]) is None


@pytest.mark.contract
def test_find_path_honors_kind_filter_and_max_depth(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    assert (
        graph.find_path(
            NODE_IDS["run"],
            NODE_IDS["hypothesis"],
            kinds={EdgeKind.INSTANCE_OF, EdgeKind.TESTS},
            max_depth=2,
        )
        is not None
    )
    assert graph.find_path(NODE_IDS["run"], NODE_IDS["hypothesis"], max_depth=1) is None


@pytest.mark.contract
def test_snapshot_and_loaded_nodes_are_immutable(example_project) -> None:
    graph = Project.open(example_project).snapshot()
    node = graph.get_node(NODE_IDS["hypothesis"])

    with pytest.raises((AttributeError, TypeError)):
        node.title = "Mutated only in memory"  # type: ignore[misc]


@pytest.mark.contract
def test_loaded_node_exposes_source_revision_without_serializing_it(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()
    node = graph.get_node(NODE_IDS["hypothesis"])

    assert len(node.revision) == 64
    assert set(node.revision) <= set("0123456789abcdef")
    assert "revision:" not in node.path.read_text(encoding="utf-8")


@pytest.mark.contract
def test_export_json_is_stable_and_contains_complete_graph(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    first = graph.export_json()
    second = graph.export_json()
    payload = json.loads(first)

    assert first == second
    assert len(payload["nodes"]) == 11
    assert len(payload["edges"]) == 14
    assert [node["id"] for node in payload["nodes"]] == sorted(
        node["id"] for node in payload["nodes"]
    )
    assert [edge["id"] for edge in payload["edges"]] == sorted(
        edge["id"] for edge in payload["edges"]
    )
    assert all("revision" not in node for node in payload["nodes"])
