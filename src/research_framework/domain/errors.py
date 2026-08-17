from __future__ import annotations

from pathlib import Path
from typing import Any

from .diagnostics import Diagnostic
from .enums import DiagnosticSeverity


class ResearchFrameworkError(Exception):
    code = "research_framework_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ProjectNotFound(ResearchFrameworkError):
    code = "project_not_found"

    def __init__(self, start: Path) -> None:
        self.start = start
        super().__init__(
            f"Research project not found from {start}", details={"start": str(start)}
        )


class NodeNotFound(ResearchFrameworkError):
    code = "node_not_found"

    def __init__(self, reference: str) -> None:
        self.reference = reference
        super().__init__(
            f"Node not found: {reference}", details={"reference": reference}
        )


class EdgeNotFound(ResearchFrameworkError):
    code = "edge_not_found"


class AmbiguousReference(ResearchFrameworkError):
    code = "ambiguous_reference"

    def __init__(self, reference: str, candidates: tuple[str, ...]) -> None:
        self.reference = reference
        self.candidates = candidates
        super().__init__(
            f"Ambiguous reference: {reference}",
            details={"reference": reference, "candidates": list(candidates)},
        )


class ValidationFailed(ResearchFrameworkError):
    code = "validation_failed"

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        errors = sum(
            diagnostic.severity is DiagnosticSeverity.ERROR
            for diagnostic in diagnostics
        )
        super().__init__(
            f"Validation failed with {errors} error(s)",
            details={"diagnostics": [item.to_dict() for item in diagnostics]},
        )


class RevisionConflict(ResearchFrameworkError):
    code = "revision_conflict"

    def __init__(
        self,
        node_id: str,
        expected_revision: str,
        actual_revision: str,
    ) -> None:
        self.node_id = node_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"Revision conflict for {node_id}",
            details={
                "node_id": node_id,
                "expected_revision": expected_revision,
                "actual_revision": actual_revision,
            },
        )


class UnsupportedFormatVersion(ResearchFrameworkError):
    code = "unsupported_format_version"

    def __init__(self, found: int, supported: set[int]) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            f"Unsupported format version {found}",
            details={"found": found, "supported": sorted(supported)},
        )


class StorageError(ResearchFrameworkError):
    code = "storage_error"
