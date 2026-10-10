"""Shared value-based redaction: strips secrets, leaves ordinary text and code alone, never raises."""
import io
import logging
import threading
import unittest
from unittest.mock import patch

import diagnostics
import progress
import redaction


class Redact(unittest.TestCase):
    def setUp(self):
        redaction.clear()
        self.addCleanup(redaction.clear)

    def test_registered_values_are_replaced_longest_first(self):
        redaction.register("abcdefgh-long-secret", "abcdefgh")
        self.assertEqual(redaction.redact("x abcdefgh-long-secret y abcdefgh z"),
                         "x [REDACTED] y [REDACTED] z")

    def test_short_none_and_non_string_values_are_ignored(self):
        redaction.register(None, 12345678, "short", "  ", "")
        self.assertEqual(redaction.registered(), [])
        self.assertEqual(redaction.redact("short 12345678"), "short 12345678")

    def test_numeric_settings_and_code_are_untouched(self):
        texts = ("CODEBOT_CONTEXT_TOKEN_BUDGET=80000 budget 80000",
                 "token = compute(max_tokens=4096)",
                 "api_key: settings.API_KEY",
                 "Basic auth is configured; bearer tokens expire",
                 "https://github.com/org/repo.git")
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(redaction.redact(text), text)

    def test_token_shapes(self):
        text = ("xoxb-1234567890-abcdefghij ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ sk-abcdefghijklmnopqrstuvwxyz "
                "AKIAABCDEFGHIJKLMNOP Authorization: Bearer eyJhbGciOiJIUzI1NiJ9 "
                "https://user:hunter22@example.com/x?api_key=abcdef123&x=1")
        safe = redaction.redact(text)
        for secret in ("xoxb-1234567890", "ghp_ABCDEF", "sk-abcdef", "AKIAABCDEFGHIJKLMNOP",
                       "eyJhbGciOiJIUzI1NiJ9", "user:hunter22", "abcdef123"):
            self.assertNotIn(secret, safe)
        self.assertIn("Bearer [REDACTED]", safe)
        self.assertIn("https://[REDACTED]@example.com", safe)
        self.assertIn("api_key=[REDACTED]&x=1", safe)

    def test_non_string_input(self):
        redaction.register("supersecretvalue")
        self.assertEqual(redaction.redact(ValueError("supersecretvalue!")), "[REDACTED]!")
        self.assertEqual(redaction.redact(None), "None")


class LogFilter(unittest.TestCase):
    def setUp(self):
        redaction.clear()
        self.addCleanup(redaction.clear)
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.addFilter(redaction.Filter())
        self.log = logging.getLogger("test.redaction")
        self.log.propagate = False
        self.log.setLevel(logging.DEBUG)
        self.log.addHandler(self.handler)
        self.addCleanup(self.log.removeHandler, self.handler)

    def test_redacts_formatted_message_and_exception_text(self):
        redaction.register("supersecretvalue")
        self.log.info("reply %r from %s", "supersecretvalue", "xoxb-1234567890-abc")
        try:
            raise RuntimeError("boom supersecretvalue")
        except RuntimeError:
            self.log.exception("failed")
        out = self.stream.getvalue()
        self.assertNotIn("supersecretvalue", out)
        self.assertNotIn("xoxb-1234567890", out)
        self.assertIn("'[REDACTED]' from [REDACTED]", out)
        self.assertIn("RuntimeError: boom [REDACTED]", out)

    def test_bad_format_args_and_odd_messages_never_raise_or_drop(self):
        record = logging.makeLogRecord({"msg": "%s %s", "args": ("only-one",)})
        self.assertTrue(redaction.Filter().filter(record))
        record = logging.makeLogRecord({"msg": {"dict": "message"}, "args": ()})
        self.assertTrue(redaction.Filter().filter(record))
        with patch.object(redaction, "redact", side_effect=RuntimeError("broken")):
            self.assertTrue(redaction.Filter().filter(
                logging.makeLogRecord({"msg": "hello", "args": ()})))
        self.log.info("still %s", "logging")
        self.assertIn("still logging", self.stream.getvalue())

    def test_heartbeat_style_thread_survives_logging_inside_except(self):
        ticks = []

        def loop():
            for _ in range(3):
                try:
                    raise OSError("write failed xoxb-1234567890-abc")
                except Exception:
                    self.log.exception("heartbeat write failed")
                ticks.append(1)

        thread = threading.Thread(target=loop)
        thread.start()
        thread.join(5)
        self.assertEqual(len(ticks), 3)
        self.assertNotIn("xoxb-1234567890", self.stream.getvalue())

    def test_install_is_idempotent_and_attaches_to_root_handlers(self):
        root = logging.getLogger()
        handler = logging.StreamHandler(io.StringIO())
        root.addHandler(handler)
        self.addCleanup(root.removeHandler, handler)
        redaction.install()
        redaction.install()
        self.assertEqual(sum(isinstance(f, redaction.Filter) for f in handler.filters), 1)


class Callers(unittest.TestCase):
    def setUp(self):
        redaction.clear()
        self.addCleanup(redaction.clear)

    def test_diagnostics_explicit_environ_and_conservative_default_scan(self):
        safe = diagnostics.redact("key=supersecret Bearer bearersecret", {"API_KEY": "supersecret"})
        self.assertNotIn("supersecret", safe)
        self.assertNotIn("bearersecret", safe)
        with patch.dict("os.environ", {"CODEBOT_CONTEXT_TOKEN_BUDGET": "80000",
                                       "SHORT_TOKEN": "abc12345",
                                       "LONG_API_TOKEN": "a-very-long-secret-value-here"}):
            safe = diagnostics.redact("80000 abc12345 a-very-long-secret-value-here")
        self.assertIn("80000", safe)
        self.assertIn("abc12345", safe)  # too short for the implicit scan
        self.assertNotIn("a-very-long-secret-value-here", safe)

    def test_progress_uses_registered_values(self):
        redaction.register("registered-secret-value")
        self.assertNotIn("registered-secret-value",
                         progress.sanitize("running with registered-secret-value"))


if __name__ == "__main__":
    unittest.main()
