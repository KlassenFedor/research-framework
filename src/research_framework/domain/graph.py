from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .actors import Actor
from .enums import EdgeKind, NodeKind, NodeStatus
from .errors import AmbiguousReference, EdgeNotFound, NodeNotFound


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (NodeKind, NodeStatus, EdgeKind)):
        return value.value
    if isinstance(value, Actor):
        result: dict[str, Any] = {"kind": value.kind.value, "id": value.id}
        if value.run_id is not None:
            result["run_id"] = value.run_id
        if value.model is not None:
            result["model"] = value.model
        return result
    return value


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen[key] = freeze_mapping(item)
        elif isinstance(item, list):
            frozen[key] = tuple(
                freeze_mapping(element) if isinstance(element, Mapping) else element
                for element in item
            )
        else:
            frozen[key] = item
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class Node:
    format_version: int
    id: str
    kind: NodeKind
    title: str
    status: NodeStatus
    summary: str | None
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    created_at: datetime
    created_by: Actor
    updated_at: datetime
    updated_by: Actor
    extensions: Mapping[str, Any]
    body: str
    path: Path
    revision: str
    data: Mapping[str, Any]

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "data")
        if name in data:
            return data[name]
        raise AttributeError(name)

    def to_dict(
        self,
        *,
        include_body: bool = False,
        include_revision: bool = False,
    ) -> dict[str, Any]:
        value: dict[str, Any] = {
            "format_version": self.format_version,
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "status": self.status.value,
        }
        if self.summary is not None:
            value["summary"] = self.summary
        value.update(_plain(self.data))
        if self.tags:
            value["tags"] = list(self.tags)
        if self.aliases:
            value["aliases"] = list(self.aliases)
        value.update(
            {
                "created_at": self.created_at.isoformat(),
                "created_by": _plain(self.created_by),
                "updated_at": self.updated_at.isoformat(),
                "updated_by": _plain(self.updated_by),
            }
        )
        if self.extensions:
            value["extensions"] = _plain(self.extensions)
        if include_body:
            value["body"] = self.body
        if include_revision:
            value["revision"] = self.revision
        return value


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    kind: EdgeKind
    source: str
    target: str
    created_at: datetime
    created_by: Actor
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "source": self.source,
            "target": self.target,
            "created_at": self.created_at.isoformat(),
            "created_by": _plain(self.created_by),
        }
        if self.rationale is not None:
            value["rationale"] = self.rationale
        return value


