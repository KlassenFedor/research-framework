"""Run every benchmark operation against one vault and emit a JSON record."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BENCH = Path(__file__).parent
PYTHON = sys.executable
RF = str(Path(sys.executable).parent / "rf")

COLD_OPS = [
    "discover",
    "load_snapshot",
    "validate_project",
    "validate_and_load",
    "open",
]
WARM_OPS = [
    "validate_and_load",
    "open",
    "get_node",
    "list_nodes",
    "traverse",
    "export_json",
    "format_check",
    "render_html",
    "update_node",
    "create_node",
]
CLI_OPS = [
    ("cli_node_show", ["node", "show", "hyp-1", "--json"]),
    ("cli_node_list", ["node", "list", "--json"]),
    ("cli_validate", ["validate", "--json"]),
    ("cli_format_check", ["format", "--check", "--json"]),
]

TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 3600


def run_op(vault: Path, op: str, cold: bool) -> dict[str, object]:
    command = [PYTHON, str(BENCH / "operations.py"), str(vault), op]
    if cold:
        command.append("--cold")
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
    except subprocess.TimeoutExpired:
        return {"op": op, "cold": cold, "status": "timeout", "seconds": None}
    if completed.returncode != 0:
        return {
            "op": op,
            "cold": cold,
            "status": "error",
            "stderr": completed.stdout[-400:] + completed.stderr[-800:],
        }
    record = json.loads(completed.stdout.strip().splitlines()[-1])
    record["cold"] = cold
    record["status"] = "ok"
    record["process_seconds"] = time.perf_counter() - started
    return record


def run_cli(vault: Path, name: str, arguments: list[str]) -> dict[str, object]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [RF, *arguments],
            cwd=vault,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"op": name, "status": "timeout", "seconds": None}
    elapsed = time.perf_counter() - started
    return {
        "op": name,
        "status": "ok" if completed.returncode == 0 else "error",
        "seconds": elapsed,
        "cold": False,
    }


def main() -> None:
    vault = Path(sys.argv[1]).resolve()
    results: list[dict[str, object]] = []
    for op in COLD_OPS:
        record = run_op(vault, op, cold=True)
        results.append(record)
        print(json.dumps(record), flush=True)
    for op in WARM_OPS:
        record = run_op(vault, op, cold=False)
        results.append(record)
        print(json.dumps(record), flush=True)
    for name, arguments in CLI_OPS:
        record = run_cli(vault, name, arguments)
        results.append(record)
        print(json.dumps(record), flush=True)
    output = BENCH / "results" / f"{vault.name}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
