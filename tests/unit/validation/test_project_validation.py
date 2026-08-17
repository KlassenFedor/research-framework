from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_framework import DiagnosticSeverity
from research_framework.validation import validate_project
from tests.conftest import NODE_IDS, RELATION_IDS


def _node_file(root: Path, folder: str, needle: str | None = None) -> Path:
    paths = sorted((root / "research" / folder).glob("*.md"))
    if needle is not None:
        paths = [path for path in paths if needle in path.name]
    assert len(paths) == 1
    return paths[0]


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _append_relation(path: Path, relation_yaml: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "\n---\n"
    end = text.index(marker, 4)
    front_matter = text[:end]
    if front_matter.endswith("relations: []"):
        front_matter = front_matter[: -len("relations: []")] + "relations:"
    path.write_text(
        front_matter + "\n" + relation_yaml.rstrip() + text[end:],
        encoding="utf-8",
    )


def _remove_relation(path: Path, relation_id: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    removing = False
    found = False
    for line in lines:
        if line.startswith(f"  - id: {relation_id}"):
            removing = True
            found = True
            continue
        if removing and (line.startswith("  - id: ") or line == "---\n"):
            removing = False
        if not removing:
            output.append(line)
    assert found
    path.write_text("".join(output), encoding="utf-8")


def _codes(root: Path) -> set[str]:
    return {diagnostic.code for diagnostic in validate_project(root)}


@pytest.mark.contract
def test_example_project_has_no_diagnostics(example_project: Path) -> None:
    assert validate_project(example_project) == ()


@pytest.mark.contract
def test_validation_collects_syntax_error_without_crashing(
    example_project: Path,
) -> None:
    path = _node_file(example_project, "questions")
    _replace(path, "\n---\n\n# Retrieval quality", "\n# missing delimiter")

    diagnostics = validate_project(example_project)

    diagnostic = next(
        item for item in diagnostics if item.code == "unclosed_front_matter"
    )
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.path == path.relative_to(example_project)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("folder", "line", "field"),
    [
        (
            "questions",
            "title: Does a larger context improve retrieval quality?\n",
            "title",
        ),
        (
            "hypotheses",
            "statement: A 32k context improves recall by at least 10% over 8k.\n",
            "statement",
        ),
        (
            "evidence",
            "observation: Recall improved by 13% with the 32k context.\n",
            "observation",
        ),
    ],
)
def test_validation_reports_missing_common_and_kind_specific_fields(
    example_project: Path, folder: str, line: str, field: str
) -> None:
    path = _node_file(
        example_project,
        folder,
        "recall-improvement" if folder == "evidence" else None,
    )
    _replace(path, line, "")

    diagnostics = validate_project(example_project)

    diagnostic = next(
        item for item in diagnostics if item.code == "missing_required_field"
    )
    assert diagnostic.field == field
    assert diagnostic.path == path.relative_to(example_project)


@pytest.mark.contract
def test_unknown_top_level_field_is_error_not_warning(example_project: Path) -> None:
    path = _node_file(example_project, "questions")
    _replace(path, "relations: []", "typo_summary: unnoticed\nrelations: []")

    diagnostics = validate_project(example_project)

    diagnostic = next(item for item in diagnostics if item.code == "unknown_field")
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.field == "typo_summary"


@pytest.mark.contract
@pytest.mark.parametrize(
    ("old", "new", "code"),
    [
        ("status: active", "status: believed", "invalid_status"),
        ("kind: question", "kind: fact", "invalid_node_kind"),
        (
            "created_at: 2026-08-17T10:00:00+07:00",
            "created_at: 2026-08-17T10:00:00",
            "timezone_required",
        ),
        (
            f"id: {NODE_IDS['question']}",
            "id: question-001",
            "invalid_node_id",
        ),
    ],
)
def test_validation_reports_invalid_enums_timestamps_and_ids(
    example_project: Path, old: str, new: str, code: str
) -> None:
    path = _node_file(example_project, "questions")
    _replace(path, old, new)

    assert code in _codes(example_project)


@pytest.mark.contract
def test_duplicate_node_ids_are_reported_with_both_paths(example_project: Path) -> None:
    source = _node_file(example_project, "questions")
    duplicate = example_project / "research" / "questions" / "duplicate.md"
    shutil.copyfile(source, duplicate)

    diagnostics = validate_project(example_project)

    diagnostic = next(item for item in diagnostics if item.code == "duplicate_node_id")
    assert diagnostic.node_id == NODE_IDS["question"]
    assert diagnostic.details["paths"] == sorted(
        [
            str(source.relative_to(example_project)),
            str(duplicate.relative_to(example_project)),
        ]
    )


@pytest.mark.contract
def test_duplicate_alias_is_reported(example_project: Path) -> None:
    claim = _node_file(example_project, "claims")
    _replace(claim, "created_at:", "aliases:\n  - H-context\ncreated_at:")

    assert "duplicate_alias" in _codes(example_project)


@pytest.mark.contract
def test_duplicate_edge_id_is_reported_globally(example_project: Path) -> None:
    evidence = _node_file(example_project, "evidence", "recall-improvement")
    _replace(evidence, RELATION_IDS["supports"], RELATION_IDS["addresses"])

    assert "duplicate_edge_id" in _codes(example_project)


@pytest.mark.contract
def test_dangling_relation_identifies_target_and_field(example_project: Path) -> None:
    hypothesis = _node_file(example_project, "hypotheses")
    _replace(hypothesis, NODE_IDS["question"], "que-01J00000000000000000ZZZZZZ")

    diagnostics = validate_project(example_project)

    diagnostic = next(item for item in diagnostics if item.code == "dangling_relation")
    assert diagnostic.node_id == NODE_IDS["hypothesis"]
    assert diagnostic.edge_id == RELATION_IDS["addresses"]
    assert diagnostic.field == "relations[0].target"
    assert "Create the target" in diagnostic.suggestion


@pytest.mark.contract
def test_relation_matrix_violation_is_reported(example_project: Path) -> None:
    hypothesis = _node_file(example_project, "hypotheses")
    _replace(hypothesis, "kind: addresses", "kind: supports")

    assert "relation_kind_mismatch" in _codes(example_project)


@pytest.mark.contract
def test_meaningless_self_link_is_reported(example_project: Path) -> None:
    hypothesis = _node_file(example_project, "hypotheses")
    _append_relation(
        hypothesis,
        f"""  - id: rel-01J0000000000000000000000T
    kind: depends_on
    target: {NODE_IDS["hypothesis"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )

    assert "self_relation" in _codes(example_project)


@pytest.mark.contract
def test_dependency_cycle_is_reported_when_policy_forbids_it(
    example_project: Path,
) -> None:
    hypothesis = _node_file(example_project, "hypotheses")
    claim = _node_file(example_project, "claims")
    _append_relation(
        hypothesis,
        f"""  - id: rel-01J0000000000000000000000T
    kind: depends_on
    target: {NODE_IDS["claim"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )
    _append_relation(
        claim,
        f"""  - id: rel-01J0000000000000000000000V
    kind: depends_on
    target: {NODE_IDS["hypothesis"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )

    diagnostics = validate_project(example_project)

    diagnostic = next(item for item in diagnostics if item.code == "dependency_cycle")
    assert set(diagnostic.details["cycle"]) == {
        NODE_IDS["hypothesis"],
        NODE_IDS["claim"],
    }


@pytest.mark.contract
def test_dependency_cycle_policy_can_be_disabled_explicitly(
    example_project: Path,
) -> None:
    config = example_project / "research.yaml"
    _replace(
        config, "forbid_dependency_cycles: true", "forbid_dependency_cycles: false"
    )
    hypothesis = _node_file(example_project, "hypotheses")
    claim = _node_file(example_project, "claims")
    _append_relation(
        hypothesis,
        f"""  - id: rel-01J0000000000000000000000T
    kind: depends_on
    target: {NODE_IDS["claim"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )
    _append_relation(
        claim,
        f"""  - id: rel-01J0000000000000000000000V
    kind: depends_on
    target: {NODE_IDS["hypothesis"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )

    assert "dependency_cycle" not in _codes(example_project)


@pytest.mark.contract
def test_run_must_have_exactly_one_instance_of_relation(example_project: Path) -> None:
    run = _node_file(example_project, "runs")
    _append_relation(
        run,
        f"""  - id: rel-01J0000000000000000000000W
    kind: instance_of
    target: {NODE_IDS["experiment"]}
    created_at: 2026-08-17T13:00:00+07:00
    created_by:
      kind: human
      id: test-author""",
    )

    assert "invalid_instance_of_count" in _codes(example_project)


@pytest.mark.contract
def test_evidence_requires_provenance_when_policy_enables_it(
    example_project: Path,
) -> None:
    evidence = _node_file(example_project, "evidence", "recall-improvement")
    _remove_relation(evidence, RELATION_IDS["derived_from_run"])

    assert "evidence_provenance_required" in _codes(example_project)


@pytest.mark.contract
def test_evidence_provenance_policy_can_be_disabled_explicitly(
    example_project: Path,
) -> None:
    config = example_project / "research.yaml"
    _replace(
        config,
        "require_evidence_provenance: true",
        "require_evidence_provenance: false",
    )
    evidence = _node_file(example_project, "evidence", "recall-improvement")
    _remove_relation(evidence, RELATION_IDS["derived_from_run"])

    assert "evidence_provenance_required" not in _codes(example_project)


@pytest.mark.contract
def test_assessment_requires_assesses_relation(example_project: Path) -> None:
    assessment = _node_file(example_project, "assessments")
    _remove_relation(assessment, RELATION_IDS["assesses"])

    assert "assessment_target_required" in _codes(example_project)


@pytest.mark.contract
def test_assessment_requires_at_least_one_basis(example_project: Path) -> None:
    assessment = _node_file(example_project, "assessments")
    _remove_relation(assessment, RELATION_IDS["based_on_support"])
    _remove_relation(assessment, RELATION_IDS["based_on_challenge"])

    assert "assessment_basis_required" in _codes(example_project)


@pytest.mark.contract
def test_links_to_archived_nodes_are_warnings(example_project: Path) -> None:
    hypothesis = _node_file(example_project, "hypotheses")
    _replace(hypothesis, "status: active", "status: archived")

    diagnostics = [
        item
        for item in validate_project(example_project)
        if item.code == "archived_target"
    ]

    assert diagnostics
    assert all(item.severity is DiagnosticSeverity.WARNING for item in diagnostics)


@pytest.mark.contract
def test_manual_file_move_does_not_change_identity_or_validity(
    example_project: Path,
) -> None:
    source = _node_file(example_project, "hypotheses")
    destination = example_project / "research" / "notes" / "renamed-manually.md"
    destination.parent.mkdir()
    source.rename(destination)

    assert validate_project(example_project) == ()
