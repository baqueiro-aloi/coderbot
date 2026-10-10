"""Reproducible synthetic incident latency plus real dedup/recovery checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from check_plan import Check
from checks import execute
from execution_store import ExecutionStore
from check_baseline import compare
from delivery_checkpoint import step


def benchmark():
    fixture = json.loads((Path(__file__).resolve().parent.parent / "tests/fixtures/runtime/permission-stall.json").read_text())
    permission = next(e for e in fixture["events"] if e["type"] == "permission.asked")
    timeout = next(e for e in fixture["events"] if e["type"] == "fixture.timeout")
    legacy_wait = timeout["at"] - permission["at"]
    with tempfile.TemporaryDirectory() as root:
        repo = Path(root) / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        store = ExecutionStore(Path(root) / "data/db")
        check = Check("final", [sys.executable, "-c", "print('pass')"])
        first = execute(check, repo, store, "t")
        recovered = execute(check, repo, store, "t")
        calls = []
        step(store, "t", "s", "RECORD", lambda: calls.append("record"))
        step(store, "t", "s", "RECORD", lambda: calls.append("record"))
        old = {"status": "fail", "failures": {"test": "same failure"}}
        gate = compare(old, old)
        assert recovered["reused"] and len(calls) == 1 and gate["status"] == "pass"
        return {"scenario": "synthetic permission-stall replay", "legacy_permission_wait_seconds": legacy_wait,
                "new_permission_response_budget_seconds": 10, "modeled_idle_reduction_percent": round(100 * (1 - 10 / legacy_wait), 2),
                "full_check_executions": 1, "recovery_reused_check": True, "record_executions": len(calls),
                "baseline_failure_gate": gate["status"], "live_Azure_speedup_measured": False}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
