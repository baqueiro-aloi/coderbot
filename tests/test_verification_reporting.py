import unittest
import verification_reporting as reporting


class VerificationReportingTests(unittest.TestCase):
    def test_omissions_and_execution_separate_without_deployment_claim(self):
        state = {'final_check_report': {'checks': [
            {'check': 'local', 'kind': 'contract', 'status': 'pass', 'gate': {'status': 'pass'}},
            {'check': 'remote', 'kind': 'upstream', 'status': 'not_run', 'gate': {'status': 'accepted_exception'},
             'exception': {'message_id': 'm', 'reason': 'no key'}}]}}
        text = reporting.summary(state)
        self.assertIn('not_run', text)
        self.assertIn('Accepted omission: remote', text)
        self.assertIn('no deployment receipt', text)
        self.assertIn('Implementation: code/commit state is not validation evidence.', text)
        self.assertIn('| remote | upstream | not_run', text)

    def test_update_preserves_human_prose_before_and_after_section(self):
        original = 'Human opening\n' + reporting.START + '\nold\n' + reporting.END + '\nHuman closing'
        updated = reporting.update_body(original, {})
        self.assertTrue(updated.startswith('Human opening\n'))
        self.assertTrue(updated.endswith('\nHuman closing'))
        self.assertEqual(reporting.update_body(updated, {}), updated)

    def test_malformed_markers_do_not_overwrite_human_work(self):
        with self.assertRaises(ValueError):
            reporting.update_body('human text ' + reporting.START, {})
