from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from research_framework.domain.diagnostics import Diagnostic
from research_framework.domain.edges import relation_is_allowed
from research_framework.domain.enums import (
    DiagnosticSeverity,
    EdgeKind,
    NodeKind,
    NodeStatus,
)
from research_framework.domain.graph import Edge, GraphSnapshot
from research_framework.progress import ProgressCallback, notify_progress
from research_framework.storage.discovery import (
    DiscoveredProject,
    discover_node_files,
    discover_project,
)
from research_framework.storage.loader import parse_edges, parse_node
from research_framework.storage.markdown_codec import (
    DecodedMarkdown,
    MarkdownCodec,
    MarkdownCodecError,
)

_ULID = r"[0-9A-HJKMNP-TV-Z]{26}"
_NODE_PREFIXES = {
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
_NODE_ID = re.compile(rf"^(?:{'|'.join(_NODE_PREFIXES.values())})-{_ULID}$")
_EDGE_ID = re.compile(rf"^rel-{_ULID}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIMEZONE_SUFFIX = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")

_COMMON_FIELDS = {
    "format_version",
    "id",
    "kind",
    "title",
    "status",
    "summary",
    "tags",
    "aliases",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "relations",
    "extensions",
}
_SPECIAL_FIELDS: dict[str, set[str]] = {
    "question": {"question", "scope"},
    "hypothesis": {"statement", "falsification_criteria", "assumptions"},
    "claim": {"statement"},
    "experiment": {"objective", "method", "success_criteria", "protocol_version"},
    "run": {"started_at", "finished_at", "outcome", "environment"},
    "evidence": {"observation", "evidence_kind", "collected_at"},
    "assessment": {"verdict", "confidence", "limitations", "review_state"},
    "source": {"source_kind", "locator", "citation", "accessed_at"},
    "artifact": {"locator", "media_type", "sha256", "size"},
    "decision": {"outcome", "rationale"},
}
_REQUIRED_COMMON = {
    "format_version",
    "id",
    "kind",
    "title",
    "status",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
}
_REQUIRED_SPECIAL: dict[str, set[str]] = {
    "question": {"question"},
    "hypothesis": {"statement", "falsification_criteria"},
    "claim": {"statement"},
    "experiment": {"objective", "method", "success_criteria", "protocol_version"},
    "run": {"started_at", "outcome"},
    "evidence": {"observation", "evidence_kind"},
    "assessment": {"verdict", "confidence", "review_state"},
    "source": {"source_kind", "locator"},
    "artifact": {"locator"},
    "decision": {"outcome", "rationale"},
}


@dataclass(slots=True)
class _Record:
    path: Path
    metadata: dict[str, Any]
    document: DecodedMarkdown | None = None
    revision: str | None = None

    @property
    def node_id(self) -> str | None:
        value = self.metadata.get("id")
        return value if isinstance(value, str) else None

    @property
    def kind(self) -> NodeKind | None:
        try:
            return NodeKind(self.metadata.get("kind"))
        except (TypeError, ValueError):
            return None


def _diagnostic(
    code: str,
    message: str,
    *,
    path: Path | None = None,
    node_id: str | None = None,
    edge_id: str | None = None,
    field: str | None = None,
    suggestion: str | None = None,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    details: dict[str, Any] | None = None,
) -> Diagnostic:
    return Diagnostic(
        severity=severity,
        code=code,
        message=message,
        path=path,
        node_id=node_id,
        edge_id=edge_id,
        field=field,
        suggestion=suggestion,
        details=details or {},
    )


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_datetime(
    value: Any,
    *,
    field: str,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> datetime | None:
    if not isinstance(value, str):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                f"{field} must be an ISO 8601 string",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                "invalid_timestamp",
                f"{field} is not a valid ISO 8601 timestamp",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        diagnostics.append(
            _diagnostic(
                "timezone_required",
                f"{field} must include a timezone",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    if _TIMEZONE_SUFFIX.search(value) is None:
        diagnostics.append(
            _diagnostic(
                "invalid_timestamp",
                f"{field} must end with Z or a ±HH:MM timezone offset",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    return parsed


def _parse_date(
    value: Any,
    *,
    field: str,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> date | None:
    if not isinstance(value, str):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                f"{field} must be an ISO 8601 date string",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    if _DATE.fullmatch(value) is None:
        diagnostics.append(
            _diagnostic(
                "invalid_date",
                f"{field} must use YYYY-MM-DD format",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                "invalid_date",
                f"{field} is not a valid ISO 8601 date",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None


def _validate_actor(
    actor: Any,
    *,
    field: str,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(actor, dict):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                f"{field} must be a mapping",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return
    allowed = {"kind", "id", "run_id", "model"}
    for unknown in sorted(set(actor) - allowed):
        diagnostics.append(
            _diagnostic(
                "unknown_field",
                f"unknown actor field: {unknown}",
                path=record.path,
                node_id=record.node_id,
                field=f"{field}.{unknown}",
            )
        )
    if actor.get("kind") not in {"human", "agent"}:
        diagnostics.append(
            _diagnostic(
                "invalid_actor_kind",
                "actor kind must be human or agent",
                path=record.path,
                node_id=record.node_id,
                field=f"{field}.kind",
            )
        )
    actor_id = actor.get("id")
    if not isinstance(actor_id, str) or not actor_id.strip():
        diagnostics.append(
            _diagnostic(
                "invalid_actor_id",
                "actor id must be a non-blank string",
                path=record.path,
                node_id=record.node_id,
                field=f"{field}.id",
            )
        )
    for optional in ("run_id", "model"):
        if optional not in actor:
            continue
        value = actor[optional]
        if not isinstance(value, str) or not value.strip():
            diagnostics.append(
                _diagnostic(
                    "invalid_field_type",
                    f"{field}.{optional} must be a non-blank string",
                    path=record.path,
                    node_id=record.node_id,
                    field=f"{field}.{optional}",
                )
            )


def _validate_string_list(
    value: Any,
    *,
    field: str,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> list[str] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                f"{field} must be a list of non-blank strings",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )
        return None
    return value


def _validate_text_field(
    metadata: Mapping[str, Any],
    *,
    field: str,
    record: _Record,
    diagnostics: list[Diagnostic],
    non_blank: bool = True,
) -> None:
    if field not in metadata:
        return
    value = metadata[field]
    if not isinstance(value, str) or (non_blank and not value.strip()):
        qualifier = "non-blank " if non_blank else ""
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                f"{field} must be a {qualifier}string",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )


def _validate_structural(record: _Record, diagnostics: list[Diagnostic]) -> None:
    metadata = record.metadata
    kind_value = metadata.get("kind")
    kind = record.kind

    for field in sorted(
        _REQUIRED_COMMON | _REQUIRED_SPECIAL.get(str(kind_value), set())
    ):
        if field not in metadata or _is_missing(metadata.get(field)):
            diagnostics.append(
                _diagnostic(
                    "missing_required_field",
                    f"required field is missing: {field}",
                    path=record.path,
                    node_id=record.node_id,
                    field=field,
                )
            )

    allowed = _COMMON_FIELDS | _SPECIAL_FIELDS.get(str(kind_value), set())
    for field in sorted(set(metadata) - allowed):
        diagnostics.append(
            _diagnostic(
                "unknown_field",
                f"unknown top-level field: {field}",
                path=record.path,
                node_id=record.node_id,
                field=field,
            )
        )

    version = metadata.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        diagnostics.append(
            _diagnostic(
                "unsupported_format_version",
                "node format_version must be 1",
                path=record.path,
                node_id=record.node_id,
                field="format_version",
            )
        )

    node_id = metadata.get("id")
    if not isinstance(node_id, str) or not _NODE_ID.fullmatch(node_id):
        diagnostics.append(
            _diagnostic(
                "invalid_node_id",
                "node id must contain a kind prefix and ULID",
                path=record.path,
                node_id=node_id if isinstance(node_id, str) else None,
                field="id",
            )
        )
    elif kind is not None and not node_id.startswith(f"{_NODE_PREFIXES[kind.value]}-"):
        diagnostics.append(
            _diagnostic(
                "invalid_node_id",
                "node id prefix does not match kind",
                path=record.path,
                node_id=node_id,
                field="id",
            )
        )

    if kind is None:
        diagnostics.append(
            _diagnostic(
                "invalid_node_kind",
                "kind is not an MVP node kind",
                path=record.path,
                node_id=record.node_id,
                field="kind",
            )
        )
    try:
        NodeStatus(metadata.get("status"))
    except (TypeError, ValueError):
        diagnostics.append(
            _diagnostic(
                "invalid_status",
                "status is not a valid lifecycle state",
                path=record.path,
                node_id=record.node_id,
                field="status",
            )
        )

    for field in ("title", "summary"):
        if field in metadata and not isinstance(metadata[field], str):
            diagnostics.append(
                _diagnostic(
                    "invalid_field_type",
                    f"{field} must be a string",
                    path=record.path,
                    node_id=record.node_id,
                    field=field,
                )
            )

    tags = metadata.get("tags")
    if "tags" in metadata:
        _validate_string_list(
            tags, field="tags", record=record, diagnostics=diagnostics
        )
    aliases = metadata.get("aliases")
    if "aliases" in metadata:
        valid_aliases = _validate_string_list(
            aliases, field="aliases", record=record, diagnostics=diagnostics
        )
        if valid_aliases is not None and len(set(valid_aliases)) != len(valid_aliases):
            diagnostics.append(
                _diagnostic(
                    "duplicate_alias",
                    "aliases must be unique",
                    path=record.path,
                    node_id=record.node_id,
                    field="aliases",
                )
            )

    created = _parse_datetime(
        metadata.get("created_at"),
        field="created_at",
        record=record,
        diagnostics=diagnostics,
    )
    updated = _parse_datetime(
        metadata.get("updated_at"),
        field="updated_at",
        record=record,
        diagnostics=diagnostics,
    )
    if created is not None and updated is not None and updated < created:
        diagnostics.append(
            _diagnostic(
                "updated_before_created",
                "updated_at cannot precede created_at",
                path=record.path,
                node_id=record.node_id,
                field="updated_at",
            )
        )
    _validate_actor(
        metadata.get("created_by"),
        field="created_by",
        record=record,
        diagnostics=diagnostics,
    )
    _validate_actor(
        metadata.get("updated_by"),
        field="updated_by",
        record=record,
        diagnostics=diagnostics,
    )

    extensions = metadata.get("extensions")
    if "extensions" in metadata and not isinstance(extensions, dict):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                "extensions must be a mapping",
                path=record.path,
                node_id=record.node_id,
                field="extensions",
            )
        )

    _validate_kind_fields(record, diagnostics)
    _validate_relations(record, diagnostics)


def _validate_kind_fields(record: _Record, diagnostics: list[Diagnostic]) -> None:
    metadata = record.metadata
    kind = record.kind
    text_fields: dict[NodeKind, tuple[tuple[str, bool], ...]] = {
        NodeKind.QUESTION: (("question", True), ("scope", False)),
        NodeKind.HYPOTHESIS: (
            ("statement", True),
            ("falsification_criteria", True),
        ),
        NodeKind.CLAIM: (("statement", True),),
        NodeKind.EXPERIMENT: (
            ("objective", True),
            ("method", True),
            ("success_criteria", True),
        ),
        NodeKind.EVIDENCE: (("observation", True),),
        NodeKind.SOURCE: (("locator", True), ("citation", False)),
        NodeKind.ARTIFACT: (("locator", True), ("media_type", True)),
        NodeKind.DECISION: (("outcome", True), ("rationale", True)),
    }
    if kind is not None:
        for field, non_blank in text_fields.get(kind, ()):
            _validate_text_field(
                metadata,
                field=field,
                record=record,
                diagnostics=diagnostics,
                non_blank=non_blank,
            )

    if kind is NodeKind.HYPOTHESIS:
        assumptions = metadata.get("assumptions")
        if "assumptions" in metadata:
            _validate_string_list(
                assumptions,
                field="assumptions",
                record=record,
                diagnostics=diagnostics,
            )
    elif kind is NodeKind.EXPERIMENT:
        protocol = metadata.get("protocol_version")
        if not (
            (isinstance(protocol, int) and not isinstance(protocol, bool))
            or (isinstance(protocol, str) and bool(protocol.strip()))
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_protocol_version",
                    "protocol_version must be an integer or non-blank string",
                    path=record.path,
                    node_id=record.node_id,
                    field="protocol_version",
                )
            )
    if kind is NodeKind.RUN:
        outcome = metadata.get("outcome")
        if outcome not in {"running", "completed", "failed", "cancelled"}:
            diagnostics.append(
                _diagnostic(
                    "invalid_run_outcome",
                    "invalid run outcome",
                    path=record.path,
                    node_id=record.node_id,
                    field="outcome",
                )
            )
        started = _parse_datetime(
            metadata.get("started_at"),
            field="started_at",
            record=record,
            diagnostics=diagnostics,
        )
        finished_value = metadata.get("finished_at")
        finished = None
        if "finished_at" in metadata:
            finished = _parse_datetime(
                finished_value,
                field="finished_at",
                record=record,
                diagnostics=diagnostics,
            )
        if outcome in {"completed", "failed", "cancelled"} and finished_value is None:
            diagnostics.append(
                _diagnostic(
                    "finished_at_required",
                    "finished run requires finished_at",
                    path=record.path,
                    node_id=record.node_id,
                    field="finished_at",
                )
            )
        if started is not None and finished is not None and finished < started:
            diagnostics.append(
                _diagnostic(
                    "run_time_order",
                    "finished_at cannot precede started_at",
                    path=record.path,
                    node_id=record.node_id,
                    field="finished_at",
                )
            )
        environment = metadata.get("environment")
        if "environment" in metadata and not isinstance(environment, dict):
            diagnostics.append(
                _diagnostic(
                    "invalid_field_type",
                    "environment must be a mapping",
                    path=record.path,
                    node_id=record.node_id,
                    field="environment",
                )
            )
    elif kind is NodeKind.EVIDENCE:
        if metadata.get("evidence_kind") not in {
            "quantitative",
            "qualitative",
            "citation",
            "derived",
            "other",
        }:
            diagnostics.append(
                _diagnostic(
                    "invalid_evidence_kind",
                    "invalid evidence_kind",
                    path=record.path,
                    node_id=record.node_id,
                    field="evidence_kind",
                )
            )
        collected_at = metadata.get("collected_at")
        if "collected_at" in metadata:
            _parse_datetime(
                collected_at,
                field="collected_at",
                record=record,
                diagnostics=diagnostics,
            )
    elif kind is NodeKind.ASSESSMENT:
        checks = (
            (
                "verdict",
                {"supported", "challenged", "refuted", "inconclusive"},
                "invalid_assessment_verdict",
            ),
            ("confidence", {"low", "medium", "high"}, "invalid_confidence"),
            (
                "review_state",
                {"proposed", "approved", "rejected"},
                "invalid_review_state",
            ),
        )
        for field, allowed, code in checks:
            if metadata.get(field) not in allowed:
                diagnostics.append(
                    _diagnostic(
                        code,
                        f"invalid assessment {field}",
                        path=record.path,
                        node_id=record.node_id,
                        field=field,
                    )
                )
        limitations = metadata.get("limitations")
        if "limitations" in metadata:
            _validate_string_list(
                limitations,
                field="limitations",
                record=record,
                diagnostics=diagnostics,
            )
    elif kind is NodeKind.SOURCE:
        if metadata.get("source_kind") not in {
            "paper",
            "book",
            "dataset",
            "web",
            "interview",
            "other",
        }:
            diagnostics.append(
                _diagnostic(
                    "invalid_source_kind",
                    "invalid source_kind",
                    path=record.path,
                    node_id=record.node_id,
                    field="source_kind",
                )
            )
        accessed_at = metadata.get("accessed_at")
        if "accessed_at" in metadata:
            _parse_date(
                accessed_at,
                field="accessed_at",
                record=record,
                diagnostics=diagnostics,
            )
    elif kind is NodeKind.ARTIFACT:
        sha256 = metadata.get("sha256")
        if "sha256" in metadata and (
            not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", sha256) is None
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_sha256",
                    "sha256 must contain 64 hexadecimal characters",
                    path=record.path,
                    node_id=record.node_id,
                    field="sha256",
                )
            )
        size = metadata.get("size")
        if "size" in metadata and (
            not isinstance(size, int) or isinstance(size, bool) or size < 0
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_artifact_size",
                    "artifact size must be a non-negative integer",
                    path=record.path,
                    node_id=record.node_id,
                    field="size",
                )
            )


def _validate_relations(record: _Record, diagnostics: list[Diagnostic]) -> None:
    relations = record.metadata.get("relations", [])
    if not isinstance(relations, list):
        diagnostics.append(
            _diagnostic(
                "invalid_field_type",
                "relations must be a list",
                path=record.path,
                node_id=record.node_id,
                field="relations",
            )
        )
        return
    for index, relation in enumerate(relations):
        prefix = f"relations[{index}]"
        if not isinstance(relation, dict):
            diagnostics.append(
                _diagnostic(
                    "invalid_field_type",
                    "relation must be a mapping",
                    path=record.path,
                    node_id=record.node_id,
                    field=prefix,
                )
            )
            continue
        allowed = {"id", "kind", "target", "rationale", "created_at", "created_by"}
        for unknown in sorted(set(relation) - allowed):
            diagnostics.append(
                _diagnostic(
                    "unknown_field",
                    f"unknown relation field: {unknown}",
                    path=record.path,
                    node_id=record.node_id,
                    field=f"{prefix}.{unknown}",
                )
            )
        edge_id = relation.get("id")
        if not isinstance(edge_id, str) or _EDGE_ID.fullmatch(edge_id) is None:
            diagnostics.append(
                _diagnostic(
                    "invalid_edge_id",
                    "edge id must be rel- followed by ULID",
                    path=record.path,
                    node_id=record.node_id,
                    edge_id=edge_id if isinstance(edge_id, str) else None,
                    field=f"{prefix}.id",
                )
            )
        try:
            EdgeKind(relation.get("kind"))
        except (TypeError, ValueError):
            diagnostics.append(
                _diagnostic(
                    "invalid_edge_kind",
                    "unknown relation kind",
                    path=record.path,
                    node_id=record.node_id,
                    edge_id=edge_id if isinstance(edge_id, str) else None,
                    field=f"{prefix}.kind",
                )
            )
        target = relation.get("target")
        if not isinstance(target, str) or _NODE_ID.fullmatch(target) is None:
            diagnostics.append(
                _diagnostic(
                    "invalid_relation_target",
                    "relation target must be a typed node ID",
                    path=record.path,
                    node_id=record.node_id,
                    edge_id=edge_id if isinstance(edge_id, str) else None,
                    field=f"{prefix}.target",
                )
            )
        rationale = relation.get("rationale")
        if "rationale" in relation and (
            not isinstance(rationale, str) or not rationale.strip()
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_field_type",
                    "relation rationale must be a non-blank string",
                    path=record.path,
                    node_id=record.node_id,
                    edge_id=edge_id if isinstance(edge_id, str) else None,
                    field=f"{prefix}.rationale",
                )
            )
        _parse_datetime(
            relation.get("created_at"),
            field=f"{prefix}.created_at",
            record=record,
            diagnostics=diagnostics,
        )
        _validate_actor(
            relation.get("created_by"),
            field=f"{prefix}.created_by",
            record=record,
            diagnostics=diagnostics,
        )


def _cycles(adjacency: Mapping[str, set[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    active: list[str] = []
    active_positions: dict[str, int] = {}
    found: list[list[str]] = []
    seen: set[frozenset[str]] = set()

    for root in sorted(adjacency):
        if state.get(root, 0) != 0:
            continue
        state[root] = 1
        active_positions[root] = 0
        active.append(root)
        stack: list[tuple[str, Iterator[str]]] = [
            (root, iter(sorted(adjacency.get(root, set()))))
        ]
        while stack:
            node, targets = stack[-1]
            try:
                target = next(targets)
            except StopIteration:
                stack.pop()
                active.pop()
                active_positions.pop(node)
                state[node] = 2
                continue
            target_state = state.get(target, 0)
            if target_state == 0:
                state[target] = 1
                active_positions[target] = len(active)
                active.append(target)
                stack.append((target, iter(sorted(adjacency.get(target, set())))))
            elif target_state == 1:
                cycle = active[active_positions[target] :].copy()
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    found.append(cycle)
    return found


def _validate_global(
    records: list[_Record],
    diagnostics: list[Diagnostic],
    *,
    root: Path,
    require_evidence_provenance: bool,
    forbid_dependency_cycles: bool,
) -> None:
    id_records: dict[str, list[_Record]] = defaultdict(list)
    alias_records: dict[str, list[_Record]] = defaultdict(list)
    edge_records: dict[str, list[tuple[_Record, int, dict[str, Any]]]] = defaultdict(
        list
    )
    for record in records:
        if record.node_id is not None:
            id_records[record.node_id].append(record)
        aliases = record.metadata.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    alias_records[alias].append(record)
        relations = record.metadata.get("relations", [])
        if isinstance(relations, list):
            for index, relation in enumerate(relations):
                if isinstance(relation, dict) and isinstance(relation.get("id"), str):
                    edge_records[relation["id"]].append((record, index, relation))

    for node_id, node_duplicates in id_records.items():
        if len(node_duplicates) > 1:
            paths = sorted(str(record.path) for record in node_duplicates)
            diagnostics.append(
                _diagnostic(
                    "duplicate_node_id",
                    f"duplicate node id: {node_id}",
                    path=node_duplicates[0].path,
                    node_id=node_id,
                    details={"paths": paths},
                )
            )
    for alias, owners in alias_records.items():
        if len(owners) > 1 or alias in id_records:
            diagnostics.append(
                _diagnostic(
                    "duplicate_alias",
                    f"alias is not unique: {alias}",
                    path=owners[0].path,
                    node_id=owners[0].node_id,
                    field="aliases",
                )
            )
    for edge_id, edge_duplicates in edge_records.items():
        if len(edge_duplicates) > 1:
            diagnostics.append(
                _diagnostic(
                    "duplicate_edge_id",
                    f"duplicate edge id: {edge_id}",
                    path=edge_duplicates[0][0].path,
                    node_id=edge_duplicates[0][0].node_id,
                    edge_id=edge_id,
                )
            )

    nodes = {node_id: owners[0] for node_id, owners in id_records.items()}
    dependency_adjacency: dict[str, set[str]] = defaultdict(set)
    decomposition_adjacency: dict[str, set[str]] = defaultdict(set)
    for record in records:
        source_id = record.node_id
        source_kind = record.kind
        if source_id is None:
            continue
        relations = record.metadata.get("relations", [])
        if not isinstance(relations, list):
            continue
        instance_count = 0
        provenance_count = 0
        assesses_count = 0
        basis_count = 0
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                continue
            relation_id = relation.get("id")
            target_id = relation.get("target")
            try:
                edge_kind = EdgeKind(relation.get("kind"))
            except (TypeError, ValueError):
                continue
            if edge_kind is EdgeKind.INSTANCE_OF:
                instance_count += 1
            elif edge_kind is EdgeKind.DERIVED_FROM:
                provenance_count += 1
            elif edge_kind is EdgeKind.ASSESSES:
                assesses_count += 1
            elif edge_kind is EdgeKind.BASED_ON:
                basis_count += 1
            if target_id == source_id and edge_kind not in {EdgeKind.RELATED_TO}:
                diagnostics.append(
                    _diagnostic(
                        "self_relation",
                        "relation cannot target its source",
                        path=record.path,
                        node_id=source_id,
                        edge_id=relation_id if isinstance(relation_id, str) else None,
                        field=f"relations[{index}].target",
                    )
                )
            if not isinstance(target_id, str) or target_id not in nodes:
                if isinstance(target_id, str):
                    diagnostics.append(
                        _diagnostic(
                            "dangling_relation",
                            "Relation target does not exist",
                            path=record.path,
                            node_id=source_id,
                            edge_id=(
                                relation_id if isinstance(relation_id, str) else None
                            ),
                            field=f"relations[{index}].target",
                            suggestion="Create the target or remove the relation",
                            details={"target": target_id},
                        )
                    )
                continue
            target = nodes[target_id]
            target_kind = target.kind
            if (
                source_kind is not None
                and target_kind is not None
                and not relation_is_allowed(source_kind, edge_kind, target_kind)
            ):
                diagnostics.append(
                    _diagnostic(
                        "relation_kind_mismatch",
                        "source and target kinds are invalid for relation",
                        path=record.path,
                        node_id=source_id,
                        edge_id=(relation_id if isinstance(relation_id, str) else None),
                        field=f"relations[{index}].kind",
                    )
                )
            if target.metadata.get("status") == "archived":
                diagnostics.append(
                    _diagnostic(
                        "archived_target",
                        "relation targets an archived node",
                        path=record.path,
                        node_id=source_id,
                        edge_id=(relation_id if isinstance(relation_id, str) else None),
                        field=f"relations[{index}].target",
                        severity=DiagnosticSeverity.WARNING,
                    )
                )
            if edge_kind is EdgeKind.DEPENDS_ON:
                dependency_adjacency[source_id].add(target_id)
            elif edge_kind is EdgeKind.DECOMPOSES:
                decomposition_adjacency[source_id].add(target_id)

        if source_kind is NodeKind.RUN and instance_count != 1:
            diagnostics.append(
                _diagnostic(
                    "invalid_instance_of_count",
                    "run must have exactly one instance_of relation",
                    path=record.path,
                    node_id=source_id,
                    field="relations",
                )
            )
        if (
            source_kind is NodeKind.EVIDENCE
            and require_evidence_provenance
            and provenance_count == 0
        ):
            diagnostics.append(
                _diagnostic(
                    "evidence_provenance_required",
                    "evidence requires a derived_from relation",
                    path=record.path,
                    node_id=source_id,
                    field="relations",
                )
            )
        if source_kind is NodeKind.ASSESSMENT:
            if assesses_count == 0:
                diagnostics.append(
                    _diagnostic(
                        "assessment_target_required",
                        "assessment requires an assesses relation",
                        path=record.path,
                        node_id=source_id,
                        field="relations",
                    )
                )
            if basis_count == 0:
                diagnostics.append(
                    _diagnostic(
                        "assessment_basis_required",
                        "assessment requires at least one based_on relation",
                        path=record.path,
                        node_id=source_id,
                        field="relations",
                    )
                )

    if forbid_dependency_cycles:
        for cycle in _cycles(dependency_adjacency):
            diagnostics.append(
                _diagnostic(
                    "dependency_cycle",
                    "depends_on relations contain a cycle",
                    details={"cycle": cycle},
                )
            )
    for cycle in _cycles(decomposition_adjacency):
        diagnostics.append(
            _diagnostic(
                "decomposition_cycle",
                "decomposes relations contain a cycle",
                details={"cycle": cycle},
            )
        )


def _load_records(
    project: DiscoveredProject,
    diagnostics: list[Diagnostic],
    *,
    exclude_path: Path | None = None,
    retain_documents: bool = False,
    progress: ProgressCallback | None = None,
) -> list[_Record]:
    codec = MarkdownCodec()
    records: list[_Record] = []
    notify_progress(
        progress,
        phase="discovering",
        current=0,
        total=None,
        message="Discovering research nodes",
    )
    node_paths = discover_node_files(project)
    notify_progress(
        progress,
        phase="discovering",
        current=1,
        total=1,
        message="Discovering research nodes",
    )
    notify_progress(
        progress,
        phase="loading",
        current=0,
        total=len(node_paths),
        message="Loading research nodes",
    )
    for processed, node_path in enumerate(node_paths, start=1):
        relative_path = node_path.relative_to(project.root)
        if relative_path == exclude_path:
            notify_progress(
                progress,
                phase="loading",
                current=processed,
                total=len(node_paths),
                message="Loading research nodes",
            )
            continue
        try:
            raw = node_path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as error:
            diagnostics.append(
                _diagnostic(
                    "file_read_error",
                    str(error),
                    path=relative_path,
                )
            )
            notify_progress(
                progress,
                phase="loading",
                current=processed,
                total=len(node_paths),
                message="Loading research nodes",
            )
            continue
        try:
            document = codec.decode(text, path=node_path)
        except MarkdownCodecError as error:
            diagnostics.append(_diagnostic(error.code, str(error), path=relative_path))
            notify_progress(
                progress,
                phase="loading",
                current=processed,
                total=len(node_paths),
                message="Loading research nodes",
            )
            continue
        record = _Record(
            path=relative_path,
            metadata=dict(document.metadata),
            document=document if retain_documents else None,
            revision=hashlib.sha256(raw).hexdigest() if retain_documents else None,
        )
        records.append(record)
        _validate_structural(record, diagnostics)
        notify_progress(
            progress,
            phase="loading",
            current=processed,
            total=len(node_paths),
            message="Loading research nodes",
        )
    return records


def _sorted_diagnostics(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                str(item.path or ""),
                item.node_id or "",
                item.edge_id or "",
                item.field or "",
                item.code,
            ),
        )
    )


def _validate_records(
    project: DiscoveredProject,
    records: list[_Record],
    diagnostics: list[Diagnostic],
) -> tuple[Diagnostic, ...]:
    _validate_global(
        records,
        diagnostics,
        root=project.root,
        require_evidence_provenance=project.config.policies.require_evidence_provenance,
        forbid_dependency_cycles=project.config.policies.forbid_dependency_cycles,
    )
    return _sorted_diagnostics(diagnostics)


def _validate_candidate_uniqueness(
    project: DiscoveredProject,
    snapshot: GraphSnapshot,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> None:
    node_id = record.node_id
    if node_id is None:
        return

    candidate_path = project.root / record.path
    existing_node = snapshot._node_by_id(node_id)
    if existing_node is not None and existing_node.path != candidate_path:
        diagnostics.append(
            _diagnostic(
                "duplicate_node_id",
                f"duplicate node id: {node_id}",
                path=record.path,
                node_id=node_id,
                details={
                    "paths": sorted(
                        (
                            str(existing_node.path.relative_to(project.root)),
                            str(record.path),
                        )
                    )
                },
            )
        )

    id_alias_owner = snapshot._alias_owner(node_id)
    if id_alias_owner is not None:
        diagnostics.append(
            _diagnostic(
                "duplicate_alias",
                f"alias is not unique: {node_id}",
                path=id_alias_owner.path.relative_to(project.root),
                node_id=id_alias_owner.id,
                field="aliases",
            )
        )

    aliases = record.metadata.get("aliases", [])
    if isinstance(aliases, list):
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            node_owner = snapshot._node_by_id(alias)
            alias_owner = snapshot._alias_owner(alias)
            if (
                alias == node_id
                or node_owner is not None
                or (alias_owner is not None and alias_owner.id != node_id)
            ):
                diagnostics.append(
                    _diagnostic(
                        "duplicate_alias",
                        f"alias is not unique: {alias}",
                        path=record.path,
                        node_id=node_id,
                        field="aliases",
                    )
                )

    relations = record.metadata.get("relations", [])
    if not isinstance(relations, list):
        return
    seen_edge_ids: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        edge_id = relation.get("id")
        if not isinstance(edge_id, str):
            continue
        existing_edge = snapshot._edge_by_id(edge_id)
        if edge_id in seen_edge_ids or (
            existing_edge is not None and existing_edge.source != node_id
        ):
            diagnostics.append(
                _diagnostic(
                    "duplicate_edge_id",
                    f"duplicate edge id: {edge_id}",
                    path=record.path,
                    node_id=node_id,
                    edge_id=edge_id,
                )
            )
        seen_edge_ids.add(edge_id)


def _cycle_details(
    source_id: str,
    target_id: str,
    path: tuple[Edge, ...],
) -> dict[str, list[str]]:
    intermediate = [edge.target for edge in path[:-1]]
    return {"cycle": [source_id, target_id, *intermediate]}


def _validate_candidate_relations(
    project: DiscoveredProject,
    snapshot: GraphSnapshot,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> None:
    source_id = record.node_id
    source_kind = record.kind
    if source_id is None:
        return
    relations = record.metadata.get("relations", [])
    if not isinstance(relations, list):
        return

    instance_count = 0
    provenance_count = 0
    assesses_count = 0
    basis_count = 0
    cycle_reported: set[EdgeKind] = set()
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue
        relation_id = relation.get("id")
        target_id = relation.get("target")
        try:
            edge_kind = EdgeKind(relation.get("kind"))
        except (TypeError, ValueError):
            continue

        if edge_kind is EdgeKind.INSTANCE_OF:
            instance_count += 1
        elif edge_kind is EdgeKind.DERIVED_FROM:
            provenance_count += 1
        elif edge_kind is EdgeKind.ASSESSES:
            assesses_count += 1
        elif edge_kind is EdgeKind.BASED_ON:
            basis_count += 1

        if target_id == source_id and edge_kind is not EdgeKind.RELATED_TO:
            diagnostics.append(
                _diagnostic(
                    "self_relation",
                    "relation cannot target its source",
                    path=record.path,
                    node_id=source_id,
                    edge_id=relation_id if isinstance(relation_id, str) else None,
                    field=f"relations[{index}].target",
                )
            )

        if not isinstance(target_id, str):
            continue
        if target_id == source_id:
            target_kind = record.kind
            target_status = record.metadata.get("status")
        else:
            target = snapshot._node_by_id(target_id)
            if target is None:
                diagnostics.append(
                    _diagnostic(
                        "dangling_relation",
                        "Relation target does not exist",
                        path=record.path,
                        node_id=source_id,
                        edge_id=(relation_id if isinstance(relation_id, str) else None),
                        field=f"relations[{index}].target",
                        suggestion="Create the target or remove the relation",
                        details={"target": target_id},
                    )
                )
                continue
            target_kind = target.kind
            target_status = target.status.value

        if (
            source_kind is not None
            and target_kind is not None
            and not relation_is_allowed(source_kind, edge_kind, target_kind)
        ):
            diagnostics.append(
                _diagnostic(
                    "relation_kind_mismatch",
                    "source and target kinds are invalid for relation",
                    path=record.path,
                    node_id=source_id,
                    edge_id=relation_id if isinstance(relation_id, str) else None,
                    field=f"relations[{index}].kind",
                )
            )

        if target_status == "archived":
            diagnostics.append(
                _diagnostic(
                    "archived_target",
                    "relation targets an archived node",
                    path=record.path,
                    node_id=source_id,
                    edge_id=relation_id if isinstance(relation_id, str) else None,
                    field=f"relations[{index}].target",
                    severity=DiagnosticSeverity.WARNING,
                )
            )

        cycle_is_forbidden = edge_kind is EdgeKind.DECOMPOSES or (
            edge_kind is EdgeKind.DEPENDS_ON
            and project.config.policies.forbid_dependency_cycles
        )
        if (
            cycle_is_forbidden
            and edge_kind not in cycle_reported
            and target_id == source_id
        ):
            code = (
                "dependency_cycle"
                if edge_kind is EdgeKind.DEPENDS_ON
                else "decomposition_cycle"
            )
            diagnostics.append(
                _diagnostic(
                    code,
                    f"{edge_kind.value} relations contain a cycle",
                    details={"cycle": [source_id]},
                )
            )
            cycle_reported.add(edge_kind)
        if (
            cycle_is_forbidden
            and edge_kind not in cycle_reported
            and target_id != source_id
            and snapshot._node_by_id(source_id) is not None
            and snapshot._node_by_id(target_id) is not None
        ):
            graph_path = snapshot.find_path(
                target_id,
                source_id,
                kinds={edge_kind},
            )
            if graph_path is not None:
                code = (
                    "dependency_cycle"
                    if edge_kind is EdgeKind.DEPENDS_ON
                    else "decomposition_cycle"
                )
                diagnostics.append(
                    _diagnostic(
                        code,
                        f"{edge_kind.value} relations contain a cycle",
                        details=_cycle_details(source_id, target_id, graph_path),
                    )
                )
                cycle_reported.add(edge_kind)

    if source_kind is NodeKind.RUN and instance_count != 1:
        diagnostics.append(
            _diagnostic(
                "invalid_instance_of_count",
                "run must have exactly one instance_of relation",
                path=record.path,
                node_id=source_id,
                field="relations",
            )
        )
    if (
        source_kind is NodeKind.EVIDENCE
        and project.config.policies.require_evidence_provenance
        and provenance_count == 0
    ):
        diagnostics.append(
            _diagnostic(
                "evidence_provenance_required",
                "evidence requires a derived_from relation",
                path=record.path,
                node_id=source_id,
                field="relations",
            )
        )
    if source_kind is NodeKind.ASSESSMENT:
        if assesses_count == 0:
            diagnostics.append(
                _diagnostic(
                    "assessment_target_required",
                    "assessment requires an assesses relation",
                    path=record.path,
                    node_id=source_id,
                    field="relations",
                )
            )
        if basis_count == 0:
            diagnostics.append(
                _diagnostic(
                    "assessment_basis_required",
                    "assessment requires at least one based_on relation",
                    path=record.path,
                    node_id=source_id,
                    field="relations",
                )
            )

    if (
        record.metadata.get("status") == "archived"
        and snapshot._node_by_id(source_id) is not None
    ):
        for edge in snapshot.incoming(source_id):
            if edge.source == source_id:
                continue
            owner = snapshot._node_by_id(edge.source)
            diagnostics.append(
                _diagnostic(
                    "archived_target",
                    "relation targets an archived node",
                    path=(
                        owner.path.relative_to(project.root)
                        if owner is not None
                        else None
                    ),
                    node_id=edge.source,
                    edge_id=edge.id,
                    field="relations",
                    severity=DiagnosticSeverity.WARNING,
                )
            )


def _validate_candidate_against_snapshot(
    project: DiscoveredProject,
    snapshot: GraphSnapshot,
    record: _Record,
    diagnostics: list[Diagnostic],
) -> tuple[Diagnostic, ...]:
    _validate_candidate_uniqueness(project, snapshot, record, diagnostics)
    _validate_candidate_relations(project, snapshot, record, diagnostics)
    return _sorted_diagnostics(diagnostics)


def validate_candidate_node(
    project: DiscoveredProject,
    *,
    path: Path,
    metadata: Mapping[str, Any],
    snapshot: GraphSnapshot | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate an in-memory node as a project addition or path replacement."""

    relative_path = path.relative_to(project.root)
    diagnostics: list[Diagnostic] = []
    record = _Record(
        path=relative_path,
        metadata=dict(metadata),
    )
    _validate_structural(record, diagnostics)
    if snapshot is not None:
        return _validate_candidate_against_snapshot(
            project,
            snapshot,
            record,
            diagnostics,
        )

    records = _load_records(
        project,
        diagnostics,
        exclude_path=relative_path,
    )
    records.append(record)
    return _validate_records(project, records, diagnostics)


def validate_project(
    path: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[Diagnostic, ...]:
    project = discover_project(path)
    diagnostics: list[Diagnostic] = []
    records = _load_records(project, diagnostics, progress=progress)
    notify_progress(
        progress,
        phase="validating",
        current=0,
        total=1,
        message="Validating graph",
    )
    result = _validate_records(project, records, diagnostics)
    notify_progress(
        progress,
        phase="validating",
        current=1,
        total=1,
        message="Validating graph",
    )
    return result


def validate_and_load_snapshot(
    project: DiscoveredProject,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[tuple[Diagnostic, ...], GraphSnapshot | None]:
    """Validate and build a snapshot from one read/decode pass."""

    diagnostics: list[Diagnostic] = []
    records = _load_records(
        project,
        diagnostics,
        retain_documents=True,
        progress=progress,
    )
    notify_progress(
        progress,
        phase="validating",
        current=0,
        total=1,
        message="Validating graph",
    )
    result = _validate_records(project, records, diagnostics)
    notify_progress(
        progress,
        phase="validating",
        current=1,
        total=1,
        message="Validating graph",
    )
    if any(item.severity is DiagnosticSeverity.ERROR for item in result):
        return result, None

    nodes = []
    edges: list[Edge] = []
    notify_progress(
        progress,
        phase="indexing",
        current=0,
        total=len(records),
        message="Building graph indexes",
    )
    for processed, record in enumerate(records, start=1):
        assert record.document is not None
        assert record.revision is not None
        node = parse_node(record.document, revision=record.revision)
        nodes.append(node)
        edges.extend(parse_edges(node, record.metadata))
        record.document = None
        record.metadata.clear()
        notify_progress(
            progress,
            phase="indexing",
            current=processed,
            total=len(records),
            message="Building graph indexes",
        )
    return result, GraphSnapshot(nodes, edges)
