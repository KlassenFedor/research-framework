"""A derived, deletable index of the vault.

The Markdown files remain the only source of truth. This index exists so that
opening an unchanged project does not have to decode every one of them again,
and so that reading a single node does not have to read all of them.

Everything here is written defensively: a cache that is missing, stale, corrupt,
of an unknown version or from a different configuration is treated as absent, and
the caller rebuilds it from the files. Deleting the cache directory must cost
time and nothing else.

The store is SQLite because the two operations that dominate at scale are
"read the rows for the files I actually care about" and "update one row after a
mutation". A single JSON document could serve neither without reading and
rewriting the whole thing.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .discovery import DiscoveredProject

_CACHE_VERSION = 3
_CACHE_DIRECTORY = ".research-cache"
_CACHE_FILE = "index-v3.sqlite3"

# Bumped whenever the canonical serialization changes, so that an is_canonical
# flag recorded by an older writer is never believed by a newer one.
CODEC_VERSION = 1


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
    # Recorded by the operations that can prove them, and believed only while the
    # fingerprint still matches the file on disk.
    structural_ok: bool = False
    is_canonical: bool | None = None
    codec_version: int = CODEC_VERSION


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
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    ctime_ns INTEGER NOT NULL,
    inode INTEGER NOT NULL,
    revision TEXT NOT NULL,
    body_offset INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    structural_ok INTEGER NOT NULL,
    is_canonical INTEGER,
    codec_version INTEGER NOT NULL,
    metadata TEXT NOT NULL,
    checksum TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nodes_by_id ON nodes (node_id);
CREATE TABLE IF NOT EXISTS aliases (
    alias TEXT PRIMARY KEY,
    path TEXT NOT NULL
);
-- A mutation replaces one node's aliases by path. Without this index that is a
-- scan of every alias in the project, which is most of the cost of a mutation.
CREATE INDEX IF NOT EXISTS aliases_by_path ON aliases (path);
"""

_COLUMNS = (
    "path, size, mtime_ns, ctime_ns, inode, revision, body_offset, node_id, "
    "structural_ok, is_canonical, codec_version, metadata, checksum"
)


def _row_checksum(values: Sequence[Any]) -> str:
    """Hash a row's content so that an edited database is spotted, not trusted."""

    return hashlib.sha256(_canonical_json(list(values))).hexdigest()


def _safe_cache_directory(project: DiscoveredProject) -> Path | None:
    target = cache_path(project)
    directory = target.parent
    if directory.is_symlink() or target.is_symlink():
        return None
    return directory


def _open_database(target: Path, *, create: bool) -> sqlite3.Connection | None:
    try:
        connection = sqlite3.connect(target, isolation_level=None)
    except (OSError, sqlite3.Error):
        return None
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        if create:
            connection.executescript(_SCHEMA)
        else:
            connection.execute("SELECT 1 FROM meta LIMIT 1")
    except sqlite3.Error:
        connection.close()
        return None
    return connection


def _discard(target: Path) -> None:
    """Delete a cache file that cannot be opened, along with its journals."""

    for path in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
        if path.is_symlink():
            continue
        with suppress(OSError):
            path.unlink(missing_ok=True)


def _connect(project: DiscoveredProject, *, create: bool) -> sqlite3.Connection | None:
    target = cache_path(project)
    directory = _safe_cache_directory(project)
    if directory is None:
        return None
    if not create and not target.is_file():
        return None
    if create:
        try:
            directory.mkdir(mode=0o700, parents=False, exist_ok=True)
            if directory.is_symlink():
                return None
            ignore = directory / ".gitignore"
            if not ignore.is_symlink() and not ignore.exists():
                ignore.write_text("*\n", encoding="utf-8")
        except OSError:
            return None
    connection = _open_database(target, create=create)
    if connection is not None or not create:
        return connection
    # The file exists but is not a database this version can use. It is derived
    # data we own, so replacing it is better than paying the cold path forever.
    if target.is_file() and not target.is_symlink():
        _discard(target)
        return _open_database(target, create=True)
    return None


