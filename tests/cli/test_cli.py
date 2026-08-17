from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import NODE_IDS


def run_cli(
    cwd: Path,
    *arguments: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).parents[2]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(root / "src"), existing_pythonpath])
    )
    environment["NO_COLOR"] = "1"
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
def test_format_check_is_read_only(example_project: Path) -> None:
    before = {
        path: path.read_bytes() for path in (example_project / "research").rglob("*.md")
    }

    result = run_cli(example_project, "format", "--check")

    assert result.returncode == 0
    assert {path: path.read_bytes() for path in before} == before


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
