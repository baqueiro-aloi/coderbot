"""Conservative result adapters: unknown failures cannot become preexisting."""
import json
import re
import xml.etree.ElementTree as ET


def parse_output(output, exit_code, reporter="text"):
    if exit_code and re.search(r"ModuleNotFoundError: No module named|ImportError: Failed to import test module", output):
        return {"status": "infrastructure", "failures": {}, "exit_code": exit_code}
    failures = {}
    recognized = exit_code == 0
    tests, skipped, failed_count = None, 0, 0
    successful_summary = True
    if reporter == "unittest":
        count = re.search(r"Ran (\d+) tests? in", output)
        recognized = bool(count)
        tests = int(count[1]) if count else None
        skip = re.search(r"skipped=(\d+)", output)
        skipped = int(skip[1]) if skip else 0
        failed_count = sum(int(m[1]) for m in re.finditer(r"(?:failures|errors|unexpected successes)=(\d+)", output))
        successful_summary = bool(re.search(r"^OK(?:\s*\([^\n]*\))?\s*$", output, re.M))
        for match in re.finditer(r"(?:FAIL|ERROR): (.+?)\n[-]+\n(.*?)(?=\n[=]{5,}|\n[-]{5,}\nRan |\Z)", output, re.S):
            failures[match[1].strip()] = match[2].strip()
    elif reporter == "node":
        counts = {m[1]: int(m[2]) for m in re.finditer(r"^# (tests|pass|fail|skipped|todo) (\d+)\s*$", output, re.M)}
        tests = counts.get('tests')
        skipped = counts.get('skipped', 0) + counts.get('todo', 0)
        failed_count = counts.get('fail', 0)
        recognized = tests is not None and all(key in counts for key in ('pass', 'fail', 'skipped'))
        successful_summary = recognized and counts['pass'] + failed_count + skipped == tests
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
            cases = list(root.iter('testcase'))
            tests = len(cases)
            skipped = sum(case.find('skipped') is not None for case in cases)
            recognized = root.tag in ('testsuite', 'testsuites')
            if 'tests' in root.attrib and int(root.attrib['tests']) != tests:
                recognized = False
            for case in cases:
                for error in list(case):
                    if error.tag in ("failure", "error"):
                        failures[case.get("classname", "") + ":" + case.get("name", "")] = (
                            error.get("message", "") + "\n" + (error.text or "")).strip()
        except (ET.ParseError, ValueError):
            recognized = False
    elif reporter == "json":
        try:
            value = json.loads(output)
            failures = value["failures"]
            recognized = isinstance(failures, dict) and all(isinstance(v, str) for v in failures.values())
            tests, skipped = value.get('tests'), value.get('skipped', 0)
            if type(tests) is not int or type(skipped) is not int or tests < 0 or skipped < 0:
                # Legacy JSON failure identities remain useful for attribution,
                # but absent counts cannot attest successful test execution.
                if exit_code == 0:
                    recognized = False
                tests, skipped = None, 0
        except (ValueError, KeyError, TypeError):
            recognized = False
    elif reporter == "playwright":
        counts = {name: sum(int(m[1]) for m in re.finditer(r"^\s*(\d+) " + name + r"\b", output, re.M))
                  for name in ('passed', 'failed', 'skipped', 'did not run', 'flaky')}
        recognized = bool(re.search(r"^\s*\d+ (?:failed|passed|skipped|did not run)\b", output, re.M))
        tests = sum(counts.values()) if recognized else None
        skipped = counts['skipped'] + counts['did not run']
        failed_count = counts['failed'] + counts['flaky']
        for match in re.finditer(r"^\s*\d+\) (\[.+?\].+?)\n(.*?)(?=^\s*\d+\) \[|^\s*\d+ (?:failed|passed)|\Z)", output, re.M | re.S):
            test = re.sub(r":\d+:\d+", ":<line>", match[1].strip())
            # Retain assertion/error context, exclude artifact paths and timing.
            detail = match[2].split("attachment #", 1)[0].strip()
            failures[test] = detail
    if tests is not None and (skipped > tests or len(failures) + skipped > tests):
        recognized = False
    if not recognized:
        status = 'unknown'
    elif failures or failed_count:
        status = 'fail'
    elif exit_code != 0 or not successful_summary:
        status = 'unknown'
    elif tests == 0:
        status = 'not_run'
    elif skipped:
        status = 'skipped'
    else:
        status = 'pass'
    return {"status": status, "failures": failures, "exit_code": exit_code,
            "tests": tests, "skipped": skipped, "executed": tests - skipped if tests is not None else None}
