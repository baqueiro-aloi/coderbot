"""Stable, retryable finalization steps; completed work is never regenerated."""
from execution_identity import digest


def step(store, task_id, identity, name, action, reconcile=None):
    key = digest([identity, name])
    rows = store.list("delivery_step", task_id, identity=key, status="complete")
    if rows:
        return rows[0]["data"]["result"]
    pending = store.list("delivery_step", task_id, identity=key, status="running")
    if pending and reconcile:
        result = reconcile()
        if result is not None:
            store.put("delivery_step", task_id=task_id, identity=key, id=pending[0]["id"],
                      status="complete", data={"step": name, "result": result})
            return result
    id = store.put("delivery_step", task_id=task_id, identity=key,
                   data={"step": name})
    result = action()
    store.put("delivery_step", task_id=task_id, identity=key, id=id, status="complete",
              data={"step": name, "result": result})
    return result
