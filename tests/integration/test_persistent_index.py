from __future__ import annotations

import json
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
    cache_path = example_project / ".research-cache" / "index-v1.json"
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
    cache_path = example_project / ".research-cache" / "index-v1.json"
    cache_path.write_text("{not valid json", encoding="utf-8")
    decoded = _count_header_decodes(monkeypatch)

    reopened = Project.open(example_project)

    assert len(decoded) == 11
    assert len(reopened.snapshot().list_nodes()) == 11
    assert json.loads(cache_path.read_text(encoding="utf-8"))["cache_version"] == 1


@pytest.mark.contract
@pytest.mark.integration
def test_index_checksum_rejects_syntactically_valid_tampering(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Project.open(example_project)
    cache_path = example_project / ".research-cache" / "index-v1.json"
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    cached["entries"][0]["metadata"]["title"] = "Tampered cache title"
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    decoded = _count_header_decodes(monkeypatch)

    Project.open(example_project)

    assert len(decoded) == 11


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
def test_project_validate_always_reads_source_files_instead_of_trusting_index(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    decoded = _count_header_decodes(monkeypatch)

    assert project.validate() == ()

    assert len(decoded) == 11


@pytest.mark.contract
@pytest.mark.integration
def test_warm_open_decodes_only_a_newly_created_node(
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

    assert decoded == [created.path]
    assert reopened.snapshot().get_node(created.id).statement == (
        "The cache is incremental."
    )


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