def _signature_matches(connection: sqlite3.Connection, expected: str) -> bool:
    try:
        rows = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return False
    return (
        rows.get("cache_version") == str(_CACHE_VERSION)
        and rows.get("config_signature") == expected
    )


def _decode_row(row: Sequence[Any]) -> CachedNodeRecord | None:
    (
        raw_path,
        size,
        mtime_ns,
        ctime_ns,
        inode,
        revision,
        body_offset,
        _node_id,
        structural_ok,
        is_canonical,
        codec_version,
        metadata_text,
        checksum,
    ) = row
    if _row_checksum(row[:-1]) != checksum:
        return None
    if not isinstance(raw_path, str) or not raw_path:
        return None
    relative_path = Path(raw_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    try:
        metadata = json.loads(metadata_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(metadata, dict):
        return None
    return CachedNodeRecord(
        path=relative_path,
        fingerprint=FileFingerprint(
            size=size, mtime_ns=mtime_ns, ctime_ns=ctime_ns, inode=inode
        ),
        revision=revision,
        body_offset=body_offset,
        metadata=metadata,
        structural_ok=bool(structural_ok),
        is_canonical=None if is_canonical is None else bool(is_canonical),
        codec_version=codec_version,
    )


def _row_values(record: CachedNodeRecord) -> list[Any]:
    node_id = record.metadata.get("id")
    values: list[Any] = [
        record.path.as_posix(),
        record.fingerprint.size,
        record.fingerprint.mtime_ns,
        record.fingerprint.ctime_ns,
        record.fingerprint.inode,
        record.revision,
        record.body_offset,
        node_id if isinstance(node_id, str) else "",
        int(record.structural_ok),
        None if record.is_canonical is None else int(record.is_canonical),
        record.codec_version,
        _canonical_json(record.metadata).decode("utf-8"),
    ]
    values.append(_row_checksum(values))
    return values


def _alias_rows(record: CachedNodeRecord) -> list[tuple[str, str]]:
    aliases = record.metadata.get("aliases", ())
    if not isinstance(aliases, list):
        return []
    path = record.path.as_posix()
    return [(alias, path) for alias in aliases if isinstance(alias, str)]


def load_index(project: DiscoveredProject) -> dict[Path, CachedNodeRecord]:
    """Return every usable entry, or an empty mapping when the cache is not."""

    connection = _connect(project, create=False)
    if connection is None:
        return {}
    with closing(connection):
        if not _signature_matches(connection, _config_signature(project)):
            return {}
        try:
            rows = connection.execute(f"SELECT {_COLUMNS} FROM nodes").fetchall()
        except sqlite3.Error:
            return {}
        records: dict[Path, CachedNodeRecord] = {}
        for row in rows:
            record = _decode_row(row)
            # One unusable row means the cache cannot be reasoned about as a
            # whole; rebuilding is cheaper than deciding what else to distrust.
            if record is None or record.path in records:
                return {}
            records[record.path] = record
        return records


def lookup_record(
    project: DiscoveredProject,
    reference: str,
) -> tuple[CachedNodeRecord | None, tuple[str, ...]]:
    """Resolve one ID, alias or unambiguous ID prefix without reading the vault.

    Returns the record and, when a prefix matched more than one node, the
    competing IDs so the caller can report the ambiguity rather than guess.
    """

    connection = _connect(project, create=False)
    if connection is None:
        return None, ()
    with closing(connection):
        if not _signature_matches(connection, _config_signature(project)):
            return None, ()
        try:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM nodes WHERE node_id = ?", (reference,)
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    f"SELECT {_COLUMNS} FROM nodes WHERE path = "
                    "(SELECT path FROM aliases WHERE alias = ?)",
                    (reference,),
                ).fetchall()
            if not rows:
                candidates = connection.execute(
                    "SELECT node_id FROM nodes WHERE node_id GLOB ? ORDER BY node_id",
                    (_glob_prefix(reference),),
                ).fetchall()
                if len(candidates) > 1:
                    return None, tuple(str(item[0]) for item in candidates)
                if len(candidates) == 1:
                    rows = connection.execute(
                        f"SELECT {_COLUMNS} FROM nodes WHERE node_id = ?",
                        (candidates[0][0],),
                    ).fetchall()
        except sqlite3.Error:
            return None, ()
        if len(rows) != 1:
            return None, ()
        return _decode_row(rows[0]), ()


def _glob_prefix(reference: str) -> str:
    escaped = reference.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]")
    return f"{escaped}*"


