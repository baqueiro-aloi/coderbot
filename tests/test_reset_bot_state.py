"""A fresh start keeps authentication and identity, but cannot resume old tasks."""
import fcntl
import tempfile
import unittest
from pathlib import Path

from scripts.reset_bot_state import reset


class ResetBotState(unittest.TestCase):
    def test_moves_active_held_and_slack_state_without_touching_credentials_or_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            target = root / "target"
            target.mkdir()
            (target / "user-work.txt").write_text("keep")
            for filename in ("state.json", "holds.json", "slack_inbox.sqlite",
                             "slack_inbox.sqlite-wal", "heartbeat", "instance_id",
                             "instance_fingerprint", "token.json", "credentials.json",
                             "processed_msgs.json", "state.lock"):
                (data / filename).write_text(filename)
            (data / "opencode").mkdir()
            (data / "opencode/auth.json").write_text("login")
            archive = reset(data)
            assert archive is not None
            self.assertEqual(archive.stat().st_mode & 0o777, 0o700)
            for filename in ("state.json", "holds.json", "slack_inbox.sqlite",
                             "slack_inbox.sqlite-wal", "heartbeat"):
                self.assertFalse((data / filename).exists())
                self.assertEqual((archive / filename).read_text(), filename)
            for filename in ("instance_id", "instance_fingerprint", "token.json",
                             "credentials.json", "processed_msgs.json", "state.lock"):
                self.assertEqual((data / filename).read_text(), filename)
            self.assertEqual((data / "opencode/auth.json").read_text(), "login")
            self.assertEqual((target / "user-work.txt").read_text(), "keep")
            self.assertIsNone(reset(data))  # repeated reset must not archive the backup

    def test_refuses_reset_while_bot_holds_the_state_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            (data / "state.json").write_text("old task")
            with (data / "state.lock").open("wb") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, "stop it"):
                    reset(data)
            self.assertEqual((data / "state.json").read_text(), "old task")


if __name__ == "__main__":
    unittest.main()
