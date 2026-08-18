from __future__ import annotations

from pathlib import Path
from typing import Never

import pytest

import research_framework.validation.validator as validator_module
from research_framework import Actor, ClaimDraft, EdgeKind, Project
from tests.conftest import NODE_IDS


@pytest.mark.contract
@pytest.mark.integration
def test_mutations_do_not_rescan_or_reload_unchanged_vault(
    example_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project.open(example_project)
    original_snapshot = project.snapshot()

    def reject_full_scan(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise AssertionError("mutation performed a full vault scan")

    with monkeypatch.context() as patch:
        patch.setattr(validator_module, "_load_records", reject_full_scan)
        created = project.create_node(
            ClaimDraft(
                title="Incremental mutation",
                statement="Mutations reuse the loaded graph.",
            ),
            actor=Actor.human("author"),
        )
        updated = project.update_node(
            created.id,
            patch={"summary": "Updated without a vault scan."},
            expected_revision=created.revision,
            actor=Actor.human("editor"),
        )
        edge = project.add_edge(
            source=updated.id,
            kind=EdgeKind.RELATED_TO,
            target=NODE_IDS["claim"],
            actor=Actor.human("editor"),
        )
        project.remove_edge(edge.id, actor=Actor.human("editor"))

    assert created.id not in {node.id for node in original_snapshot.list_nodes()}
    assert project.snapshot().get_node(created.id).summary == (
        "Updated without a vault scan."
    )
    assert project.validate() == ()
