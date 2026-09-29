"""Source and conversation mode requirements are independent at startup."""
import unittest
from unittest.mock import MagicMock, patch

import config
with patch.dict("sys.modules", {"gmail_client": MagicMock()}):
    import main


class ChannelConfiguration(unittest.TestCase):
    def check(self, source, channel, **options):
        values = {"TASK_SOURCE": source, "COMM_CHANNEL": channel,
                  "USER_EMAIL": "" if channel == "slack" else "owner@example.com",
                  "DOC_ID": "doc-id" if source == "gdoc" else "",
                  "GH_PROJECT_OWNER": "team" if source == "github" else "",
                  "GH_PROJECT_NUMBER": 2 if source == "github" else 0,
                  "JIRA_URL": "https://team.atlassian.net" if source == "jira" else "",
                  "JIRA_PROJECT_KEY": "TEAM" if source == "jira" else "",
                  "JIRA_EMAIL": "jira@example.com" if source == "jira" else "",
                  "JIRA_API_TOKEN": "token" if source == "jira" else "",
                  "JIRA_PICK_LABEL": "codebot-ready" if source == "jira" else "",
                  "SLACK_CHANNEL_ID": "C12345" if channel == "slack" else "",
                  "SLACK_BOT_TOKEN": "xoxb-token" if channel == "slack" else "",
                  "SLACK_APP_TOKEN": "xapp-token" if channel == "slack" else ""}
        values.update(options)
        with patch.multiple(config, **values), \
             patch.object(main, "validate_managed_runtime"), \
             patch.object(main, "_acquire_single_instance_lock"), \
             patch.object(main.task_source, "validate"), \
             patch.object(main.task_source, "describe", return_value="source"), \
             patch.object(main.gmail_client, "start"), \
             patch.object(main, "load_state", return_value={"state": "IDLE"}), \
             patch.object(main.threading.Thread, "start"), \
             patch.object(main.config.REPO_PATH.__class__, "exists", return_value=True), \
             patch.object(main, "_run_loop", side_effect=SystemExit("started")):
            main.main()

    def test_all_sources_and_channels(self):
        for source in ("gdoc", "github", "jira"):
            for channel in ("email", "slack"):
                with self.subTest(source=source, channel=channel):
                    with self.assertRaisesRegex(SystemExit, "started"):
                        self.check(source, channel)

    def test_jira_requires_credentials_only_when_selected(self):
        with self.assertRaisesRegex(SystemExit, "CODEBOT_JIRA_API_TOKEN"):
            self.check("jira", "email", JIRA_API_TOKEN="")
        with self.assertRaisesRegex(SystemExit, "CODEBOT_JIRA_PICK_LABEL"):
            self.check("jira", "email", JIRA_PICK_LABEL="")
        with self.assertRaisesRegex(SystemExit, "CODEBOT_SLACK_APP_TOKEN"):
            self.check("gdoc", "slack", SLACK_APP_TOKEN="")

    def test_statuses_and_channel_are_validated(self):
        with self.assertRaisesRegex(SystemExit, "CODEBOT_JIRA_PICK_STATUS"):
            self.check("jira", "email", JIRA_PICK_STATUS="")
        with self.assertRaisesRegex(SystemExit, "CODEBOT_SLACK_CHANNEL_ID"):
            self.check("github", "slack", SLACK_CHANNEL_ID="G123")
        with self.assertRaisesRegex(SystemExit, "CODEBOT_COMM_CHANNEL"):
            self.check("gdoc", "sms")


if __name__ == "__main__":
    unittest.main()
