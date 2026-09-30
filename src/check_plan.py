"""Versioned, declarative checks for the trusted deterministic runner."""
from dataclasses import asdict, dataclass, field
import json
import sys
from pathlib import Path


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

    def __post_init__(self):
        if not self.id or not self.argv or not all(isinstance(x, str) and x for x in self.argv):
            raise ValueError("Check requires id and nonempty argv strings")
        if self.timeout <= 0 or self.scope not in ("full", "focused"):
            raise ValueError("Invalid check timeout or scope")
        for values in (self.inputs, self.env_keys, self.resources):
            if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                raise ValueError("Check list fields must contain strings")

    def to_dict(self):
        return asdict(self)


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


def discover(repo):
    repo = Path(repo)
    configured = load(repo)
    if configured is not None:
        return configured
    checks = []
    for directory in (".", "backend", "PICAv1/backend"):
        area = repo / directory
        if (area / "tests").is_dir() and (directory != "." or (area / "requirements.txt").exists()):
            python = area / ".venv/bin/python"
            checks.append(Check("unit:" + directory,
                [str(python.resolve()) if python.exists() else sys.executable,
                 "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=directory,
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
                    reporter="node" if name == "test" and "node --test" in scripts[name] else "text"))
    if (repo / "e2e/run.sh").exists():
        checks.append(Check("e2e", ["./run.sh"], cwd="e2e", inputs=["*"],
                            resources=["harness:" + str(repo.resolve())], reporter="playwright"))
    return checks
