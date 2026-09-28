"""Google consent is conditional on the selected source, channel and evidence."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ConditionalScopes(unittest.TestCase):
    def scopes(self, source, channel, evidence):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ | {
                "PYTHONPATH": str(ROOT / "src"), "CODEBOT_DATA_DIR": tmp,
                "CODEBOT_TASK_SOURCE": source, "CODEBOT_COMM_CHANNEL": channel,
                "CODEBOT_EVIDENCE_UPLOAD": evidence,
            }
            output = subprocess.run([sys.executable, "-c", "import json,config; print(json.dumps(config.SCOPES))"],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=10,
                                    check=True).stdout
            return json.loads(output)

    def test_jira_slack_without_upload_has_no_google_consent(self):
        self.assertEqual(self.scopes("jira", "slack", "off"), [])

    def test_gdoc_slack_and_jira_email_request_only_necessary_scopes(self):
        gdoc = self.scopes("gdoc", "slack", "off")
        self.assertEqual(len(gdoc), 2)
        self.assertTrue(any("documents" in scope for scope in gdoc))
        self.assertTrue(any("drive" in scope for scope in gdoc))
        self.assertFalse(any("gmail" in scope for scope in gdoc))
        jira_email = self.scopes("jira", "email", "off")
        self.assertEqual(len(jira_email), 1)
        self.assertIn("gmail", jira_email[0])


if __name__ == "__main__":
    unittest.main()
