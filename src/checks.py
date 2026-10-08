"""Deterministic checks with content-bound results and per-run reports."""
from pathlib import Path
import os
import subprocess
import time
import uuid
import logging
import secret_safety
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import operations
import preparation
from check_results import parse_output
from execution_identity import digest, environment_identity, snapshot
log = logging.getLogger(__name__)


def environment_revision(store, repo, check_id):
    rows = store.list("check_environment", "environment:" + str(Path(repo).resolve()), identity=check_id)
    return rows[0]["data"]["revision"] if rows else 0


def invalidate_environment(store, repo, check_ids):
    """A runtime repair invalidates only affected results, including baseline cache."""
    task_id = "environment:" + str(Path(repo).resolve())
    for check_id in set(check_ids):
        rows = store.list("check_environment", task_id, identity=check_id)
        store.put("check_environment", task_id=task_id, identity=check_id,
                  id=rows[0]["id"] if rows else None,
                  data={"revision": environment_revision(store, repo, check_id) + 1})


def execute_plan(plan, repo, store, task_id, *, workers=3):
    # Each process takes sorted exclusive resources before launch. Preserve result
    # order for deterministic reporting, independently of completion order.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(copy_context().run, execute, check, repo, store, task_id) for check in plan]
        return [future.result() for future in futures]


def execute(check, repo, store, task_id, *, reuse=True, secret_handles=()):
    if not secret_handles:
        import secret_intake
        secret_handles = secret_intake.bindings(task_id, check)
    if secret_handles:
        from private_secrets import PrivateSecrets
        private = PrivateSecrets(store.path.parent / 'private-secrets')
        with private.environment(secret_handles, task_id=task_id, check=check) as env:
            return _execute(check, repo, store, task_id, reuse=reuse, environ=env)
    return _execute(check, repo, store, task_id, reuse=reuse)


def _execute(check, repo, store, task_id, *, reuse=True, environ=None):
    repo = Path(repo).resolve()
    preparation_error = None
    if check.preparation:
        try:
            preparation.ensure(check.preparation, repo, store, task_id)
        except (RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as error:
            preparation_error = error
    cwd = (repo / check.cwd).resolve()
    import effective_environment
    installed = effective_environment.installed(check.argv, cwd)
    content = snapshot(repo, check.inputs)
    environment = environment_identity(check.argv, cwd, env_keys=check.env_keys,
        environ=environ,
        tools={**tool_versions(check.argv, cwd), 'installed': installed,
               "repair_revision": environment_revision(store, repo, check.id)},
        key_path=store.path.parent / "identity.key",
        config_files=sorted(set([repo / '.env', cwd / '.env',
            *repo.glob('.env.*'), *cwd.glob('.env.*')])))
    from check_baseline import dependency_snapshot, dependency_inputs
    dependencies = dependency_snapshot(repo, dependency_inputs(check, repo))
    identity = digest({"content": content, "environment": environment, "check": check.to_dict(),
                        "dependencies": dependencies, "version": 3})
    previous = store.reusable_check(task_id, identity) if reuse and not preparation_error and installed['verified'] else None
    previous_result = previous['data']['result'] if previous else {}
    age = time.time() - previous_result.get('finished', 0)
    fresh = (check.max_age_seconds is None or 0 <= age <= check.max_age_seconds)
    if check.kind in ('upstream', 'postdeployment') and check.max_age_seconds is None:
        fresh = False
    if previous and fresh and previous_result.get('status') in ('pass', 'fail'):
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
        if preparation_error:
            raise OSError("Check preparation failed: " + str(preparation_error))
        process = operations.run(check.argv, cwd=cwd, timeout=check.timeout,
                                  exclusive=check.resources, **({'env': environ} if environ is not None else {}))
        output = secret_safety.redact(process.stdout + "\n" + process.stderr)
        result = parse_output(output, process.returncode, check.reporter)
    except (subprocess.TimeoutExpired, TimeoutError, OSError) as error:
        output = secret_safety.redact(f"{type(error).__name__}: {error}")
        result = {"status": "infrastructure", "failures": {}, "exit_code": None}
    except BaseException:
        store.put("check_run", task_id=task_id, id=run_id, identity=identity,
                  status="interrupted", data={"check": check.id})
        raise
    report = report_dir / "output.log"
    report.write_text(output)
    result.update(check=check.id, identity=identity, content=content, environment=environment,
                  report=str(report), started=started, finished=time.time(), reused=False,
                  repetition_reason=reason, run_id=run_id, kind=check.kind,
                  contract_version=check.contract_version, requirements=check.requirements,
                   scenarios=check.scenarios, external_dependencies=check.external_dependencies)
    result['provenance'] = 'verified_v2'
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
