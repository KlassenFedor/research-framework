"""A reader and a writer for the canonical front matter this framework emits.

Every file written by the framework uses one narrow, fully known corner of block
YAML. Recognising exactly that corner is far cheaper than running a general YAML
parser, and the parser stays the authority: both functions here return ``None``
the moment they meet anything they cannot account for, and the caller falls back
to :mod:`research_framework.storage.yaml_codec`.

That fallback is what makes the fast path safe rather than merely quick. The
subset accepted below is strictly smaller than restricted YAML — anchors,
aliases, tags, merge keys, complex keys and duplicate keys simply cannot be
expressed in it — so nothing reaches an application that the audited loader
would have rejected, and nothing is guessed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import yaml

# Keys the writer emits unquoted, and the only keys the reader accepts plain.
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

# The one numeric shape handled here without consulting PyYAML. Anything else
# numeric is handed over rather than reimplemented, because YAML 1.1 also
# resolves octal, hexadecimal, sexagesimal and underscore-separated forms.
_SIMPLE_INT = re.compile(r"[-+]?(?:0|[1-9][0-9]*)\Z")

_NULL = frozenset({"", "~", "null", "Null", "NULL"})

_BOOL_TAG = "tag:yaml.org,2002:bool"
_INT_TAG = "tag:yaml.org,2002:int"
_NULL_TAG = "tag:yaml.org,2002:null"
_STR_TAG = "tag:yaml.org,2002:str"

# The project narrows what a plain scalar may implicitly become: YAML 1.1
# booleans and timestamps stop resolving, so "yes" and a date stay strings.
# yaml_codec builds RestrictedLoader from the two names below, so the reader
# here and the loader it defers to cannot drift apart.
DISABLED_IMPLICIT_TAGS = frozenset({_BOOL_TAG, "tag:yaml.org,2002:timestamp"})
STRICT_BOOL_PATTERN = re.compile(r"^(?:true|false)$", re.IGNORECASE)
STRICT_BOOL_FIRST = "tTfF"


def _implicit_table(
    disabled: frozenset[str],
    extra: tuple[str, re.Pattern[str], str] | None,
) -> dict[str, tuple[tuple[str, re.Pattern[str]], ...]]:
    """Group PyYAML's implicit resolvers by first character, minus ``disabled``."""

    table: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items():
        for tag, pattern in resolvers:
            if tag in disabled or tag == _STR_TAG:
                continue
            table.setdefault(first, []).append((tag, pattern))
    if extra is not None:
        tag, pattern, firsts = extra
        for first in firsts:
            table.setdefault(first, []).append((tag, pattern))
    return {first: tuple(items) for first, items in table.items()}


# What the loader would make of a plain scalar.
_READER_IMPLICIT = _implicit_table(
    DISABLED_IMPLICIT_TAGS,
    (_BOOL_TAG, STRICT_BOOL_PATTERN, STRICT_BOOL_FIRST),
)
# What the emitter must quote to keep a string a string. The dumper still
# carries the full YAML 1.1 table, which is why "yes" and dates come back
# quoted even though the loader would no longer reinterpret them.
_WRITER_IMPLICIT = _implicit_table(frozenset(), None)

# Characters that carry meaning to YAML at the start of a plain scalar, plus the
# quoting styles the writer does not attempt to reproduce.
_LEADING_INDICATOR = frozenset("-?:,[]{}#&*!|>\"%@`'")

# Anything the emitter would have to escape, or that changes how a line is read.
_UNPRINTABLE = re.compile(r"[\x00-\x1f\x7f-\x9f﻿]")

# PyYAML is configured with width=100 and folds a plain or single-quoted scalar
# at a space once the column passes that. A line no longer than the width has no
# such position, so staying under it is what makes the writer's output exact.
_MAX_LINE = 100


class _Unsupported(Exception):
    """Raised internally when the value leaves the recognised subset."""


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _plain_scalar(token: str) -> Any:
    if not token:
        return None
    for tag, pattern in _READER_IMPLICIT.get(token[0], ()):
        if not pattern.match(token):
            continue
        if tag == _NULL_TAG:
            return None
        if tag == _BOOL_TAG:
            return token.lower() == "true"
        if tag == _INT_TAG and _SIMPLE_INT.match(token):
            return int(token)
        # Floats, and the numeric bases and separators YAML 1.1 still accepts,
        # are the loader's business rather than this reader's.
        raise _Unsupported

    # It is a string, so it must also end where it appears to: nothing in it may
    # open a comment, a nested mapping or another YAML construct.
    if token[0] in _LEADING_INDICATOR or " #" in token or "\t" in token:
        raise _Unsupported
    if ": " in token or token.endswith(":"):
        raise _Unsupported
    if token != token.strip() or _UNPRINTABLE.search(token):
        raise _Unsupported
    return token


def _scalar(token: str) -> Any:
    if token == "{}":
        return {}
    if token == "[]":
        return []
    if token.startswith("'"):
        if len(token) < 2 or not token.endswith("'"):
            raise _Unsupported
        inner = token[1:-1]
        # A lone quote inside means the scalar was folded or escaped in a way
        # this reader does not model.
        if inner.replace("''", "").count("'"):
            raise _Unsupported
        if _UNPRINTABLE.search(inner):
            raise _Unsupported
        return inner.replace("''", "'")
    return _plain_scalar(token)