def write_index(
    project: DiscoveredProject,
    records: Iterable[CachedNodeRecord],
) -> bool:
    """Replace the whole index. Used when the vault has been read end to end."""

    connection = _connect(project, create=True)
    if connection is None:
        return False
    with closing(connection):
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM nodes")
            connection.execute("DELETE FROM aliases")
            connection.execute("DELETE FROM meta")
            connection.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                (
                    ("cache_version", str(_CACHE_VERSION)),
                    ("config_signature", _config_signature(project)),
                ),
            )
            placeholders = ", ".join("?" * 13)
            for record in records:
                connection.execute(
                    f"INSERT OR REPLACE INTO nodes ({_COLUMNS}) "
                    f"VALUES ({placeholders})",
                    _row_values(record),
                )
                connection.executemany(
                    "INSERT OR REPLACE INTO aliases (alias, path) VALUES (?, ?)",
                    _alias_rows(record),
                )
            connection.execute("COMMIT")
        except sqlite3.Error:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            return False
    return True


def update_index_entry(
    project: DiscoveredProject,
    record: CachedNodeRecord,
    *,
    previous_path: Path | None = None,
) -> bool:
    """Record one node after a mutation, leaving every other entry untouched."""

    connection = _connect(project, create=False)
    if connection is None:
        return False
    with closing(connection):
        if not _signature_matches(connection, _config_signature(project)):
            return False
        try:
            connection.execute("BEGIN IMMEDIATE")
            for path in filter(None, (previous_path, record.path)):
                posix = path.as_posix()
                connection.execute("DELETE FROM nodes WHERE path = ?", (posix,))
                connection.execute("DELETE FROM aliases WHERE path = ?", (posix,))
            placeholders = ", ".join("?" * 13)
            connection.execute(
                f"INSERT OR REPLACE INTO nodes ({_COLUMNS}) VALUES ({placeholders})",
                _row_values(record),
            )
            connection.executemany(
                "INSERT OR REPLACE INTO aliases (alias, path) VALUES (?, ?)",
                _alias_rows(record),
            )
            connection.execute("COMMIT")
        except sqlite3.Error:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            return False
    return True


def mark_canonical(
    project: DiscoveredProject,
    verdicts: Iterable[tuple[Path, FileFingerprint, bool]],
) -> bool:
    """Store what a formatting check proved about files it actually examined."""

    connection = _connect(project, create=False)
    if connection is None:
        return False
    with closing(connection):
        if not _signature_matches(connection, _config_signature(project)):
            return False
        try:
            connection.execute("BEGIN IMMEDIATE")
            for path, fingerprint, canonical in verdicts:
                posix = path.as_posix()
                rows = connection.execute(
                    f"SELECT {_COLUMNS} FROM nodes WHERE path = ?", (posix,)
                ).fetchall()
                if len(rows) != 1:
                    continue
                record = _decode_row(rows[0])
                # Only a row still describing this exact file may be updated:
                # anything else would attach the verdict to different content.
                if record is None or record.fingerprint != fingerprint:
                    continue
                updated = replace(
                    record, is_canonical=canonical, codec_version=CODEC_VERSION
                )
                placeholders = ", ".join("?" * 13)
                connection.execute(
                    f"INSERT OR REPLACE INTO nodes ({_COLUMNS}) "
                    f"VALUES ({placeholders})",
                    _row_values(updated),
                )
            connection.execute("COMMIT")
        except sqlite3.Error:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            return False
    return True
