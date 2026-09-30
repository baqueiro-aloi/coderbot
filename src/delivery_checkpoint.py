"""Stable, retryable finalization steps; completed work is never regenerated."""
from execution_identity import digest


def step(store, task_id, identity, name, action):
    key = digest([identity, name])
    rows = store.list("delivery_step", task_id, identity=key, status="complete")
    if rows:
        return rows[0]["data"]["result"]
    id = store.put("delivery_step", task_id=task_id, identity=key,
                   data={"step": name})
    result = action()
    store.put("delivery_step", task_id=task_id, identity=key, id=id, status="complete",
              data={"step": name, "result": result})
    return result
