"""What the index is allowed to save, and what it must never let through.

Every test here pairs a saving with the thing that must still be noticed: a
formatting check that reads nothing must still catch a file that has changed, and
a single-node read that skips the graph must still refuse a stale or ambiguous
answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    Actor,
    AmbiguousReference,
    ClaimDraft,
    NodeNotFound,
    Project,
    ValidationFailed,
)
from research_framework.storage.markdown_codec import MarkdownCodec, MarkdownHeader
from tests.conftest import NODE_IDS


def _count_header_decodes(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    original = MarkdownCodec.decode_header
    decoded: list[Path] = []

    def counted(self: MarkdownCodec, text: str, *, path: Path) -> MarkdownHeader:
        decoded.append(path)
        return original(self, text, path=path)

    monkeypatch.setattr(MarkdownCodec, "decode_header", counted)
    return decoded


@pytest.mark.contract
@pytest.mark.integration
def test_repeated_format_check_reads_no_node_file(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fixture is deliberately hand-written, so canonicalize it first: the
    # claim under test is about repeating a check, not about the first one.
    Project.open(example_project).format(check=False)
    project = Project.open(example_project)
    first = project.format(check=True)
    assert first.changed_paths == ()

    decoded = _count_header_decodes(monkeypatch)
    second = Project.open(example_project).format(check=True)

    assert decoded == []
    assert second.checked_files == first.checked_files
    assert second.changed_paths == ()


@pytest.mark.contract
@pytest.mark.integration
def test_format_check_still_sees_a_file_that_stops_being_canonical(
    example_project: Path,
) -> None:
    Project.open(example_project).format(check=False)
    assert Project.open(example_project).format(check=True).changed_paths == ()

    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8").replace("kind: claim", "kind:    claim", 1),
        encoding="utf-8",
    )

    result = Project.open(example_project).format(check=True)

    assert result.changed_paths == (claim,)


@pytest.mark.contract
@pytest.mark.integration
def test_format_apply_then_check_reads_nothing_more(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8").replace("kind: claim", "kind:  claim", 1),
        encoding="utf-8",
    )
    applied = Project.open(example_project).format(check=False)
    assert applied.applied

    decoded = _count_header_decodes(monkeypatch)
    result = Project.open(example_project).format(check=True)

    assert decoded == []
    assert result.changed_paths == ()


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_matches_the_full_graph_without_building_it(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    expected = project.snapshot().get_node(NODE_IDS["hypothesis"])
    decoded = _count_header_decodes(monkeypatch)

    node = Project.read_node(example_project, NODE_IDS["hypothesis"])

    assert decoded == []
    assert node.id == expected.id
    assert node.title == expected.title
    assert node.revision == expected.revision
    assert node.statement == expected.statement
    assert node.body == expected.body


@pytest.mark.contract
@pytest.mark.integration
@pytest.mark.parametrize("reference", ["H-context", "hyp-01J000000000000000000000"])
def test_read_node_resolves_alias_and_unambiguous_prefix(
    example_project: Path, reference: str
) -> None:
    Project.open(example_project)

    node = Project.read_node(example_project, reference)

    assert node.id == NODE_IDS["hypothesis"]


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_reports_an_ambiguous_prefix_instead_of_choosing(
    example_project: Path,
) -> None:
    Project.open(example_project)

    with pytest.raises(AmbiguousReference):
        # Two evidence nodes share this prefix.
        Project.read_node(example_project, "evd-")


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_still_fails_on_an_unknown_reference(
    example_project: Path,
) -> None:
    Project.open(example_project)

    with pytest.raises(NodeNotFound):
        Project.read_node(example_project, "clm-01J99999999999999999999999")


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_sees_an_edit_made_outside_the_framework(
    example_project: Path,
) -> None:
    Project.open(example_project)
    claim_path = next((example_project / "research" / "claims").glob("*.md"))
    claim_path.write_text(
        claim_path.read_text(encoding="utf-8").replace(
            "title: Larger contexts increase inference cost",
            "title: Edited by hand",
        ),
        encoding="utf-8",
    )

    node = Project.read_node(example_project, NODE_IDS["claim"])

    assert node.title == "Edited by hand"


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_works_without_any_index(example_project: Path) -> None:
    # The very first read of a project has no cache to consult.
    node = Project.read_node(example_project, NODE_IDS["decision"])

    assert node.id == NODE_IDS["decision"]


@pytest.mark.contract
@pytest.mark.integration
def test_read_node_finds_a_node_created_in_the_same_session(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    created = project.create_node(
        ClaimDraft(title="Fresh claim", statement="Written just now."),
        actor=Actor.human("author"),
    )

    node = Project.read_node(example_project, created.id)

    assert node.title == "Fresh claim"
    assert node.body == created.body


@pytest.mark.contract
@pytest.mark.integration
def test_index_backed_validation_reports_a_break_made_after_indexing(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    assert project.validate() == ()

    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8").replace(
            "target: que-01J00000000000000000000001",
            "target: que-01J99999999999999999999999",
        ),
        encoding="utf-8",
    )

    indexed = project.validate()
    full = project.validate(full=True)

    assert {item.code for item in indexed} >= {"dangling_relation"}
    assert indexed == full


@pytest.mark.contract
@pytest.mark.integration
def test_format_revalidates_a_vault_edited_after_it_was_opened(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8").replace(
            "target: que-01J00000000000000000000001",
            "target: que-01J99999999999999999999999",
        ),
        encoding="utf-8",
    )

    # Skipping validation is only allowed while the vault still matches what was
    # validated; this edit means it does not.
    with pytest.raises(ValidationFailed) as raised:
        project.format(check=True)

    assert {item.code for item in raised.value.diagnostics} >= {"dangling_relation"}


@pytest.mark.contract
@pytest.mark.integration
def test_format_revalidates_when_a_node_appears_after_opening(
    example_project: Path,
) -> None:
    project = Project.open(example_project)
    smuggled = example_project / "research" / "claims" / "clm-invalid--broken.md"
    smuggled.write_text("---\nid: clm-broken\nkind: claim\n---\n", encoding="utf-8")

    with pytest.raises(ValidationFailed):
        project.format(check=True)
