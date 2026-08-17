from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .yaml_codec import RestrictedYamlError, dump_restricted_yaml, load_restricted_yaml


class MarkdownCodecError(ValueError):
    def __init__(self, code: str, path: Path, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True, slots=True)
class DecodedMarkdown:
    metadata: Mapping[str, Any]
    body: str
    path: Path

    def with_metadata(self, metadata: Mapping[str, Any]) -> DecodedMarkdown:
        return replace(self, metadata=metadata)


class MarkdownCodec:
    def decode(self, text: str, *, path: Path) -> DecodedMarkdown:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            raise MarkdownCodecError(
                "missing_front_matter",
                path,
                "Markdown node must start with YAML front matter",
            )

        closing_index = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.rstrip("\r\n") == "---"
            ),
            None,
        )
        if closing_index is None:
            raise MarkdownCodecError(
                "unclosed_front_matter",
                path,
                "YAML front matter has no closing delimiter",
            )

        front_matter = "".join(lines[1:closing_index])
        if any(marker in front_matter for marker in ("<<<<<<<", "=======", ">>>>>>>")):
            raise MarkdownCodecError(
                "git_conflict_marker",
                path,
                "front matter contains unresolved Git conflict markers",
            )

        try:
            metadata = load_restricted_yaml(front_matter)
        except RestrictedYamlError as error:
            raise MarkdownCodecError(error.code, path, str(error)) from error

        return DecodedMarkdown(
            metadata=metadata,
            body="".join(lines[closing_index + 1 :]),
            path=path,
        )

    def encode(self, document: DecodedMarkdown) -> str:
        metadata = dict(document.metadata)
        kind = metadata.get("kind")
        special_fields = {
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
            "assessment": (
                "verdict",
                "confidence",
                "limitations",
                "review_state",
            ),
            "source": ("source_kind", "locator", "citation", "accessed_at"),
            "artifact": ("locator", "media_type", "sha256", "size"),
            "decision": ("outcome", "rationale"),
        }
        field_order = (
            "format_version",
            "id",
            "kind",
            "title",
            "status",
            "summary",
            *special_fields.get(str(kind), ()),
            "tags",
            "aliases",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "extensions",
            "relations",
        )
        ordered: dict[str, Any] = {}
        for field in field_order:
            if field in metadata:
                ordered[field] = metadata[field]
        for field, value in metadata.items():
            if field not in ordered:
                ordered[field] = value

        encoded = dump_restricted_yaml(ordered)
        return f"---\n{encoded}---\n{document.body}"
