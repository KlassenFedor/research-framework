from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

COMMON_FIELD_ORDER: tuple[str, ...] = (
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
    "extensions",
    "relations",
)

SPECIAL_FIELD_ORDER: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "question": ("question", "scope"),
        "hypothesis": ("statement", "falsification_criteria", "assumptions"),
        "claim": ("statement",),
        "experiment": (
            "objective",
            "method",
            "success_criteria",
            "protocol_version",
        ),
        "run": ("started_at", "finished_at", "outcome", "environment"),
        "evidence": ("observation", "evidence_kind", "collected_at"),
        "assessment": ("verdict", "confidence", "limitations", "review_state"),
        "source": ("source_kind", "locator", "citation", "accessed_at"),
        "artifact": ("locator", "media_type", "sha256", "size"),
        "decision": ("outcome", "rationale"),
    }
)

COMMON_FIELDS: frozenset[str] = frozenset(COMMON_FIELD_ORDER)

SPECIAL_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {kind: frozenset(fields) for kind, fields in SPECIAL_FIELD_ORDER.items()}
)

REQUIRED_COMMON: frozenset[str] = frozenset(
    {
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
)

REQUIRED_SPECIAL: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "question": frozenset({"question"}),
        "hypothesis": frozenset({"statement", "falsification_criteria"}),
        "claim": frozenset({"statement"}),
        "experiment": frozenset(
            {"objective", "method", "success_criteria", "protocol_version"}
        ),
        "run": frozenset({"started_at", "outcome"}),
        "evidence": frozenset({"observation", "evidence_kind"}),
        "assessment": frozenset({"verdict", "confidence", "review_state"}),
        "source": frozenset({"source_kind", "locator"}),
        "artifact": frozenset({"locator"}),
        "decision": frozenset({"outcome", "rationale"}),
    }
)

#: Fields that identify a node or record its creation; ``update_node`` refuses
#: to patch them.
IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "format_version",
        "id",
        "kind",
        "created_at",
        "created_by",
        "relations",
    }
)


def schema_fields(kind: object) -> frozenset[str]:
    """Every top-level field the file contract allows for ``kind``."""

    return COMMON_FIELDS | SPECIAL_FIELDS.get(_kind_value(kind), frozenset())


def required_fields(kind: object) -> frozenset[str]:
    """Every top-level field the file contract requires for ``kind``."""

    return REQUIRED_COMMON | REQUIRED_SPECIAL.get(_kind_value(kind), frozenset())


def field_order(kind: object) -> tuple[str, ...]:
    """Front matter field order for ``kind``, special fields after ``summary``."""

    special = SPECIAL_FIELD_ORDER.get(_kind_value(kind), ())
    summary_at = COMMON_FIELD_ORDER.index("summary")
    return (
        *COMMON_FIELD_ORDER[: summary_at + 1],
        *special,
        *COMMON_FIELD_ORDER[summary_at + 1 :],
    )


def allowed_update_fields(kind: object) -> frozenset[str]:
    """Fields a ``update_node`` patch may set for ``kind``.

    Built from the schema rather than from the keys a document happens to hold,
    so an optional field that was omitted at creation time can still be added
    later (see bug-reports/005).
    """

    return schema_fields(kind) - IMMUTABLE_FIELDS


def _kind_value(kind: object) -> str:
    value = getattr(kind, "value", kind)
    return value if isinstance(value, str) else str(value)
