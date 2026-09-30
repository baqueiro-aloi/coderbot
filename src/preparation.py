"""Dependency preparation is reusable only with matching inputs and live probes."""
from execution_identity import digest, snapshot
import operations


def ensure(spec, repo, store, task_id):
    identity = digest({"spec": spec, "inputs": snapshot(repo, spec.get("inputs", ["*"]))})
    saved = store.list("operation", task_id, identity=identity, status="prepared")
    probes = spec.get("probes", [])
    if saved and probes and all(operations.run(p, cwd=repo, timeout=30).returncode == 0 for p in probes):
        return {"identity": identity, "reused": True}
    for command in spec.get("commands", []):
        result = operations.run(command, cwd=repo, timeout=spec.get("timeout", 900),
                                exclusive=["prepare:" + str(repo)])
        if result.returncode:
            raise RuntimeError("Dependency preparation failed")
    if not probes or not all(operations.run(p, cwd=repo, timeout=30).returncode == 0 for p in probes):
        raise RuntimeError("Prepared dependencies failed availability probes")
    store.put("operation", task_id=task_id, status="prepared", identity=identity, data={"preparation": spec})
    return {"identity": identity, "reused": False}
