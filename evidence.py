"""Run the e2e suite and record evidence (Playwright video or Newman report) for a feature."""
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import config

log = logging.getLogger(__name__)

E2E_DIR = config.REPO_PATH / "e2e"
# The compose file run.sh brings up (relative to E2E_DIR); torn down by codebot itself
# when a timed-out run.sh could not (see _teardown_stack).
E2E_COMPOSE_FILE = os.environ.get("CODEBOT_E2E_COMPOSE_FILE") or "docker-compose.e2e.yaml"

_SPEC_GLOBS = {
    "playwright": "e2e/tests/*.spec.ts",
    "newman": "e2e/collections/*.postman_collection.json",
}


def reported_specs(output: str) -> list[str]:
    """Extract E2E_SPEC paths without carrying Markdown code delimiters into run.sh."""
    return [
        spec
        for line in output.splitlines() if line.startswith("E2E_SPEC:")
        if (spec := line[len("E2E_SPEC:"):].strip().strip("`"))
    ]


def normalize_spec_files(spec_files: list[str]) -> list[str]:
    """Remove presentation-only Markdown delimiters from persisted spec names."""
    return [spec for value in spec_files if (spec := value.strip().strip("`"))]


def detect_branch_specs(kind: str | None) -> list[str]:
    """Spec/collection files added/changed on this branch vs the base branch (fallback
    for evidence).

    Used when the implementation output never reported E2E_SPEC lines, so the
    evidence step still records evidence from the feature's own e2e tests instead
    of silently producing nothing.
    """
    glob = _SPEC_GLOBS.get(kind, _SPEC_GLOBS["playwright"])
    for base in (f"origin/{config.BASE_BRANCH}", config.BASE_BRANCH):
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", f"{base}...HEAD", "--", glob],
            cwd=config.REPO_PATH, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            specs = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            if specs:
                log.info("detect_branch_specs: %d spec(s) vs %s: %s", len(specs), base, specs)
            return specs
    log.warning("detect_branch_specs: could not diff against %s", config.BASE_BRANCH)
    return []


