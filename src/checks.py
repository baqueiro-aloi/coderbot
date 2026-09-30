"""Deterministic checks with content-bound results and per-run reports."""
from pathlib import Path
import os
import subprocess
import time
import uuid

import operations
from check_results import parse_output
from execution_identity import digest, environment_identity, snapshot


def execute(check, repo, store, task_id, *, reuse=True):
    repo = Path(repo).resolve()
    cwd = (repo / check.cwd).resolve()
    content = snapshot(repo, check.inputs)
    environment = environment_identity(check.argv, cwd, env_keys=check.env_keys,
        key_path=store.path.parent / "identity.key")
    identity = digest({"content": content, "environment": environment, "check": check.to_dict(), "version": 1})
    previous = store.reusable_check(task_id, identity) if reuse else None
    if previous:
        return {**previous["data"]["result"], "reused": True}
    run_id = uuid.uuid4().hex
    report_dir = store.path.parent / "outbox/checks" / run_id
    report_dir.mkdir(parents=True)
    started = time.time()
    store.put("check_run", task_id=task_id, id=run_id, identity=identity, data={"check": check.id})
    try:
        process = operations.run(check.argv, cwd=cwd, timeout=check.timeout,
                                 exclusive=check.resources)
        output = process.stdout + "\n" + process.stderr
        result = parse_output(output, process.returncode, check.reporter)
    except (subprocess.TimeoutExpired, TimeoutError, OSError) as error:
        output = f"{type(error).__name__}: {error}"
        result = {"status": "infrastructure", "failures": {}, "exit_code": None}
    except BaseException:
        store.put("check_run", task_id=task_id, id=run_id, identity=identity,
                  status="interrupted", data={"check": check.id})
        raise
    report = report_dir / "output.log"
    report.write_text(output)
    result.update(check=check.id, identity=identity, content=content, environment=environment,
                  report=str(report), started=started, finished=time.time(), reused=False)
    store.put("check_run", task_id=task_id, id=run_id, identity=identity, status="complete",
              data={"check": check.to_dict(), "result": result})
    return result
