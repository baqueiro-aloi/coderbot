"""Conservative result adapters: unknown failures cannot become preexisting."""
import json
import re
import xml.etree.ElementTree as ET


def parse_output(output, exit_code, reporter="text"):
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
    # Playwright list output is not a stable identity contract. Use JSON/JUnit via
    # an explicit plan for baseline attribution; zero exit is still a real pass.
    status = "pass" if exit_code == 0 else "fail" if recognized and failures else "unknown"
    return {"status": status, "failures": failures, "exit_code": exit_code}
