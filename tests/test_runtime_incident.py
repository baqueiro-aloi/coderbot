"""Sanitized incident replay: completed tests do not explain the permission wait."""
import json
import unittest
from pathlib import Path


class IncidentReplayTests(unittest.TestCase):
    def test_legacy_cli_ignores_child_permission_after_tests_finished(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/runtime/permission-stall.json").read_text())
        events = fixture["events"]
        permission = next(e for e in events if e["type"] == "permission.asked")
        replies = [e for e in events if e["type"] == "permission.asked"
                   and e["properties"]["sessionID"] == fixture["root_session"]]
        self.assertEqual(replies, [])
        self.assertEqual(events[1]["properties"]["part"]["state"]["status"], "completed")
        timeout = next(e for e in events if e["type"] == "fixture.timeout")
        self.assertEqual(timeout["at"] - permission["at"], 6590)


if __name__ == "__main__":
    unittest.main()
