"""One final verification policy for all suites and all lifecycle paths."""
import logging
from pathlib import Path

import check_plan
import checks
import config
from check_baseline import baseline_result, compare
from execution_identity import snapshot

log = logging.getLogger(__name__)


def run(state, repo, store):
    plan = [c for c in check_plan.discover(repo) if c.scope == "full"]
    waived = any(w.get("scope") == "e2e:general" for w in state.get("check_waivers", []))
    if waived:
        plan = [c for c in plan if not c.id.startswith("e2e")]
    # A reported full check supplements discovery; focused checks never replace it.
    known = {c.id for c in plan}
    declared = set()
    for entry in state.get("reported_check_plan", []):
        check = check_plan.Check(**entry)
        if check.scope == "full" and check.id not in known:
            if waived and check.id.startswith("e2e"):
                continue
            plan.append(check)
            declared.add(check.id)
    task_id = store.task_identity(state, repo)
    results = checks.execute_plan(plan, repo, store, task_id)
    outcomes = []
    for check, result in zip(plan, results):
        if result.get("zero_tests"):
            if config.EMPTY_SUITE_FAILS and check.id in declared:
                result = {**result, "status": "not_run"}
            else:
                log.warning("final check %s passed but executed 0 tests", check.id)
        if result["status"] == "not_run":
            gate = {"status": "fail", "preexisting": [], "regressions": [],
                    "reason": "0 tests executed: fix test discovery/selection or drop the check from CHECK_PLAN"}
        elif result["status"] == "pass":
            gate = {"status": "pass", "preexisting": [], "regressions": []}
        elif result["status"] == "fail" and state.get("base_sha"):
            baseline = baseline_result(check, repo, state["base_sha"], store)
            gate = compare(result, baseline, roots=(Path(repo).resolve(),))
            gate["baseline"] = {"sha": state["base_sha"], "status": baseline["status"],
                                "report": baseline.get("report"), "detail": baseline.get("detail")}
            if baseline.get('reason'):
                gate['reason'] = baseline['reason']
        else:
            gate = {"status": "indeterminate", "preexisting": [], "regressions": []}
        outcomes.append({**result, "gate": gate})
    return {"snapshot": snapshot(repo), "status": "pass" if outcomes and all(r["gate"]["status"] == "pass" and r["status"] == "pass" for r in outcomes)
            else "indeterminate" if not outcomes or any(r["gate"]["status"] == "indeterminate" for r in outcomes)
            else "fail", "checks": outcomes}
