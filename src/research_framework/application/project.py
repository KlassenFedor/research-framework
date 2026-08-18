from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_framework.domain.actors import Actor
from research_framework.domain.diagnostics import Diagnostic
from research_framework.domain.edges import RelationDraft
from research_framework.domain.enums import (
    DiagnosticSeverity,
    EdgeKind,
    NodeKind,
    NodeStatus,
)
from research_framework.domain.errors import (
    AmbiguousReference,
    NodeNotFound,
    RevisionConflict,
    StorageError,
    ValidationFailed,
)
from research_framework.domain.graph import Edge, GraphSnapshot, Node
from research_framework.domain.nodes import NodeDraft
from research_framework.storage.discovery import (
    DiscoveredProject,
    discover_node_files,
    discover_project,
)
from research_framework.storage.loader import load_snapshot, parse_edges, parse_node
from research_framework.storage.markdown_codec import DecodedMarkdown, MarkdownCodec
from research_framework.storage.yaml_codec import dump_restricted_yaml

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_PREFIXES = {
    NodeKind.QUESTION: "que",
    NodeKind.HYPOTHESIS: "hyp",
    NodeKind.CLAIM: "clm",
    NodeKind.EXPERIMENT: "exp",
    NodeKind.RUN: "run",
    NodeKind.EVIDENCE: "evd",
    NodeKind.ASSESSMENT: "asm",
    NodeKind.SOURCE: "src",
    NodeKind.ARTIFACT: "art",
    NodeKind.DECISION: "dec",
}
_FOLDERS = {
    NodeKind.QUESTION: "questions",
    NodeKind.HYPOTHESIS: "hypotheses",
    NodeKind.CLAIM: "claims",
    NodeKind.EXPERIMENT: "experiments",
    NodeKind.RUN: "runs",
    NodeKind.EVIDENCE: "evidence",
    NodeKind.ASSESSMENT: "assessments",
    NodeKind.SOURCE: "sources",
    NodeKind.ARTIFACT: "artifacts",
    NodeKind.DECISION: "decisions",
}


@dataclass(frozen=True, slots=True)
class FormatResult:
    """Outcome of checking or applying canonical node serialization."""

    checked_files: int
    changed_paths: tuple[Path, ...]
    applied: bool


@dataclass(frozen=True, slots=True)
class _FormatCandidate:
    path: Path
    node_id: str
    original: bytes
    formatted: bytes
    revision: str


def _ulid() -> str:
    milliseconds = int(time.time() * 1000) & ((1 << 48) - 1)
    value = (milliseconds << 80) | secrets.randbits(80)
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD[value & 31]
        value >>= 5
    return "".join(encoded)


def _actor_dict(actor: Actor) -> dict[str, str]:
    value = {"kind": actor.kind.value, "id": actor.id}
    if actor.run_id is not None:
        value["run_id"] = actor.run_id
    if actor.model is not None:
        value["model"] = actor.model
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    characters: list[str] = []
    separator_pending = False
    for character in normalized:
        category = unicodedata.category(character)
        if character.isalnum() or (category.startswith("M") and characters):
            if separator_pending and characters:
                characters.append("-")
            characters.append(character)
            separator_pending = False
        elif characters:
            separator_pending = True
    return "".join(characters)[:80].rstrip("-") or "node"


