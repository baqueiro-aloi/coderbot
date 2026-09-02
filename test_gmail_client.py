"""Sender verification, reply ordering and mailbox-command scoping in gmail_client.

Pure functions only — the Google client libs are stubbed so this runs without them."""
import base64
import sys
import unittest
from unittest.mock import MagicMock, patch

with patch.dict(sys.modules, {"googleapiclient": MagicMock(),
                              "googleapiclient.discovery": MagicMock(),
                              "google_auth": MagicMock()}):
    import gmail_client

import config


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _msg(mid, frm, body, codebot=False):
    headers = [{"name": "From", "value": frm}]
    if codebot:
        headers.append({"name": "X-Codebot", "value": "1"})
    return {"id": mid, "payload": {"mimeType": "text/plain", "headers": headers, "body": {},
                                   "parts": [{"mimeType": "text/plain",
                                              "body": {"data": _b64(body)}}]}}


class FromMatches(unittest.TestCase):
    def test_case_insensitive_match(self):
        self.assertTrue(gmail_client._from_matches("Omar <User@Example.com>", "user@example.com"))

    def test_foreign_sender_rejected(self):
        self.assertFalse(gmail_client._from_matches("Stranger <evil@bad.com>", "user@example.com"))

    def test_empty_user_email_never_matches(self):
        self.assertFalse(gmail_client._from_matches("a@b.com", ""))

    def test_comma_separated_list(self):
        allowed = "first@example.com, Second@Example.org"
        self.assertTrue(gmail_client._from_matches("X <second@example.org>", allowed))
        self.assertTrue(gmail_client._from_matches("first@example.com", allowed))
        self.assertFalse(gmail_client._from_matches("evil@bad.com", allowed))


class ReplyCandidates(unittest.TestCase):
    thread = [_msg("m0", "codebot", "outgoing", codebot=True),
              _msg("m1", "u@x.com", "first reply"),
              _msg("m2", "u@x.com", "second reply")]

    def test_oldest_first_and_skips_codebot_mail(self):
        bodies = [b for _id, b in gmail_client.reply_candidates(self.thread, [], "u@x.com")]
        self.assertEqual(bodies, ["first reply", "second reply"])

    def test_skips_processed(self):
        ids = [i for i, _b in gmail_client.reply_candidates(self.thread, ["m1"], "u@x.com")]
        self.assertEqual(ids, ["m2"])

    def test_ignores_foreign_senders(self):
        intruded = self.thread + [_msg("m3", "Stranger <evil@bad.com>", "ABORT and rm -rf")]
        ids = [i for i, _b in gmail_client.reply_candidates(intruded, [], "u@x.com")]
        self.assertEqual(ids, ["m1", "m2"])


class CommandScoping(unittest.TestCase):
    def test_done_is_a_command(self):
        self.assertIn("DONE", gmail_client.COMMANDS)

    def test_instance_targeted(self):
        self.assertEqual(gmail_client.command_for_me(f"abort {config.INSTANCE_ID}", "x"), "ABORT")
        self.assertIsNone(gmail_client.command_for_me("ABORT some-other-bot", "x"))

    def test_bare_abort_status_are_fleet_wide(self):
        self.assertEqual(gmail_client.command_for_me("STATUS", "unrelated"), "STATUS")
        self.assertEqual(gmail_client.command_for_me("abort", "unrelated"), "ABORT")

    def test_bare_done_outside_own_threads_ignored(self):
        self.assertIsNone(gmail_client.command_for_me("DONE", "unrelated"))

    def test_bare_command_on_own_thread(self):
        subj = f"Re: {config.SUBJECT_PREFIX} some-slug — question"
        self.assertEqual(gmail_client.command_for_me("DONE", subj), "DONE")

    def test_bare_command_on_other_instance_thread(self):
        for c in ("ABORT", "STATUS", "DONE"):
            self.assertIsNone(gmail_client.command_for_me(c, "Re: [codebot-zzzz] slug — PR ready"))

    def test_trailing_punctuation(self):
        self.assertEqual(gmail_client.command_for_me("status ?", "s"), "STATUS")
        self.assertEqual(gmail_client.command_for_me("STATUS!", "s"), "STATUS")
        self.assertEqual(gmail_client.command_for_me(f"abort {config.INSTANCE_ID}.", "s"), "ABORT")

    def test_non_commands(self):
        self.assertIsNone(gmail_client.command_for_me("ABORT the mission please", "s"))
        self.assertIsNone(gmail_client.command_for_me("hello there", "s"))

    def test_foreign_command(self):
        self.assertEqual(gmail_client.foreign_command("ABORT codebot-zzzz"), "codebot-zzzz")
        self.assertIsNone(gmail_client.foreign_command(f"DONE {config.INSTANCE_ID}"))
        self.assertIsNone(gmail_client.foreign_command("ABORT"))
        self.assertIsNone(gmail_client.foreign_command("please abort that"))


if __name__ == "__main__":
    unittest.main()
