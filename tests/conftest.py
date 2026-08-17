from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_PROJECT = FIXTURES / "example_project"

NODE_IDS = {
    "question": "que-01J00000000000000000000001",
    "hypothesis": "hyp-01J00000000000000000000002",
    "claim": "clm-01J00000000000000000000003",
    "experiment": "exp-01J00000000000000000000004",
    "run": "run-01J00000000000000000000005",
    "evidence": "evd-01J00000000000000000000006",
    "assessment": "asm-01J00000000000000000000007",
    "source": "src-01J00000000000000000000008",
    "artifact": "art-01J00000000000000000000009",
    "decision": "dec-01J0000000000000000000000A",
    "challenging_evidence": "evd-01J0000000000000000000000B",
}

RELATION_IDS = {
    "addresses": "rel-01J0000000000000000000000C",
    "tests": "rel-01J0000000000000000000000D",
    "instance_of": "rel-01J0000000000000000000000E",
    "produces_evidence": "rel-01J0000000000000000000000F",
    "produces_artifact": "rel-01J0000000000000000000000G",
    "derived_from_run": "rel-01J0000000000000000000000H",
    "supports": "rel-01J0000000000000000000000J",
    "derived_from_source": "rel-01J0000000000000000000000K",
    "challenges": "rel-01J0000000000000000000000M",
    "assesses": "rel-01J0000000000000000000000N",
    "based_on_support": "rel-01J0000000000000000000000P",
    "based_on_challenge": "rel-01J0000000000000000000000Q",
    "claim_address": "rel-01J0000000000000000000000R",
    "decision_basis": "rel-01J0000000000000000000000S",
}

ACTOR = {"kind": "human", "id": "test-author"}
TIMESTAMP = "2026-08-17T10:00:00+07:00"


@pytest.fixture
def example_project(tmp_path: Path) -> Path:
    destination = tmp_path / "example-project"
    shutil.copytree(EXAMPLE_PROJECT, destination)
    return destination


def relation(
    relation_id: str,
    kind: str,
    target: str,
    *,
    rationale: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": relation_id,
        "kind": kind,
        "target": target,
        "created_at": TIMESTAMP,
        "created_by": ACTOR.copy(),
    }
    if rationale is not None:
        value["rationale"] = rationale
    return value


def node_metadata(kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "format_version": 1,
        "id": NODE_IDS[kind],
        "kind": kind,
        "title": f"Test {kind}",
        "status": "active",
        "created_at": TIMESTAMP,
        "created_by": ACTOR.copy(),
        "updated_at": TIMESTAMP,
        "updated_by": ACTOR.copy(),
        "relations": [],
    }
    special_fields: dict[str, dict[str, Any]] = {
        "question": {"question": "What is being tested?"},
        "hypothesis": {
            "statement": "The intervention improves the result.",
            "falsification_criteria": "The improvement is below 10%.",
        },
        "claim": {"statement": "The measured value increased."},
        "experiment": {
            "objective": "Measure the intervention.",
            "method": "Run a controlled benchmark.",
            "success_criteria": "At least 10% improvement.",
            "protocol_version": 1,
        },
        "run": {
            "started_at": TIMESTAMP,
            "outcome": "completed",
        },
        "evidence": {
            "observation": "The result improved by 13%.",
            "evidence_kind": "quantitative",
        },
        "assessment": {
            "verdict": "supported",
            "confidence": "high",
            "review_state": "approved",
        },
        "source": {
            "source_kind": "paper",
            "locator": "https://example.test/paper",
        },
        "artifact": {"locator": "artifacts/result.json"},
        "decision": {
            "outcome": "Adopt the intervention.",
            "rationale": "The approved assessment supports it.",
        },
    }
    metadata.update(special_fields[kind])
    return metadata


def markdown_document(metadata: dict[str, Any], body: str = "\n# Body\n") -> str:
    # JSON is a strict subset of YAML. This helper avoids coupling tests to the
    # YAML library selected by the implementation.
    front_matter = json.dumps(metadata, ensure_ascii=False, indent=2)
    return f"---\n{front_matter}\n---\n{body}"


def write_node(
    root: Path,
    relative_path: str,
    metadata: dict[str, Any],
    body: str = "\n# Body\n",
) -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown_document(metadata, body), encoding="utf-8")
    return target
