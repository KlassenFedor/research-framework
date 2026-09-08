from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from research_framework.domain.errors import (
    ProjectNotFound,
    StorageError,
    UnsupportedFormatVersion,
)

from .yaml_codec import RestrictedYamlError, load_restricted_yaml

_PROJECT_ID = re.compile(r"^prj-[0-9A-HJKMNP-TV-Z]{26}$")


@dataclass(frozen=True, slots=True)
class ProjectPolicies:
    require_falsification_criteria: bool = True
    require_evidence_provenance: bool = True
    forbid_dependency_cycles: bool = True


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    format_version: int
    project_id: str
    title: str
    vault: str
    default_language: str = "en"
    policies: ProjectPolicies = ProjectPolicies()


@dataclass(frozen=True, slots=True)
class DiscoveredProject:
    root: Path
    config_path: Path
    vault: Path
    config: ProjectConfig


def _read_config(path: Path) -> ProjectConfig:
    try:
        raw = load_restricted_yaml(path.read_text(encoding="utf-8"))
    except (OSError, RestrictedYamlError) as error:
        raise StorageError(f"cannot read project config {path}: {error}") from error

    allowed = {
        "format_version",
        "project_id",
        "title",
        "vault",
        "default_language",
        "policies",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise StorageError(
            f"unknown project config field(s): {', '.join(sorted(unknown))}"
        )

    version = raw.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise StorageError("project format_version must be an integer")
    if version != 1:
        raise UnsupportedFormatVersion(version, {1})

    required_strings = ("project_id", "title", "vault")
    for field in required_strings:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise StorageError(
                f"project config field {field} must be a non-blank string"
            )

    project_id = raw["project_id"]
    if _PROJECT_ID.fullmatch(project_id) is None:
        raise StorageError("project_id must be prj- followed by a ULID")

    language = raw.get("default_language", "en")
    if not isinstance(language, str) or not language.strip():
        raise StorageError("default_language must be a non-blank string")

    raw_policies = raw.get("policies", {})
    if not isinstance(raw_policies, dict):
        raise StorageError("policies must be a mapping")
    allowed_policies = {
        "require_falsification_criteria",
        "require_evidence_provenance",
        "forbid_dependency_cycles",
    }
    unknown_policies = set(raw_policies) - allowed_policies
    if unknown_policies:
        raise StorageError(
            f"unknown project policy: {', '.join(sorted(unknown_policies))}"
        )
    for field, value in raw_policies.items():
        if not isinstance(value, bool):
            raise StorageError(f"project policy {field} must be boolean")

    policies = ProjectPolicies(**raw_policies)
    return ProjectConfig(
        format_version=version,
        project_id=raw["project_id"],
        title=raw["title"],
        vault=raw["vault"],
        default_language=language,
        policies=policies,
    )


def discover_project(start: Path) -> DiscoveredProject:
    original = start
    resolved = start.resolve()
    current = resolved.parent if resolved.is_file() else resolved
    config_path: Path | None = None
    for candidate in (current, *current.parents):
        possible = candidate / "research.yaml"
        if possible.is_file():
            config_path = possible
            break
    if config_path is None:
        raise ProjectNotFound(original)

    config = _read_config(config_path)
    vault_setting = Path(config.vault)
    if vault_setting.is_absolute() or PureWindowsPath(config.vault).is_absolute():
        raise StorageError("vault must be a relative path inside the project root")
    root = config_path.parent.resolve()
    vault = (root / vault_setting).resolve()
    if not vault.is_relative_to(root):
        raise StorageError("vault resolves outside the project root")
    if not vault.is_dir():
        raise StorageError(f"vault directory does not exist: {vault}")
    return DiscoveredProject(
        root=root,
        config_path=config_path,
        vault=vault,
        config=config,
    )


def discover_node_files(project: DiscoveredProject) -> tuple[Path, ...]:
    """List the node files in the vault, in a deterministic order.

    Directory entries carry their own type, so walking with :func:`os.scandir`
    answers "file or directory, and is it a link?" without a further system call
    per entry. Refusing to descend into a symlinked directory is what keeps the
    walk inside the vault: no entry reached this way can resolve outside it, so
    no path has to be resolved to find that out.
    """

    names: list[str] = []
    root = str(project.vault)
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        pending.append(entry.path)
                        continue
                    if not entry.name.endswith(".md") or entry.name == "PROJECT.md":
                        continue
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                names.append(entry.path)
    # Order by path segment, which is how Path compares. Sorting the raw strings
    # would disagree whenever a directory name is a prefix of another and the
    # next character sorts below the separator.
    names.sort(key=lambda name: name.split(os.sep))
    return tuple(Path(name) for name in names)
