from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import ProjectNotFound, StorageError, UnsupportedFormatVersion
from research_framework.storage.discovery import discover_node_files, discover_project


@pytest.mark.contract
def test_project_is_discovered_from_nested_directory(example_project: Path) -> None:
    nested = example_project / "research" / "hypotheses"

    discovered = discover_project(nested)

    assert discovered.root == example_project.resolve()
    assert discovered.config_path == example_project / "research.yaml"
    assert discovered.vault == example_project / "research"
    assert discovered.config.project_id == "prj-01J00000000000000000000000"


@pytest.mark.contract
def test_project_discovery_accepts_file_as_starting_point(
    example_project: Path,
) -> None:
    node_file = next((example_project / "research" / "questions").glob("*.md"))

    discovered = discover_project(node_file)

    assert discovered.root == example_project.resolve()


@pytest.mark.contract
def test_project_discovery_fails_clearly_when_config_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFound) as raised:
        discover_project(tmp_path)

    assert raised.value.start == tmp_path


@pytest.mark.contract
def test_unknown_project_format_version_is_not_migrated_implicitly(
    example_project: Path,
) -> None:
    config = example_project / "research.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "format_version: 1", "format_version: 2"
        ),
        encoding="utf-8",
    )

    with pytest.raises(UnsupportedFormatVersion) as raised:
        discover_project(example_project)

    assert raised.value.found == 2
    assert raised.value.supported == {1}


@pytest.mark.contract
@pytest.mark.parametrize("vault", ["../outside", "/tmp/outside"])
def test_vault_must_resolve_inside_project_root(tmp_path: Path, vault: str) -> None:
    (tmp_path / "research.yaml").write_text(
        "\n".join(
            [
                "format_version: 1",
                "project_id: prj-01J00000000000000000000000",
                "title: Unsafe project",
                f"vault: {vault}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(StorageError, match="vault"):
        discover_project(tmp_path)


@pytest.mark.contract
def test_node_discovery_is_recursive_sorted_and_ignores_project_overview(
    example_project: Path,
) -> None:
    discovered = discover_project(example_project)

    files = discover_node_files(discovered)

    assert len(files) == 11
    assert list(files) == sorted(files)
    assert all(path.suffix == ".md" for path in files)
    assert discovered.vault / "PROJECT.md" not in files


@pytest.mark.contract
def test_discovery_ignores_non_markdown_files(example_project: Path) -> None:
    ignored = example_project / "research" / "questions" / "notes.txt"
    ignored.write_text("not a node", encoding="utf-8")
    discovered = discover_project(example_project)

    assert ignored not in discover_node_files(discovered)


@pytest.mark.contract
def test_discovery_does_not_follow_symlinked_files_outside_vault(
    example_project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("---\nid: unsafe\n---\n", encoding="utf-8")
    link = example_project / "research" / "questions" / "outside-link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    discovered = discover_project(example_project)

    assert link not in discover_node_files(discovered)


@pytest.mark.contract
def test_discovery_orders_paths_the_way_path_comparison_does(
    example_project: Path,
) -> None:
    # A directory whose name is a prefix of another, with a following character
    # below the path separator, is where raw string ordering and Path ordering
    # disagree.
    vault = example_project / "research"
    (vault / "questions-extra").mkdir()
    (vault / "questions-extra" / "note.md").write_text(
        "---\nid: x\n---\n", encoding="utf-8"
    )
    discovered = discover_project(example_project)

    files = discover_node_files(discovered)

    assert list(files) == sorted(files)


@pytest.mark.contract
def test_discovery_does_not_descend_into_a_symlinked_directory(
    example_project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "smuggled.md").write_text("---\nid: unsafe\n---\n", encoding="utf-8")
    link = example_project / "research" / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("platform does not support symlinks")

    discovered = discover_project(example_project)

    assert all("smuggled" not in path.name for path in discover_node_files(discovered))
