from __future__ import annotations

import pytest

from research_framework import Actor, ActorKind


@pytest.mark.contract
def test_human_actor_has_stable_machine_readable_identity() -> None:
    actor = Actor.human("fedor")

    assert actor.kind is ActorKind.HUMAN
    assert actor.id == "fedor"
    assert actor.run_id is None
    assert actor.model is None


@pytest.mark.contract
def test_agent_actor_preserves_run_and_model_provenance() -> None:
    actor = Actor.agent(
        "literature-reviewer",
        run_id="run-2026-08-17-001",
        model="example-model",
    )

    assert actor.kind is ActorKind.AGENT
    assert actor.id == "literature-reviewer"
    assert actor.run_id == "run-2026-08-17-001"
    assert actor.model == "example-model"


@pytest.mark.contract
@pytest.mark.parametrize("actor_id", ["", " ", "\n"])
def test_actor_rejects_blank_id(actor_id: str) -> None:
    with pytest.raises(ValueError, match="id"):
        Actor.human(actor_id)


@pytest.mark.contract
def test_actor_is_immutable() -> None:
    actor = Actor.human("fedor")

    with pytest.raises((AttributeError, TypeError)):
        actor.id = "someone-else"  # type: ignore[misc]
