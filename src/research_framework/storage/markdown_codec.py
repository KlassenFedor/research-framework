from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from research_framework.domain.fields import field_order as _field_order

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


@dataclass(frozen=True, slots=True)
class MarkdownHeader:
    metadata: Mapping[str, Any]
    body_offset: int
    path: Path


def _next_line(text: str, start: int) -> tuple[str, int]:
    """Return one line without its terminator and the following offset."""

    newline = text.find("\n", start)
    carriage = text.find("\r", start)
    endings = tuple(index for index in (newline, carriage) if index >= 0)
    if not endings:
        return text[start:], len(text)
    end = min(endings)
    following = end + 1
    if text[end] == "\r" and following < len(text) and text[following] == "\n":
        following += 1
    return text[start:end], following


class MarkdownCodec:
    def decode_header(self, text: str, *, path: Path) -> MarkdownHeader:
        first_line, cursor = _next_line(text, 0)
        if first_line != "---":
            raise MarkdownCodecError(
                "missing_front_matter",
                path,
                "Markdown node must start with YAML front matter",
            )

        front_matter_start = cursor
        closing_start: int | None = None
        body_offset: int | None = None
        while cursor < len(text):
            line_start = cursor
            line, cursor = _next_line(text, cursor)
            if line == "---":
                closing_start = line_start
                body_offset = cursor
                break
        if closing_start is None or body_offset is None:
            raise MarkdownCodecError(
                "unclosed_front_matter",
                path,
                "YAML front matter has no closing delimiter",
            )

        front_matter = text[front_matter_start:closing_start]
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

        return MarkdownHeader(metadata=metadata, body_offset=body_offset, path=path)

    def decode(self, text: str, *, path: Path) -> DecodedMarkdown:
        header = self.decode_header(text, path=path)
        return DecodedMarkdown(
            metadata=header.metadata,
            body=text[header.body_offset :],
            path=path,
        )

    def encode(self, document: DecodedMarkdown) -> str:
        metadata = dict(document.metadata)
        kind = metadata.get("kind")
        field_order = _field_order(kind)
        ordered: dict[str, Any] = {}
        for field in field_order:
            if field in metadata:
                ordered[field] = metadata[field]
        for field, value in metadata.items():
            if field not in ordered:
                ordered[field] = value

        encoded = dump_restricted_yaml(ordered)
        return f"---\n{encoded}---\n{document.body}"
