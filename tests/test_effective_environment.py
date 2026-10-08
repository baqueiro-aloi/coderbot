import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import effective_environment


class EffectiveEnvironmentTests(unittest.TestCase):
    def test_actual_python_probe_reports_installed_packages(self):
        with tempfile.TemporaryDirectory() as root:
            value = effective_environment.installed([sys.executable, '-m', 'unittest'], root)
        self.assertTrue(value['verified'])
        self.assertIn('prefix', value['python'])
        self.assertIsInstance(value['python']['packages'], list)

    def test_changed_install_without_manifest_is_distinct(self):
        values = []
        for version in ('1.0', '2.0'):
            with patch.object(effective_environment.operations, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps({'prefix': '/runtime', 'packages': [['sdk', version]]}))):
                values.append(effective_environment.installed(['python3'], '.'))
        self.assertNotEqual(*values)

    def test_unusable_probe_never_claims_verified_environment(self):
        with patch.object(effective_environment.operations, 'run', return_value=SimpleNamespace(returncode=1, stdout='{}')):
            self.assertFalse(effective_environment.installed(['npm', 'test'], '.')['verified'])