def _teardown_stack() -> None:
    """Force-remove the e2e compose stack. run.sh typically tears the stack down via a
    bash `trap cleanup EXIT`, but our subprocess timeout SIGKILLs run.sh and SIGKILL does
    not run traps — so a timed-out run leaks the stack's containers/network, which then
    collide with every later run. Python must do the cleanup the killed shell couldn't.
    No-op when the harness has no such compose file."""
    if not (E2E_DIR / E2E_COMPOSE_FILE).exists():
        log.info("no %s in %s; nothing to tear down", E2E_COMPOSE_FILE, E2E_DIR)
        return
    try:
        proc = subprocess.run(
            ["docker", "compose", "-f", E2E_COMPOSE_FILE, "down", "-v", "--remove-orphans"],
            cwd=E2E_DIR, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            log.warning("e2e stack teardown rc=%d: %s", proc.returncode, proc.stderr[-500:])
        else:
            log.info("e2e stack torn down after timeout")
    except Exception:
        log.exception("e2e stack teardown failed")


def run_suite() -> tuple[bool, str]:
    """Run the full e2e suite via run.sh. Returns (passed, output tail)."""
    log.info("running full e2e suite in %s", E2E_DIR)
    try:
        proc = subprocess.run(
            ["./run.sh"], cwd=E2E_DIR, capture_output=True, text=True,
            timeout=config.E2E_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        log.error("e2e suite timed out after %ss; tearing down leaked stack",
                  config.E2E_TIMEOUT_SECONDS)
        _teardown_stack()
        tail = ((exc.stdout or "") + "\n" + (exc.stderr or ""))[-6000:]
        return False, f"e2e suite TIMED OUT after {config.E2E_TIMEOUT_SECONDS}s\n{tail}"
    output = (proc.stdout + "\n" + proc.stderr)[-8000:]
    log.info("e2e suite exit=%d", proc.returncode)
    return proc.returncode == 0, output


def record_evidence(spec_files: list[str], kind: str | None) -> list[Path]:
    """Re-run the given spec/collection files with evidence recording forced on;
    return the recorded evidence file(s) — a stitched Playwright video, or the
    generated Newman run report."""
    spec_files = normalize_spec_files(spec_files)
    if not spec_files:
        log.info("record_evidence: no spec files given — falling back to branch spec detection")
        spec_files = detect_branch_specs(kind)
    if not spec_files:
        log.warning("record_evidence: no spec/collection files found — no evidence will be produced")
        return []
    if kind == "newman":
        return _record_newman_report(spec_files)
    return _record_playwright_video(spec_files)


def _run_recording(specs: list[str], extra_args: list[str]) -> str:
    """One run.sh invocation with video forced on; best-effort (clips are harvested
    after). Returns the run's output tail for diagnostics."""
    try:
        proc = subprocess.run(
            ["./run.sh", *specs, *extra_args], cwd=E2E_DIR, capture_output=True, text=True,
            timeout=config.E2E_TIMEOUT_SECONDS,
            # The target harness exposes a documented opt-in to Playwright's `video: "on"`
            # setting. Both spellings: PICA_E2E_VIDEO for harnesses built against this
            # contract and PW_VIDEO for older Playwright configs that gate on it.
            env={**os.environ, "PICA_E2E_VIDEO": "on", "PW_VIDEO": "on"},
        )
    except subprocess.TimeoutExpired:
        # Evidence is best-effort: tear down the leaked stack and harvest whatever
        # clips were produced before the timeout rather than crashing the PR flow.
        log.error("evidence run timed out after %ss; tearing down leaked stack",
                  config.E2E_TIMEOUT_SECONDS)
        _teardown_stack()
        return f"evidence run TIMED OUT after {config.E2E_TIMEOUT_SECONDS}s"
    if proc.returncode != 0:
        log.warning("evidence run exit=%d; stderr tail:\n%s", proc.returncode, proc.stderr[-1500:])
    return (proc.stdout + proc.stderr)[-1500:]


def _record_playwright_video(spec_files: list[str]) -> list[Path]:
    """Re-run the given specs with video forced on; return the recorded .webm files.

    Prefers the dedicated `@evidence` demo test (the IMPLEMENT prompt requires one per
    feature): it is written to be watchable, so recording only it keeps loosely related
    tests out of the emailed video. Specs without one fall back to recording everything
    in the given files.
    """
    results_dir = E2E_DIR / "test-results"

    def clips() -> set[Path]:
        return set(results_dir.rglob("*.webm")) if results_dir.exists() else set()

    before = clips()
    specs = [Path(s).name for s in spec_files]
    log.info("recording evidence: re-running @evidence tests of %s with video on", specs)
    tail = _run_recording(specs, ["--grep", "@evidence"])
    after = clips()
    if not (after - before):
        log.info("no @evidence-tagged test produced a clip; re-running full specs %s", specs)
        tail = _run_recording(specs, [])
        after = clips()
    new = sorted(after - before)
    if not new:
        log.warning("no NEW .webm files after evidence run (before=%d, after=%d); "
                    "check PICA_E2E_VIDEO/PW_VIDEO wiring and test-results mount, and whether "
                    "the spec skipped itself (bare `./run.sh <spec>` invocation, no extra "
                    "flags/env). Run output tail:\n%s", len(before), len(after), tail)
    videos = new or sorted(after)
    kept = [v for v in videos if v.stat().st_size > 0]
    for v in kept:
        log.info("evidence clip: %s (%d bytes)", v, v.stat().st_size)
    dropped = [v for v in videos if v.stat().st_size == 0]
    if dropped:
        log.warning("dropped %d zero-byte clip(s): %s", len(dropped), [str(v) for v in dropped])
    if not kept:
        log.info("_record_playwright_video: no clips to stitch")
        return []
    stitched = _stitch_to_mp4(kept)
    if stitched:
        log.info("_record_playwright_video: returning stitched %s (%d bytes)", stitched, stitched.stat().st_size)
        return [stitched]
    log.warning("_record_playwright_video: stitching unavailable/failed; returning %d raw webm clip(s)", len(kept))
    return kept


def _stitch_to_mp4(clips: list[Path]) -> Path | None:
    """Concatenate .webm clips into one H.264 .mp4 via ffmpeg. None on failure.

    Each clip is scaled/padded to a common 1280x720 frame so clips recorded at
    different viewport sizes concatenate cleanly.

    ffmpeg writes to a scratch dir under /tmp and the finished file is moved into
    config.DATA_DIR afterwards — never into e2e/test-results (created by the
    root-running playwright container, so the codebot uid cannot write there on a
    Linux host; Docker Desktop on macOS masks this), and not straight into data/
    either (that failed with access denied on a deployed host). /tmp is always
    writable for the codebot uid; if the move fails the /tmp file is returned rather
    than losing the evidence.
    """
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not found; cannot stitch/convert evidence videos")
        return None
    scratch_dir = Path(tempfile.mkdtemp(prefix="codebot-evidence-", dir="/tmp"))
    out = scratch_dir / "evidence.mp4"
    w, h = 1280, 720
    inputs: list[str] = []
    filters = []
    for i, clip in enumerate(clips):
        inputs += ["-i", str(clip.resolve())]
        filters.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
        )
    labels = "".join(f"[v{i}]" for i in range(len(clips)))
    filter_complex = ";".join(filters) + f";{labels}concat=n={len(clips)}:v=1:a=0[out]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
           "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(out)]
    log.info("stitching %d clip(s) into %s via ffmpeg (scratch dir %s)",
             len(clips), out.name, scratch_dir)
    returned_from_tmp = False  # the scratch dir only survives if we return its file
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=config.E2E_TIMEOUT_SECONDS)
        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            log.warning("ffmpeg stitch failed rc=%d; stderr tail:\n%s",
                        proc.returncode, proc.stderr[-1500:])
            return None
        dest = config.DATA_DIR / out.name
        try:
            shutil.move(str(out), dest)  # move handles cross-device (/tmp -> data)
        except OSError:
            log.exception("could not move %s into %s; returning the /tmp file",
                          out, config.DATA_DIR)
            returned_from_tmp = True
            return out
        return dest
    finally:
        if not returned_from_tmp:
            shutil.rmtree(scratch_dir, ignore_errors=True)