def _plain(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


class Project:
    """Application service shared by the Python API and presentation adapters."""

    def __init__(self, discovered: DiscoveredProject, snapshot: GraphSnapshot) -> None:
        self._discovered = discovered
        self._snapshot = snapshot
        self._snapshot_shared = False
        self._codec = MarkdownCodec()
        self._last_diagnostics: tuple[Diagnostic, ...] = ()

    @classmethod
    def open(cls, path: Path) -> Project:
        discovered = discover_project(path)
        from research_framework.validation import validate_project

        diagnostics = validate_project(discovered.root)
        if any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics):
            raise ValidationFailed(diagnostics)
        return cls(discovered, load_snapshot(discovered))

    @classmethod
    def init(
        cls,
        path: Path,
        *,
        title: str,
        default_language: str = "en",
    ) -> Project:
        target = path.resolve()
        if target.exists() and any(target.iterdir()):
            raise StorageError(f"target directory is not empty: {target}")
        if not title.strip():
            raise ValueError("title must not be blank")
        target.mkdir(parents=True, exist_ok=True)
        vault = target / "research"
        vault.mkdir()
        for folder in _FOLDERS.values():
            (vault / folder).mkdir(exist_ok=True)
        (vault / "PROJECT.md").write_text(f"# {title}\n", encoding="utf-8")
        config = {
            "format_version": 1,
            "project_id": f"prj-{_ulid()}",
            "title": title,
            "vault": "research",
            "default_language": default_language,
            "policies": {
                "require_falsification_criteria": True,
                "require_evidence_provenance": True,
                "forbid_dependency_cycles": True,
            },
        }
        (target / "research.yaml").write_text(
            dump_restricted_yaml(config), encoding="utf-8"
        )
        return cls.open(target)

    def snapshot(self) -> GraphSnapshot:
        self._snapshot_shared = True
        return self._snapshot

    def last_diagnostics(self) -> tuple[Diagnostic, ...]:
        """Diagnostics from the latest reporting operation when it succeeded."""

        return self._last_diagnostics

    @property
    def root(self) -> Path:
        return self._discovered.root

    def validate(self) -> tuple[Diagnostic, ...]:
        from research_framework.validation import validate_project

        return validate_project(self.root)

    def format(self, *, check: bool = False) -> FormatResult:
        """Check or apply canonical YAML front matter across the vault.

        Markdown bodies are copied byte-for-byte. Applying changes is treated as
        one operation: all outputs are prepared before the first write and prior
        writes are rolled back if a later write or snapshot refresh fails.
        """

        self._last_diagnostics = ()
        diagnostics = self.validate()
        if any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics):
            raise ValidationFailed(diagnostics)

        paths = discover_node_files(self._discovered)
        candidates: list[_FormatCandidate] = []
        for path in paths:
            self._safe_target(path)
            try:
                original = path.read_bytes()
            except OSError as error:
                raise StorageError(
                    f"cannot read node before formatting: {path}"
                ) from error
            try:
                text = original.decode("utf-8")
            except UnicodeDecodeError as error:
                raise StorageError(f"node is not valid UTF-8: {path}") from error
            document = self._codec.decode(text, path=path)
            formatted = self._codec.encode(document).encode("utf-8")
            # Prepare and parse every output before touching any destination.
            self._codec.decode(formatted.decode("utf-8"), path=path)
            if formatted == original:
                continue
            candidates.append(
                _FormatCandidate(
                    path=path,
                    node_id=str(document.metadata.get("id", "unknown")),
                    original=original,
                    formatted=formatted,
                    revision=hashlib.sha256(original).hexdigest(),
                )
            )

        result = FormatResult(
            checked_files=len(paths),
            changed_paths=tuple(candidate.path for candidate in candidates),
            applied=not check and bool(candidates),
        )
        if check:
            self._last_diagnostics = diagnostics
            return result

        written: list[_FormatCandidate] = []
        try:
            for candidate in candidates:
                try:
                    current = candidate.path.read_bytes()
                except OSError as error:
                    raise StorageError(
                        f"cannot read node before formatting: {candidate.path}"
                    ) from error
                actual_revision = hashlib.sha256(current).hexdigest()
                if actual_revision != candidate.revision:
                    raise RevisionConflict(
                        candidate.node_id,
                        candidate.revision,
                        actual_revision,
                    )
                self._atomic_write_bytes(candidate.path, candidate.formatted)
                written.append(candidate)
            self._refresh()
        except Exception:
            rollback_errors: list[Exception] = []
            for candidate in reversed(written):
                try:
                    current = candidate.path.read_bytes()
                    if current != candidate.formatted:
                        rollback_errors.append(
                            StorageError(
                                "refusing to overwrite a concurrent edit while rolling "
                                f"back formatting: {candidate.path}"
                            )
                        )
                        continue
                    self._atomic_write_bytes(candidate.path, candidate.original)
                # Rollback must continue after any individual restoration failure
                # so that as many original files as possible are recovered.
                except Exception as rollback_error:  # noqa: BLE001
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise StorageError(
                    "cannot fully roll back failed project formatting"
                ) from rollback_errors[0]
            raise

        self._last_diagnostics = diagnostics
        return result

    def _refresh(self) -> None:
        diagnostics = self.validate()
        if any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics):
            raise ValidationFailed(diagnostics)
        self._snapshot = load_snapshot(self._discovered)
        self._snapshot_shared = False

    def _safe_target(self, target: Path) -> None:
        vault = self._discovered.vault.resolve()
        if not target.parent.resolve().is_relative_to(vault):
            raise StorageError("write target resolves outside vault")
        if target.is_symlink():
            raise StorageError("refusing to write through symlink")

    def _write_document(
        self,
        target: Path,
        metadata: Mapping[str, Any],
        body: str,
        *,
        expected_revision: str | None = None,
    ) -> tuple[DecodedMarkdown, bytes]:
        self._safe_target(target)
        if expected_revision is not None:
            try:
                current = target.read_bytes()
            except OSError as error:
                raise StorageError(
                    f"cannot read node before update: {target}"
                ) from error
            actual_revision = hashlib.sha256(current).hexdigest()
            if actual_revision != expected_revision:
                node_id = str(metadata.get("id", "unknown"))
                raise RevisionConflict(node_id, expected_revision, actual_revision)

        encoded = self._codec.encode(
            DecodedMarkdown(metadata=metadata, body=body, path=target)
        )
        # Decode before touching the destination so serialization failures are
        # never able to corrupt a valid node.
        document = self._codec.decode(encoded, path=target)
        raw = encoded.encode("utf-8")
        self._atomic_write_bytes(target, raw)
        return document, raw

    def _publish_document(self, document: DecodedMarkdown, raw: bytes) -> None:
        """Publish one already validated and serialized document in memory."""

        node = parse_node(document, revision=hashlib.sha256(raw).hexdigest())
        edges = parse_edges(node, document.metadata)
        if self._snapshot_shared:
            self._snapshot = self._snapshot._replacing_node(node, edges)
        else:
            self._snapshot._replace_node_in_place(node, edges)
        self._snapshot_shared = False

    def _atomic_write_bytes(self, target: Path, content: bytes) -> None:
        self._safe_target(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".rf-", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._safe_target(target)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _invalid(
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ValidationFailed:
        return ValidationFailed(
            (
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code=code,
                    message=message,
                    field=field,
                    details=dict(details or {}),
                ),
            )
        )

    def _validate_candidate_document(
        self,
        target: Path,
        metadata: Mapping[str, Any],
    ) -> tuple[Diagnostic, ...]:
        from research_framework.validation import validate_candidate_node

        diagnostics = validate_candidate_node(
            self._discovered,
            path=target,
            metadata=metadata,
            snapshot=self._snapshot,
        )
        if any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics):
            raise ValidationFailed(diagnostics)
        return diagnostics

    def _replace_document(
        self,
        target: Path,
        metadata: Mapping[str, Any],
        body: str,
        *,
        expected_revision: str,
    ) -> tuple[Diagnostic, ...]:
        diagnostics = self._validate_candidate_document(target, metadata)
        self._safe_target(target)
        try:
            original = target.read_bytes()
        except OSError as error:
            raise StorageError(f"cannot read node before update: {target}") from error
        actual_revision = hashlib.sha256(original).hexdigest()
        if actual_revision != expected_revision:
            node_id = str(metadata.get("id", "unknown"))
            raise RevisionConflict(node_id, expected_revision, actual_revision)

        written = False
        try:
            document, raw = self._write_document(
                target,
                metadata,
                body,
                expected_revision=expected_revision,
            )
            written = True
            self._publish_document(document, raw)
        except Exception:
            if written:
                try:
                    self._atomic_write_bytes(target, original)
                except Exception as rollback_error:
                    raise StorageError(
                        f"cannot roll back failed node update: {target}"
                    ) from rollback_error
            raise
        return diagnostics

    def create_node(
        self,
        draft: NodeDraft,
        *,
        actor: Actor,
        initial_relations: Sequence[RelationDraft] = (),
    ) -> Node:
        self._last_diagnostics = ()
        kind = draft.kind
        node_id = f"{_PREFIXES[kind]}-{_ulid()}"
        timestamp = _now()
        metadata: dict[str, Any] = {
            "format_version": 1,
            "id": node_id,
            "kind": kind.value,
            "title": draft.title,
            "status": NodeStatus.DRAFT.value,
        }
        for field in fields(draft):
            if field.name in {"title", "body"}:
                continue
            value = getattr(draft, field.name)
            if value is None or value in ((), frozenset()):
                continue
            metadata[field.name] = _plain(value)
        relations: list[dict[str, Any]] = []
        for index, relation_draft in enumerate(initial_relations):
            if not isinstance(relation_draft, RelationDraft):
                raise self._invalid(
                    "invalid_relation_draft",
                    "initial relation must be a RelationDraft",
                    field=f"initial_relations[{index}]",
                )
            try:
                target_node = self._snapshot.get_node(relation_draft.target)
            except NodeNotFound as error:
                raise self._invalid(
                    "relation_target_not_found",
                    f"relation target does not exist: {relation_draft.target}",
                    field=f"initial_relations[{index}].target",
                    details={"target": relation_draft.target},
                ) from error
            except AmbiguousReference as error:
                raise self._invalid(
                    "ambiguous_relation_target",
                    f"relation target is ambiguous: {relation_draft.target}",
                    field=f"initial_relations[{index}].target",
                    details={
                        "target": relation_draft.target,
                        "candidates": list(error.candidates),
                    },
                ) from error
            relation: dict[str, Any] = {
                "id": f"rel-{_ulid()}",
                "kind": relation_draft.kind.value,
                "target": target_node.id,
                "created_at": timestamp,
                "created_by": _actor_dict(actor),
            }
            if relation_draft.rationale is not None:
                relation["rationale"] = relation_draft.rationale
            relations.append(relation)

        metadata.update(
            {
                "created_at": timestamp,
                "created_by": _actor_dict(actor),
                "updated_at": timestamp,
                "updated_by": _actor_dict(actor),
                "relations": relations,
            }
        )
        folder = self._discovered.vault / _FOLDERS[kind]
        target = folder / f"{node_id}--{_slug(draft.title)}.md"
        body = draft.body or f"\n# {draft.title}\n"
        diagnostics = self._validate_candidate_document(target, metadata)
        if target.exists():
            raise StorageError(f"refusing to overwrite existing node: {target}")

        written = False
        try:
            document, raw = self._write_document(target, metadata, body)
            written = True
            self._publish_document(document, raw)
        except Exception:
            if written:
                try:
                    target.unlink(missing_ok=True)
                except OSError as rollback_error:
                    raise StorageError(
                        f"cannot roll back failed node creation: {target}"
                    ) from rollback_error
            raise
        self._last_diagnostics = diagnostics
        return self._snapshot.get_node(node_id)

    def _read_current(
        self,
        reference: str,
        *,
        expected_revision: str | None = None,
    ) -> tuple[Node, dict[str, Any], str]:
        node = self._snapshot.get_node(reference)
        self._safe_target(node.path)
        try:
            raw = node.path.read_bytes()
        except OSError as error:
            raise StorageError(f"cannot read node: {node.path}") from error
        actual_revision = hashlib.sha256(raw).hexdigest()
        if expected_revision is not None and actual_revision != expected_revision:
            raise RevisionConflict(node.id, expected_revision, actual_revision)
        document = self._codec.decode(raw.decode("utf-8"), path=node.path)
        return node, dict(document.metadata), document.body

    def update_node(
        self,
        node_id: str,
        *,
        patch: Mapping[str, Any],
        expected_revision: str,
        actor: Actor,
    ) -> Node:
        self._last_diagnostics = ()
        node, metadata, body = self._read_current(
            node_id, expected_revision=expected_revision
        )
        immutable = {
            "format_version",
            "id",
            "kind",
            "created_at",
            "created_by",
            "relations",
        }
        if immutable.intersection(patch):
            field = min(immutable.intersection(patch))
            raise self._invalid(
                "immutable_field", f"cannot update {field}", field=field
            )
        allowed = set(metadata) | {"summary", "tags", "aliases", "extensions"}
        unknown = set(patch) - allowed
        if unknown:
            field = min(unknown)
            raise self._invalid("unknown_field", f"unknown field: {field}", field=field)
        if "status" in patch:
            try:
                NodeStatus(patch["status"])
            except (TypeError, ValueError) as error:
                raise self._invalid(
                    "invalid_status", "invalid node status", field="status"
                ) from error
        for field in ("tags", "aliases"):
            if field in patch and (
                not isinstance(patch[field], (list, tuple, set, frozenset))
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in patch[field]
                )
            ):
                raise self._invalid(
                    "invalid_field_type", f"{field} must be strings", field=field
                )
        metadata.update({key: _plain(value) for key, value in patch.items()})
        metadata["updated_at"] = _now()
        metadata["updated_by"] = _actor_dict(actor)
        diagnostics = self._replace_document(
            node.path,
            metadata,
            body,
            expected_revision=expected_revision,
        )
        self._last_diagnostics = diagnostics
        return self._snapshot.get_node(node.id)

    def archive_node(
        self,
        node_id: str,
        *,
        expected_revision: str,
        actor: Actor,
    ) -> Node:
        return self.update_node(
            node_id,
            patch={"status": NodeStatus.ARCHIVED.value},
            expected_revision=expected_revision,
            actor=actor,
        )

    def add_edge(
        self,
        *,
        source: str,
        kind: EdgeKind | str,
        target: str,
        actor: Actor,
        rationale: str | None = None,
    ) -> Edge:
        self._last_diagnostics = ()
        source_node = self._snapshot.get_node(source)
        target_node = self._snapshot.get_node(target)
        edge_kind = EdgeKind(kind)
        _, metadata, body = self._read_current(
            source_node.id, expected_revision=source_node.revision
        )
        edge_id = f"rel-{_ulid()}"
        relation: dict[str, Any] = {
            "id": edge_id,
            "kind": edge_kind.value,
            "target": target_node.id,
            "created_at": _now(),
            "created_by": _actor_dict(actor),
        }
        if rationale is not None:
            relation["rationale"] = rationale
        relations = list(metadata.get("relations", []))
        relations.append(relation)
        metadata["relations"] = relations
        metadata["updated_at"] = _now()
        metadata["updated_by"] = _actor_dict(actor)
        diagnostics = self._replace_document(
            source_node.path,
            metadata,
            body,
            expected_revision=source_node.revision,
        )
        self._last_diagnostics = diagnostics
        return self._snapshot.get_edge(edge_id)

    def remove_edge(self, edge_id: str, *, actor: Actor) -> None:
        self._last_diagnostics = ()
        edge = self._snapshot.get_edge(edge_id)
        source_node = self._snapshot.get_node(edge.source)
        _, metadata, body = self._read_current(
            source_node.id, expected_revision=source_node.revision
        )
        metadata["relations"] = [
            relation
            for relation in metadata.get("relations", [])
            if relation.get("id") != edge.id
        ]
        metadata["updated_at"] = _now()
        metadata["updated_by"] = _actor_dict(actor)
        diagnostics = self._replace_document(
            source_node.path,
            metadata,
            body,
            expected_revision=source_node.revision,
        )
        self._last_diagnostics = diagnostics
