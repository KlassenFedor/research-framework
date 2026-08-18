from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import DiscoveredProject

_CACHE_VERSION = 1
_CACHE_DIRECTORY = ".research-cache"
_CACHE_FILE = "index-v1.json"


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    size: int
    mtime_ns: int
    ctime_ns: int
    inode: int

    @classmethod
    def from_path(cls, path: Path) -> FileFingerprint:
        stat = path.stat()
        return cls(
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            ctime_ns=stat.st_ctime_ns,
            inode=stat.st_ino,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "inode": self.inode,
        }


@dataclass(frozen=True, slots=True)
class CachedNodeRecord:
    path: Path
    fingerprint: FileFingerprint
    revision: str
    body_offset: int
    metadata: dict[str, Any]


def cache_path(project: DiscoveredProject) -> Path:
    return project.root / _CACHE_DIRECTORY / _CACHE_FILE


def _config_signature(project: DiscoveredProject) -> str:
    config = project.config
    value = {
        "format_version": config.format_version,
        "project_id": config.project_id,
        "title": config.title,
        "vault": config.vault,
        "default_language": config.default_language,
        "policies": {
            "require_falsification_criteria": (
                config.policies.require_falsification_criteria
            ),
            "require_evidence_provenance": (
                config.policies.require_evidence_provenance
            ),
            "forbid_dependency_cycles": config.policies.forbid_dependency_cycles,
        },
    }
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _decode_fingerprint(value: object) -> FileFingerprint | None:
    if not isinstance(value, dict) or set(value) != {
        "size",
        "mtime_ns",
        "ctime_ns",
        "inode",
    }:
        return None
    fields = {
        key: _non_negative_integer(value[key])
        for key in ("size", "mtime_ns", "ctime_ns", "inode")
    }
    if any(item is None for item in fields.values()):
        return None
    return FileFingerprint(
        size=fields["size"],  # type: ignore[arg-type]
        mtime_ns=fields["mtime_ns"],  # type: ignore[arg-type]
        ctime_ns=fields["ctime_ns"],  # type: ignore[arg-type]
        inode=fields["inode"],  # type: ignore[arg-type]
    )


def _decode_entry(
    project: DiscoveredProject,
    value: object,
) -> CachedNodeRecord | None:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "fingerprint",
        "revision",
        "body_offset",
        "metadata",
    }:
        return None
    raw_path = value["path"]
    revision = value["revision"]
    body_offset = _non_negative_integer(value["body_offset"])
    metadata = value["metadata"]
    fingerprint = _decode_fingerprint(value["fingerprint"])
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not isinstance(revision, str)
        or len(revision) != 64
        or any(character not in "0123456789abcdef" for character in revision)
        or body_offset is None
        or not isinstance(metadata, dict)
        or fingerprint is None
    ):
        return None
    relative_path = Path(raw_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    try:
        absolute_path = (project.root / relative_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not absolute_path.is_relative_to(project.vault):
        return None
    return CachedNodeRecord(
        path=relative_path,
        fingerprint=fingerprint,
        revision=revision,
        body_offset=body_offset,
        metadata=dict(metadata),
    )


def load_index(project: DiscoveredProject) -> dict[Path, CachedNodeRecord]:
    target = cache_path(project)
    if target.is_symlink() or target.parent.is_symlink():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    if not isinstance(value, dict) or set(value) != {
        "cache_version",
        "config_signature",
        "entries",
        "content_sha256",
    }:
        return {}
    content_sha256 = value.get("content_sha256")
    unsigned = {key: item for key, item in value.items() if key != "content_sha256"}
    if (
        value.get("cache_version") != _CACHE_VERSION
        or value.get("config_signature") != _config_signature(project)
        or not isinstance(value.get("entries"), list)
        or not isinstance(content_sha256, str)
        or hashlib.sha256(_canonical_json(unsigned)).hexdigest() != content_sha256
    ):
        return {}

    records: dict[Path, CachedNodeRecord] = {}
    for raw_entry in value["entries"]:
        entry = _decode_entry(project, raw_entry)
        if entry is None or entry.path in records:
            return {}
        records[entry.path] = entry
    return records


def _entry_dict(record: CachedNodeRecord) -> dict[str, object]:
    return {
        "path": record.path.as_posix(),
        "fingerprint": record.fingerprint.to_dict(),
        "revision": record.revision,
        "body_offset": record.body_offset,
        "metadata": record.metadata,
    }


def write_index(
    project: DiscoveredProject,
    records: list[CachedNodeRecord],
) -> bool:
    target = cache_path(project)
    directory = target.parent
    temporary: Path | None = None
    try:
        if directory.is_symlink() or target.is_symlink():
            return False
        directory.mkdir(mode=0o700, parents=False, exist_ok=True)
        if directory.is_symlink():
            return False
        ignore = directory / ".gitignore"
        if ignore.is_symlink():
            return False
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")
        unsigned: dict[str, object] = {
            "cache_version": _CACHE_VERSION,
            "config_signature": _config_signature(project),
            "entries": [
                _entry_dict(record)
                for record in sorted(records, key=lambda item: item.path)
            ],
        }
        value = {
            **unsigned,
            "content_sha256": hashlib.sha256(_canonical_json(unsigned)).hexdigest(),
        }
        encoded = _canonical_json(value) + b"\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".index-",
            suffix=".tmp",
            dir=directory,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return True
    except (OSError, TypeError, ValueError):
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return False
