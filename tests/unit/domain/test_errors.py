from __future__ import annotations

from pathlib import Path

import pytest

from research_framework import (
    AmbiguousReference,
    Diagnostic,
    DiagnosticSeverity,
    EdgeNotFound,
    NodeNotFound,
    ProjectNotFound,
    ResearchFrameworkError,
    RevisionConflict,
    StorageError,
    UnsupportedFormatVersion,
    ValidationFailed,
)


@pytest.mark.contract
def test_public_errors_share_one_stable_base_class() -> None:
    errors = (
        ProjectNotFound,
        NodeNotFound,
        EdgeNotFound,
        AmbiguousReference,
        ValidationFailed,
        RevisionConflict,
        UnsupportedFormatVersion,
        StorageError,
    )

    assert all(issubclass(error, ResearchFrameworkError) for error in errors)


@pytest.mark.contract
def test_error_has_human_message_and_machine_code() -> None:
    error = NodeNotFound("hyp-missing")

    assert error.code == "node_not_found"
    assert "hyp-missing" in str(error)
    assert error.details == {"reference": "hyp-missing"}


@pytest.mark.contract
def test_diagnostic_has_stable_machine_readable_shape() -> None:
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        code="dangling_relation",
        message="Relation target does not exist",
        path=Path("research/evidence/example.md"),
        node_id="evd-example",
        edge_id="rel-example",
        field="relations[0].target",
        suggestion="Create the target or remove the relation",
    )

    assert diagnostic.to_dict() == {
        "severity": "error",
        "code": "dangling_relation",
        "message": "Relation target does not exist",
        "path": "research/evidence/example.md",
        "node_id": "evd-example",
        "edge_id": "rel-example",
        "field": "relations[0].target",
        "suggestion": "Create the target or remove the relation",
        "details": {},
    }


@pytest.mark.contract
def test_validation_failed_preserves_all_diagnostics() -> None:
    diagnostics = (
        Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="first",
            message="First error",
        ),
        Diagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="second",
            message="Warning",
        ),
    )

    error = ValidationFailed(diagnostics)

    assert error.diagnostics == diagnostics
    assert error.code == "validation_failed"
    assert "1 error" in str(error)
