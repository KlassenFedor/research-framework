"""Generate a synthetic but valid research vault of a requested node count."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from research_framework.storage.markdown_codec import DecodedMarkdown, MarkdownCodec
from research_framework.storage.yaml_codec import dump_restricted_yaml

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODEC = MarkdownCodec()

TS = "2026-08-17T10:00:00+00:00"
ACTOR = {"kind": "human", "id": "bench-author"}

FOLDERS = {
    "question": "questions",
    "hypothesis": "hypotheses",
    "claim": "claims",
    "experiment": "experiments",
    "run": "runs",
    "evidence": "evidence",
    "assessment": "assessments",
    "source": "sources",
    "artifact": "artifacts",
    "decision": "decisions",
}
PREFIXES = {
    "question": "que",
    "hypothesis": "hyp",
    "claim": "clm",
    "experiment": "exp",
    "run": "run",
    "evidence": "evd",
    "assessment": "asm",
    "source": "src",
    "artifact": "art",
    "decision": "dec",
}

# One repeating unit: 11 nodes, ~16 outgoing relations (~1.45 per node).
UNIT = (
    "question",
    "hypothesis",
    "claim",
    "experiment",
    "run",
    "evidence",
    "evidence",
    "assessment",
    "source",
    "artifact",
    "decision",
)
UNIT_SIZE = len(UNIT)

BODY = (
    "\n# Synthetic node\n\n"
    "Generated for benchmarking. The body is deliberately of a realistic size so "
    "that byte-level costs (read, decode, offset handling) are not understated.\n\n"
    "Paragraph two keeps the file around a kilobyte, which matches the shape of "
    "hand-written research notes in this framework rather than a stub.\n"
)


def ulid(value: int) -> str:
    out = ["0"] * 26
    for index in range(25, -1, -1):
        out[index] = CROCKFORD[value & 31]
        value >>= 5
    return "".join(out)


def node_id(kind: str, serial: int) -> str:
    return f"{PREFIXES[kind]}-{ulid((1 << 125) | serial)}"


def rel_id(serial: int) -> str:
    return f"rel-{ulid((1 << 125) | serial)}"


def relation(counter: list[int], kind: str, target: str) -> dict[str, object]:
    counter[0] += 1
    return {
        "id": rel_id(counter[0]),
        "kind": kind,
        "target": target,
        "created_at": TS,
        "created_by": dict(ACTOR),
    }


def kind_fields(kind: str, serial: int) -> dict[str, object]:
    if kind == "question":
        return {"question": f"Does change {serial} move the target metric?"}
    if kind == "hypothesis":
        return {
            "statement": f"Change {serial} improves the target metric.",
            "falsification_criteria": "No improvement above noise across three runs.",
        }
    if kind == "claim":
        return {"statement": f"Change {serial} has a measurable cost."}
    if kind == "experiment":
        return {
            "objective": f"Measure the effect of change {serial}.",
            "method": "Run the fixed benchmark in both configurations.",
            "success_criteria": "Recall improves by at least ten percent.",
            "protocol_version": 1,
        }
    if kind == "run":
        return {
            "started_at": TS,
            "finished_at": TS,
            "outcome": "completed",
            "environment": {"host": "bench", "cores": 12},
        }
    if kind == "evidence":
        return {
            "observation": f"Observation {serial} recorded from the run.",
            "evidence_kind": "quantitative",
            "collected_at": TS,
        }
    if kind == "assessment":
        return {
            "verdict": "supported",
            "confidence": "medium",
            "review_state": "approved",
        }
    if kind == "source":
        return {
            "source_kind": "paper",
            "locator": f"https://example.invalid/paper/{serial}",
            "citation": f"Author {serial}. Synthetic paper.",
        }
    if kind == "artifact":
        return {
            "locator": f"artifacts/run-{serial}.json",
            "media_type": "application/json",
            "size": 4096,
        }
    if kind == "decision":
        return {
            "outcome": f"Adopt change {serial}.",
            "rationale": "The assessment supports the hypothesis.",
        }
    raise ValueError(kind)


def build_unit(unit_index: int, counter: list[int]) -> list[tuple[str, dict]]:
    base = unit_index * UNIT_SIZE
    ids = {}
    serials = {}
    seen: dict[str, int] = {}
    for offset, kind in enumerate(UNIT):
        occurrence = seen.get(kind, 0)
        seen[kind] = occurrence + 1
        key = kind if occurrence == 0 else f"{kind}{occurrence + 1}"
        serials[key] = base + offset
        ids[key] = node_id(kind, base + offset)

    rels: dict[str, list[dict]] = {key: [] for key in ids}
    rels["hypothesis"].append(relation(counter, "addresses", ids["question"]))
    rels["claim"].append(relation(counter, "addresses", ids["question"]))
    rels["claim"].append(relation(counter, "derived_from", ids["source"]))
    rels["experiment"].append(relation(counter, "tests", ids["hypothesis"]))
    rels["run"].append(relation(counter, "instance_of", ids["experiment"]))
    rels["run"].append(relation(counter, "produces", ids["evidence"]))
    rels["run"].append(relation(counter, "produces", ids["evidence2"]))
    rels["run"].append(relation(counter, "produces", ids["artifact"]))
    rels["evidence"].append(relation(counter, "derived_from", ids["run"]))
    rels["evidence"].append(relation(counter, "supports", ids["hypothesis"]))
    rels["evidence2"].append(relation(counter, "derived_from", ids["run"]))
    rels["evidence2"].append(relation(counter, "challenges", ids["hypothesis"]))
    rels["assessment"].append(relation(counter, "assesses", ids["hypothesis"]))
    rels["assessment"].append(relation(counter, "based_on", ids["evidence"]))
    rels["assessment"].append(relation(counter, "based_on", ids["evidence2"]))
    rels["decision"].append(relation(counter, "based_on", ids["assessment"]))
    # One cross-unit edge keeps the graph connected instead of a pile of islands.
    if unit_index > 0:
        previous = node_id("hypothesis", (unit_index - 1) * UNIT_SIZE + 1)
        rels["hypothesis"].append(relation(counter, "decomposes", previous))

    documents = []
    for key, identifier in ids.items():
        kind = key.rstrip("23456789") if key[-1].isdigit() else key
        serial = serials[key]
        metadata: dict[str, object] = {
            "format_version": 1,
            "id": identifier,
            "kind": kind,
            "title": f"Synthetic {kind} {serial}",
            "status": "active",
            "summary": f"Synthetic {kind} number {serial} generated for benchmarking.",
        }
        metadata.update(kind_fields(kind, serial))
        metadata["tags"] = ["bench", f"unit-{unit_index % 50}"]
        metadata["aliases"] = [f"{PREFIXES[kind]}-{serial}"]
        metadata["created_at"] = TS
        metadata["created_by"] = dict(ACTOR)
        metadata["updated_at"] = TS
        metadata["updated_by"] = dict(ACTOR)
        if rels[key]:
            metadata["relations"] = rels[key]
        documents.append((kind, metadata))
    return documents


def write_vault(root: Path, node_count: int) -> tuple[int, int]:
    vault = root / "research"
    vault.mkdir(parents=True)
    for folder in FOLDERS.values():
        (vault / folder).mkdir()
    (vault / "PROJECT.md").write_text("# Benchmark project\n", encoding="utf-8")
    config = {
        "format_version": 1,
        "project_id": f"prj-{ulid((1 << 125) | 999999)}",
        "title": "Benchmark project",
        "vault": "research",
        "default_language": "en",
        "policies": {
            "require_falsification_criteria": True,
            "require_evidence_provenance": True,
            "forbid_dependency_cycles": True,
        },
    }
    (root / "research.yaml").write_text(dump_restricted_yaml(config), encoding="utf-8")

    counter = [0]
    written = 0
    units = (node_count + UNIT_SIZE - 1) // UNIT_SIZE
    for unit_index in range(units):
        for kind, metadata in build_unit(unit_index, counter):
            identifier = str(metadata["id"])
            slug = str(metadata["title"]).lower().replace(" ", "-")
            path = vault / FOLDERS[kind] / f"{identifier}--{slug}.md"
            document = DecodedMarkdown(metadata=metadata, body=BODY, path=path)
            text = CODEC.encode(document)
            path.write_text(text, encoding="utf-8")
            written += 1
    return written, counter[0]


if __name__ == "__main__":
    target = Path(sys.argv[1])
    count = int(sys.argv[2])
    nodes, edges = write_vault(target, count)
    print(f"{nodes} nodes, {edges} relations at {target}")
