from __future__ import annotations

import json
from importlib import resources
from typing import Any


def _load(name: str) -> dict[str, Any]:
    resource = resources.files(__package__).joinpath(name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON Schema resource must be an object: {name}")
    return value


def node_schema() -> dict[str, Any]:
    """Return an independent copy of the format-version 1 Node schema."""

    return _load("node-v1.schema.json")


def project_schema() -> dict[str, Any]:
    """Return an independent copy of the format-version 1 project schema."""

    return _load("project-v1.schema.json")


__all__ = ["node_schema", "project_schema"]
