from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from research_framework.domain.actors import Actor
from research_framework.domain.enums import ActorKind, EdgeKind, NodeKind, NodeStatus
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


def parse_actor(value: Mapping[str, Any]) -> Actor:
    return Actor(
        kind=ActorKind(value["kind"]),
        id=value["id"],
        run_id=value.get("run_id"),
        model=value.get("model"),
    )


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def parse_node(document: DecodedMarkdown, *, revision: str) -> Node:
    metadata = document.metadata
    data = {key: value for key, value in metadata.items() if key not in COMMON_FIELDS}
    return Node(
        format_version=metadata["format_version"],
        id=metadata["id"],
        kind=NodeKind(metadata["kind"]),
        title=metadata["title"],
        status=NodeStatus(metadata["status"]),
        summary=metadata.get("summary"),
        tags=tuple(metadata.get("tags", ())),
        aliases=tuple(metadata.get("aliases", ())),
        created_at=parse_datetime(metadata["created_at"]),
        created_by=parse_actor(metadata["created_by"]),
        updated_at=parse_datetime(metadata["updated_at"]),
        updated_by=parse_actor(metadata["updated_by"]),
        extensions=freeze_mapping(metadata.get("extensions", {})),
        body=document.body,
        path=document.path,
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
        document = codec.decode(raw.decode("utf-8"), path=path)
        node = parse_node(document, revision=hashlib.sha256(raw).hexdigest())
        nodes.append(node)
        edges.extend(parse_edges(node, document.metadata))
    return tuple(nodes), tuple(edges)


def load_snapshot(project: DiscoveredProject) -> GraphSnapshot:
    nodes, edges = load_documents(project)
    return GraphSnapshot(nodes, edges)
