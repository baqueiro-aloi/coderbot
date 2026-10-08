import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import evidence


class NewmanEvidenceTests(unittest.TestCase):
    def test_timeout_preserves_diagnostics_not_approved_reports(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with patch.object(evidence, 'E2E_DIR', root), \
                 patch.object(evidence.config, 'DATA_DIR', root / 'data'), \
                 patch('evidence.operations.run', side_effect=subprocess.TimeoutExpired(['run'], 1)), \
                 patch('evidence._teardown_stack') as teardown, \
                 patch('evidence.snapshot', return_value='content'):
                self.assertEqual(evidence._record_newman_report(['a.postman_collection.json']), [])
            teardown.assert_called_once()
            self.assertTrue(list((root / 'data').rglob('diagnostic.json')))

    def test_success_requires_current_structured_report_and_nonzero_assertions(self):
        for exit_code, assertions, failures, expected in ((0, 1, [], True), (1, 1, ['bad'], False),
                                                        (0, 0, [], False), (0, 1, ['bad'], False)):
            with self.subTest(exit_code=exit_code, assertions=assertions, failures=failures), \
                 tempfile.TemporaryDirectory() as root:
                root = Path(root)
                results = root / 'test-results'
                results.mkdir()
                def run(cmd, **kwargs):
                    (results / 'report.html').write_text('report')
                    (results / 'report.json').write_text(json.dumps({'run': {
                        'stats': {'assertions': {'total': assertions, 'failed': len(failures), 'pending': 0}},
                        'failures': failures}}))
                    return subprocess.CompletedProcess(cmd, exit_code, 'done', '')
                with patch.object(evidence, 'E2E_DIR', root), \
                     patch.object(evidence.config, 'DATA_DIR', root / 'data'), \
                     patch('evidence.operations.run', side_effect=run), \
                     patch('evidence.snapshot', return_value='content'):
                    files = evidence._record_newman_report(['a.postman_collection.json'])
                self.assertEqual(bool(files), expected)

    def test_html_without_current_json_is_not_approved(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            results = root / 'test-results'
            results.mkdir()
            (results / 'old.json').write_text(json.dumps({'run': {'failures': [],
                'stats': {'assertions': {'total': 1, 'failed': 0, 'pending': 0}}}}))
            def run(cmd, **kwargs):
                (results / 'report.html').write_text('report')
                return subprocess.CompletedProcess(cmd, 0, '', '')
            with patch.object(evidence, 'E2E_DIR', root), \
                 patch.object(evidence.config, 'DATA_DIR', root / 'data'), \
                 patch('evidence.operations.run', side_effect=run), \
                 patch('evidence.snapshot', return_value='content'):
                self.assertEqual(evidence._record_newman_report(['a.postman_collection.json']), [])

    def test_overwritten_reports_are_detected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            results = root / 'test-results'
            results.mkdir()
            (results / 'report.html').write_text('old')
            (results / 'report.json').write_text('{}')
            def run(cmd, **kwargs):
                (results / 'report.html').write_text('new')
                (results / 'report.json').write_text(json.dumps({'run': {'failures': [],
                    'stats': {'assertions': {'total': 2, 'failed': 0, 'pending': 0}}}}))
                return subprocess.CompletedProcess(cmd, 0, '', '')
            with patch.object(evidence, 'E2E_DIR', root), \
                 patch.object(evidence.config, 'DATA_DIR', root / 'data'), \
                 patch('evidence.operations.run', side_effect=run), \
                 patch('evidence.snapshot', return_value='content'):
                self.assertEqual(evidence._record_newman_report(['a.postman_collection.json']),
                                 [results / 'report.html'])
