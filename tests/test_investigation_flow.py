"""Controller gates exercise direct and question-continuation entry points."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import main
from tests import test_integration_investigation as investigation_fixtures


class InvestigationFlowTests(unittest.TestCase):
    def test_invalid_report_uses_bounded_controller_correction(self):
        state = self.state()
        result = self.result({'version': 1, 'integrations': 'invalid'})
        with patch.object(main, 'save_state'), patch.object(main.checks, 'execute_plan') as execute:
            self.assertTrue(main.handle_result(state, result, 'EXPLORING'))
        execute.assert_not_called()
        self.assertEqual(state['state'], 'EXPLORING')
        self.assertEqual(state['investigation_round'], 1)
        self.assertNotIn('integration_inventory', state)

    def state(self):
        return {'state': 'EXPLORING', 'slug': 'task', 'branch': 'task', 'item': 'integrate service',
                'session_id': 'session'}

    def result(self, inventory=None):
        return SimpleNamespace(session_id='session', question=None, attachments=[],
            output='summary' if inventory is None else 'INTEGRATION_INVENTORY: ' + json.dumps(inventory))

    def test_missing_inventory_does_not_advance_either_exploration_path(self):
        for direct in (True, False):
            state = self.state()
            with self.subTest(direct=direct), patch.object(main, 'announce_milestone'), \
                 patch.object(main.agent_runner, 'run', return_value=self.result()), \
                 patch.object(main, 'handle_result', return_value=False), \
                 patch.object(main, '_undo_premature_work', return_value=''), \
                 patch.object(main, 'save_state'), patch.object(main, 'email'):
                if direct:
                    main.do_explore(state)
                else:
                    main._continue_exploring(state, self.result())
            self.assertEqual(state['state'], 'EXPLORING')
            self.assertIn('missing', state['exploration_feedback'].lower())

    def test_explicit_empty_inventory_advances(self):
        state = self.state()
        with patch.object(main, 'announce_milestone'), patch.object(main, 'save_state'), \
             patch.object(main, '_undo_premature_work', return_value=''):
            main._continue_exploring(state, self.result({'version': 1, 'integrations': []}))
        self.assertEqual(state['state'], 'PROPOSING')
        self.assertEqual(state['integration_inventory']['integrations'], [])

    def test_material_assumption_blocks_and_asks_exact_missing_information(self):
        value = investigation_fixtures.InvestigationTests().inventory()
        value['integrations'][0]['assumptions'] = [{'claim': 'Responses compatible', 'status': 'pending',
            'material': True, 'impact': 'route selection', 'next_action': 'provide endpoint docs'}]
        state = self.state()
        with patch.object(main, 'save_state'), patch.object(main, 'email') as email, \
             patch.object(main, '_undo_premature_work', return_value=''):
            main._continue_exploring(state, self.result(value))
        self.assertEqual(state['state'], 'WAIT_REPLY')
        self.assertEqual(state['return_state'], 'EXPLORING')
        self.assertIn('provide endpoint docs', email.call_args.args[2])

    def test_proposal_and_approval_cannot_bypass_missing_new_inventory(self):
        state = {**self.state(), 'state': 'PROPOSING', 'investigation_required': True}
        with patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.object(main.proposal_package, 'prepare') as prepare:
            main._send_proposal_review(state, 'proposal')
        prepare.assert_not_called()
        state['state'] = 'WAIT_APPROVAL'
        with patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.object(main.replanning, 'approve') as approve:
            main.do_approval_reply(state, 'approve')
        approve.assert_not_called()

    def test_invalid_inventory_requires_research_not_human_technical_repair(self):
        state = self.state()
        value = investigation_fixtures.InvestigationTests().inventory()
        value['integrations'][0]['sources'][0]['version'] = 'latest'
        with patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.object(main, '_undo_premature_work', return_value=''):
            main._continue_exploring(state, self.result(value))
        self.assertEqual(state['state'], 'EXPLORING')
        self.assertIn('version', state['exploration_feedback'])
