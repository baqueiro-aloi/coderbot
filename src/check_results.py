"""Conservative result adapters: unknown failures cannot become preexisting."""
import json
import re
import xml.etree.ElementTree as ET


def parse_output(output, exit_code, reporter="text"):
    if exit_code and re.search(r"ModuleNotFoundError: No module named|ImportError: Failed to import test module", output):
        return {"status": "infrastructure", "failures": {}, "exit_code": exit_code}
    failures = {}
    recognized = exit_code == 0
    if reporter == "unittest":
        recognized = bool(re.search(r"Ran \d+ tests? in", output))
        for match in re.finditer(r"(?:FAIL|ERROR): (.+?)\n[-]+\n(.*?)(?=\n[=]{5,}|\n[-]{5,}\nRan |\Z)", output, re.S):
            failures[match[1].strip()] = match[2].strip()
    elif reporter == "node":
        recognized = bool(re.search(r"# (?:tests|pass) \d+", output))
        for match in re.finditer(r"not ok \d+ - (.+?)\n(.*?)(?=\n(?:ok |not ok |#)|\Z)", output, re.S):
            failures[match[1].strip()] = match[2].strip()
    elif reporter == "eslint":
        # ESLint's default stylish format. Require a complete summary and account
        # for every error; a truncated/unfamiliar format remains unknown.
        text = re.sub(r"\x1b\[[0-9;]*m", "", output)
        summary = re.search(r"\d+ problems? \((\d+) errors?, \d+ warnings?\)", text)
        current = None
        for line in text.splitlines():
            if line.startswith("/"):
                current = line.strip()
            match = re.match(r"\s+(\d+):(\d+)\s+error\s+(.+?)\s{2,}(\S+)\s*$", line)
            if current and match:
                identity = f"{current}:{match[1]}:{match[2]}:{match[4]}"
                failures[identity] = match[3]
        recognized = bool(summary and int(summary[1]) == len(failures))
    elif reporter == "junit":
        try:
            root = ET.fromstring(output)
            recognized = True
            for case in root.iter("testcase"):
                for error in list(case):
                    if error.tag in ("failure", "error"):
                        failures[case.get("classname", "") + ":" + case.get("name", "")] = (
                            error.get("message", "") + "\n" + (error.text or "")).strip()
        except ET.ParseError:
            recognized = False
    elif reporter == "json":
        try:
            value = json.loads(output)
            failures = value["failures"]
            recognized = isinstance(failures, dict) and all(isinstance(v, str) for v in failures.values())
        except (ValueError, KeyError, TypeError):
            recognized = False
    elif reporter == "playwright":
        recognized = bool(re.search(r"\d+ (?:failed|passed)\b", output))
        for match in re.finditer(r"^\s*\d+\) (\[.+?\].+?)\n(.*?)(?=^\s*\d+\) \[|^\s*\d+ (?:failed|passed)|\Z)", output, re.M | re.S):
            test = re.sub(r":\d+:\d+", ":<line>", match[1].strip())
            # Retain assertion/error context, exclude artifact paths and timing.
            detail = match[2].split("attachment #", 1)[0].strip()
            failures[test] = detail
    # Playwright list output is not a stable identity contract. Use JSON/JUnit via
    # an explicit plan for baseline attribution; zero exit is still a real pass.
    status = "pass" if exit_code == 0 else "fail" if recognized and failures else "unknown"
    return {"status": status, "failures": failures, "exit_code": exit_code}
