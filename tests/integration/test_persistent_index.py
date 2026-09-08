from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_framework import Actor, ClaimDraft, Project, ValidationFailed
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
def test_second_project_open_reuses_persistent_metadata_index(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cold = Project.open(example_project)
    expected_ids = tuple(node.id for node in cold.snapshot().list_nodes())
    cache_path = example_project / ".research-cache" / "index-v3.sqlite3"
    assert cache_path.is_file()
    assert (cache_path.parent / ".gitignore").read_text(encoding="utf-8") == "*\n"

    decoded = _count_header_decodes(monkeypatch)
    warm = Project.open(example_project)

    assert decoded == []
    assert tuple(node.id for node in warm.snapshot().list_nodes()) == expected_ids


@pytest.mark.contract
@pytest.mark.integration
def test_warm_open_decodes_only_the_changed_node(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    claim = next((example_project / "research" / "claims").glob("*.md"))
    original = claim.read_text(encoding="utf-8")
    claim.write_text(
        original.replace(
            "title: Larger contexts increase inference cost",
            "title: Context windows have a measurable inference cost",
        ),
        encoding="utf-8",
    )
    decoded = _count_header_decodes(monkeypatch)

    warm = Project.open(example_project)

    assert decoded == [claim]
    assert warm.snapshot().get_node(NODE_IDS["claim"]).title == (
        "Context windows have a measurable inference cost"
    )


@pytest.mark.contract
@pytest.mark.integration
def test_corrupt_index_is_ignored_and_atomically_rebuilt(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    cache_path = example_project / ".research-cache" / "index-v3.sqlite3"
    cache_path.write_bytes(b"this is not a database")
    decoded = _count_header_decodes(monkeypatch)

    reopened = Project.open(example_project)

    assert len(decoded) == 11
    assert len(reopened.snapshot().list_nodes()) == 11
    with sqlite3.connect(cache_path) as rebuilt:
        stored = dict(rebuilt.execute("SELECT key, value FROM meta").fetchall())
    assert stored["cache_version"] == "3"


@pytest.mark.contract
@pytest.mark.integration
def test_index_checksum_rejects_syntactically_valid_tampering(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    cache_path = example_project / ".research-cache" / "index-v3.sqlite3"
    with sqlite3.connect(cache_path) as tampered:
        row = tampered.execute("SELECT path, metadata FROM nodes LIMIT 1").fetchone()
        edited = row[1].replace('"title":"', '"title":"Tampered ')
        # Valid SQL, valid JSON, and a checksum that no longer describes the row.
        tampered.execute(
            "UPDATE nodes SET metadata = ? WHERE path = ?", (edited, row[0])
        )
    decoded = _count_header_decodes(monkeypatch)

    reopened = Project.open(example_project)

    assert len(decoded) == 11
    assert all(
        not node.title.startswith("Tampered")
        for node in reopened.snapshot().list_nodes()
    )


@pytest.mark.contract
@pytest.mark.integration
def test_cached_metadata_never_hides_a_new_validation_error(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    claim = next((example_project / "research" / "claims").glob("*.md"))
    claim.write_text(
        claim.read_text(encoding="utf-8").replace(
            "target: que-01J00000000000000000000001",
            "target: que-01J99999999999999999999999",
        ),
        encoding="utf-8",
    )
    decoded = _count_header_decodes(monkeypatch)

    with pytest.raises(ValidationFailed) as raised:
        Project.open(example_project)

    assert decoded == [claim]
    assert {item.code for item in raised.value.diagnostics} >= {"dangling_relation"}


@pytest.mark.contract
@pytest.mark.integration
def test_project_validate_reuses_the_index_for_unchanged_files(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    decoded = _count_header_decodes(monkeypatch)

    assert project.validate() == ()

    assert decoded == []


@pytest.mark.contract
@pytest.mark.integration
def test_full_validate_reads_every_source_file_and_agrees_with_the_fast_path(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    indexed = project.validate()
    decoded = _count_header_decodes(monkeypatch)

    full = project.validate(full=True)

    assert len(decoded) == 11
    assert full == indexed


@pytest.mark.contract
@pytest.mark.integration
def test_creating_a_node_leaves_the_index_ready_for_the_next_open(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    created = project.create_node(
        ClaimDraft(title="Added after indexing", statement="The cache is incremental."),
        actor=Actor.human("author"),
    )
    decoded = _count_header_decodes(monkeypatch)

    reopened = Project.open(example_project)

    # The mutation recorded what it wrote, so reopening reads no Markdown at all.
    assert decoded == []
    assert reopened.snapshot().get_node(created.id).statement == (
        "The cache is incremental."
    )
    assert reopened.snapshot().get_node(created.id).body == created.body


@pytest.mark.contract
@pytest.mark.integration
def test_config_change_invalidates_the_whole_index(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    config = example_project / "research.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "title: Example retrieval research",
            "title: Renamed research graph",
        ),
        encoding="utf-8",
    )
    decoded = _count_header_decodes(monkeypatch)

    Project.open(example_project)

    assert len(decoded) == 11


@pytest.mark.contract
@pytest.mark.integration
def test_cache_directory_symlink_is_never_followed(
    example_project: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    cache_directory = example_project / ".research-cache"
    try:
        cache_directory.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    project = Project.open(example_project)

    assert len(project.snapshot().list_nodes()) == 11
    assert list(outside.iterdir()) == []
