"""Versioned, declarative checks for the trusted deterministic runner."""
from dataclasses import asdict, dataclass, field, replace
import json
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Check:
    id: str
    argv: list[str]
    cwd: str = "."
    inputs: list[str] = field(default_factory=lambda: ["*"])
    env_keys: list[str] = field(default_factory=list)
    timeout: float = 900
    resources: list[str] = field(default_factory=list)
    reporter: str = "text"
    scope: str = "full"
    preparation: dict | None = None
    dependency_inputs: list[str] | None = None
    # Optional checks (e.g. live calls to a third-party API) are skipped, not failed,
    # when any of their env_keys has no value.
    optional: bool = False

    def __post_init__(self):
        self.optional = self.optional is True  # agent JSON may send "no"/"false" strings
        if not self.id or not self.argv or not all(isinstance(x, str) and x for x in self.argv):
            raise ValueError("Check requires id and nonempty argv strings")
        if self.timeout <= 0 or self.scope not in ("full", "focused"):
            raise ValueError("Invalid check timeout or scope")
        for values in (self.inputs, self.env_keys, self.resources):
            if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                raise ValueError("Check list fields must contain strings")
        if self.dependency_inputs is not None and (not isinstance(self.dependency_inputs, list) or
                not all(isinstance(p, str) and p for p in self.dependency_inputs)):
            raise ValueError("Check dependency inputs must be nonempty strings")

    def to_dict(self):
        value = asdict(self)
        if not value["optional"]:
            # Omitted when false so state written by this code still loads in older code.
            value.pop("optional")
        return value

    def missing_credentials(self, environ) -> list[str]:
        return [name for name in self.env_keys if not (environ.get(name) or "").strip()]


def relax(checks, names):
    """Checks needing any credential the user chose to go without become optional."""
    names = set(names or ())
    return [replace(c, optional=True) if names & set(c.env_keys) else c for c in checks]


def parse(value):
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("checks"), list):
        raise ValueError("Check plan must have version 1 and checks array")
    checks = [Check(**entry) for entry in value["checks"]]
    if len({c.id for c in checks}) != len(checks):
        raise ValueError("Duplicate check ids")
    return checks


def load(repo):
    path = Path(repo) / ".codebot/checks.json"
    return parse(json.loads(path.read_text())) if path.exists() else None


def _reported(output):
    markers = list(re.finditer(r"(?m)^CHECK_PLAN:[ \t]*", output))
    if not markers:
        return [], None
    text = output[markers[-1].end():].lstrip()
    # Accept a pretty-printed object, including a JSON fence after the marker.
    # Never search prose for a later object or fall back to an earlier plan.
    if text.startswith("```json\n"):
        text = text[len("```json\n"):].lstrip()
    elif text.startswith("```\n"):
        text = text[len("```\n"):].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(text)
        return parse(value), None
    except json.JSONDecodeError:
        return [], "CHECK_PLAN must contain a valid JSON object with version 1 and a checks array"
    except (ValueError, TypeError, AttributeError):
        return [], "CHECK_PLAN has invalid check fields, schema, or duplicate check IDs"


def reported(output):
    checks, error = _reported(output)
    if error:
        log.warning("Ignoring malformed agent check plan: %s", error)
    return checks


def reported_error(output):
    """A rejected plan is not successful verification or an empty valid plan."""
    return _reported(output)[1]


def discover(repo):
    repo = Path(repo)
    configured = load(repo)
    if configured is not None:
        return configured
    checks = []
    for directory in (".", "backend"):
        area = repo / directory
        if (area / "tests").is_dir() and (directory != "." or (area / "requirements.txt").exists()):
            # Preserve the venv launcher path: resolving its symlink runs the base
            # interpreter without pyvenv.cfg and loses all installed dependencies.
            candidates = [area / name / "bin/python" for name in (".venv", "venv")]
            python = next((p for p in candidates if p.is_file()), None)
            checks.append(Check("unit:" + directory,
                [str(python.absolute()) if python else sys.executable,
                 "-m", "unittest", "discover", "-s", "tests", "-v", *(["-t", "."] if directory == "." else [])], cwd=directory,
                inputs=[directory] if directory != "." else ["src", "tests", "requirements.txt"],
                reporter="unittest"))
    for directory in (".", "frontend"):
        package = repo / directory / "package.json"
        if not package.exists():
            continue
        scripts = json.loads(package.read_text()).get("scripts", {})
        for name in ("test", "lint", "build"):
            if name in scripts:
                checks.append(Check(f"{name}:{directory}", ["npm", "test"] if name == "test"
                    else ["npm", "run", name], cwd=directory, inputs=[directory],
                    reporter="node" if name == "test" and "node --test" in scripts[name] else
                    "eslint" if name == "lint" and "eslint" in scripts[name] else "text"))
    if (repo / "e2e/run.sh").exists():
        import harness_contract
        managed = harness_contract.load(repo)
        checks.extend(managed if managed is not None else [Check("e2e", ["./run.sh"], cwd="e2e", inputs=["*"],
                            resources=["harness:" + str(repo.resolve())], reporter="playwright")])
    return checks
