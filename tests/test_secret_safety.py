"""Synthetic secret values only; no runtime credentials are read."""
import unittest

import secret_safety


class SecretSafetyTests(unittest.TestCase):
    def setUp(self):
        secret_safety.clear()
        self.addCleanup(secret_safety.clear)

    def test_dynamic_secret_and_entire_access_link_are_redacted(self):
        key = 'synthetic-dynamic-value'
        link = 'https://private.example/?paste#synthetic-decryption-key'
        secret_safety.register(key, link)
        safe = secret_safety.redact(f'error {key}: {link}', environ={})
        self.assertNotIn(key, safe)
        self.assertNotIn(link, safe)
        self.assertNotIn('synthetic-decryption-key', safe)

    def test_inline_forms_and_environment_values(self):
        text = ('Authorization: Basic YWJj api_key="synthetic-key" '
                'password=synthetic-pass Bearer synthetic-bearer '
                'https://user:synthetic-pass@host/a?token=synthetic-query '
                'sk-synthetic123 ghp_synthetic123 xoxb-synthetic-123')
        safe = secret_safety.redact(text, environ={'SERVICE_TOKEN': 'environment-value'})
        for value in ('YWJj', 'synthetic-key', 'synthetic-pass', 'synthetic-bearer',
                      'synthetic-query', 'sk-synthetic123', 'ghp_synthetic123', 'xoxb-synthetic-123'):
            self.assertNotIn(value, safe)
        self.assertNotIn('environment-value', secret_safety.redact('environment-value',
            environ={'SERVICE_TOKEN': 'environment-value'}))

    def test_safe_structure_preserves_contract_fields_not_secret_values(self):
        secret_safety.register('synthetic-nested')
        result = secret_safety.safe({'status': 'pass', 'argv': ['test'],
                                    'detail': ['synthetic-nested']}, environ={})
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['argv'], ['test'])
        self.assertEqual(result['detail'], ['[REDACTED]'])
