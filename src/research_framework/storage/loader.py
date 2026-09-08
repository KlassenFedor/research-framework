from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from research_framework.domain.actors import Actor
from research_framework.domain.enums import ActorKind, EdgeKind, NodeKind, NodeStatus
from research_framework.domain.errors import RevisionConflict, StorageError
from research_framework.domain.graph import Edge, GraphSnapshot, Node, freeze_mapping

from .discovery import DiscoveredProject, discover_node_files
from .markdown_codec import DecodedMarkdown, MarkdownCodec

COMMON_FIELDS = {
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


# A graph has far fewer actors than nodes, and every node names two of them.
# Handing out one shared instance per distinct actor removes a per-node object
# without changing anything observable, since Actor is frozen.
_ACTORS: dict[tuple[str, str, str | None, str | None], Actor] = {}


def parse_actor(value: Mapping[str, Any]) -> Actor:
    key = (value["kind"], value["id"], value.get("run_id"), value.get("model"))
    actor = _ACTORS.get(key)
    if actor is None:
        actor = Actor(
            kind=ActorKind(key[0]),
            id=sys.intern(key[1]),
            run_id=key[2],
            model=key[3],
        )
        _ACTORS[key] = actor
    return actor


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class LazyMarkdownBody:
    path: Path
    body_offset: int
    revision: str
    node_id: str

    def __call__(self) -> str:
        try:
            raw = self.path.read_bytes()
        except OSError as error:
            raise StorageError(f"cannot read node body: {self.path}") from error
        actual_revision = hashlib.sha256(raw).hexdigest()
        if actual_revision != self.revision:
            raise RevisionConflict(self.node_id, self.revision, actual_revision)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StorageError(f"node body is not valid UTF-8: {self.path}") from error
        return text[self.body_offset :]


def parse_node(document: DecodedMarkdown, *, revision: str) -> Node:
    return parse_node_metadata(
        document.metadata,
        path=document.path,
        revision=revision,
        body=document.body,
    )


def parse_node_metadata(
    metadata: Mapping[str, Any],
    *,
    path: Path,
    revision: str,
    body: str | LazyMarkdownBody,
) -> Node:
    data = {key: value for key, value in metadata.items() if key not in COMMON_FIELDS}
    return Node(
        format_version=metadata["format_version"],
        id=metadata["id"],
        kind=NodeKind(metadata["kind"]),
        title=metadata["title"],
        status=NodeStatus(metadata["status"]),
        summary=metadata.get("summary"),
        # Tags repeat across the whole graph; aliases do not, but interning a
        # unique string only costs the lookup that proved it unique.
        tags=tuple(sys.intern(tag) for tag in metadata.get("tags", ())),
        aliases=tuple(metadata.get("aliases", ())),
        created_at=parse_datetime(metadata["created_at"]),
        created_by=parse_actor(metadata["created_by"]),
        updated_at=parse_datetime(metadata["updated_at"]),
        updated_by=parse_actor(metadata["updated_by"]),
        extensions=freeze_mapping(metadata.get("extensions", {})),
        _body=body,
        path=path,
        revision=revision,
        data=freeze_mapping(data),
    )


def parse_edges(node: Node, metadata: Mapping[str, Any]) -> tuple[Edge, ...]:
    edges: list[Edge] = []
    for relation in metadata.get("relations", ()):
        edges.append(
            Edge(
                id=relation["id"],
                kind=EdgeKind(relation["kind"]),
                source=node.id,
                target=relation["target"],
                rationale=relation.get("rationale"),
                created_at=parse_datetime(relation["created_at"]),
                created_by=parse_actor(relation["created_by"]),
            )
        )
    return tuple(edges)


def load_documents(
    project: DiscoveredProject,
) -> tuple[tuple[Node, ...], tuple[Edge, ...]]:
    codec = MarkdownCodec()
    nodes: list[Node] = []
    edges: list[Edge] = []
    for path in discover_node_files(project):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        header = codec.decode_header(text, path=path)
        revision = hashlib.sha256(raw).hexdigest()
        node_id = str(header.metadata.get("id", "unknown"))
        node = parse_node_metadata(
            header.metadata,
            path=path,
            revision=revision,
            body=LazyMarkdownBody(path, header.body_offset, revision, node_id),
        )
        nodes.append(node)
        edges.extend(parse_edges(node, header.metadata))
    return tuple(nodes), tuple(edges)


def load_snapshot(project: DiscoveredProject) -> GraphSnapshot:
    nodes, edges = load_documents(project)
    return GraphSnapshot(nodes, edges)
