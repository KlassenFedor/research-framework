from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_framework import Actor, EdgeKind, HypothesisDraft, Project, QuestionDraft
from tests.cli.test_cli import json_stdout, run_cli


@pytest.mark.contract
@pytest.mark.integration
def test_init_create_link_reopen_traverse_validate_and_export(tmp_path: Path) -> None:
    project = Project.init(tmp_path / "study", title="End-to-end study")
    actor = Actor.human("researcher")
    question = project.create_node(
        QuestionDraft(
            title="Does the intervention work?",
            question="Does the intervention improve recall?",
            tags={"retrieval"},
        ),
        actor=actor,
    )
    hypothesis = project.create_node(
        HypothesisDraft(
            title="The intervention improves recall",
            statement="The intervention improves recall by at least 10%.",
            falsification_criteria="Recall improves by less than 10%.",
            tags={"retrieval"},
        ),
        actor=actor,
    )
    edge = project.add_edge(
        source=hypothesis.id,
        kind=EdgeKind.ADDRESSES,
        target=question.id,
        actor=actor,
    )

    reopened = Project.open(project.root)
    graph = reopened.snapshot()
    traversed = graph.traverse(hypothesis.id, depth=1, direction="outgoing")
    exported = json.loads(graph.export_json())

    assert reopened.validate() == ()
    assert [node.id for node in traversed] == [question.id]
    assert graph.get_edge(edge.id).target == question.id
    assert {node["id"] for node in exported["nodes"]} == {
        question.id,
        hypothesis.id,
    }


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.cli
def test_cli_and_python_api_return_same_graph_data(example_project: Path) -> None:
    python_payload = json.loads(Project.open(example_project).snapshot().export_json())

    cli_result = run_cli(example_project, "graph", "export", "--format", "json")
    cli_payload = json.loads(cli_result.stdout)

    assert cli_result.returncode == 0
    assert cli_payload == python_payload


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.cli
def test_cli_mutation_is_immediately_visible_to_python_api(
    example_project: Path,
) -> None:
    request = {
        "title": "Created by CLI",
        "statement": "CLI and API share the application layer.",
        "actor": {"kind": "human", "id": "researcher"},
    }

    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )
    payload = json_stdout(result)
    loaded = Project.open(example_project).snapshot().get_node(payload["data"]["id"])

    assert result.returncode == 0
    assert loaded.statement == request["statement"]
