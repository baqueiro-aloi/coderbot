from pathlib import Path
import tempfile
import unittest

import attachments
import secret_safety


class AttachmentSecretTests(unittest.TestCase):
    def test_all_text_suffixes_rejected_before_transport_copy(self):
        secret_safety.register('synthetic-attachment-credential')
        self.addCleanup(secret_safety.clear)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for suffix in ('.log', '.txt', '.json', '.html', '.unknown'):
                path = root / ('file' + suffix)
                path.write_text('synthetic-attachment-credential')
                with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'sensitive text'):
                    attachments.prepare(attachments.describe(path), 10000, root / 'transport')
            self.assertFalse((root / 'transport').exists())

    def test_sanitized_copy_allowed_without_overwriting_original(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'diagnostic.txt'
            path.write_text('Authorization: Bearer abcdefgh')
            with self.assertRaises(ValueError):
                attachments.assert_safe_text(path)
            cleaned = path.with_name('cleaned.txt')
            cleaned.write_text(secret_safety.redact(path.read_text()))
            # Redaction must be idempotent for safely prepared diagnostics.
            self.assertEqual(secret_safety.redact(cleaned.read_text()), cleaned.read_text())
            attachments.assert_safe_text(cleaned)
