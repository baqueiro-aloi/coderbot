from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from release_readiness import verify


class ReadinessTests(unittest.TestCase):
    def args(self):
        return dict(image='sha256:actual', expected_image='sha256:actual', release_sha='a' * 40,
            expected_sha='a' * 40, state_before={'branch': 'task'}, state_after={'branch': 'task'})

    def test_liveness_without_functional_probes_is_not_verified(self):
        self.assertEqual(verify(**self.args(), probes=[])['status'], 'not_verified')

    def test_both_probes_required_and_failure_not_hidden(self):
        probes = [{'id': kind, 'kind': kind, 'argv': ['probe', kind], 'timeout': 10}
                  for kind in ('readiness', 'smoke')]
        self.assertEqual(verify(**self.args(), probes=probes,
            runner=Mock(return_value=SimpleNamespace(returncode=0)))['status'], 'pass')
        self.assertEqual(verify(**self.args(), probes=probes,
            runner=Mock(side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)]))['status'], 'fail')

    def test_wrong_image_and_lost_task_state_rejected(self):
        for change in ({'image': 'other'}, {'release_sha': 'b' * 40}, {'state_after': {'branch': 'lost'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(**{**self.args(), **change}, probes=[])
