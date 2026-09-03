"""Command-line interface for SpecJam."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calibration import calibrate_memory, load_calibration_cases
from .classification import classify_request
from .embeddings import DEFAULT_LOCAL_MODEL, FastEmbedProvider
from .graph_engine import load_graph, record_route
from .installer import inspect_installation, install, scaffold_flow, update, verify
from .memory import MemoryKind, MemoryQuery, MemoryRecord, SQLiteVectorMemory
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


def _embedding(value: str) -> tuple[float, ...]:
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise TypeError
        return tuple(float(item) for item in parsed)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("embedding must be a JSON array of numbers") from exc


def _add_local_options(parser: argparse.ArgumentParser, *, embedding: bool = False) -> None:
    parser.add_argument("--dimensions", type=int)
    if embedding:
        parser.add_argument("--embedding", type=_embedding)
    parser.add_argument("--model", default=DEFAULT_LOCAL_MODEL)
    parser.add_argument("--cache-dir")
    parser.add_argument("--backend", choices=("auto", "exact", "sqlite-vec"), default="auto")


def _provider(args, *, allow_download: bool = False) -> FastEmbedProvider:
    return FastEmbedProvider(
        args.model,
        cache_dir=args.cache_dir,
        local_files_only=not allow_download,
    )


def _vector(args, text: str) -> tuple[int, tuple[float, ...], FastEmbedProvider | None]:
    if getattr(args, "embedding", None) is not None:
        vector = tuple(args.embedding)
        dimensions = args.dimensions or len(vector)
        return dimensions, vector, None
    provider = _provider(args)
    if args.dimensions is not None and args.dimensions != provider.dimensions:
        raise ValueError(
            f"configured dimensions {args.dimensions} do not match model dimensions {provider.dimensions}"
        )
    return provider.dimensions, tuple(provider.embed(text)), provider


def _configured_store(args, dimensions: int, provider: FastEmbedProvider | None = None) -> SQLiteVectorMemory:
    store = SQLiteVectorMemory(args.db, dimensions, vector_backend=args.backend)
    if provider is not None:
        store.configure_embedding("fastembed", provider.model)
    else:
        metadata = store.metadata()
        # Bind new CLI-created projections to their embedding space. Legacy
        # unprofiled databases remain readable, but a profiled automatic store
        # cannot be silently written or queried with an unrelated manual vector.
        if store.count() == 0 or "embedding_provider" in metadata:
            store.configure_embedding("manual", f"float32-{dimensions}")
    return store


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

    memory = commands.add_parser("memory", help="manage the SQLite retrieval projection")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_prepare = memory_commands.add_parser("prepare", help="download and verify the local embedding model")
    memory_prepare.add_argument("--model", default=DEFAULT_LOCAL_MODEL)
    memory_prepare.add_argument("--cache-dir")
    memory_init = memory_commands.add_parser("init", help="initialize a typed vector store")
    memory_init.add_argument("--db", default=".specjam/memory/specjam.db")
    _add_local_options(memory_init)
    memory_add = memory_commands.add_parser("add", help="append one embedded memory")
    memory_add.add_argument("--db", default=".specjam/memory/specjam.db")
    _add_local_options(memory_add, embedding=True)
    memory_add.add_argument("--kind", required=True, choices=tuple(kind.value for kind in MemoryKind))
    memory_add.add_argument("--content", required=True)
    memory_add.add_argument("--source-ref", required=True)
    memory_add.add_argument("--id")
    memory_add.add_argument("--run-id")
    memory_add.add_argument("--increment-id")
    memory_add.add_argument("--graph-id")
    memory_add.add_argument("--stage")
    memory_add.add_argument("--role")
    memory_search = memory_commands.add_parser("search", help="run structured hybrid recall")
    memory_search.add_argument("--db", default=".specjam/memory/specjam.db")
    _add_local_options(memory_search, embedding=True)
    memory_search.add_argument("--text")
    memory_search.add_argument("--top-k", type=int, default=3)
    memory_search.add_argument("--min-score", type=float, default=0.0)
    memory_search.add_argument("--kind", action="append", choices=tuple(kind.value for kind in MemoryKind), default=[])
    memory_search.add_argument("--graph-id")
    memory_search.add_argument("--stage")
    memory_search.add_argument("--role")
    memory_search.add_argument("--run-id")
    memory_search.add_argument("--increment-id")
    memory_search.add_argument("--exclude-run-id")
    memory_calibrate = memory_commands.add_parser("calibrate", help="tune recall policy from labelled cases")
    memory_calibrate.add_argument("--db", default=".specjam/memory/specjam.db")
    _add_local_options(memory_calibrate)
    memory_calibrate.add_argument("--cases", required=True)
    memory_calibrate.add_argument("--top-k", action="append", type=int)
    memory_calibrate.add_argument("--min-score", action="append", type=float)
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
    if args.command == "memory" and args.memory_command == "prepare":
        provider = _provider(args, allow_download=True)
        provider.prepare()
        _emit({"provider": "fastembed", "model": provider.model, "dimensions": provider.dimensions, "ready": True})
        return 0
    if args.command == "memory" and args.memory_command == "init":
        if args.dimensions is not None:
            dimensions, provider = args.dimensions, None
        else:
            provider = _provider(args)
            dimensions = provider.dimensions
        store = _configured_store(args, dimensions, provider)
        metadata = store.metadata()
        _emit({
            "database": str(store.path), "dimensions": store.dimensions, "records": store.count(),
            "vector_backend": store.vector_backend,
            "embedding_provider": metadata.get("embedding_provider"),
            "embedding_model": metadata.get("embedding_model"),
        })
        return 0
    if args.command == "memory" and args.memory_command == "add":
        dimensions, embedding, provider = _vector(args, args.content)
        store = _configured_store(args, dimensions, provider)
        record = MemoryRecord.create(
            id=args.id, kind=args.kind, content=args.content, embedding=embedding,
            source_ref=args.source_ref, run_id=args.run_id, increment_id=args.increment_id,
            graph_id=args.graph_id, stage=args.stage, role=args.role,
        )
        inserted = store.add(record)
        _emit({"id": record.id, "inserted": inserted, "records": store.count()})
        return 0
    if args.command == "memory" and args.memory_command == "search":
        text = args.text or ""
        if not text and args.embedding is None:
            raise ValueError("search requires --text when --embedding is omitted")
        dimensions, embedding, provider = _vector(args, text)
        store = _configured_store(args, dimensions, provider)
        matches = store.search(MemoryQuery(
            embedding=embedding, text=args.text, top_k=args.top_k, min_score=args.min_score,
            kinds=tuple(MemoryKind(kind) for kind in args.kind), graph_id=args.graph_id,
            stage=args.stage, role=args.role, run_id=args.run_id, increment_id=args.increment_id,
            exclude_run_id=args.exclude_run_id,
        ))
        _emit({"matches": [{
            "id": match.record.id,
            "kind": match.record.kind.value,
            "content": match.record.content,
            "source_ref": match.record.source_ref,
            "score": round(match.score, 6),
            "vector_score": round(match.vector_score, 6),
            "lexical_rank": match.lexical_rank,
        } for match in matches]})
        return 0
    if args.command == "memory" and args.memory_command == "calibrate":
        if args.dimensions is not None:
            dimensions, provider = args.dimensions, None
        else:
            provider = _provider(args)
            dimensions = provider.dimensions
        store = _configured_store(args, dimensions, provider)
        options = {}
        if args.top_k:
            options["top_k_values"] = tuple(args.top_k)
        if args.min_score:
            options["min_score_values"] = tuple(args.min_score)
        report = calibrate_memory(store, load_calibration_cases(args.cases), **options)
        _emit(report.to_dict())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
