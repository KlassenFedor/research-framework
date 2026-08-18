from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from research_framework import Project, StorageError
from research_framework.presentation.html_graph import (
    GraphView,
    GraphViewEdge,
    GraphViewNode,
    build_graph_view,
    compute_anchor_associations,
    render_graph_html,
    write_graph_html,
)
from tests.conftest import NODE_IDS, RELATION_IDS


def view_node(node_id: str, kind: str) -> GraphViewNode:
    return GraphViewNode(
        id=node_id,
        kind=kind,
        status="active",
        title=node_id,
        summary=None,
        tags=(),
        aliases=(),
        body="",
        details={},
    )


@pytest.mark.contract
def test_full_graph_view_is_deterministic_and_complete(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    first = build_graph_view(graph, title="Example graph")
    second = build_graph_view(graph, title="Example graph")
    payload = first.to_dict()

    assert first == second
    assert payload["title"] == "Example graph"
    assert payload["focus"] is None
    assert payload["depth"] is None
    assert len(payload["nodes"]) == 11
    assert len(payload["edges"]) == 14
    assert [node["id"] for node in payload["nodes"]] == sorted(
        node["id"] for node in payload["nodes"]
    )
    assert [edge["id"] for edge in payload["edges"]] == sorted(
        edge["id"] for edge in payload["edges"]
    )

    hypothesis = next(
        node for node in payload["nodes"] if node["id"] == NODE_IDS["hypothesis"]
    )
    assert hypothesis["kind"] == "hypothesis"
    assert hypothesis["status"] == "active"
    assert hypothesis["tags"] == ["retrieval", "context"]
    assert hypothesis["aliases"] == ["H-context"]
    assert hypothesis["summary"] == "Compare 32k context with an 8k baseline."
    assert "falsifiable threshold" in hypothesis["body"]
    assert hypothesis["details"]["statement"].startswith("A 32k context")
    assert "revision" not in hypothesis["details"]

    relation = next(
        edge for edge in payload["edges"] if edge["id"] == RELATION_IDS["supports"]
    )
    assert relation["kind"] == "supports"
    assert relation["source"] == NODE_IDS["evidence"]
    assert relation["target"] == NODE_IDS["hypothesis"]
    assert relation["rationale"] == "The observed improvement exceeds the threshold."


@pytest.mark.contract
def test_focused_graph_view_contains_induced_neighborhood(example_project) -> None:
    graph = Project.open(example_project).snapshot()

    view = build_graph_view(graph, title="Local graph", focus="H-context", depth=1)
    payload = view.to_dict()
    node_ids = {node["id"] for node in payload["nodes"]}

    assert payload["focus"] == NODE_IDS["hypothesis"]
    assert payload["depth"] == 1
    assert node_ids == {
        NODE_IDS["hypothesis"],
        NODE_IDS["question"],
        NODE_IDS["experiment"],
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
        NODE_IDS["assessment"],
    }
    assert payload["edges"]
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids
        for edge in payload["edges"]
    )
    assert {edge["kind"] for edge in payload["edges"]} >= {
        "addresses",
        "tests",
        "supports",
        "challenges",
        "assesses",
        "based_on",
    }


