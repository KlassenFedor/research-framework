from __future__ import annotations

from pathlib import Path

from research_framework import Project
from research_framework.presentation import (
    render_edges,
    render_neighborhood,
    render_node,
    render_nodes,
    render_path,
)
from tests.conftest import NODE_IDS


def test_render_node_includes_identity_audit_data_and_markdown_body(
    example_project: Path,
) -> None:
    node = Project.open(example_project).snapshot().get_node(NODE_IDS["question"])

    rendered = render_node(node)

    assert f"ID:       {node.id}" in rendered
    assert "Question: Does increasing context" in rendered
    assert "Created:" in rendered
    assert f"Revision: {node.revision}" in rendered
    assert "Body:\n# Retrieval quality" in rendered


def test_render_nodes_keeps_headers_for_empty_results_and_lists_rows(
    example_project: Path,
) -> None:
    graph = Project.open(example_project).snapshot()

    empty = render_nodes(())
    listed = render_nodes((graph.get_node(NODE_IDS["hypothesis"]),))

    assert "ID  KIND  STATUS  TITLE" in empty
    assert NODE_IDS["hypothesis"] in listed
    assert "hypothesis" in listed


def test_render_edges_displays_optional_rationale_as_an_empty_cell(
    example_project: Path,
) -> None:
    graph = Project.open(example_project).snapshot()
    edge = next(
        edge for edge in graph.outgoing(NODE_IDS["run"]) if edge.rationale is None
    )

    rendered = render_edges((edge,))

    assert "ID" in rendered and "RATIONALE" in rendered
    assert edge.id in rendered
    assert edge.kind.value in rendered


def test_render_neighborhood_shows_both_directions_and_empty_state(
    example_project: Path,
) -> None:
    graph = Project.open(example_project).snapshot()
    center = graph.get_node(NODE_IDS["hypothesis"])
    edges = (*graph.outgoing(center.id), *graph.incoming(center.id))

    rendered = render_neighborhood(graph, center, edges)
    empty = render_neighborhood(
        graph,
        graph.get_node(NODE_IDS["question"]),
        (),
    )

    assert "→ addresses" in rendered
    assert "← tests" in rendered
    assert "(no adjacent relations)" in empty


def test_render_path_covers_found_empty_and_missing_paths(
    example_project: Path,
) -> None:
    graph = Project.open(example_project).snapshot()
    found = graph.find_path(NODE_IDS["run"], NODE_IDS["hypothesis"])

    rendered = render_path(graph, NODE_IDS["run"], found)
    empty = render_path(graph, NODE_IDS["question"], ())
    missing = render_path(graph, NODE_IDS["question"], None)

    assert "instance_of" in rendered
    assert NODE_IDS["hypothesis"] in rendered
    assert empty.startswith(NODE_IDS["question"])
    assert missing == f"No path from {NODE_IDS['question']}"
