from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.conftest import NODE_IDS, RELATION_IDS


def run_cli(
    cwd: Path,
    *arguments: str,
    input_text: str | None = None,
    environment_overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).parents[2]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(root / "src"), existing_pythonpath])
    )
    environment["NO_COLOR"] = "1"
    environment.update(environment_overrides or {})
    return subprocess.run(
        [sys.executable, "-m", "research_framework", *arguments],
        cwd=cwd,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def json_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    assert "\x1b[" not in result.stdout
    return json.loads(result.stdout)


def archive_fixture_node(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert "status: active" in source
    path.write_text(
        source.replace("status: active", "status: archived", 1), encoding="utf-8"
    )


@pytest.mark.contract
@pytest.mark.cli
def test_root_help_lists_stable_mvp_command_groups(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "--help")

    assert result.returncode == 0
    for command in ("init", "node", "link", "graph", "validate", "format"):
        assert command in result.stdout


@pytest.mark.contract
@pytest.mark.cli
def test_validate_clean_project_in_human_mode(example_project: Path) -> None:
    result = run_cli(example_project, "validate")

    assert result.returncode == 0
    assert "valid" in result.stdout.lower()
    assert result.stderr == ""


@pytest.mark.contract
@pytest.mark.cli
def test_validate_json_mode_emits_exactly_one_json_document(
    example_project: Path,
) -> None:
    result = run_cli(example_project, "validate", "--json")

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload == {"ok": True, "data": {"diagnostics": []}, "warnings": []}
    assert result.stderr == ""


@pytest.mark.contract
@pytest.mark.cli
def test_validate_reports_structured_diagnostic_and_exit_three(
    example_project: Path,
) -> None:
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    hypothesis.write_text(
        hypothesis.read_text(encoding="utf-8").replace(
            NODE_IDS["question"], "que-01J00000000000000000ZZZZZZ"
        ),
        encoding="utf-8",
    )

    result = run_cli(example_project, "validate", "--json")

    payload = json_stdout(result)
    assert result.returncode == 3
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_failed"
    assert payload["error"]["details"]["diagnostics"][0]["code"] == (
        "dangling_relation"
    )


@pytest.mark.contract
@pytest.mark.cli
def test_node_show_resolves_prefix_in_json_mode(example_project: Path) -> None:
    result = run_cli(example_project, "node", "show", "hyp-01J000", "--json")

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["data"]["id"] == NODE_IDS["hypothesis"]
    assert payload["data"]["kind"] == "hypothesis"
    assert "A larger context improves recall" in payload["data"]["body"]


@pytest.mark.contract
@pytest.mark.cli
def test_node_list_applies_multiple_filters(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "node",
        "list",
        "--kind",
        "hypothesis",
        "--status",
        "active",
        "--tag",
        "retrieval",
        "--tag",
        "context",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert [item["id"] for item in payload["data"]] == [NODE_IDS["hypothesis"]]


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_accepts_noninteractive_json_from_stdin(
    example_project: Path,
) -> None:
    request = {
        "title": "Replication improves confidence",
        "statement": "Consistent replications improve confidence.",
        "tags": ["replication"],
        "actor": {"kind": "agent", "id": "claim-writer", "run_id": "run-42"},
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
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["data"]["id"].startswith("clm-")
    assert payload["data"]["created_by"]["id"] == "claim-writer"


@pytest.mark.contract
@pytest.mark.cli
@pytest.mark.parametrize(
    ("kind", "invalid", "message"),
    [
        ("claim", {"summmary": "must not disappear"}, "unknown claim field"),
        ("claim", {"tags": "abc"}, "tags must be a list"),
        ("claim", {"aliases": "C-main"}, "aliases must be a list"),
        ("claim", {"body": 42}, "body must be a string"),
        (
            "claim",
            {"actor": {"kind": "human", "id": 42}},
            "actor.id must be a non-blank string",
        ),
        (
            "claim",
            {"actor": {"kind": "agent", "id": "writer", "run_id": None}},
            "actor.run_id must be a non-blank string",
        ),
        (
            "claim",
            {"actor": {"kind": "human", "id": "writer", "run_id": "run-42"}},
            "actor.run_id is only valid for agents",
        ),
        (
            "claim",
            {"actor": {"kind": "human", "id": "writer", "extra": "ignored"}},
            "unknown actor field",
        ),
        ("claim", {"initial_relations": None}, "initial_relations must be a list"),
        (
            "claim",
            {
                "initial_relations": [
                    {
                        "kind": "related_to",
                        "target": NODE_IDS["claim"],
                        "rationale": None,
                    }
                ]
            },
            "rationale must be a non-blank string",
        ),
        (
            "hypothesis",
            {"assumptions": "fixed benchmark"},
            "assumptions must be a list",
        ),
        ("assessment", {"limitations": "small sample"}, "limitations must be a list"),
        ("run", {"environment": []}, "environment must be an object"),
        ("experiment", {"protocol_version": True}, "protocol_version must be"),
        ("artifact", {"size": True}, "size must be an integer"),
    ],
)
def test_node_create_json_rejects_unknown_fields_and_wrong_types_without_writing(
    example_project: Path,
    kind: str,
    invalid: dict[str, object],
    message: str,
) -> None:
    valid_by_kind: dict[str, dict[str, object]] = {
        "claim": {"statement": "Strict input preserves every field."},
        "hypothesis": {
            "statement": "Strict input prevents coercion.",
            "falsification_criteria": "A malformed request is accepted.",
        },
        "assessment": {
            "verdict": "supported",
            "confidence": "high",
            "review_state": "approved",
        },
        "run": {
            "started_at": "2026-08-18T10:00:00+07:00",
            "outcome": "running",
        },
        "experiment": {
            "objective": "Reject coercion.",
            "method": "Submit malformed JSON.",
            "success_criteria": "The request fails.",
            "protocol_version": 1,
        },
        "artifact": {"locator": "artifacts/result.json"},
    }
    request = {
        "title": "Strict JSON input",
        **valid_by_kind[kind],
        "actor": {"kind": "human", "id": "creator"},
        **invalid,
    }
    before = set((example_project / "research").rglob("*.md"))

    result = run_cli(
        example_project,
        "node",
        "create",
        kind,
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert message in payload["error"]["message"]
    assert set((example_project / "research").rglob("*.md")) == before


@pytest.mark.contract
@pytest.mark.cli
@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ({"extra": "ignored"}, "unknown node update field"),
        ({"patch": []}, "patch must be an object"),
        ({"expected_revision": 42}, "expected_revision must be a non-blank string"),
        (
            {"actor": {"kind": "human", "id": 42}},
            "actor.id must be a non-blank string",
        ),
    ],
)
def test_node_update_json_rejects_invalid_envelope_without_writing(
    example_project: Path,
    invalid: dict[str, object],
    message: str,
) -> None:
    claim = next((example_project / "research" / "claims").glob("*.md"))
    before = claim.read_bytes()
    shown = run_cli(example_project, "node", "show", NODE_IDS["claim"], "--json")
    request = {
        "patch": {"summary": "Valid update"},
        "expected_revision": json_stdout(shown)["data"]["revision"],
        "actor": {"kind": "human", "id": "reviewer"},
        **invalid,
    }

    result = run_cli(
        example_project,
        "node",
        "update",
        NODE_IDS["claim"],
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert message in payload["error"]["message"]
    assert claim.read_bytes() == before


@pytest.mark.contract
@pytest.mark.cli
@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ({"extra": "ignored"}, "unknown link add field"),
        ({"source": 42}, "source must be a non-blank string"),
        ({"rationale": None}, "rationale must be a non-blank string"),
        (
            {"actor": {"kind": "human", "id": 42}},
            "actor.id must be a non-blank string",
        ),
    ],
)
def test_link_add_json_rejects_invalid_envelope_without_writing(
    example_project: Path,
    invalid: dict[str, object],
    message: str,
) -> None:
    evidence = next((example_project / "research" / "evidence").glob("*.md"))
    before = evidence.read_bytes()
    request = {
        "source": NODE_IDS["evidence"],
        "kind": "supports",
        "target": NODE_IDS["claim"],
        "rationale": "The measurement supports the claim.",
        "actor": {"kind": "human", "id": "reviewer"},
        **invalid,
    }

    result = run_cli(
        example_project,
        "link",
        "add",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert message in payload["error"]["message"]
    assert evidence.read_bytes() == before


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_accepts_initial_relations_from_json(
    example_project: Path,
) -> None:
    request = {
        "title": "Atomic benchmark run",
        "started_at": "2026-08-17T12:00:00+07:00",
        "outcome": "running",
        "initial_relations": [
            {
                "kind": "instance_of",
                "target": NODE_IDS["experiment"],
                "rationale": "Uses the benchmark protocol.",
            }
        ],
        "actor": {"kind": "agent", "id": "runner", "run_id": "run-42"},
    }

    created = run_cli(
        example_project,
        "node",
        "create",
        "run",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )
    payload = json_stdout(created)
    listed = run_cli(
        example_project,
        "link",
        "list",
        payload["data"]["id"],
        "--direction",
        "outgoing",
        "--json",
    )

    assert created.returncode == listed.returncode == 0
    assert json_stdout(listed)["data"] == [
        {
            "id": json_stdout(listed)["data"][0]["id"],
            "kind": "instance_of",
            "source": payload["data"]["id"],
            "target": NODE_IDS["experiment"],
            "created_at": payload["data"]["created_at"],
            "created_by": {"kind": "agent", "id": "runner", "run_id": "run-42"},
            "rationale": "Uses the benchmark protocol.",
        }
    ]


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_required_relation_failure_leaves_no_file(
    example_project: Path,
) -> None:
    before = set((example_project / "research" / "runs").glob("*.md"))
    request = {
        "title": "Disconnected run",
        "started_at": "2026-08-17T12:00:00+07:00",
        "outcome": "running",
        "actor": {"kind": "human", "id": "creator"},
    }

    result = run_cli(
        example_project,
        "node",
        "create",
        "run",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    assert result.returncode == 3
    assert json_stdout(result)["error"]["code"] == "validation_failed"
    assert set((example_project / "research" / "runs").glob("*.md")) == before


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_accepts_required_relation_flags(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "node",
        "create",
        "run",
        "--title",
        "Flag-created run",
        "--started-at",
        "2026-08-17T12:00:00+07:00",
        "--outcome",
        "running",
        "--instance-of",
        NODE_IDS["experiment"],
        "--actor",
        "runner",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    node = next(
        path
        for path in (example_project / "research" / "runs").glob("*.md")
        if payload["data"]["id"] in path.name
    )
    text = node.read_text(encoding="utf-8")
    assert "kind: instance_of" in text
    assert f"target: {NODE_IDS['experiment']}" in text


@pytest.mark.contract
@pytest.mark.cli
@pytest.mark.parametrize(
    "initial_relations",
    [
        {"kind": "instance_of", "target": NODE_IDS["experiment"]},
        [{"kind": "unknown", "target": NODE_IDS["experiment"]}],
        [{"kind": "instance_of"}],
        [
            {
                "id": "rel-01J000000000000000000ZZZZZ",
                "kind": "instance_of",
                "target": NODE_IDS["experiment"],
            }
        ],
    ],
)
def test_node_create_rejects_malformed_initial_relations(
    example_project: Path,
    initial_relations: object,
) -> None:
    before = set((example_project / "research" / "runs").glob("*.md"))
    request = {
        "title": "Malformed relation run",
        "started_at": "2026-08-17T12:00:00+07:00",
        "outcome": "running",
        "initial_relations": initial_relations,
        "actor": {"kind": "human", "id": "creator"},
    }

    result = run_cli(
        example_project,
        "node",
        "create",
        "run",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    assert result.returncode == 2
    assert json_stdout(result)["error"]["code"] == "invalid_arguments"
    assert set((example_project / "research" / "runs").glob("*.md")) == before


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_accepts_documented_human_oriented_flags(
    example_project: Path,
) -> None:
    result = run_cli(
        example_project,
        "node",
        "create",
        "hypothesis",
        "--title",
        "Replication confirms recall",
        "--statement",
        "Three replications improve recall by at least 10%.",
        "--falsification-criteria",
        "Median improvement is below 10%.",
        "--tag",
        "replication",
        "--actor",
        "fedor",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["data"]["kind"] == "hypothesis"
    assert payload["data"]["tags"] == ["replication"]


@pytest.mark.contract
@pytest.mark.cli
def test_json_mode_never_prompts_for_missing_input(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--json",
        input_text="",
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_arguments"
    assert "Title" not in result.stderr


@pytest.mark.contract
@pytest.mark.cli
def test_node_update_and_archive_cover_full_lifecycle(example_project: Path) -> None:
    shown = run_cli(
        example_project,
        "node",
        "show",
        NODE_IDS["claim"],
        "--json",
    )
    revision = json_stdout(shown)["data"]["revision"]
    update_request = {
        "patch": {"summary": "Updated through CLI"},
        "expected_revision": revision,
        "actor": {"kind": "human", "id": "reviewer"},
    }

    updated = run_cli(
        example_project,
        "node",
        "update",
        NODE_IDS["claim"],
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(update_request),
    )
    updated_payload = json_stdout(updated)
    archived = run_cli(
        example_project,
        "node",
        "archive",
        NODE_IDS["claim"],
        "--expected-revision",
        updated_payload["data"]["revision"],
        "--actor",
        "reviewer",
        "--json",
    )

    assert updated.returncode == archived.returncode == 0
    assert updated_payload["data"]["summary"] == "Updated through CLI"
    assert json_stdout(archived)["data"]["status"] == "archived"


@pytest.mark.contract
@pytest.mark.cli
def test_node_archive_json_returns_incoming_relation_warning(
    example_project: Path,
) -> None:
    shown = run_cli(
        example_project,
        "node",
        "show",
        NODE_IDS["hypothesis"],
        "--json",
    )

    result = run_cli(
        example_project,
        "node",
        "archive",
        NODE_IDS["hypothesis"],
        "--expected-revision",
        json_stdout(shown)["data"]["revision"],
        "--actor",
        "archivist",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["data"]["status"] == "archived"
    assert any(
        warning["code"] == "archived_target" and warning["details"] == {}
        for warning in payload["warnings"]
    )


@pytest.mark.contract
@pytest.mark.cli
def test_cli_revision_conflict_uses_exit_code_five(example_project: Path) -> None:
    shown = run_cli(
        example_project,
        "node",
        "show",
        NODE_IDS["claim"],
        "--json",
    )
    revision = json_stdout(shown)["data"]["revision"]
    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8") + "\nExternal edit.\n",
        encoding="utf-8",
    )
    request = {
        "patch": {"summary": "Stale write"},
        "expected_revision": revision,
        "actor": {"kind": "human", "id": "reviewer"},
    }

    result = run_cli(
        example_project,
        "node",
        "update",
        NODE_IDS["claim"],
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    assert result.returncode == 5
    assert json_stdout(result)["error"]["code"] == "revision_conflict"


@pytest.mark.contract
@pytest.mark.cli
def test_node_update_semantic_failure_does_not_change_file(
    example_project: Path,
) -> None:
    run = next((example_project / "research" / "runs").glob("*.md"))
    before = run.read_bytes()
    shown = run_cli(example_project, "node", "show", NODE_IDS["run"], "--json")
    request = {
        "patch": {"outcome": "succeeded"},
        "expected_revision": json_stdout(shown)["data"]["revision"],
        "actor": {"kind": "human", "id": "editor"},
    }

    result = run_cli(
        example_project,
        "node",
        "update",
        NODE_IDS["run"],
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    assert result.returncode == 3
    assert json_stdout(result)["error"]["code"] == "validation_failed"
    assert run.read_bytes() == before


@pytest.mark.contract
@pytest.mark.cli
def test_link_add_from_json_and_list_incoming_relation(example_project: Path) -> None:
    request = {
        "source": NODE_IDS["evidence"],
        "kind": "supports",
        "target": NODE_IDS["claim"],
        "rationale": "The measurement supports the cost claim.",
        "actor": {"kind": "human", "id": "reviewer"},
    }

    created = run_cli(
        example_project,
        "link",
        "add",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )
    created_payload = json_stdout(created)
    listed = run_cli(
        example_project,
        "link",
        "list",
        NODE_IDS["claim"],
        "--direction",
        "incoming",
        "--json",
    )
    listed_payload = json_stdout(listed)

    assert created.returncode == 0
    assert created_payload["data"]["id"].startswith("rel-")
    assert created_payload["data"] in listed_payload["data"]


@pytest.mark.contract
@pytest.mark.cli
def test_link_add_json_returns_archived_target_warning(example_project: Path) -> None:
    claim = next((example_project / "research" / "claims").glob("*.md"))
    archive_fixture_node(claim)
    request = {
        "source": NODE_IDS["evidence"],
        "kind": "supports",
        "target": NODE_IDS["claim"],
        "actor": {"kind": "human", "id": "reviewer"},
    }

    result = run_cli(
        example_project,
        "link",
        "add",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["ok"] is True
    assert any(
        warning["code"] == "archived_target"
        and warning["edge_id"] == payload["data"]["id"]
        for warning in payload["warnings"]
    )


@pytest.mark.contract
@pytest.mark.cli
def test_link_add_human_mode_writes_warning_to_stderr(example_project: Path) -> None:
    claim = next((example_project / "research" / "claims").glob("*.md"))
    archive_fixture_node(claim)

    result = run_cli(
        example_project,
        "link",
        "add",
        NODE_IDS["evidence"],
        "supports",
        NODE_IDS["claim"],
        "--actor",
        "reviewer",
    )

    assert result.returncode == 0
    assert result.stdout.startswith("Created rel-")
    assert "warning: archived_target:" in result.stderr


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_json_returns_initial_relation_warning(
    example_project: Path,
) -> None:
    experiment = next((example_project / "research" / "experiments").glob("*.md"))
    archive_fixture_node(experiment)
    request = {
        "title": "Archived protocol run",
        "started_at": "2026-08-17T12:00:00+07:00",
        "outcome": "running",
        "initial_relations": [
            {"kind": "instance_of", "target": NODE_IDS["experiment"]}
        ],
        "actor": {"kind": "human", "id": "runner"},
    }

    result = run_cli(
        example_project,
        "node",
        "create",
        "run",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert any(
        warning["code"] == "archived_target"
        and warning["node_id"] == payload["data"]["id"]
        for warning in payload["warnings"]
    )


@pytest.mark.contract
@pytest.mark.cli
def test_link_add_global_failure_does_not_change_file(example_project: Path) -> None:
    run = next((example_project / "research" / "runs").glob("*.md"))
    before = run.read_bytes()
    request = {
        "source": NODE_IDS["run"],
        "kind": "instance_of",
        "target": NODE_IDS["experiment"],
        "actor": {"kind": "human", "id": "editor"},
    }

    result = run_cli(
        example_project,
        "link",
        "add",
        "--from-json",
        "-",
        "--json",
        input_text=json.dumps(request),
    )

    assert result.returncode == 3
    assert json_stdout(result)["error"]["code"] == "validation_failed"
    assert run.read_bytes() == before


@pytest.mark.contract
@pytest.mark.cli
def test_link_remove_required_relation_does_not_change_file(
    example_project: Path,
) -> None:
    run = next((example_project / "research" / "runs").glob("*.md"))
    before = run.read_bytes()

    result = run_cli(
        example_project,
        "link",
        "remove",
        RELATION_IDS["instance_of"],
        "--actor",
        "editor",
        "--json",
    )

    assert result.returncode == 3
    assert json_stdout(result)["error"]["code"] == "validation_failed"
    assert run.read_bytes() == before


@pytest.mark.contract
@pytest.mark.cli
def test_link_remove_deletes_edge_by_global_id(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "link",
        "remove",
        "rel-01J0000000000000000000000J",
        "--actor",
        "reviewer",
        "--json",
    )
    listed = run_cli(
        example_project,
        "link",
        "list",
        NODE_IDS["evidence"],
        "--json",
    )

    assert result.returncode == 0
    assert json_stdout(result)["data"]["removed"] is True
    assert all(
        edge["id"] != "rel-01J0000000000000000000000J"
        for edge in json_stdout(listed)["data"]
    )


@pytest.mark.contract
@pytest.mark.cli
def test_graph_traverse_and_path_are_available_as_json(example_project: Path) -> None:
    traversal = run_cli(
        example_project,
        "graph",
        "traverse",
        NODE_IDS["hypothesis"],
        "--direction",
        "incoming",
        "--depth",
        "1",
        "--json",
    )
    path = run_cli(
        example_project,
        "graph",
        "path",
        NODE_IDS["run"],
        NODE_IDS["hypothesis"],
        "--json",
    )

    traversal_payload = json_stdout(traversal)
    path_payload = json_stdout(path)
    assert traversal.returncode == 0
    assert {node["id"] for node in traversal_payload["data"]["nodes"]} == {
        NODE_IDS["experiment"],
        NODE_IDS["evidence"],
        NODE_IDS["challenging_evidence"],
        NODE_IDS["assessment"],
    }
    assert [edge["kind"] for edge in path_payload["data"]["edges"]] == [
        "instance_of",
        "tests",
    ]


@pytest.mark.contract
@pytest.mark.cli
def test_graph_show_returns_center_node_and_adjacent_edges(
    example_project: Path,
) -> None:
    result = run_cli(
        example_project,
        "graph",
        "show",
        NODE_IDS["hypothesis"],
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["data"]["center"]["id"] == NODE_IDS["hypothesis"]
    assert {edge["kind"] for edge in payload["data"]["edges"]} == {
        "addresses",
        "tests",
        "supports",
        "challenges",
        "assesses",
    }


@pytest.mark.contract
@pytest.mark.cli
def test_graph_export_is_deterministic_json(example_project: Path) -> None:
    first = run_cli(example_project, "graph", "export", "--format", "json")
    second = run_cli(example_project, "graph", "export", "--format", "json")

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert len(payload["nodes"]) == 11
    assert len(payload["edges"]) == 14


@pytest.mark.contract
@pytest.mark.cli
def test_graph_render_writes_standalone_html_at_project_root(
    example_project: Path,
) -> None:
    nested = example_project / "research" / "hypotheses"

    result = run_cli(nested, "graph", "render")

    target = example_project / "research-graph.html"
    assert result.returncode == 0
    assert result.stderr == ""
    assert f"Rendered 11 nodes and 14 relations to {target}" in result.stdout
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not (nested / "research-graph.html").exists()


@pytest.mark.contract
@pytest.mark.cli
def test_graph_render_supports_focused_json_mode(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "graph",
        "render",
        "--focus",
        "H-context",
        "--depth",
        "1",
        "--output",
        "reports/local.html",
        "--json",
    )

    payload = json_stdout(result)
    target = example_project / "reports" / "local.html"
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload == {
        "ok": True,
        "data": {
            "output": str(target),
            "nodes": 6,
            "edges": 7,
            "focus": NODE_IDS["hypothesis"],
            "depth": 1,
        },
        "warnings": [],
    }
    html = target.read_text(encoding="utf-8")
    assert NODE_IDS["hypothesis"] in html
    assert NODE_IDS["source"] not in html


@pytest.mark.contract
@pytest.mark.cli
def test_graph_render_rejects_depth_without_focus(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "graph",
        "render",
        "--depth",
        "1",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert "--depth requires --focus" in payload["error"]["message"]
    assert not (example_project / "research-graph.html").exists()


@pytest.mark.contract
@pytest.mark.cli
def test_graph_render_refuses_to_write_inside_canonical_vault(
    example_project: Path,
) -> None:
    result = run_cli(
        example_project,
        "graph",
        "render",
        "--output",
        "research/generated.html",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert "outside the research vault" in payload["error"]["message"]
    assert not (example_project / "research" / "generated.html").exists()


@pytest.mark.contract
@pytest.mark.cli
def test_missing_and_ambiguous_references_use_exit_code_four(
    example_project: Path,
) -> None:
    missing = run_cli(example_project, "node", "show", "hyp-missing", "--json")
    ambiguous = run_cli(example_project, "node", "show", "evd-01J000", "--json")

    assert missing.returncode == ambiguous.returncode == 4
    assert json_stdout(missing)["error"]["code"] == "node_not_found"
    assert json_stdout(ambiguous)["error"]["code"] == "ambiguous_reference"


@pytest.mark.contract
@pytest.mark.cli
def test_missing_edge_uses_not_found_exit_code_four(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "link",
        "remove",
        "rel-01M00000000000000000000000",
        "--actor",
        "reviewer",
        "--json",
    )

    assert result.returncode == 4
    assert json_stdout(result)["error"]["code"] == "edge_not_found"


@pytest.mark.contract
@pytest.mark.cli
def test_invalid_cli_arguments_use_exit_code_two(example_project: Path) -> None:
    result = run_cli(example_project, "graph", "traverse", "--depth", "not-an-int")

    assert result.returncode == 2


@pytest.mark.contract
@pytest.mark.cli
def test_unknown_format_version_uses_exit_code_six(example_project: Path) -> None:
    config = example_project / "research.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "format_version: 1", "format_version: 99"
        ),
        encoding="utf-8",
    )

    result = run_cli(example_project, "validate", "--json")

    assert result.returncode == 6
    assert json_stdout(result)["error"]["code"] == "unsupported_format_version"


@pytest.mark.contract
@pytest.mark.cli
def test_validation_warnings_do_not_make_command_fail(example_project: Path) -> None:
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    hypothesis.write_text(
        hypothesis.read_text(encoding="utf-8").replace(
            "status: active", "status: archived"
        ),
        encoding="utf-8",
    )

    result = run_cli(example_project, "validate", "--json")

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["warnings"]
    assert all(item["severity"] == "warning" for item in payload["warnings"])


@pytest.mark.contract
@pytest.mark.cli
def test_validation_human_mode_prints_warnings_to_stderr(
    example_project: Path,
) -> None:
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    archive_fixture_node(hypothesis)

    result = run_cli(example_project, "validate")

    assert result.returncode == 0
    assert result.stdout == "Project is valid\n"
    assert "warning: archived_target:" in result.stderr


@pytest.mark.contract
@pytest.mark.cli
def test_format_check_is_read_only(example_project: Path) -> None:
    before = {
        path: path.read_bytes() for path in (example_project / "research").rglob("*.md")
    }

    result = run_cli(example_project, "format", "--check", "--json")

    payload = json_stdout(result)
    assert result.returncode == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "formatting_required"
    assert len(payload["error"]["details"]["paths"]) == 11
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.contract
@pytest.mark.cli
def test_format_applies_changes_and_second_check_is_clean(
    example_project: Path,
) -> None:
    project_readme = example_project / "research" / "PROJECT.md"
    readme_before = project_readme.read_bytes()
    nodes = {
        path: path.read_bytes()
        for path in (example_project / "research").rglob("*.md")
        if path.name != "PROJECT.md"
    }

    applied = run_cli(example_project, "format", "--json")

    payload = json_stdout(applied)
    assert applied.returncode == 0
    assert payload["ok"] is True
    assert payload["data"] == {
        "formatted": True,
        "check": False,
        "checked_files": 11,
        "changed_files": sorted(
            str(path.relative_to(example_project)) for path in nodes
        ),
    }
    assert payload["warnings"] == []
    assert project_readme.read_bytes() == readme_before
    assert {path: _body_bytes(path.read_bytes()) for path in nodes} == {
        path: _body_bytes(raw) for path, raw in nodes.items()
    }

    checked = run_cli(example_project, "format", "--check", "--json")

    checked_payload = json_stdout(checked)
    assert checked.returncode == 0
    assert checked_payload == {
        "ok": True,
        "data": {
            "formatted": False,
            "check": True,
            "checked_files": 11,
            "changed_files": [],
        },
        "warnings": [],
    }


@pytest.mark.contract
@pytest.mark.cli
def test_format_json_surfaces_project_warnings(example_project: Path) -> None:
    hypothesis = next((example_project / "research" / "hypotheses").glob("*.md"))
    archive_fixture_node(hypothesis)

    result = run_cli(example_project, "format", "--json")

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["data"]["formatted"] is True
    assert payload["warnings"]
    assert all(item["severity"] == "warning" for item in payload["warnings"])


def _body_bytes(raw: bytes) -> bytes:
    closing = raw.index(b"\n---\n", 4)
    return raw[closing + len(b"\n---\n") :]


@pytest.mark.contract
@pytest.mark.cli
def test_init_command_creates_project_at_explicit_path(tmp_path: Path) -> None:
    target = tmp_path / "initialized"

    result = run_cli(
        tmp_path,
        "init",
        str(target),
        "--title",
        "Initialized project",
        "--default-language",
        "ru",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 0
    assert payload["data"]["root"] == str(target.resolve())
    assert (target / "research.yaml").is_file()


@pytest.mark.contract
@pytest.mark.cli
def test_node_show_human_mode_renders_metadata_and_body(
    example_project: Path,
) -> None:
    result = run_cli(example_project, "node", "show", NODE_IDS["question"])

    assert result.returncode == 0
    assert f"ID:       {NODE_IDS['question']}" in result.stdout
    assert "Kind:     question" in result.stdout
    assert "Status:   active" in result.stdout
    assert "Revision:" in result.stdout
    assert "Body:" in result.stdout
    assert "This is the root research question." in result.stdout


@pytest.mark.contract
@pytest.mark.cli
def test_node_list_human_mode_renders_a_table(example_project: Path) -> None:
    result = run_cli(example_project, "node", "list", "--kind", "hypothesis")

    assert result.returncode == 0
    assert all(column in result.stdout for column in ("ID", "KIND", "STATUS", "TITLE"))
    assert NODE_IDS["hypothesis"] in result.stdout
    assert "A larger context improves recall" in result.stdout


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_edit_opens_configured_editor_and_saves_body(
    example_project: Path,
    tmp_path: Path,
) -> None:
    editor = tmp_path / "editor.py"
    editor.write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text("
        "'# Edited body\\n\\nWritten in the configured editor.\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--title",
        "Editor-created claim",
        "--statement",
        "The editor body is persisted.",
        "--actor",
        "author",
        "--edit",
        environment_overrides={"EDITOR": f"{sys.executable} {editor}"},
    )

    assert result.returncode == 0
    created = next(
        path
        for path in (example_project / "research" / "claims").glob("*.md")
        if "editor-created-claim" in path.name
    )
    assert created.read_text(encoding="utf-8").endswith(
        "# Edited body\n\nWritten in the configured editor.\n"
    )


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_edit_failure_does_not_create_a_node(
    example_project: Path,
    tmp_path: Path,
) -> None:
    editor = tmp_path / "failing-editor.py"
    editor.write_text("raise SystemExit(7)\n", encoding="utf-8")
    before = set((example_project / "research" / "claims").glob("*.md"))

    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--title",
        "Cancelled editor claim",
        "--statement",
        "This node must not be written.",
        "--actor",
        "author",
        "--edit",
        environment_overrides={"EDITOR": f"{sys.executable} {editor}"},
    )

    assert result.returncode == 2
    assert "editor exited with status 7" in result.stderr
    assert set((example_project / "research" / "claims").glob("*.md")) == before


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_reads_body_file(example_project: Path, tmp_path: Path) -> None:
    body = tmp_path / "claim-body.md"
    body.write_text("# Imported body\n\nKept as Markdown.\n", encoding="utf-8")

    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--title",
        "Body file claim",
        "--statement",
        "The body comes from a file.",
        "--actor",
        "author",
        "--body-file",
        str(body),
    )

    assert result.returncode == 0
    created = next(
        path
        for path in (example_project / "research" / "claims").glob("*.md")
        if "body-file-claim" in path.name
    )
    assert created.read_text(encoding="utf-8").endswith(
        body.read_text(encoding="utf-8")
    )


@pytest.mark.contract
@pytest.mark.cli
def test_node_create_rejects_editor_in_json_mode(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "node",
        "create",
        "claim",
        "--title",
        "Interactive JSON claim",
        "--statement",
        "JSON output must stay machine-readable.",
        "--actor",
        "author",
        "--edit",
        "--json",
    )

    payload = json_stdout(result)
    assert result.returncode == 2
    assert payload["error"]["code"] == "invalid_arguments"
    assert "--edit is not available in JSON mode" in payload["error"]["message"]


@pytest.mark.contract
@pytest.mark.cli
def test_link_list_human_mode_renders_a_table(example_project: Path) -> None:
    result = run_cli(
        example_project,
        "link",
        "list",
        NODE_IDS["hypothesis"],
        "--direction",
        "incoming",
    )

    assert result.returncode == 0
    assert all(
        column in result.stdout
        for column in ("ID", "KIND", "SOURCE", "TARGET", "RATIONALE")
    )
    assert NODE_IDS["hypothesis"] in result.stdout
    assert "supports" in result.stdout


@pytest.mark.contract
@pytest.mark.cli
def test_graph_show_human_mode_renders_directional_neighborhood(
    example_project: Path,
) -> None:
    result = run_cli(example_project, "graph", "show", NODE_IDS["hypothesis"])

    assert result.returncode == 0
    assert NODE_IDS["hypothesis"] in result.stdout
    assert "A larger context improves recall" in result.stdout
    assert "→" in result.stdout
    assert "←" in result.stdout
    assert "tests" in result.stdout
    assert NODE_IDS["experiment"] in result.stdout


@pytest.mark.contract
@pytest.mark.cli
def test_graph_path_human_mode_renders_nodes_and_relation_kinds(
    example_project: Path,
) -> None:
    result = run_cli(
        example_project,
        "graph",
        "path",
        NODE_IDS["run"],
        NODE_IDS["hypothesis"],
    )

    assert result.returncode == 0
    assert NODE_IDS["run"] in result.stdout
    assert NODE_IDS["experiment"] in result.stdout
    assert NODE_IDS["hypothesis"] in result.stdout
    assert "instance_of" in result.stdout
    assert "tests" in result.stdout