@pytest.mark.contract
def test_anchor_associations_follow_context_chains_and_stop_at_anchors(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()
    view = build_graph_view(graph, title="Example graph")

    associations = compute_anchor_associations(
        view,
        anchor_kinds={"hypothesis", "claim"},
    )

    assert associations[NODE_IDS["hypothesis"]] == (NODE_IDS["hypothesis"],)
    assert associations[NODE_IDS["claim"]] == (NODE_IDS["claim"],)
    assert associations[NODE_IDS["assessment"]] == (NODE_IDS["hypothesis"],)
    assert associations[NODE_IDS["run"]] == (NODE_IDS["hypothesis"],)
    assert associations[NODE_IDS["artifact"]] == (NODE_IDS["hypothesis"],)
    assert associations[NODE_IDS["source"]] == (NODE_IDS["hypothesis"],)
    assert associations[NODE_IDS["question"]] == tuple(
        sorted((NODE_IDS["hypothesis"], NODE_IDS["claim"]))
    )

    question_centered = compute_anchor_associations(
        view,
        anchor_kinds={"question"},
    )
    assert question_centered[NODE_IDS["assessment"]] == (NODE_IDS["question"],)


@pytest.mark.contract
def test_anchor_associations_support_multiple_anchors_unlinked_context_and_ignore_related_to() -> (
    None
):
    view = GraphView(
        title="Associations",
        focus=None,
        depth=None,
        nodes=(
            view_node("hyp-a", "hypothesis"),
            view_node("clm-b", "claim"),
            view_node("asm-shared", "assessment"),
            view_node("evd-child", "evidence"),
            view_node("src-weak", "source"),
            view_node("art-unlinked", "artifact"),
        ),
        edges=(
            GraphViewEdge("rel-a", "assesses", "asm-shared", "hyp-a", None),
            GraphViewEdge("rel-b", "based_on", "asm-shared", "clm-b", None),
            GraphViewEdge("rel-child", "derived_from", "evd-child", "asm-shared", None),
            GraphViewEdge("rel-weak", "related_to", "src-weak", "hyp-a", None),
        ),
    )

    associations = compute_anchor_associations(
        view,
        anchor_kinds={"hypothesis", "claim"},
    )

    expected = ("clm-b", "hyp-a")
    assert associations["asm-shared"] == expected
    assert associations["evd-child"] == expected
    assert associations["src-weak"] == ()
    assert associations["art-unlinked"] == ()


@pytest.mark.contract
def test_graph_view_rejects_depth_without_focus_and_negative_depth(
    example_project,
) -> None:
    graph = Project.open(example_project).snapshot()

    with pytest.raises(ValueError, match="requires focus"):
        build_graph_view(graph, title="Graph", depth=1)
    with pytest.raises(ValueError, match="must not be negative"):
        build_graph_view(graph, title="Graph", focus="H-context", depth=-1)
    with pytest.raises(ValueError, match="title must not be blank"):
        build_graph_view(graph, title="  ")


@pytest.mark.contract
def test_html_is_standalone_deterministic_and_embeds_safe_json(example_project) -> None:
    graph = Project.open(example_project).snapshot()
    view = build_graph_view(
        graph,
        title='Research </script><script>alert("title")</script>',
        focus="H-context",
        depth=1,
    )

    first = render_graph_html(view)
    second = render_graph_html(view)

    assert first == second
    assert first.startswith("<!doctype html>")
    assert '<script type="application/json" id="graph-data">' in first
    assert "<script src=" not in first
    assert '<link rel="stylesheet"' not in first
    assert "cytoscape" not in first.lower()
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert" in first
    assert "<title>Research &lt;/script&gt;&lt;script&gt;alert(" in first

    embedded = first.split('<script type="application/json" id="graph-data">', 1)[
        1
    ].split("</script>", 1)[0]
    payload = json.loads(embedded)
    assert payload == view.to_dict()


@pytest.mark.contract
def test_html_contains_interactive_graph_controls(example_project) -> None:
    graph = Project.open(example_project).snapshot()
    html = render_graph_html(build_graph_view(graph, title="Example graph"))

    for element_id in (
        "graph-canvas",
        "search",
        "kind-filters",
        "tag-picker",
        "tag-picker-summary",
        "tag-filters",
        "tag-match",
        "clear-tags",
        "visibility-mode",
        "anchor-picker",
        "anchor-picker-summary",
        "anchor-kind-filters",
        "show-unlinked",
        "relation-filter",
        "fit",
        "reset-layout",
        "details",
        "graph-data",
    ):
        assert f'id="{element_id}"' in html
    assert "localStorage" in html
    assert "requestAnimationFrame" in html
    assert "devicePixelRatio" in html
    assert "selectedTags" in html
    assert ".some(tag => node.tags.includes(tag))" in html
    assert ".every(tag => node.tags.includes(tag))" in html
    assert "tags: all" in html
    assert 'value="independent"' in html
    assert 'value="linked"' in html
    assert 'kind === "hypothesis" || kind === "claim"' in html
    assert "computeAnchorAssociations" in html
    assert 'edge.kind === "related_to"' in html
    assert "owners.some(ownerId => visibleAnchorIds.has(ownerId))" in html
    assert "showUnlinked.checked && matches" in html


@pytest.mark.contract
def test_hidden_nodes_remain_selectable_from_relation_details(example_project) -> None:
    graph = Project.open(example_project).snapshot()
    html = render_graph_html(build_graph_view(graph, title="Example graph"))

    assert (
        "if (selectedId && !byId.get(selectedId).visible) selectedId = null" not in html
    )
    assert "if (!node || !node.visible)" not in html
    assert "Hidden by current filters" in html
    assert 'button.addEventListener("click", () => selectNode(neighborId))' in html


@pytest.mark.contract
def test_write_graph_html_creates_parents_and_atomically_replaces_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "reports" / "graph.html"

    write_graph_html(target, "first")
    write_graph_html(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert list(target.parent.glob(".graph.html.*.tmp")) == []


@pytest.mark.contract
def test_write_graph_html_preserves_old_file_and_cleans_temp_on_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "graph.html"
    target.write_text("old", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(StorageError, match="simulated replace failure"):
        write_graph_html(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".graph.html.*.tmp")) == []
