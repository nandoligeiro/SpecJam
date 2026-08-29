"""Command-line interface for SpecJam."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .classification import classify_request
from .graph_engine import load_graph, record_route
from .installer import inspect_installation, install, scaffold_flow, update, verify
from .model import RouteState
from .rws import load_rwsa, validate_rwsa


def _emit(value) -> None:
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _flags(values: list[str] | None) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for value in values or []:
        key, separator, raw = value.partition("=")
        result[key] = raw.lower() not in {"0", "false", "no", "off"} if separator else True
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specjam", description="Deterministic agentic engineering workspace")
    commands = parser.add_subparsers(dest="command", required=True)

    install_parser = commands.add_parser("install", help="install the managed workspace")
    install_parser.add_argument("--target", default=".")
    install_parser.add_argument("--force", action="store_true")

    verify_parser = commands.add_parser("verify", help="verify managed files and lockfile")
    verify_parser.add_argument("--target", default=".")

    update_parser = commands.add_parser("update", help="update unchanged managed files")
    update_parser.add_argument("--target", default=".")
    update_parser.add_argument("--remove-stale", action="store_true")

    inspect_parser = commands.add_parser("inspect", help="inspect installation metadata")
    inspect_parser.add_argument("--target", default=".")

    classify_parser = commands.add_parser("classify", help="classify work into L0-L3")
    classify_parser.add_argument("text", nargs="+")
    classify_parser.add_argument("--ambiguous", action="store_true")
    classify_parser.add_argument("--critical", action="store_true")

    graph = commands.add_parser("graph", help="validate a graph")
    graph_commands = graph.add_subparsers(dest="graph_command", required=True)
    graph_validate = graph_commands.add_parser("validate")
    graph_validate.add_argument("path")

    route = commands.add_parser("route", help="evaluate one graph gate")
    route.add_argument("--graph", required=True)
    route.add_argument("--stage", required=True)
    route.add_argument("--artifact", action="append", default=[])
    route.add_argument("--flag", action="append", default=[])
    route.add_argument("--trail")
    route.add_argument("--run-id", default="local")

    rws = commands.add_parser("rws", help="validate an RWSA contract")
    rws_commands = rws.add_subparsers(dest="rws_command", required=True)
    rws_validate = rws_commands.add_parser("validate")
    rws_validate.add_argument("path")

    flow = commands.add_parser("flow", help="scaffold durable flow artifacts")
    flow_commands = flow.add_subparsers(dest="flow_command", required=True)
    scaffold = flow_commands.add_parser("scaffold")
    scaffold.add_argument("--target", default=".")
    scaffold.add_argument("--flow", required=True, choices=("discovery", "delivery", "postmortem"))
    scaffold.add_argument("--slug", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install":
        _emit(install(args.target, force=args.force).to_dict())
        return 0
    if args.command == "verify":
        report = verify(args.target)
        _emit(report.to_dict())
        return 0 if not (report.missing or report.modified or report.stale) else 1
    if args.command == "update":
        _emit(update(args.target, remove_stale=args.remove_stale).to_dict())
        return 0
    if args.command == "inspect":
        _emit(inspect_installation(args.target))
        return 0
    if args.command == "classify":
        _emit(classify_request(" ".join(args.text), ambiguous=args.ambiguous, critical=args.critical).to_dict())
        return 0
    if args.command == "graph" and args.graph_command == "validate":
        graph = load_graph(args.path)
        _emit({"valid": True, "graph": graph.id, "nodes": sorted(graph.nodes)})
        return 0
    if args.command == "route":
        graph = load_graph(args.graph)
        state = RouteState(args.stage, frozenset(args.artifact), _flags(args.flag))
        if args.trail:
            decision = record_route(__import__("specjam.graph_engine", fromlist=["TrailStore"]).TrailStore(args.trail), args.run_id, graph, state)
        else:
            from .graph_engine import route
            decision = route(graph, state)
        _emit(decision.to_dict())
        return 0 if decision.may_advance or not decision.blocked else 2
    if args.command == "rws" and args.rws_command == "validate":
        profile = load_rwsa(args.path)
        _emit({"valid": True, "skill": profile.routing.name, "workflow_steps": len(profile.workflow)})
        return 0
    if args.command == "flow" and args.flow_command == "scaffold":
        path = scaffold_flow(args.target, args.flow, args.slug)
        _emit({"flow": args.flow, "path": str(path)})
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
