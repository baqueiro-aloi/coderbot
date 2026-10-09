import unittest

import prompts
import agent_runner


class AutonomyBoundaryTests(unittest.TestCase):
    def test_runner_and_environment_forbid_unapproved_external_escalation(self):
        environment, runner = prompts.ENVIRONMENT, agent_runner._language_prompt('')
        self.assertIn('IAM changes', environment)
        self.assertIn('separate authorization', ' '.join(environment.split()))
        self.assertIn('deploy', environment)
        self.assertIn('Never kill unknown processes', runner)
        self.assertIn('never authorize merge, IAM or spending', runner)
