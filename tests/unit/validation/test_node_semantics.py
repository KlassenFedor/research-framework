from __future__ import annotations

from pathlib import Path

import pytest

from research_framework.validation import validate_project


def _file(root: Path, folder: str, needle: str | None = None) -> Path:
    files = list((root / "research" / folder).glob("*.md"))
    if needle is not None:
        files = [path for path in files if needle in path.name]
    assert len(files) == 1
    return files[0]


def _replace(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    assert old in source
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def _codes(root: Path) -> set[str]:
    return {diagnostic.code for diagnostic in validate_project(root)}


@pytest.mark.contract
@pytest.mark.parametrize(
    ("folder", "needle", "old", "new", "expected_code"),
    [
        (
            "runs",
            None,
            "outcome: completed",
            "outcome: succeeded",
            "invalid_run_outcome",
        ),
        (
            "evidence",
            "recall-improvement",
            "evidence_kind: quantitative",
            "evidence_kind: anecdotal",
            "invalid_evidence_kind",
        ),
        (
            "assessments",
            None,
            "verdict: supported",
            "verdict: true",
            "invalid_assessment_verdict",
        ),
        (
            "assessments",
            None,
            "confidence: medium",
            "confidence: certain",
            "invalid_confidence",
        ),
        (
            "assessments",
            None,
            "review_state: approved",
            "review_state: final",
            "invalid_review_state",
        ),
        (
            "sources",
            None,
            "source_kind: paper",
            "source_kind: tweet",
            "invalid_source_kind",
        ),
    ],
)
def test_kind_specific_enums_are_strict(
    example_project: Path,
    folder: str,
    needle: str | None,
    old: str,
    new: str,
    expected_code: str,
) -> None:
    _replace(_file(example_project, folder, needle), old, new)

    assert expected_code in _codes(example_project)


@pytest.mark.contract
def test_finished_run_cannot_end_before_it_starts(example_project: Path) -> None:
    run = _file(example_project, "runs")
    _replace(
        run,
        "finished_at: 2026-08-17T11:20:00+07:00",
        "finished_at: 2026-08-17T10:59:59+07:00",
    )

    assert "run_time_order" in _codes(example_project)


@pytest.mark.contract
def test_completed_run_requires_finished_at(example_project: Path) -> None:
    run = _file(example_project, "runs")
    _replace(run, "finished_at: 2026-08-17T11:20:00+07:00\n", "")

    assert "finished_at_required" in _codes(example_project)


@pytest.mark.contract
def test_artifact_sha256_must_be_64_hex_characters(example_project: Path) -> None:
    artifact = _file(example_project, "artifacts")
    line = "sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    _replace(artifact, line, "sha256: not-a-hash")

    assert "invalid_sha256" in _codes(example_project)


@pytest.mark.contract
def test_artifact_size_cannot_be_negative(example_project: Path) -> None:
    artifact = _file(example_project, "artifacts")
    _replace(artifact, "size: 4096", "size: -1")

    assert "invalid_artifact_size" in _codes(example_project)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        ("kind: human", "kind: service", "invalid_actor_kind"),
        ("id: test-author", "id: ''", "invalid_actor_id"),
    ],
)
def test_actor_shape_is_validated_at_every_occurrence(
    example_project: Path, old: str, new: str, expected_code: str
) -> None:
    question = _file(example_project, "questions")
    _replace(question, old, new)

    assert expected_code in _codes(example_project)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("replacement", "expected_code"),
    [
        ("tags: retrieval", "invalid_field_type"),
        ("tags:\n  - retrieval\n  - 42", "invalid_field_type"),
        ("aliases:\n  - Q-context\n  - Q-context", "duplicate_alias"),
    ],
)
def test_tags_and_aliases_are_strict_string_lists(
    example_project: Path, replacement: str, expected_code: str
) -> None:
    question = _file(example_project, "questions")
    if replacement.startswith("tags:"):
        _replace(question, "tags:\n  - retrieval", replacement)
    else:
        _replace(question, "aliases:\n  - Q-context", replacement)

    assert expected_code in _codes(example_project)


@pytest.mark.contract
def test_updated_at_cannot_precede_created_at(example_project: Path) -> None:
    question = _file(example_project, "questions")
    _replace(
        question,
        "updated_at: 2026-08-17T10:00:00+07:00",
        "updated_at: 2026-08-16T10:00:00+07:00",
    )

    assert "updated_before_created" in _codes(example_project)
