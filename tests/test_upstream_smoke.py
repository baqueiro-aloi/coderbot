import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_plan import Check
import upstream_smoke


class UpstreamSmokeTests(unittest.TestCase):
    def setUp(self):
        self.check = Check('service:smoke', ['smoke'], kind='upstream', contract_version=2,
            max_age_seconds=30, timeout=30, external_dependencies=['service'], env_keys=['SERVICE_KEY'])
        self.request = {'version': 1, 'service': 'service', 'environment': 'test',
            'env_keys': ['SERVICE_KEY'], 'permissions': ['inference'], 'check_ids': ['service:smoke'],
            'effects': 'synthetic inference smoke', 'paid': True, 'max_cost': .01, 'currency': 'USD'}
        self.state = {'external_authorizations': []}
        self.store = type('Store', (), {'task_identity': lambda *args: 'task'})()

    def test_paid_smoke_needs_authorization_and_scoped_handle(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PermissionError):
                upstream_smoke.run(self.state, root, self.store, self.check, self.request, secret_handles=['handle'])
            self.state['external_authorizations'] = [{'request_identity': hashlib.sha256(
                json.dumps(self.request, sort_keys=True).encode()).hexdigest()}]
            with patch.object(upstream_smoke.checks, 'execute', return_value={'status': 'pass'}) as execute:
                result = upstream_smoke.run(self.state, root, self.store, self.check, self.request, secret_handles=['handle'])
            self.assertEqual(result['evidence_class'], 'upstream')
            self.assertTrue(result['synthetic'])
            execute.assert_called_once()

    def test_listing_or_unbounded_check_cannot_be_called_smoke(self):
        bad = Check('service:list', ['list'], kind='upstream', contract_version=2,
            max_age_seconds=30, timeout=121, external_dependencies=['service'])
        with self.assertRaises(ValueError):
            upstream_smoke.run(self.state, Path('.'), self.store, bad, {**self.request, 'check_ids': ['service:list']})