class GraphSnapshot:
    __slots__ = ("_aliases", "_edges", "_incoming", "_nodes", "_outgoing")

    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        node_map = {node.id: node for node in nodes}
        edge_map = {edge.id: edge for edge in edges}
        aliases: dict[str, str] = {}
        for node in node_map.values():
            for alias in node.aliases:
                aliases[alias] = node.id
        outgoing: dict[str, list[Edge]] = {node_id: [] for node_id in node_map}
        incoming: dict[str, list[Edge]] = {node_id: [] for node_id in node_map}
        for edge in edge_map.values():
            outgoing.setdefault(edge.source, []).append(edge)
            incoming.setdefault(edge.target, []).append(edge)
        self._nodes = node_map
        self._edges = edge_map
        self._aliases = aliases
        self._outgoing = {
            key: tuple(sorted(value, key=lambda edge: edge.id))
            for key, value in outgoing.items()
        }
        self._incoming = {
            key: tuple(sorted(value, key=lambda edge: edge.id))
            for key, value in incoming.items()
        }

    @classmethod
    def _from_indexes(
        cls,
        *,
        nodes: Mapping[str, Node],
        edges: Mapping[str, Edge],
        aliases: Mapping[str, str],
        outgoing: Mapping[str, tuple[Edge, ...]],
        incoming: Mapping[str, tuple[Edge, ...]],
    ) -> GraphSnapshot:
        snapshot = cls.__new__(cls)
        snapshot._nodes = dict(nodes)
        snapshot._edges = dict(edges)
        snapshot._aliases = dict(aliases)
        snapshot._outgoing = dict(outgoing)
        snapshot._incoming = dict(incoming)
        return snapshot

    def _node_by_id(self, node_id: str) -> Node | None:
        """Return only an exact ID match, without alias or prefix resolution."""

        return self._nodes.get(node_id)

    def _alias_owner(self, alias: str) -> Node | None:
        """Return the Node owning an exact alias."""

        node_id = self._aliases.get(alias)
        return self._nodes.get(node_id) if node_id is not None else None

    def _edge_by_id(self, edge_id: str) -> Edge | None:
        """Return an exact relation match without raising."""

        return self._edges.get(edge_id)

    def _replacing_node(self, node: Node, edges: Iterable[Edge]) -> GraphSnapshot:
        """Create a snapshot by replacing one Node and its outgoing relations.

        Existing snapshots remain immutable. Only indexes affected by the
        replacement are recomputed; no document is read from storage.
        """

        snapshot = self._from_indexes(
            nodes=self._nodes,
            edges=self._edges,
            aliases=self._aliases,
            outgoing=self._outgoing,
            incoming=self._incoming,
        )
        snapshot._replace_node_in_place(node, edges)
        return snapshot

    def _replace_node_in_place(self, node: Node, edges: Iterable[Edge]) -> None:
        """Update indexes owned exclusively by a Project instance."""

        replacement_edges = tuple(sorted(edges, key=lambda edge: edge.id))
        if any(edge.source != node.id for edge in replacement_edges):
            raise ValueError("replacement edges must originate from the node")

        previous_node = self._nodes.get(node.id)
        previous_edges = self._outgoing.get(node.id, ())

        self._nodes[node.id] = node

        for edge in previous_edges:
            self._edges.pop(edge.id, None)
        for edge in replacement_edges:
            self._edges[edge.id] = edge

        if previous_node is not None:
            for alias in previous_node.aliases:
                if self._aliases.get(alias) == node.id:
                    self._aliases.pop(alias)
        for alias in node.aliases:
            self._aliases[alias] = node.id

        self._outgoing[node.id] = replacement_edges

        affected_targets = {
            *(edge.target for edge in previous_edges),
            *(edge.target for edge in replacement_edges),
        }
        for target in affected_targets:
            target_edges = [
                edge
                for edge in self._incoming.get(target, ())
                if edge.source != node.id
            ]
            target_edges.extend(
                edge for edge in replacement_edges if edge.target == target
            )
            self._incoming[target] = tuple(
                sorted(target_edges, key=lambda edge: edge.id)
            )
        self._incoming.setdefault(node.id, ())

    def get_node(self, reference: str) -> Node:
        if reference in self._nodes:
            return self._nodes[reference]
        if reference in self._aliases:
            return self._nodes[self._aliases[reference]]
        candidates = tuple(
            sorted(node_id for node_id in self._nodes if node_id.startswith(reference))
        )
        if len(candidates) == 1:
            return self._nodes[candidates[0]]
        if len(candidates) > 1:
            raise AmbiguousReference(reference, candidates)
        raise NodeNotFound(reference)

    def get_edge(self, edge_id: str) -> Edge:
        try:
            return self._edges[edge_id]
        except KeyError as error:
            raise EdgeNotFound(f"Edge not found: {edge_id}") from error

    def list_nodes(
        self,
        *,
        kind: NodeKind | str | None = None,
        status: NodeStatus | str | None = None,
        tags: set[str] | frozenset[str] | None = None,
    ) -> tuple[Node, ...]:
        kind_value = NodeKind(kind) if kind is not None else None
        status_value = NodeStatus(status) if status is not None else None
        required_tags = set(tags or ())
        result = (
            node
            for node in self._nodes.values()
            if (kind_value is None or node.kind is kind_value)
            and (status_value is None or node.status is status_value)
            and required_tags.issubset(node.tags)
        )
        return tuple(sorted(result, key=lambda node: (node.created_at, node.id)))

    @staticmethod
    def _kind_values(kinds: set[EdgeKind | str] | None) -> set[EdgeKind] | None:
        if kinds is None:
            return None
        return {EdgeKind(kind) for kind in kinds}

    def outgoing(
        self,
        node_id: str,
        *,
        kinds: set[EdgeKind | str] | None = None,
    ) -> tuple[Edge, ...]:
        node = self.get_node(node_id)
        accepted = self._kind_values(kinds)
        return tuple(
            edge
            for edge in self._outgoing.get(node.id, ())
            if accepted is None or edge.kind in accepted
        )

    def incoming(
        self,
        node_id: str,
        *,
        kinds: set[EdgeKind | str] | None = None,
    ) -> tuple[Edge, ...]:
        node = self.get_node(node_id)
        accepted = self._kind_values(kinds)
        return tuple(
            edge
            for edge in self._incoming.get(node.id, ())
            if accepted is None or edge.kind in accepted
        )

    def neighbors(
        self,
        node_id: str,
        *,
        direction: str = "both",
        kinds: set[EdgeKind | str] | None = None,
    ) -> tuple[Node, ...]:
        node = self.get_node(node_id)
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be outgoing, incoming, or both")
        accepted = self._kind_values(kinds)
        return self._neighbors(node.id, direction=direction, accepted=accepted)

    def _neighbors(
        self,
        node_id: str,
        *,
        direction: str,
        accepted: set[EdgeKind] | None,
    ) -> tuple[Node, ...]:
        neighbor_ids: set[str] = set()
        symmetric = {EdgeKind.CONTRADICTS, EdgeKind.RELATED_TO}
        for edge in self._outgoing.get(node_id, ()):
            if accepted is not None and edge.kind not in accepted:
                continue
            if direction in {"outgoing", "both"} or edge.kind in symmetric:
                neighbor_ids.add(edge.target)
        for edge in self._incoming.get(node_id, ()):
            if accepted is not None and edge.kind not in accepted:
                continue
            if direction in {"incoming", "both"} or edge.kind in symmetric:
                neighbor_ids.add(edge.source)

        return tuple(
            sorted(
                (self._nodes[neighbor_id] for neighbor_id in neighbor_ids),
                key=lambda item: (item.created_at, item.id),
            )
        )

    def traverse(
        self,
        node_id: str,
        depth: int,
        *,
        direction: str = "both",
        kinds: set[EdgeKind | str] | None = None,
    ) -> tuple[Node, ...]:
        start = self.get_node(node_id)
        if depth < 0:
            raise ValueError("depth must not be negative")
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be outgoing, incoming, or both")
        accepted = self._kind_values(kinds)
        visited = {start.id}
        result: list[Node] = []
        queue: deque[tuple[str, int]] = deque([(start.id, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbor in self._neighbors(
                current,
                direction=direction,
                accepted=accepted,
            ):
                if neighbor.id in visited:
                    continue
                visited.add(neighbor.id)
                result.append(neighbor)
                queue.append((neighbor.id, current_depth + 1))
        return tuple(result)

    def find_path(
        self,
        source_id: str,
        target_id: str,
        *,
        kinds: set[EdgeKind | str] | None = None,
        max_depth: int | None = None,
    ) -> tuple[Edge, ...] | None:
        source = self.get_node(source_id)
        target = self.get_node(target_id)
        if source.id == target.id:
            return ()
        accepted = self._kind_values(kinds)
        queue: deque[tuple[str, int]] = deque([(source.id, 0)])
        visited = {source.id}
        predecessor: dict[str, Edge] = {}
        while queue:
            current, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            for edge in self._outgoing.get(current, ()):
                if accepted is not None and edge.kind not in accepted:
                    continue
                if edge.target in visited or edge.target not in self._nodes:
                    continue
                visited.add(edge.target)
                predecessor[edge.target] = edge
                if edge.target == target.id:
                    path: list[Edge] = []
                    cursor = target.id
                    while cursor != source.id:
                        previous = predecessor[cursor]
                        path.append(previous)
                        cursor = previous.source
                    path.reverse()
                    return tuple(path)
                queue.append((edge.target, depth + 1))
        return None

    def export_json(self) -> str:
        payload = {
            "nodes": [
                self._nodes[node_id].to_dict() for node_id in sorted(self._nodes)
            ],
            "edges": [
                self._edges[edge_id].to_dict() for edge_id in sorted(self._edges)
            ],
        }
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
