from __future__ import annotations

from enum import Enum


class ActorKind(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


class NodeKind(str, Enum):
    QUESTION = "question"
    HYPOTHESIS = "hypothesis"
    CLAIM = "claim"
    EXPERIMENT = "experiment"
    RUN = "run"
    EVIDENCE = "evidence"
    ASSESSMENT = "assessment"
    SOURCE = "source"
    ARTIFACT = "artifact"
    DECISION = "decision"


class NodeStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class EdgeKind(str, Enum):
    ADDRESSES = "addresses"
    DECOMPOSES = "decomposes"
    DEPENDS_ON = "depends_on"
    TESTS = "tests"
    INSTANCE_OF = "instance_of"
    PRODUCES = "produces"
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    CONTRADICTS = "contradicts"
    ASSESSES = "assesses"
    BASED_ON = "based_on"
    SUPERSEDES = "supersedes"
    RELATED_TO = "related_to"


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
