import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import remote_review


class RemoteReviewTests(unittest.TestCase):
    def test_provider_contract_and_atomic_merge_condition(self):
        sha = 'a' * 40
        with patch.object(remote_review.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({'state': 'OPEN', 'headRefOid': sha}))) as run:
            value = remote_review.head('pr', '.')
        self.assertIn('state,headRefOid', run.call_args.args[0])
        self.assertTrue(remote_review.reviewed({'reviewed_remote_sha': sha}, value))
        self.assertFalse(remote_review.reviewed({}, value))
        self.assertFalse(remote_review.reviewed({'reviewed_remote_sha': 'b' * 40}, value))
        self.assertEqual(remote_review.merge_argv('pr', sha)[-2:], ['--match-head-commit', sha])

    def test_invalid_payload_and_failed_query_cannot_prove_head(self):
        for value in ({}, [], {'state': 'OPEN', 'headRefOid': 'bad'}):
            with patch.object(remote_review.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps(value))), self.assertRaises(ValueError):
                remote_review.head('pr', '.')
        with self.assertRaises(ValueError):
            remote_review.merge_argv('pr', None)

    def test_force_thread_override_cannot_bypass_changed_remote_head(self):
        import main
        state = {'state': 'WAIT_MERGE', 'pr_url': 'pr', 'reviewed_remote_sha': 'a' * 40}
        with patch.object(main.agent_runner, 'run', return_value=SimpleNamespace(output='{"action":"merge","force":true}')), \
             patch.object(main, '_conversation_delivery_blocked', return_value=False), \
             patch.object(main, '_pr_merge_state', return_value=('OPEN', 'MERGEABLE')), \
             patch.object(remote_review, 'head', return_value={'state': 'OPEN', 'headRefOid': 'b' * 40}), \
             patch.object(main, 'save_state'), patch.object(main, 'email'), \
             patch.object(main.subprocess, 'run') as merge:
            main.do_merge_reply(state, 'merge anyway')
        merge.assert_not_called()
        self.assertEqual(state['state'], 'WAIT_REVIEW')
        self.assertNotIn('reviewed_remote_sha', state)

    def test_provider_race_rejection_preserves_task_and_requires_retry(self):
        import main
        state = {'state': 'WAIT_MERGE', 'pr_url': 'pr', 'reviewed_remote_sha': 'a' * 40}
        with patch.object(main.agent_runner, 'run', return_value=SimpleNamespace(output='{"action":"merge","force":true}')), \
             patch.object(main, '_conversation_delivery_blocked', return_value=False), \
             patch.object(main, '_pr_merge_state', return_value=('OPEN', 'MERGEABLE')), \
             patch.object(remote_review, 'head', return_value={'state': 'OPEN', 'headRefOid': 'a' * 40}), \
             patch.object(main, 'email'), patch.object(main, '_finish_task') as finish, \
             patch.object(main.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='head changed')) as merge:
            main.do_merge_reply(state, 'merge anyway')
        self.assertEqual(merge.call_args.args[0][-2:], ['--match-head-commit', 'a' * 40])
        finish.assert_not_called()
        self.assertEqual(state['state'], 'WAIT_MERGE')
