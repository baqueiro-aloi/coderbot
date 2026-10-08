import copy
import unittest

import phase_checkpoint


class CheckpointPolicyTests(unittest.TestCase):
    def test_external_decisions_invalidate_same_prompt_replay(self):
        state = {'state': 'EXPLORING'}
        before = phase_checkpoint.key(state, 'same prompt')
        for field, value in [('integration_inventory', {'version': 1, 'integrations': []}),
            ('validation_overrides', [{'checks': {'live': 'scope'}}]),
            ('external_authorizations', [{'request_identity': 'authorized'}]),
            ('reviewed_remote_sha', 'a' * 40), ('verification_guidance', 'updated endpoint')]:
            with self.subTest(field=field):
                changed = copy.deepcopy(state)
                changed[field] = value
                self.assertNotEqual(before, phase_checkpoint.key(changed, 'same prompt'))

    def test_administrative_state_does_not_invalidate_policy_identity(self):
        state = {'state': 'EXPLORING', 'validation_overrides': [{'checks': {'live': 'scope'}}]}
        self.assertEqual(phase_checkpoint.key(state, 'prompt'), phase_checkpoint.key(
            {**state, 'last_ping': 123, 'session_id': 'new', 'question_rounds': 2}, 'prompt'))
