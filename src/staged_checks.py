"""Cheap checks, selected focused E2E, then bounded full regression execution."""
import check_plan
import checks


def run(state, plan, repo, store, *, evaluate=None):
    plan = check_plan.normalize(plan, repo)
    task = store.task_identity(state, repo)
    outcomes = []
    def execute(selected, *, focused=False, full=False):
        kwargs = {"audit_task": task} if full else {}
        result = checks.execute_plan(selected, repo, store, task, **kwargs) if selected else []
        if len(result) != len(selected):
            result = [{"check": c.id, "status": "unknown", "reason": "incomplete_check_results"} for c in selected]
        result = [{**r, "check": c.id, **({"gate": evaluate(c, r)} if evaluate else {})}
                  for c, r in zip(selected, result)]
        outcomes.extend(result)
        if focused:
            return all(not r.get("zero_tests") and r.get("status") == "pass" and
                       type(r.get("test_count")) is int and r["test_count"] > 0 for r in result)
        if evaluate:
            return all(r["gate"]["status"] == "pass" for r in result)
        return all(r.get("status") in ("pass", "skipped") for r in result)

    cheap = [c for c in plan if not check_plan.is_e2e(c, repo)]
    focused = [c for c in plan if check_plan.is_e2e(c, repo) and c.scope == "focused"]
    full = [c for c in plan if check_plan.is_e2e(c, repo) and c.scope == "full"]
    if not execute(cheap):
        return {"stage": "unit_functional", "checks": outcomes}
    invalid = [c for c in focused if not check_plan.has_e2e_selection(c)]
    if (full and not focused) or invalid:
        issues = [{"check": c.id, "argv": c.argv, "cwd": c.cwd,
                   "reason": "unfiltered_e2e_registered_as_focused"} for c in invalid]
        return {"stage": "needs_focused_e2e", "checks": outcomes,
                "selection_issues": issues or [{"reason": "missing_focused_e2e", "full_checks": [c.id for c in full]}]}
    if not execute(focused, focused=True):
        return {"stage": "focused_e2e", "checks": outcomes}
    if not full:
        return {"stage": "complete", "checks": outcomes}
    execute(full, full=True)
    if any(r.get("reason") == "full_e2e_budget_exhausted" or
           r.get("gate", {}).get("baseline", {}).get("reason") == "full_e2e_budget_exhausted" for r in outcomes):
        return {"stage": "full_e2e_budget_exhausted", "checks": outcomes}
    return {"stage": "complete", "checks": outcomes}
