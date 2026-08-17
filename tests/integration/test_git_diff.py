from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from research_framework import (
    Actor,
    ClaimDraft,
    EdgeKind,
    HypothesisDraft,
    Project,
    QuestionDraft,
)
from research_framework.domain.graph import Node


def _git(root: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        pytest.skip("git executable is not available")
    result = subprocess.run(
        [executable, *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-m", message)


def _relative(root: Path, node: Node) -> str:
    return str(node.path.relative_to(root))


def _body(raw: str) -> str:
    closing = raw.index("\n---\n", 4)
    return raw[closing + len("\n---\n") :]


def _tracked_project(tmp_path: Path) -> tuple[Project, Node, Node, Node]:
    root = tmp_path / "tracked-study"
    project = Project.init(root, title="Tracked study")
    actor = Actor.human("researcher")
    question = project.create_node(
        QuestionDraft(
            title="Does the intervention work?",
            question="Does the intervention improve recall?",
            body="# Question\n\nThe research question.\n",
        ),
        actor=actor,
    )
    hypothesis = project.create_node(
        HypothesisDraft(
            title="The intervention improves recall",
            statement="The intervention improves recall by at least 10%.",
            falsification_criteria="Recall improves by less than 10%.",
            body="# Hypothesis\n\nThe proposed explanation.\n",
        ),
        actor=actor,
    )
    claim = project.create_node(
        ClaimDraft(
            title="Baseline claim",
            statement="The baseline is reproducible.",
            body="# Claim\n\nBody text must remain stable.\n",
        ),
        actor=actor,
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Research Framework Tests")
    _git(root, "config", "user.email", "tests@example.invalid")
    _commit(root, "baseline")
    return project, question, hypothesis, claim


@pytest.mark.contract
@pytest.mark.integration
def test_typical_mutations_produce_local_human_readable_git_diffs(
    tmp_path: Path,
) -> None:
    project, question, hypothesis, claim = _tracked_project(tmp_path)
    root = project.root
    actor = Actor.human("reviewer")

    created = project.create_node(
        ClaimDraft(
            title="Replication claim",
            statement="The replication confirms the result.",
            body="# Replication\n\nIndependent result.\n",
        ),
        actor=actor,
    )
    created_path = _relative(root, created)
    assert _git(root, "status", "--porcelain") == f"?? {created_path}\n"
    _commit(root, "create claim")

    updated = project.update_node(
        claim.id,
        patch={"summary": "Reviewed against the replication."},
        expected_revision=claim.revision,
        actor=actor,
    )
    claim_path = _relative(root, updated)
    update_diff = _git(root, "diff", "--unified=0", "--", claim_path)
    assert _git(root, "diff", "--name-only") == f"{claim_path}\n"
    assert "+summary: Reviewed against the replication." in update_diff
    assert "Body text must remain stable." not in update_diff
    _commit(root, "update claim")

    edge = project.add_edge(
        source=hypothesis.id,
        kind=EdgeKind.ADDRESSES,
        target=question.id,
        rationale="Connects the explanation to its question.",
        actor=actor,
    )
    hypothesis_path = _relative(root, project.snapshot().get_node(hypothesis.id))
    add_diff = _git(root, "diff", "--unified=0", "--", hypothesis_path)
    assert _git(root, "diff", "--name-only") == f"{hypothesis_path}\n"
    assert "+  kind: addresses" in add_diff
    assert f"+  target: {question.id}" in add_diff
    _commit(root, "add relation")

    project.remove_edge(edge.id, actor=actor)
    remove_diff = _git(root, "diff", "--unified=0", "--", hypothesis_path)
    assert _git(root, "diff", "--name-only") == f"{hypothesis_path}\n"
    assert "-  kind: addresses" in remove_diff
    _commit(root, "remove relation")

    current_claim = project.snapshot().get_node(claim.id)
    project.archive_node(
        claim.id,
        expected_revision=current_claim.revision,
        actor=actor,
    )
    archive_diff = _git(root, "diff", "--unified=0", "--", claim_path)
    assert _git(root, "diff", "--name-only") == f"{claim_path}\n"
    assert "-status: draft" in archive_diff
    assert "+status: archived" in archive_diff


@pytest.mark.contract
@pytest.mark.integration
def test_format_git_diff_changes_only_front_matter_of_drifted_file(
    tmp_path: Path,
) -> None:
    project, _, _, claim = _tracked_project(tmp_path)
    root = project.root
    claim_path = _relative(root, claim)
    original = claim.path.read_text(encoding="utf-8")
    claim.path.write_text(
        original.replace("---\n", "---\n# deliberate formatting drift\n", 1),
        encoding="utf-8",
    )
    body_before = _body(claim.path.read_text(encoding="utf-8"))
    _commit(root, "introduce formatting drift")

    result = project.format()

    diff = _git(root, "diff", "--unified=0", "--", claim_path)
    assert tuple(path.relative_to(root) for path in result.changed_paths) == (
        Path(claim_path),
    )
    assert _git(root, "diff", "--name-only") == f"{claim_path}\n"
    assert "-# deliberate formatting drift" in diff
    assert "Body text must remain stable." not in diff
    assert _body(claim.path.read_text(encoding="utf-8")) == body_before
