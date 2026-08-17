from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import fields
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from research_framework import node_schema, project_schema
from research_framework.domain.enums import ActorKind, EdgeKind, NodeKind, NodeStatus
from research_framework.storage.discovery import ProjectPolicies
from research_framework.storage.markdown_codec import MarkdownCodec
from research_framework.storage.yaml_codec import load_restricted_yaml


def _node_documents(root: Path) -> list[dict[str, Any]]:
    codec = MarkdownCodec()
    documents: list[dict[str, Any]] = []
    for path in sorted((root / "research").rglob("*.md")):
        if path.name == "PROJECT.md":
            continue
        document = codec.decode(path.read_text(encoding="utf-8"), path=path)
        documents.append(dict(document.metadata))
    return documents


def _node_by_kind(root: Path, kind: str) -> dict[str, Any]:
    return next(item for item in _node_documents(root) if item["kind"] == kind)


def _errors(schema: dict[str, Any], value: Any) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(value)]


@pytest.mark.contract
def test_public_schemas_are_valid_draft_2020_12_package_resources() -> None:
    nodes = node_schema()
    project = project_schema()

    Draft202012Validator.check_schema(nodes)
    Draft202012Validator.check_schema(project)
    assert nodes["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert project["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert nodes["$id"] == "urn:research-framework:schema:node:1"
    assert project["$id"] == "urn:research-framework:schema:project:1"

    package = resources.files("research_framework.schemas")
    assert package.joinpath("node-v1.schema.json").is_file()
    assert package.joinpath("project-v1.schema.json").is_file()


@pytest.mark.contract
def test_schema_api_returns_independent_values() -> None:
    changed = node_schema()
    changed["title"] = "caller mutation"

    assert node_schema()["title"] == "Research Framework node front matter v1"


@pytest.mark.contract
def test_schema_enums_and_policy_names_match_python_contract() -> None:
    definitions = node_schema()["$defs"]
    common = definitions["common"]["properties"]
    relation = definitions["relation"]["properties"]
    actor = definitions["actor"]["properties"]
    policies = project_schema()["properties"]["policies"]["properties"]

    assert common["kind"]["enum"] == [kind.value for kind in NodeKind]
    assert common["status"]["enum"] == [status.value for status in NodeStatus]
    assert relation["kind"]["enum"] == [kind.value for kind in EdgeKind]
    assert actor["kind"]["enum"] == [kind.value for kind in ActorKind]
    assert set(policies) == {field.name for field in fields(ProjectPolicies)}


@pytest.mark.contract
def test_example_project_and_every_node_kind_match_published_schemas(
    example_project: Path,
) -> None:
    nodes = _node_documents(example_project)
    config = load_restricted_yaml(
        (example_project / "research.yaml").read_text(encoding="utf-8")
    )

    assert len(nodes) == 11
    assert {node["kind"] for node in nodes} == {
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
    assert all(not _errors(node_schema(), node) for node in nodes)
    assert _errors(project_schema(), config) == []


def _remove_statement(value: dict[str, Any]) -> None:
    value.pop("statement")


def _mismatch_id_prefix(value: dict[str, Any]) -> None:
    value["id"] = "que-01J00000000000000000000003"


def _add_unknown_field(value: dict[str, Any]) -> None:
    value["statment"] = value["statement"]


@pytest.mark.contract
@pytest.mark.parametrize(
    "mutate",
    [_remove_statement, _mismatch_id_prefix, _add_unknown_field],
    ids=["required-kind-field", "id-kind-prefix", "unknown-top-level-field"],
)
def test_node_schema_rejects_kind_and_top_level_structural_errors(
    example_project: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    metadata = copy.deepcopy(_node_by_kind(example_project, "claim"))
    mutate(metadata)

    assert _errors(node_schema(), metadata)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("kind", "field", "invalid"),
    [
        ("question", "tags", ["retrieval", 42]),
        ("question", "aliases", ["Q-context", "Q-context"]),
        ("experiment", "protocol_version", True),
        ("run", "outcome", "succeeded"),
        ("evidence", "collected_at", "2026-08-17T10:00:00"),
        ("assessment", "confidence", "certain"),
        ("source", "source_kind", "social-media"),
        ("artifact", "sha256", "not-a-sha256"),
        ("artifact", "size", -1),
    ],
)
def test_node_schema_rejects_invalid_common_and_kind_specific_values(
    example_project: Path,
    kind: str,
    field: str,
    invalid: Any,
) -> None:
    metadata = copy.deepcopy(_node_by_kind(example_project, kind))
    metadata[field] = invalid

    assert _errors(node_schema(), metadata)


@pytest.mark.contract
def test_node_schema_checks_nested_relation_and_actor_shapes(
    example_project: Path,
) -> None:
    evidence = _node_by_kind(example_project, "evidence")
    invalid_edge = copy.deepcopy(evidence)
    invalid_edge["relations"][0]["id"] = "edge-not-ulid"
    invalid_actor = copy.deepcopy(evidence)
    invalid_actor["created_by"] = {"kind": "robot", "id": "agent"}

    assert _errors(node_schema(), invalid_edge)
    assert _errors(node_schema(), invalid_actor)


@pytest.mark.contract
def test_node_schema_does_not_claim_to_validate_graph_semantics(
    example_project: Path,
) -> None:
    hypothesis = copy.deepcopy(_node_by_kind(example_project, "hypothesis"))
    target = hypothesis["relations"][0]["target"]
    hypothesis["relations"][0]["target"] = f"{target[:-1]}Z"

    assert _errors(node_schema(), hypothesis) == []


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("format_version", 2),
        ("project_id", "project-1"),
        ("title", ""),
        ("vault", "/absolute/vault"),
        ("default_language", ""),
        ("policies", {"require_evidence_provenance": "yes"}),
    ],
)
def test_project_schema_rejects_invalid_configuration_values(
    example_project: Path,
    field: str,
    invalid: Any,
) -> None:
    config = load_restricted_yaml(
        (example_project / "research.yaml").read_text(encoding="utf-8")
    )
    config[field] = invalid

    assert _errors(project_schema(), config)