def _indent_of(line: str) -> int:
    width = len(line) - len(line.lstrip(" "))
    if line[width : width + 1] == "\t":
        raise _Unsupported
    return width


def _read_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        raise _Unsupported
    if lines[index][indent : indent + 2] == "- ":
        return _read_sequence(lines, index, indent)
    return _read_mapping(lines, index, indent)


def _child_indent(lines: list[str], index: int, indent: int) -> int:
    if index >= len(lines):
        raise _Unsupported
    child = _indent_of(lines[index])
    # A nested mapping is written one level in; a sequence stays at the parent's
    # column, which is how PyYAML emits block sequences inside a mapping.
    if child == indent and lines[index][indent : indent + 2] == "- ":
        return indent
    if child == indent + 2:
        return child
    raise _Unsupported


def _read_mapping(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            raise _Unsupported
        current = _indent_of(line)
        if current < indent:
            break
        if current > indent:
            raise _Unsupported
        rest = line[indent:]
        if rest.startswith("- "):
            break
        separator = rest.find(": ")
        if separator == -1:
            if not rest.endswith(":"):
                raise _Unsupported
            key = rest[:-1]
            if not _PLAIN_KEY.match(key) or key in result:
                raise _Unsupported
            result[key], index = _read_block(
                lines, index + 1, _child_indent(lines, index + 1, indent)
            )
            continue
        key = rest[:separator]
        if not _PLAIN_KEY.match(key) or key in result:
            raise _Unsupported
        result[key] = _scalar(rest[separator + 2 :])
        index += 1
    return result, index


def _read_sequence(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if _indent_of(line) != indent or not line[indent:].startswith("- "):
            break
        rest = line[indent + 2 :]
        if rest.find(": ") == -1 and not rest.endswith(":"):
            result.append(_scalar(rest))
            index += 1
            continue
        # A mapping item: rewrite the "- " lead-in as indentation so the mapping
        # reader sees a plain block, then continue from there.
        lines[index] = " " * (indent + 2) + rest
        item, index = _read_mapping(lines, index, indent + 2)
        result.append(item)
    return result, index


def parse_canonical(text: str) -> dict[str, Any] | None:
    """Return the mapping in ``text``, or ``None`` if it is not the known subset."""

    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return None
    try:
        value, index = _read_block(lines, 0, 0)
    except (_Unsupported, IndexError):
        return None
    if index != len(lines) or not isinstance(value, dict):
        return None
    return value


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


def _write_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise _Unsupported
    if value == "":
        return "''"
    if _UNPRINTABLE.search(value) or "\n" in value or "\t" in value:
        raise _Unsupported
    # Would the plain form read back as something other than this string?
    resolves_elsewhere = any(
        pattern.match(value) for _, pattern in _WRITER_IMPLICIT.get(value[0], ())
    )
    # Characters that may stop the emitter writing the scalar plain. The test is
    # deliberately wider than the emitter's, so a value it would have written
    # plain can land here — and is then declined rather than quoted differently.
    reserved_shape = (
        value[0] in _LEADING_INDICATOR
        or value.startswith(" ")
        or value.endswith((" ", ":"))
        or ": " in value
        or " #" in value
    )
    if not resolves_elsewhere and not reserved_shape:
        return value
    # Quoting is reproduced only where the reason is unambiguous: the plain form
    # would read back as a bool, a null, a number or a date. Where the reason is
    # instead the scalar's shape, the emitter's own rules decide.
    if resolves_elsewhere and not reserved_shape:
        return "'" + value.replace("'", "''") + "'"
    raise _Unsupported


def _line(pad: str, text: str) -> str:
    if len(pad) + len(text) > _MAX_LINE:
        raise _Unsupported
    return f"{pad}{text}\n"


def _write(value: Any, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not _PLAIN_KEY.match(key):
                raise _Unsupported
            if isinstance(item, (Mapping, list)):
                if not item:
                    empty = "{}" if isinstance(item, Mapping) else "[]"
                    out.append(_line(pad, f"{key}: {empty}"))
                    continue
                out.append(_line(pad, f"{key}:"))
                _write(item, indent if isinstance(item, list) else indent + 2, out)
            else:
                out.append(_line(pad, f"{key}: {_write_scalar(item)}"))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                if not item:
                    out.append(_line(pad, "- {}"))
                    continue
                nested: list[str] = []
                _write(item, indent + 2, nested)
                out.append(f"{pad}- {nested[0][indent + 2 :]}")
                out.extend(nested[1:])
            elif isinstance(item, list):
                # Nested sequences never occur in the node contract.
                raise _Unsupported
            else:
                out.append(_line(pad, f"- {_write_scalar(item)}"))
        return
    raise _Unsupported


def dump_canonical(value: Mapping[str, Any]) -> str | None:
    """Serialize ``value``, or return ``None`` to defer to the YAML emitter."""

    out: list[str] = []
    try:
        _write(value, 0, out)
    except _Unsupported:
        return None
    return "".join(out)
