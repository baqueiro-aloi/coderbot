"""One final verification policy for all suites and all lifecycle paths."""
from pathlib import Path

import check_plan
import checks
from check_baseline import baseline_result, compare
from execution_identity import snapshot


def run(state, repo, store):
    plan = [c for c in check_plan.discover(repo) if c.scope == "full"]
    # A reported full check supplements discovery; focused checks never replace it.
    known = {c.id for c in plan}
    for entry in state.get("reported_check_plan", []):
        check = check_plan.Check(**entry)
        if check.scope == "full" and check.id not in known:
            plan.append(check)
    task_id = store.task_identity(state, repo)
    results = checks.execute_plan(plan, repo, store, task_id)
    outcomes = []
    for check, result in zip(plan, results):
        if result["status"] == "pass":
            gate = {"status": "pass", "preexisting": [], "regressions": []}
        elif result["status"] == "fail" and state.get("base_sha"):
            baseline = baseline_result(check, repo, state["base_sha"], store)
            gate = compare(result, baseline, roots=(Path(repo).resolve(),))
        else:
            gate = {"status": "indeterminate", "preexisting": [], "regressions": []}
        outcomes.append({**result, "gate": gate})
    return {"snapshot": snapshot(repo), "status": "pass" if outcomes and all(r["gate"]["status"] == "pass" for r in outcomes)
            else "indeterminate" if not outcomes or any(r["gate"]["status"] == "indeterminate" for r in outcomes)
            else "fail", "checks": outcomes}
