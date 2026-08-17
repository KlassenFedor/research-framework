from __future__ import annotations

from dataclasses import dataclass

from .enums import ActorKind


@dataclass(frozen=True, slots=True)
class Actor:
    kind: ActorKind
    id: str
    run_id: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("actor id must not be blank")

    @classmethod
    def human(cls, actor_id: str) -> Actor:
        return cls(kind=ActorKind.HUMAN, id=actor_id)

    @classmethod
    def agent(
        cls,
        actor_id: str,
        *,
        run_id: str | None = None,
        model: str | None = None,
    ) -> Actor:
        return cls(
            kind=ActorKind.AGENT,
            id=actor_id,
            run_id=run_id,
            model=model,
        )
