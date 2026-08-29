"""Smoke test executed against built wheel and source distributions."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.resources import files

from specjam import __version__
from specjam.graph_engine import load_graph


assert __version__ == "0.0.1"

subprocess.run([sys.executable, "-m", "specjam", "--help"], check=True, stdout=subprocess.DEVNULL)

graph_root = files("specjam.payload").joinpath("workspace", "graphs")
expected = {
    "discovery-graph.json": ("discovery", "epic", "done"),
    "delivery-graph.json": ("delivery", "context", "done"),
    "postmortem-graph.json": ("postmortem", "triage", "done"),
}
for filename, (graph_id, start, terminal) in expected.items():
    resource = graph_root.joinpath(filename)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    graph = load_graph(resource)
    assert payload["graph"] == graph_id
    assert graph.start_stage == start
    assert graph.terminal_stages == frozenset({terminal})

print(f"specjam {__version__}: distribution smoke test passed")
