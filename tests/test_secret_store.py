"""Credential storage, injection and link capture: private, expiring, and inert when off."""
import os
import sqlite3
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import conversation
import redaction
import secret_store

LINK = "https://abc123def.lhr.life/?0123456789abcdef#" + "7" * 44


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        for name, value in (("DATA_DIR", self.data), ("CREDENTIAL_REQUESTS", True)):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        redaction.clear()
        self.addCleanup(redaction.clear)
        self.addCleanup(secret_store.activate, None)
        self.addCleanup(secret_store._captured.clear)


class Storage(Base):
    def test_private_permissions_ttl_and_redaction(self):
        secret_store.put("task-a", "STRIPE_KEY", "sk_test_value_123", ttl=60, source="privatebin")
        directory = secret_store._task_dir("task-a")
        self.assertEqual(stat.S_IMODE(os.stat(self.data / "secrets").st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(directory).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(directory / "STRIPE_KEY.json").st_mode), 0o600)
        self.assertEqual(secret_store.values("task-a"), {"STRIPE_KEY": "sk_test_value_123"})
        self.assertEqual(redaction.redact("key sk_test_value_123"), "key [REDACTED]")
        self.assertEqual(secret_store.values("task-b"), {})
        with patch.object(secret_store.time, "time", return_value=time.time() + 120):
            self.assertEqual(secret_store.values("task-a"), {})
        self.assertFalse((directory / "STRIPE_KEY.json").exists())

    def test_drop_and_sweep(self):
        secret_store.put("t1", "API_KEY", "value-one-1", ttl=60, source="x")
        secret_store.put("t2", "API_KEY", "value-two-2", ttl=1, source="x")
        with patch.object(secret_store.time, "time", return_value=time.time() + 30):
            secret_store.sweep()
        self.assertFalse(secret_store._task_dir("t2").exists())
        secret_store.drop_task("t1")
        self.assertFalse(secret_store._task_dir("t1").exists())

    def test_reserved_names_are_refused(self):
        for name in ("GH_TOKEN", "PATH", "CODEBOT_SLACK_BOT_TOKEN", "LD_PRELOAD", "lower", "X"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                secret_store.put("t", name, "value-123456", ttl=60, source="x")


class Injection(Base):
    def test_environment_adds_active_task_values_without_touching_os_environ(self):
        secret_store.put("task-a", "STRIPE_KEY", "sk_test_value_123", ttl=60, source="x")
        self.assertNotIn("STRIPE_KEY", secret_store.environment())
        secret_store.activate("task-a")
        self.assertEqual(secret_store.environment({"A": "1"}), {"A": "1", "STRIPE_KEY": "sk_test_value_123"})
        self.assertNotIn("STRIPE_KEY", os.environ)
        self.assertTrue(secret_store.available("STRIPE_KEY"))
        with patch.object(config, "CREDENTIAL_REQUESTS", False):
            self.assertEqual(secret_store.environment({"A": "1"}), {"A": "1"})

    def test_unreadable_store_falls_back_to_the_plain_environment(self):
        secret_store.activate("task-a")
        with patch.object(secret_store, "values", side_effect=OSError("denied")):
            self.assertEqual(secret_store.environment({"A": "1"}), {"A": "1"})
            self.assertFalse(secret_store.available("STRIPE_KEY"))

    def test_agent_and_check_environments_receive_credentials(self):
        import checks
        import claude_runner
        secret_store.put("task-a", "STRIPE_KEY", "sk_test_value_123", ttl=60, source="x")
        secret_store.activate("task-a")
        self.assertEqual(checks.check_environment()["STRIPE_KEY"], "sk_test_value_123")
        with patch.object(claude_runner.operations, "run") as run:
            claude_runner._run(["claude", "-p"])
        self.assertEqual(run.call_args.kwargs["env"]["STRIPE_KEY"], "sk_test_value_123")


class Capture(Base):
    def test_links_are_replaced_registered_and_available_by_message(self):
        text = secret_store.capture("m1", f"here {LINK} thanks")
        self.assertEqual(text, "here [secure-link] thanks")
        self.assertEqual(secret_store.take_links("m1"), [LINK])
        self.assertEqual(redaction.redact(LINK), "[REDACTED]")
        self.assertTrue(secret_store.forget("m1"))
        self.assertEqual(secret_store.take_links("m1"), [])
        self.assertFalse(secret_store.forget("m1"))

    def test_ordinary_text_and_feature_off_are_untouched(self):
        self.assertEqual(secret_store.capture("m", "see https://example.com/?a=1#top"),
                         "see https://example.com/?a=1#top")
        with patch.object(config, "CREDENTIAL_REQUESTS", False):
            self.assertEqual(secret_store.capture("m", LINK), LINK)

    def test_facade_captures_and_slack_row_is_scrubbed_after_handling(self):
        import slack_client
        with patch.object(config, "COMM_CHANNEL", "slack"):
            with slack_client._database() as db:
                db.execute("INSERT INTO messages(id,channel,root_ts,ts,text) VALUES(?,?,?,?,?)",
                           ("C1:2", "C1", "1", "2", f"key {LINK}"))
            with patch.object(slack_client, "poll_reply", return_value=("C1:2", f"key {LINK}")):
                self.assertEqual(conversation.poll_reply("C1:1"), ("C1:2", "key [secure-link]"))
            conversation.mark_processed("C1:2")
        stored = sqlite3.connect(self.data / "slack_inbox.sqlite").execute(
            "SELECT text, handled FROM messages WHERE id='C1:2'").fetchone()
        self.assertEqual(stored, ("key [secure-link]", 1))


class Requests(Base):
    def test_parse_request(self):
        output = 'work\nCREDENTIAL_REQUEST: {"env":"STRIPE_KEY","purpose":"live refund test","service":"Stripe"}\n'
        self.assertEqual(secret_store.parse_request(output),
                         {"env": "STRIPE_KEY", "purpose": "live refund test", "service": "Stripe",
                          "optional": True})
        for bad in ("CREDENTIAL_REQUEST: {not json", 'CREDENTIAL_REQUEST: {"env":"GH_TOKEN"}',
                    'CREDENTIAL_REQUEST: ["x"]', "no request here", None):
            with self.subTest(bad=bad):
                self.assertIsNone(secret_store.parse_request(bad))
        with patch.object(config, "CREDENTIAL_REQUESTS", False):
            self.assertIsNone(secret_store.parse_request(output))


if __name__ == "__main__":
    unittest.main()
