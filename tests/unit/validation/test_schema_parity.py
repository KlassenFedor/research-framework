from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from research_framework import node_schema, project_schema
from research_framework.domain.errors import StorageError
from research_framework.storage.discovery import discover_project
from research_framework.storage.markdown_codec import MarkdownCodec
from research_framework.storage.yaml_codec import (
    dump_restricted_yaml,
    load_restricted_yaml,
)
from research_framework.validation import validate_project

Mutation = Callable[[dict[str, Any]], None]


def _schema_errors(schema: dict[str, Any], value: Any) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(value)]


def _mutate_node(root: Path, kind: str, mutation: Mutation) -> None:
    codec = MarkdownCodec()
    path = next(
        candidate
        for candidate in sorted((root / "research").rglob("*.md"))
        if candidate.name != "PROJECT.md"
        and codec.decode(
            candidate.read_text(encoding="utf-8"), path=candidate
        ).metadata["kind"]
        == kind
    )
    document = codec.decode(path.read_text(encoding="utf-8"), path=path)
    metadata = copy.deepcopy(dict(document.metadata))
    mutation(metadata)
    path.write_text(
        codec.encode(document.with_metadata(metadata)),
        encoding="utf-8",
    )
    assert _schema_errors(node_schema(), metadata)


def _set(field: str, value: Any) -> Mutation:
    def mutate(metadata: dict[str, Any]) -> None:
        metadata[field] = value

    return mutate


def _set_created_actor(field: str, value: Any) -> Mutation:
    def mutate(metadata: dict[str, Any]) -> None:
        metadata["created_by"][field] = value

    return mutate


def _set_first_relation(field: str, value: Any) -> Mutation:
    def mutate(metadata: dict[str, Any]) -> None:
        metadata["relations"][0][field] = value

    return mutate


@pytest.mark.contract
@pytest.mark.parametrize(
    ("kind", "mutation", "expected_code"),
    [
        ("question", _set("format_version", True), "unsupported_format_version"),
        ("question", _set("summary", None), "invalid_field_type"),
        ("question", _set("tags", None), "invalid_field_type"),
        ("question", _set("aliases", None), "invalid_field_type"),
        ("question", _set("extensions", None), "invalid_field_type"),
        ("question", _set("scope", 42), "invalid_field_type"),
        (
            "hypothesis",
            _set("assumptions", ["fixed benchmark", 42]),
            "invalid_field_type",
        ),
        ("hypothesis", _set("assumptions", None), "invalid_field_type"),
        ("claim", _set("statement", 42), "invalid_field_type"),
        ("experiment", _set("objective", 42), "invalid_field_type"),
        (
            "experiment",
            _set("protocol_version", True),
            "invalid_protocol_version",
        ),
        ("run", _set("environment", []), "invalid_field_type"),
        ("run", _set("environment", None), "invalid_field_type"),
        ("run", _set("finished_at", None), "invalid_field_type"),
        (
            "evidence",
            _set("collected_at", "2026-08-17T11:20:00"),
            "timezone_required",
        ),
        (
            "evidence",
            _set("collected_at", "2026-08-17T11:20:00+07"),
            "invalid_timestamp",
        ),
        ("evidence", _set("collected_at", None), "invalid_field_type"),
        (
            "assessment",
            _set("limitations", ["small sample", 42]),
            "invalid_field_type",
        ),
        ("assessment", _set("limitations", None), "invalid_field_type"),
        ("source", _set("citation", 42), "invalid_field_type"),
        ("source", _set("accessed_at", "2026-99-99"), "invalid_date"),
        ("source", _set("accessed_at", "20260817"), "invalid_date"),
        ("source", _set("accessed_at", None), "invalid_field_type"),
        ("artifact", _set("media_type", ""), "invalid_field_type"),
        ("artifact", _set("sha256", None), "invalid_sha256"),
        ("artifact", _set("size", None), "invalid_artifact_size"),
        ("decision", _set("rationale", 42), "invalid_field_type"),
        (
            "question",
            _set_created_actor("run_id", 42),
            "invalid_field_type",
        ),
        (
            "question",
            _set_created_actor("run_id", None),
            "invalid_field_type",
        ),
        ("question", _set_created_actor("extra", "value"), "unknown_field"),
        (
            "hypothesis",
            _set_first_relation("target", "not-a-node-id"),
            "invalid_relation_target",
        ),
        (
            "hypothesis",
            _set_first_relation("rationale", ""),
            "invalid_field_type",
        ),
        (
            "hypothesis",
            _set_first_relation("rationale", None),
            "invalid_field_type",
        ),
        (
            "hypothesis",
            _set_first_relation("extra", "value"),
            "unknown_field",
        ),
    ],
)
def test_runtime_validator_rejects_values_rejected_by_node_schema(
    example_project: Path,
    kind: str,
    mutation: Mutation,
    expected_code: str,
) -> None:
    _mutate_node(example_project, kind, mutation)

    codes = {diagnostic.code for diagnostic in validate_project(example_project)}

    assert expected_code in codes


@pytest.mark.contract
@pytest.mark.parametrize(
    ("field", "invalid", "message"),
    [
        ("project_id", "project-1", "project_id"),
        ("vault", "C:\\outside", "relative path"),
        ("vault", "\\\\server\\share", "relative path"),
    ],
)
def test_project_discovery_rejects_values_rejected_by_project_schema(
    example_project: Path,
    field: str,
    invalid: Any,
    message: str,
) -> None:
    config_path = example_project / "research.yaml"
    config = load_restricted_yaml(config_path.read_text(encoding="utf-8"))
    config[field] = invalid
    config_path.write_text(dump_restricted_yaml(config), encoding="utf-8")
    assert _schema_errors(project_schema(), config)

    with pytest.raises(StorageError, match=message):
        discover_project(example_project)
