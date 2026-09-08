"""Break the cold validate path into phases and time each one separately."""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from research_framework.storage.discovery import discover_node_files, discover_project
from research_framework.storage.index_cache import (
    FileFingerprint,
    load_index,
    write_index,
)
from research_framework.storage.markdown_codec import MarkdownCodec
from research_framework.storage.yaml_codec import (
    load_restricted_yaml,
)
from research_framework.validation import validator as V

VAULT = Path(sys.argv[1])
codec = MarkdownCodec()
phases: dict[str, float] = {}


def mark(name: str, started: float) -> float:
    now = time.perf_counter()
    phases[name] = phases.get(name, 0.0) + (now - started)
    return now


start = time.perf_counter()
project = discover_project(VAULT)
paths = discover_node_files(project)
mark("discover", start)

texts: list[str] = []
raws: list[bytes] = []
for path in paths:
    start = time.perf_counter()
    FileFingerprint.from_path(path)
    start = mark("stat", start)
    raw = path.read_bytes()
    start = mark("read_bytes", start)
    text = raw.decode("utf-8")
    mark("utf8_decode", start)
    raws.append(raw)
    texts.append(text)

headers: list[object] = []
for path, text in zip(paths, texts):
    start = time.perf_counter()
    header = codec.decode_header(text, path=path)
    mark("decode_header_total", start)
    headers.append(header)

# Isolate the YAML cost inside decode_header.
front_matters: list[str] = []
for text in texts:
    start = time.perf_counter()
    end = text.index("\n---", 4)
    front = text[4:end]
    mark("split_front_matter", start)
    front_matters.append(front)
for front in front_matters:
    start = time.perf_counter()
    load_restricted_yaml(front)
    mark("yaml_load", start)

start = time.perf_counter()
for raw in raws:
    hashlib.sha256(raw).hexdigest()
mark("sha256", start)

records = []
diagnostics: list[object] = []
for path, header in zip(paths, headers):
    relative = path.relative_to(project.root)
    record = V._Record(
        path=relative,
        metadata=dict(header.metadata),
        body_offset=header.body_offset,
        revision=None,
    )
    records.append(record)

start = time.perf_counter()
for record in records:
    V._validate_structural(record, diagnostics)
mark("structural", start)

start = time.perf_counter()
V._validate_global(
    records,
    diagnostics,
    root=project.root,
    require_evidence_provenance=project.config.policies.require_evidence_provenance,
    forbid_dependency_cycles=project.config.policies.forbid_dependency_cycles,
)
mark("global", start)

# Canonical re-encode, the formatter path.
start = time.perf_counter()
for path, text in zip(paths, texts):
    document = codec.decode(text, path=path)
    encoded = codec.encode(document).encode("utf-8")
    codec.decode(encoded.decode("utf-8"), path=path)
mark("format_roundtrip", start)

start = time.perf_counter()
cached = load_index(project)
mark("cache_load", start)
phases["cache_entries"] = float(len(cached))
if cached:
    start = time.perf_counter()
    write_index(project, list(cached.values()))
    mark("cache_write", start)

phases["nodes"] = float(len(paths))
phases["peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
print(json.dumps(phases, indent=2))
