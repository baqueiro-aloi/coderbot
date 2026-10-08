"""Stable, retryable finalization steps; completed work is never regenerated."""
from execution_identity import digest


def step(store, task_id, identity, name, action, reconcile=None, *, validate=None):
    key = digest([identity, name])
    rows = store.list("delivery_step", task_id, identity=key, status="complete")
    for row in rows:
        result = row["data"]["result"]
        if validate is None or validate(result):
            return result
        store.update("delivery_step", row, status="retryable", reason="cached result invalid")
    pending = store.list("delivery_step", task_id, identity=key, status="running")
    if pending and reconcile:
        result = reconcile()
        if result is not None and (validate is None or validate(result)):
            store.put("delivery_step", task_id=task_id, identity=key, id=pending[0]["id"],
                      status="complete", data={"step": name, "result": result})
            return result
    id = store.put("delivery_step", task_id=task_id, identity=key,
                   data={"step": name})
    try:
        result = action()
    except Exception as exc:
        row = store.get("delivery_step", id)
        store.update("delivery_step", row, status="retryable", error=str(exc))
        raise
    status = "complete" if validate is None or validate(result) else "retryable"
    if isinstance(result, dict) and result.get("status") in ("blocked", "not_applicable"):
        status = result["status"]
    store.put("delivery_step", task_id=task_id, identity=key, id=id, status=status,
              data={"step": name, "result": result})
    return result
