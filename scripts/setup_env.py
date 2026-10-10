"""Lossless-enough .env editing: never regenerate unrelated settings or secrets."""
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from scripts.setup_catalog import BY_KEY, validate

_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*?)(\r?\n)?$")


def _decode(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].replace("\\'", "'")
    return value


def _encode(value: str) -> str:
    if any(ch in value for ch in (" ", "#", "$", "'", '"')):
        return "'" + value.replace("'", "\\'") + "'"
    return value


class EnvFile:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lines = self.path.read_text().splitlines(keepends=True) if self.path.exists() else []
        self.values = {}
        for line in self.lines:
            if match := _ASSIGNMENT.match(line):
                self.values[match[1]] = _decode(match[2])

    def with_changes(self, changes: dict[str, str]) -> dict[str, str]:
        return self.values | changes

    def preview(self, changes: dict[str, str]) -> str:
        entries = []
        for key, value in changes.items():
            if self.values.get(key) == value:
                continue
            secret = BY_KEY[key].secret
            before = "(set)" if secret and self.values.get(key) else self.values.get(key, "(unset)")
            after = "(set)" if secret and value else value or "(empty)"
            entries.append(f"{key}: {before} -> {after}")
        return "\n".join(entries) if entries else "No changes."

    def _updated_text(self, changes: dict[str, str]) -> str:
        changed = {key: value for key, value in changes.items()
                   if self.values.get(key) != value}
        positions = {}
        for index, line in enumerate(self.lines):
            if match := _ASSIGNMENT.match(line):
                positions[match[1]] = index
        lines = self.lines[:]
        for key, value in changed.items():
            new_line = f"{key}={_encode(value)}\n"
            if key in positions:
                original = lines[positions[key]]
                lines[positions[key]] = new_line.rstrip("\n") + ("\r\n" if original.endswith("\r\n") else "\n")
            else:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                lines.append(new_line)
        return "".join(lines)

    def save(self, changes: dict[str, str],
             validator: Callable[[dict[str, str]], list[str]] | None = None) -> Path | None:
        if any(key not in BY_KEY for key in changes):
            raise ValueError("setup can only edit cataloged keys")
        errors = (validator or validate)(self.with_changes(changes))
        if errors:
            raise ValueError("\n".join(errors))
        data = self._updated_text(changes)
        if data == "".join(self.lines):
            return None
        backup = None
        if self.path.exists():
            index = 1
            while (candidate := self.path.with_name(f"{self.path.name}.bak.{index}")).exists():
                index += 1
            shutil.copy2(self.path, candidate)
            candidate.chmod(0o600)
            backup = candidate
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temp.chmod(0o600)
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)
        return backup
