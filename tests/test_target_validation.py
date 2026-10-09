import json
from pathlib import Path
import tempfile
import unittest

import target_validation


class TargetValidationTests(unittest.TestCase):
    def value(self):
        return {'version': 1, 'targets': [{'id': 'service', 'matrix': [
            {'capability': 'inference', 'route': '/v1/chat', 'auth': 'bearer', 'parameters': ['model', 'stream']},
            {'capability': 'tools', 'route': '/v1/chat', 'auth': 'bearer', 'parameters': ['tools']}],
            'fixtures': [{'path': 'fixtures/service.json', 'source': 'https://vendor.example.test/openapi'}]}]}

    def test_matrix_has_real_fixture_traceability(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); (root / 'fixtures').mkdir(); (root / 'fixtures/service.json').write_text('{}')
            self.assertEqual(target_validation.validate(self.value(), root)['targets'][0]['id'], 'service')

    def test_duplicate_capability_and_untraced_fixture_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); (root / 'fixtures').mkdir(); (root / 'fixtures/service.json').write_text('{}')
            for mutate in (
                lambda v: v['targets'][0]['matrix'].append(dict(v['targets'][0]['matrix'][0])),
                lambda v: v['targets'][0]['fixtures'][0].update(source='assumed'),
                lambda v: v['targets'][0]['matrix'][0].update(parameters='discarded')):
                value = self.value(); mutate(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    target_validation.validate(value, root)

    def test_invocation_rejects_duplicate_auth_wrong_api_and_dropped_parameters(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); (root / 'fixtures').mkdir(); (root / 'fixtures/service.json').write_text('{}')
            contract = target_validation.validate(self.value(), root)
            good = dict(route='/v1/chat', headers={'Authorization': 'Bearer synthetic'},
                        payload={'model': 'test', 'stream': False},
                        transport={'effective_route': '/v1/chat', 'isolation_id': 'task-a'})
            self.assertEqual(target_validation.invocation(contract, 'service', 'inference', **good)['parameters'], ['model', 'stream'])
            for change in (
                {'headers': {'Authorization': 'Bearer x', 'X-Api-Key': 'x'}},
                {'route': '/v0/chat'}, {'payload': {'model': 'test', 'internal': True}},
                {'transport': {'effective_route': '/v1/chat', 'isolation_id': ''}}):
                args = {**good, **change}
                with self.subTest(change=change), self.assertRaises(ValueError):
                    target_validation.invocation(contract, 'service', 'inference', **args)
