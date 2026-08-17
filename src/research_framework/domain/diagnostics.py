from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from .enums import DiagnosticSeverity


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: DiagnosticSeverity
    code: str
    message: str
    path: Path | None = None
    node_id: str | None = None
    edge_id: str | None = None
    field: str | None = None
    suggestion: str | None = None
    details: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "path": str(self.path) if self.path is not None else None,
            "node_id": self.node_id,
            "edge_id": self.edge_id,
            "field": self.field,
            "suggestion": self.suggestion,
            "details": self.details,
        }