def stitch_playwright_clips(files: list[Path]) -> Path | None:
    """Stitch non-empty Playwright clips supplied by an agent into one MP4."""
    clips = [file for file in files if file.suffix.lower() == ".webm" and file.exists()
             and file.stat().st_size > 0]
    return _stitch_to_mp4(clips) if clips else None


def _record_newman_report(spec_files: list[str]) -> list[Path]:
    """Re-run the given Postman collections; return the newest generated report file.

    Newman has no UI to record, so the evidence analog is whatever report file
    e2e/run.sh's Newman invocation writes (e.g. an HTML report) — same
    before/after-diff pattern as the Playwright video path, without stitching.
    """
    results_dir = E2E_DIR / "test-results"
    before = set(results_dir.rglob("*.html")) if results_dir.exists() else set()
    collections = [Path(s).name for s in spec_files]
    log.info("recording Newman evidence: re-running collection(s) %s", collections)
    try:
        proc = subprocess.run(
            ["./run.sh", *collections], cwd=E2E_DIR, capture_output=True, text=True,
            timeout=config.E2E_TIMEOUT_SECONDS,
        )
        tail = (proc.stdout + proc.stderr)[-1500:]
        if proc.returncode != 0:
            log.warning("Newman evidence run exit=%d; stderr tail:\n%s",
                        proc.returncode, proc.stderr[-1500:])
    except subprocess.TimeoutExpired:
        log.error("Newman evidence run timed out after %ss; tearing down leaked stack",
                  config.E2E_TIMEOUT_SECONDS)
        _teardown_stack()
        tail = "TIMED OUT"
    after = set(results_dir.rglob("*.html")) if results_dir.exists() else set()
    new = sorted(after - before)
    if not new:
        log.warning("no NEW report file after Newman evidence run (before=%d, after=%d); "
                    "check the reporter wiring and test-results mount, and whether the "
                    "collection skipped itself (bare `./run.sh <collection>` invocation, no "
                    "extra flags/env). Run output tail:\n%s",
                    len(before), len(after), tail)
        return []
    newest = max(new, key=lambda p: p.stat().st_mtime)
    if newest.stat().st_size == 0:
        log.warning("newest Newman report %s is zero bytes; dropping it", newest)
        return []
    log.info("evidence report: %s (%d bytes)", newest, newest.stat().st_size)
    return [newest]
