"""A successful process is not necessarily an executed test suite."""
import unittest

from check_plan import parse
from check_results import parse_output


class CheckEvidenceTests(unittest.TestCase):
    def test_zero_and_all_skipped_never_pass(self):
        for reporter, text, expected in (
            ('unittest', 'Ran 0 tests in 0.001s\nOK', 'not_run'),
            ('unittest', 'Ran 3 tests in 0.001s\nOK (skipped=3)', 'skipped'),
            ('node', '# tests 0\n# pass 0\n# fail 0\n# skipped 0', 'not_run'),
            ('junit', '<testsuite tests="0"/>', 'not_run'),
            ('junit', '<testsuite><testcase name="a"><skipped/></testcase></testsuite>', 'skipped'),
            ('playwright', '3 skipped', 'skipped'),
            ('json', '{"failures":{},"tests":0,"skipped":0}', 'not_run')):
            with self.subTest(reporter=reporter, text=text):
                self.assertEqual(parse_output(text, 0, reporter)['status'], expected)

    def test_partial_skips_preserved_not_passed(self):
        result = parse_output('Ran 3 tests in 0.1s\nOK (skipped=1)', 0, 'unittest')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['tests'], 3)
        self.assertEqual(result['executed'], 2)
        self.assertEqual(result['skipped'], 1)

    def test_success_requires_recognized_test_result(self):
        for reporter in ('unittest', 'node', 'junit', 'json', 'playwright'):
            with self.subTest(reporter=reporter):
                self.assertEqual(parse_output('everything worked', 0, reporter)['status'], 'unknown')
        self.assertEqual(parse_output('build succeeded', 0, 'text')['status'], 'pass')

    def test_positive_known_results_pass(self):
        for reporter, text in (
            ('unittest', 'Ran 2 tests in 0.1s\nOK'),
            ('node', '# tests 2\n# pass 2\n# fail 0\n# skipped 0\n# todo 0'),
            ('junit', '<testsuite tests="1"><testcase name="a"/></testsuite>'),
            ('json', '{"failures":{},"tests":1,"skipped":0}'),
            ('playwright', '2 passed (1s)')):
            with self.subTest(reporter=reporter):
                self.assertEqual(parse_output(text, 0, reporter)['status'], 'pass')

    def test_contradictory_results_never_pass(self):
        for reporter, text in (
            ('unittest', 'Ran 1 test in 0.1s\nFAILED (failures=1)'),
            ('node', '# tests 2\n# pass 1\n# fail 0\n# skipped 0\n# todo 0'),
            ('junit', '<testsuite tests="3"><testcase name="a"/></testsuite>'),
            ('json', '{"failures":{"a":"bad"},"tests":1,"skipped":0}'),
            ('playwright', '1 failed\n1 passed')):
            with self.subTest(reporter=reporter):
                self.assertNotEqual(parse_output(text, 0, reporter)['status'], 'pass')

    def test_version_two_contract_has_explicit_provenance_and_v1_is_legacy(self):
        check = parse({'version': 2, 'checks': [{'id': 'live', 'argv': ['test'],
            'kind': 'upstream', 'requirements': ['r1'], 'scenarios': ['r1:s1'],
            'external_dependencies': ['service'], 'env_keys': ['SERVICE_KEY'],
            'max_age_seconds': 60}]})[0]
        self.assertEqual(check.kind, 'upstream')
        self.assertEqual(check.requirements, ['r1'])
        self.assertEqual(check.max_age_seconds, 60)
        self.assertEqual(check.contract_version, 2)
        self.assertEqual(parse({'version': 1, 'checks': [{'id': 'old', 'argv': ['test']}]})[0].contract_version, 1)

    def test_invalid_provenance_rejected(self):
        for fields in ({'kind': 'imaginary'}, {'max_age_seconds': -1},
                       {'requirements': [None]}, {'external_dependencies': 'service'},
                       {'kind': 'upstream', 'max_age_seconds': None}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                parse({'version': 2, 'checks': [{'id': 'x', 'argv': ['test'], **fields}]})
