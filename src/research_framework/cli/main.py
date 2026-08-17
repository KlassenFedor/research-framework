from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from research_framework import (
    Actor,
    AmbiguousReference,
    ArtifactDraft,
    AssessmentDraft,
    ClaimDraft,
    DecisionDraft,
    EvidenceDraft,
    ExperimentDraft,
    HypothesisDraft,
    NodeNotFound,
    Project,
    ProjectNotFound,
    QuestionDraft,
    RelationDraft,
    ResearchFrameworkError,
    RevisionConflict,
    RunDraft,
    SourceDraft,
    UnsupportedFormatVersion,
    ValidationFailed,
)
from research_framework.domain.enums import DiagnosticSeverity, EdgeKind
from research_framework.validation import validate_project


class CliUsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _json(value: Any) -> None:
    sys.stdout.write(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    )


def _success(data: Any, warnings: Sequence[Any] = ()) -> None:
    _json(
        {
            "ok": True,
            "data": data,
            "warnings": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in warnings
            ],
        }
    )


def _mutation_success(
    project: Project,
    data: Any,
    *,
    json_mode: bool,
    message: str,
) -> None:
    warnings = tuple(
        diagnostic
        for diagnostic in project.last_diagnostics()
        if diagnostic.severity is DiagnosticSeverity.WARNING
    )
    if json_mode:
        _success(data, warnings)
        return
    print(message)
    for warning in warnings:
        print(f"warning: {warning.code}: {warning.message}", file=sys.stderr)


def _error(code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
    _json(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": dict(details or {}),
            },
        }
    )


def _actor(value: Mapping[str, Any]) -> Actor:
    kind = value.get("kind")
    if kind == "human":
        return Actor.human(str(value.get("id", "")))
    if kind == "agent":
        return Actor.agent(
            str(value.get("id", "")),
            run_id=value.get("run_id"),
            model=value.get("model"),
        )
    raise CliUsageError("actor.kind must be human or agent")


def _human_actor(actor_id: str | None) -> Actor:
    if actor_id is None:
        raise CliUsageError("--actor is required")
    return Actor.human(actor_id)


def _read_request(source: str | None) -> dict[str, Any]:
    if source is None:
        raise CliUsageError("--from-json is required in JSON mode")
    try:
        text = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as error:
        raise CliUsageError(f"invalid JSON input: {error}") from error
    if not isinstance(value, dict):
        raise CliUsageError("JSON input must be an object")
    return value


_DRAFTS = {
    "question": QuestionDraft,
    "hypothesis": HypothesisDraft,
    "claim": ClaimDraft,
    "experiment": ExperimentDraft,
    "run": RunDraft,
    "evidence": EvidenceDraft,
    "assessment": AssessmentDraft,
    "source": SourceDraft,
    "artifact": ArtifactDraft,
    "decision": DecisionDraft,
}


def _draft(kind: str, data: Mapping[str, Any]) -> Any:
    constructor = _DRAFTS[kind]
    allowed = {field.name for field in dataclasses.fields(constructor)}
    values = {key: value for key, value in data.items() if key in allowed}
    try:
        return constructor(**values)
    except (TypeError, ValueError) as error:
        raise CliUsageError(str(error)) from error


