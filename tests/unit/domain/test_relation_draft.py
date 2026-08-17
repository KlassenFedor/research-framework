from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from research_framework import EdgeKind, RelationDraft


@pytest.mark.contract
def test_relation_draft_normalizes_string_kind() -> None:
    draft = RelationDraft("supports", "hyp-01J00000000000000000000002")  # type: ignore[arg-type]

    assert draft.kind is EdgeKind.SUPPORTS


@pytest.mark.contract
@pytest.mark.parametrize(
    ("kind", "target", "rationale", "message"),
    [
        ("unknown", "hyp-01J00000000000000000000002", None, "unknown"),
        (EdgeKind.SUPPORTS, "", None, "target"),
        (EdgeKind.SUPPORTS, "   ", None, "target"),
        (EdgeKind.SUPPORTS, "hyp-01J00000000000000000000002", "", "rationale"),
    ],
)
def test_relation_draft_rejects_invalid_caller_fields(
    kind: object,
    target: str,
    rationale: str | None,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        RelationDraft(kind, target, rationale)  # type: ignore[arg-type]


@pytest.mark.contract
def test_relation_draft_is_immutable() -> None:
    draft = RelationDraft(EdgeKind.SUPPORTS, "hyp-01J00000000000000000000002")

    with pytest.raises(FrozenInstanceError):
        draft.target = "hyp-01J00000000000000000000003"  # type: ignore[misc]
