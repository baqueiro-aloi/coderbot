"""Functional release receipts; heartbeat/systemd are only liveness."""
import subprocess
import time

def verify(*, image, expected_image, release_sha, expected_sha, state_before,
           state_after, probes, runner=subprocess.run):
    if image != expected_image or release_sha != expected_sha:
        raise ValueError('Release image/SHA does not match authorized target')
    preserved = all(state_before.get(key) == state_after.get(key) for key in
        ('execution_task_id', 'branch', 'session_id', 'validation_overrides'))
    if not preserved:
        raise ValueError('Release did not preserve durable task state')
    results = []
    for probe in probes:
        if (not isinstance(probe, dict) or probe.get('kind') not in ('readiness', 'smoke')
                or not isinstance(probe.get('argv'), list) or not probe['argv']
                or any(not isinstance(arg, str) or not arg for arg in probe['argv'])
                or type(probe.get('timeout')) not in (int, float) or not 0 < probe['timeout'] <= 120):
            raise ValueError('Release requires explicit bounded readiness/smoke probes')
        try:
            result = runner(probe['argv'], capture_output=True, text=True, timeout=probe['timeout'])
            outcome = 'pass' if result.returncode == 0 else 'fail'
        except (OSError, subprocess.TimeoutExpired):
            outcome = 'blocked'
        results.append({'id': probe.get('id'), 'kind': probe['kind'], 'status': outcome})
    kinds = {result['kind'] for result in results if result['status'] == 'pass'}
    status = 'pass' if {'readiness', 'smoke'} <= kinds and all(
        result['status'] == 'pass' for result in results) else 'not_verified' if not results else 'fail'
    return {'version': 1, 'image_digest': image, 'release_sha': release_sha, 'state_preserved': preserved,
            'status': status, 'probes': results, 'finished': time.time()}
