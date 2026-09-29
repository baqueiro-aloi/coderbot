"""Prepare the VM's .env without changing the local copy or revealing secrets."""
import sys
from pathlib import Path

from scripts.setup_env import EnvFile


PATH_KEYS = (
    "CODEBOT_DATA_DIR", "CLAUDE_CONFIG_PATH", "CODEBOT_E2E_COMPOSE_FILE",
    "CODEBOT_SUPERPOWERS_PLUGIN_DIR", "CODEBOT_BRIDGE_PLUGIN_DIR",
    "CODEBOT_OPENSPEC_SKILLS_DIR",
)


def prepare(source: Path, destination: Path, app: Path, target: Path,
            vm_target: Path) -> None:
    original = EnvFile(source)
    if not original.values.get("CODEBOT_REPO_PATH"):
        raise ValueError("CODEBOT_REPO_PATH is missing from .env")
    changes = {"CODEBOT_REPO_PATH": str(vm_target)}

    def translate(value: str) -> str:
        for local, remote in ((target, vm_target), (app, Path("/app"))):
            if value == str(local) or value.startswith(str(local) + "/"):
                return str(remote) + value[len(str(local)):]
        return value

    for key in PATH_KEYS:
        if value := original.values.get(key):
            rewritten = translate(value)
            if (rewritten == value and value.startswith("/") and
                    not value.startswith(("/app/", "/opt/", str(vm_target) + "/"))):
                raise ValueError(f"{key} references a path outside the copied directories; "
                                 "configure its VM location explicitly")
            if rewritten != value:
                changes[key] = rewritten

    destination.write_text(original._updated_text(changes))
    destination.chmod(0o600)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit("Usage: python3 -m scripts.prepare_vm_env SOURCE OUTPUT APP TARGET VM_TARGET")
    try:
        prepare(*(Path(arg) for arg in sys.argv[1:]))
    except ValueError as error:
        raise SystemExit(str(error)) from error
