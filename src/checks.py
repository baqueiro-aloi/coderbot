"""Deterministic checks with content-bound results and per-run reports."""
from pathlib import Path
import os
import subprocess
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import operations
import preparation
from check_results import parse_output
from execution_identity import digest, environment_identity, snapshot
log = logging.getLogger(__name__)


def execute_plan(plan, repo, store, task_id, *, workers=3):
    # Each process takes sorted exclusive resources before launch. Preserve result
    # order for deterministic reporting, independently of completion order.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(copy_context().run, execute, check, repo, store, task_id) for check in plan]
        return [future.result() for future in futures]


def execute(check, repo, store, task_id, *, reuse=True):
    repo = Path(repo).resolve()
    if check.preparation:
        preparation.ensure(check.preparation, repo, store, task_id)
    cwd = (repo / check.cwd).resolve()
    content = snapshot(repo, check.inputs)
    environment = environment_identity(check.argv, cwd, env_keys=check.env_keys,
        tools=tool_versions(check.argv, cwd), key_path=store.path.parent / "identity.key")
    identity = digest({"content": content, "environment": environment, "check": check.to_dict(), "version": 1})
    previous = store.reusable_check(task_id, identity) if reuse else None
    if previous and previous["data"]["result"]["status"] not in ("infrastructure", "unknown"):
        log.info("check reused: %s status=%s report=%s", check.id,
                 previous["data"]["result"]["status"], previous["data"]["result"].get("report"))
        return {**previous["data"]["result"], "reused": True}
    candidates = store.list("check_run", task_id)
    previous_check = next((r for r in candidates if isinstance(r["data"].get("check"), dict)
                           and r["data"]["check"].get("id") == check.id), None)
    reason = "no_previous_result"
    if previous_check:
        old = previous_check["data"].get("result", {})
        reason = ("content_changed" if old.get("content") != content else
                  "environment_or_command_changed" if old.get("environment") != environment else
                  "incomplete_or_unusable_result")
    run_id = uuid.uuid4().hex
    report_dir = store.path.parent / "outbox/checks" / run_id
    report_dir.mkdir(parents=True)
    started = time.time()
    store.put("check_run", task_id=task_id, id=run_id, identity=identity, data={"check": check.id})
    log.info("check started: %s cwd=%s timeout=%ss reason=%s", check.id, cwd, check.timeout, reason)
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
                  report=str(report), started=started, finished=time.time(), reused=False,
                  repetition_reason=reason)
    store.put("check_run", task_id=task_id, id=run_id, identity=identity, status="complete",
              data={"check": check.to_dict(), "result": result})
    log.info("check finished: %s status=%s exit=%s duration=%.1fs report=%s", check.id,
             result["status"], result["exit_code"], result["finished"] - started, report)
    return result


def tool_versions(argv, cwd):
    """Version probes are part of identity; unknown means conservative no reuse."""
    executable = argv[0]
    versions = {"executable": executable}
    if Path(executable).name in ("node", "npm", "python", "python3", "pytest", "openspec"):
        result = operations.run([executable, "--version"], cwd=cwd, timeout=15, kind="probe")
        versions["version"] = (result.stdout + result.stderr).strip()[:300]
    elif (Path(cwd) / executable).is_file():
        import hashlib
        versions["executable_hash"] = hashlib.sha256((Path(cwd) / executable).read_bytes()).hexdigest()
    for name in ("node", "python3"):
        if name == executable:
            continue
        try:
            probe = operations.run([name, "--version"], cwd=cwd, timeout=15, kind="probe")
            versions[name] = (probe.stdout + probe.stderr).strip()[:100]
        except OSError:
            versions[name] = "unavailable"
    return versions