def _initial_relations(value: Any) -> tuple[RelationDraft, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CliUsageError("initial_relations must be a list")
    result: list[RelationDraft] = []
    allowed = {"kind", "target", "rationale"}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise CliUsageError(f"initial_relations[{index}] must be an object")
        unknown = set(item) - allowed
        if unknown:
            field = min(unknown)
            raise CliUsageError(f"unknown initial_relations[{index}] field: {field}")
        try:
            result.append(
                RelationDraft(
                    kind=EdgeKind(item.get("kind")),
                    target=item.get("target"),
                    rationale=item.get("rationale"),
                )
            )
        except (TypeError, ValueError) as error:
            raise CliUsageError(
                f"invalid initial_relations[{index}]: {error}"
            ) from error
    return tuple(result)


def _flag_relations(args: argparse.Namespace) -> tuple[RelationDraft, ...]:
    relations: list[RelationDraft] = []
    if args.instance_of is not None:
        relations.append(RelationDraft(EdgeKind.INSTANCE_OF, args.instance_of))
    for target in args.derived_from or ():
        relations.append(RelationDraft(EdgeKind.DERIVED_FROM, target))
    for target in args.assesses or ():
        relations.append(RelationDraft(EdgeKind.ASSESSES, target))
    for target in args.based_on or ():
        relations.append(RelationDraft(EdgeKind.BASED_ON, target))
    return tuple(relations)


def _node_to_dict(node: Any, *, detail: bool = True) -> dict[str, Any]:
    return node.to_dict(include_body=detail, include_revision=detail)


def _build_parser() -> Parser:
    parser = Parser(prog="rf", description="Text-first research graph")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--title", required=True)
    init.add_argument("--default-language", default="en")
    init.add_argument("--json", action="store_true")

    node = commands.add_parser("node")
    node_commands = node.add_subparsers(dest="node_command", required=True)
    create = node_commands.add_parser("create")
    create.add_argument("kind", choices=sorted(_DRAFTS))
    create.add_argument("--from-json")
    create.add_argument("--title")
    create.add_argument("--summary")
    create.add_argument("--question")
    create.add_argument("--scope")
    create.add_argument("--statement")
    create.add_argument("--falsification-criteria")
    create.add_argument("--objective")
    create.add_argument("--method")
    create.add_argument("--success-criteria")
    create.add_argument("--protocol-version", type=int)
    create.add_argument("--started-at")
    create.add_argument("--finished-at")
    create.add_argument("--outcome")
    create.add_argument("--observation")
    create.add_argument("--evidence-kind")
    create.add_argument("--verdict")
    create.add_argument("--confidence")
    create.add_argument("--review-state")
    create.add_argument("--source-kind")
    create.add_argument("--locator")
    create.add_argument("--rationale")
    create.add_argument("--instance-of")
    create.add_argument("--derived-from", action="append")
    create.add_argument("--assesses", action="append")
    create.add_argument("--based-on", action="append")
    create.add_argument("--tag", action="append", dest="tags")
    create.add_argument("--alias", action="append", dest="aliases")
    create.add_argument("--actor")
    create.add_argument("--json", action="store_true")

    show = node_commands.add_parser("show")
    show.add_argument("reference")
    show.add_argument("--json", action="store_true")

    listing = node_commands.add_parser("list")
    listing.add_argument("--kind")
    listing.add_argument("--status")
    listing.add_argument("--tag", action="append", dest="tags")
    listing.add_argument("--json", action="store_true")

    update = node_commands.add_parser("update")
    update.add_argument("reference")
    update.add_argument("--from-json")
    update.add_argument("--json", action="store_true")

    archive = node_commands.add_parser("archive")
    archive.add_argument("reference")
    archive.add_argument("--expected-revision", required=True)
    archive.add_argument("--actor", required=True)
    archive.add_argument("--json", action="store_true")

    link = commands.add_parser("link")
    link_commands = link.add_subparsers(dest="link_command", required=True)
    add = link_commands.add_parser("add")
    add.add_argument("source", nargs="?")
    add.add_argument("kind", nargs="?")
    add.add_argument("target", nargs="?")
    add.add_argument("--rationale")
    add.add_argument("--actor")
    add.add_argument("--from-json")
    add.add_argument("--json", action="store_true")

    link_list = link_commands.add_parser("list")
    link_list.add_argument("reference")
    link_list.add_argument(
        "--direction", choices=("incoming", "outgoing", "both"), default="both"
    )
    link_list.add_argument("--json", action="store_true")

    remove = link_commands.add_parser("remove")
    remove.add_argument("edge_id")
    remove.add_argument("--actor", required=True)
    remove.add_argument("--json", action="store_true")

    graph = commands.add_parser("graph")
    graph_commands = graph.add_subparsers(dest="graph_command", required=True)
    graph_show = graph_commands.add_parser("show")
    graph_show.add_argument("reference")
    graph_show.add_argument("--json", action="store_true")

    traverse = graph_commands.add_parser("traverse")
    traverse.add_argument("reference")
    traverse.add_argument(
        "--direction", choices=("incoming", "outgoing", "both"), default="both"
    )
    traverse.add_argument("--depth", type=int, default=1)
    traverse.add_argument("--json", action="store_true")

    path = graph_commands.add_parser("path")
    path.add_argument("source")
    path.add_argument("target")
    path.add_argument("--json", action="store_true")

    export = graph_commands.add_parser("export")
    export.add_argument("--format", choices=("json",), default="json")

    validate = commands.add_parser("validate")
    validate.add_argument("--json", action="store_true")

    formatting = commands.add_parser("format")
    formatting.add_argument("--check", action="store_true")
    formatting.add_argument("--json", action="store_true")

    return parser


def _handle(args: argparse.Namespace) -> int | None:
    cwd = Path.cwd()
    if args.command == "init":
        project = Project.init(
            Path(args.path),
            title=args.title,
            default_language=args.default_language,
        )
        data = {"root": str(project.root)}
        _success(data) if args.json else print(f"Initialized {project.root}")
        return

    if args.command == "validate":
        diagnostics = validate_project(cwd)
        errors = [
            item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR
        ]
        warnings = [
            item for item in diagnostics if item.severity is DiagnosticSeverity.WARNING
        ]
        if errors:
            details = {"diagnostics": [item.to_dict() for item in diagnostics]}
            if args.json:
                _error("validation_failed", "Project validation failed", details)
            else:
                for item in diagnostics:
                    print(f"{item.severity.value}: {item.code}: {item.message}")
            raise SystemExit(3)
        data = {
            "diagnostics": [
                item.to_dict() for item in diagnostics if item not in warnings
            ]
        }
        if args.json:
            _success(data, warnings)
        else:
            print("Project is valid")
        return

    if args.command == "format":
        project = Project.open(cwd)
        result = project.format(check=args.check)
        changed = [str(path.relative_to(project.root)) for path in result.changed_paths]
        if args.check and changed:
            message = f"{len(changed)} file(s) require formatting"
            if args.json:
                _error("formatting_required", message, {"paths": changed})
            else:
                print(message, file=sys.stderr)
                for path in changed:
                    print(path, file=sys.stderr)
            return 1
        data = {
            "formatted": result.applied and bool(changed),
            "check": args.check,
            "checked_files": result.checked_files,
            "changed_files": changed,
        }
        message = (
            f"Formatted {len(changed)} file(s)" if changed else "Formatting is valid"
        )
        _mutation_success(
            project,
            data,
            json_mode=args.json,
            message=message,
        )
        return

    project = Project.open(cwd)
    graph = project.snapshot()

    if args.command == "node":
        if args.node_command == "show":
            node = graph.get_node(args.reference)
            data = _node_to_dict(node)
            _success(data) if args.json else print(f"{node.id} {node.title}")
        elif args.node_command == "list":
            nodes = graph.list_nodes(
                kind=args.kind,
                status=args.status,
                tags=set(args.tags or ()),
            )
            data = [_node_to_dict(node, detail=False) for node in nodes]
            _success(data) if args.json else [
                print(f"{node.id} {node.title}") for node in nodes
            ]
        elif args.node_command == "create":
            if args.from_json is not None:
                request = _read_request(args.from_json)
                actor = _actor(request.pop("actor", {}))
                relations = _initial_relations(request.pop("initial_relations", []))
                values = request
            else:
                if args.json and args.title is None:
                    raise CliUsageError("node input is required in JSON mode")
                actor = _human_actor(args.actor)
                relations = _flag_relations(args)
                values = {
                    key: value
                    for key, value in vars(args).items()
                    if key
                    in {
                        "title",
                        "summary",
                        "question",
                        "scope",
                        "statement",
                        "falsification_criteria",
                        "objective",
                        "method",
                        "success_criteria",
                        "protocol_version",
                        "started_at",
                        "finished_at",
                        "outcome",
                        "observation",
                        "evidence_kind",
                        "verdict",
                        "confidence",
                        "review_state",
                        "source_kind",
                        "locator",
                        "rationale",
                        "tags",
                        "aliases",
                    }
                    and value is not None
                }
            created = project.create_node(
                _draft(args.kind, values),
                actor=actor,
                initial_relations=relations,
            )
            data = _node_to_dict(created)
            _mutation_success(
                project,
                data,
                json_mode=args.json,
                message=f"Created {created.id}",
            )
        elif args.node_command == "update":
            request = _read_request(args.from_json)
            updated = project.update_node(
                args.reference,
                patch=request.get("patch", {}),
                expected_revision=request.get("expected_revision", ""),
                actor=_actor(request.get("actor", {})),
            )
            data = _node_to_dict(updated)
            _mutation_success(
                project,
                data,
                json_mode=args.json,
                message=f"Updated {updated.id}",
            )
        elif args.node_command == "archive":
            archived = project.archive_node(
                args.reference,
                expected_revision=args.expected_revision,
                actor=_human_actor(args.actor),
            )
            data = _node_to_dict(archived)
            _mutation_success(
                project,
                data,
                json_mode=args.json,
                message=f"Archived {archived.id}",
            )
        return

    if args.command == "link":
        if args.link_command == "add":
            if args.from_json is not None:
                request = _read_request(args.from_json)
                source = request.get("source")
                kind = request.get("kind")
                target = request.get("target")
                rationale = request.get("rationale")
                actor = _actor(request.get("actor", {}))
            else:
                source, kind, target = args.source, args.kind, args.target
                rationale = args.rationale
                actor = _human_actor(args.actor)
            if not all(
                isinstance(item, str) and item for item in (source, kind, target)
            ):
                raise CliUsageError("source, kind, and target are required")
            edge = project.add_edge(
                source=source,
                kind=kind,
                target=target,
                rationale=rationale,
                actor=actor,
            )
            data = edge.to_dict()
            _mutation_success(
                project,
                data,
                json_mode=args.json,
                message=f"Created {edge.id}",
            )
        elif args.link_command == "list":
            edges = []
            if args.direction in {"outgoing", "both"}:
                edges.extend(graph.outgoing(args.reference))
            if args.direction in {"incoming", "both"}:
                edges.extend(graph.incoming(args.reference))
            unique = {edge.id: edge for edge in edges}
            data = [unique[edge_id].to_dict() for edge_id in sorted(unique)]
            _success(data) if args.json else [
                print(f"{item['id']} {item['kind']}") for item in data
            ]
        elif args.link_command == "remove":
            project.remove_edge(args.edge_id, actor=_human_actor(args.actor))
            data = {"id": args.edge_id, "removed": True}
            _mutation_success(
                project,
                data,
                json_mode=args.json,
                message=f"Removed {args.edge_id}",
            )
        return

    if args.command == "graph":
        if args.graph_command == "show":
            center = graph.get_node(args.reference)
            edges = {
                edge.id: edge
                for edge in (*graph.outgoing(center.id), *graph.incoming(center.id))
            }
            data = {
                "center": _node_to_dict(center, detail=False),
                "edges": [edges[edge_id].to_dict() for edge_id in sorted(edges)],
            }
            _success(data) if args.json else print(f"{center.id}: {len(edges)} edges")
        elif args.graph_command == "traverse":
            nodes = graph.traverse(
                args.reference,
                depth=args.depth,
                direction=args.direction,
            )
            data = {"nodes": [_node_to_dict(node, detail=False) for node in nodes]}
            _success(data) if args.json else [
                print(f"{node.id} {node.title}") for node in nodes
            ]
        elif args.graph_command == "path":
            path = graph.find_path(args.source, args.target)
            data = {"edges": [edge.to_dict() for edge in (path or ())]}
            _success(data) if args.json else print(
                " -> ".join(edge.id for edge in (path or ()))
            )
        elif args.graph_command == "export":
            sys.stdout.write(graph.export_json())
        return


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in arguments
    try:
        args = _build_parser().parse_args(arguments)
        exit_code = _handle(args)
        return 0 if exit_code is None else exit_code
    except CliUsageError as error:
        if json_mode:
            _error("invalid_arguments", str(error))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except RevisionConflict as error:
        if json_mode:
            _error(error.code, str(error), error.details)
        else:
            print(str(error), file=sys.stderr)
        return 5
    except UnsupportedFormatVersion as error:
        if json_mode:
            _error(error.code, str(error), error.details)
        else:
            print(str(error), file=sys.stderr)
        return 6
    except ValidationFailed as error:
        if json_mode:
            _error(error.code, str(error), error.details)
        else:
            print(str(error), file=sys.stderr)
        return 3
    except (NodeNotFound, AmbiguousReference, ProjectNotFound) as error:
        if json_mode:
            _error(error.code, str(error), error.details)
        else:
            print(str(error), file=sys.stderr)
        return 4
    except (ValueError, TypeError) as error:
        if json_mode:
            _error("invalid_arguments", str(error))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except ResearchFrameworkError as error:
        if json_mode:
            _error(error.code, str(error), error.details)
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
