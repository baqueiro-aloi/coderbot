from pathlib import Path
import tempfile
import unittest

import integration_investigation as investigation


class InvestigationTests(unittest.TestCase):
    def inventory(self):
        return {'version': 1, 'integrations': [{'id': 'service', 'kind': 'external',
            'versions': {'declared': '1.2', 'installed': '1.2', 'deployment': '1.2'},
            'sources': [{'url': 'https://docs.example.test/v1.2/api', 'consulted_at': '2026-10-08',
                         'version': '1.2', 'evidence': 'POST /v1/messages uses x-api-key'}],
            'contract': {'method': 'POST', 'route': '/v1/messages', 'auth': 'x-api-key',
                'isolation': 'workspace', 'request': 'messages array', 'response': 'content array',
                'errors': ['401'], 'capabilities': ['messages']},
            'assumptions': [], 'checks': ['service:live']} ]}

    def test_complete_version_specific_inventory_is_valid(self):
        self.assertEqual(investigation.validate(self.inventory(), Path('/repo'))['integrations'][0]['id'], 'service')

    def test_wrong_version_and_unresolved_material_assumption_block_design(self):
        inventory = self.inventory()
        inventory['integrations'][0]['sources'][0]['version'] = 'latest'
        with self.assertRaisesRegex(ValueError, 'version'):
            investigation.validate(inventory, Path('/repo'))
        inventory = self.inventory()
        inventory['integrations'][0]['assumptions'] = [{'claim': 'Responses supported',
            'status': 'pending', 'material': True, 'impact': 'routing', 'next_action': 'inspect endpoint docs'}]
        result = investigation.validate(inventory, Path('/repo'))
        self.assertIn('Responses supported', investigation.blockers(result)[0])

    def test_internal_contract_requires_existing_implementation_and_consumer(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            value = self.inventory()
            integration = value['integrations'][0]
            integration['kind'] = 'internal'
            integration['implementation'] = ['handler.py']
            integration['consumers'] = ['client.py']
            with self.assertRaises(ValueError):
                investigation.validate(value, repo)
            (repo / 'handler.py').write_text('def handler(): return {"content": []}')
            (repo / 'client.py').write_text('handler()')
            self.assertEqual(investigation.validate(value, repo)['version'], 1)
            (repo / 'handler.py').unlink()
            (repo / 'handler.py').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                investigation.validate(value, repo)

    def test_duplicate_missing_contract_and_invalid_sources_rejected(self):
        for change in ('duplicate', 'route', 'source', 'date'):
            value = self.inventory()
            if change == 'duplicate':
                value['integrations'].append(value['integrations'][0])
            elif change == 'route':
                del value['integrations'][0]['contract']['route']
            elif change == 'source':
                value['integrations'][0]['sources'][0]['url'] = 'http://docs.example.test/'
            else:
                value['integrations'][0]['sources'][0]['consulted_at'] = 'someday'
            with self.subTest(change=change), self.assertRaises(ValueError):
                investigation.validate(value, Path('/repo'))

    def test_no_integration_is_explicit_not_inferred_from_missing_report(self):
        self.assertEqual(investigation.reported('ordinary summary'), None)
        self.assertEqual(investigation.reported('INTEGRATION_INVENTORY: {"version":1,"integrations":[]}'),
                         {'version': 1, 'integrations': []})
