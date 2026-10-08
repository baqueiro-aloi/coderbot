from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import main


class BaseCheckoutSafetyTests(unittest.TestCase):
    def test_unknown_work_prevents_destructive_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'app').write_text('base')
            subprocess.run(['git', 'add', 'app'], cwd=repo, check=True)
            subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.test',
                            'commit', '-qm', 'base'], cwd=repo, check=True)
            (repo / 'app').write_text('human edit')
            (repo / 'secret.txt').write_text('synthetic-secret')
            with patch.object(main.config, 'REPO_PATH', repo), patch.object(main, '_git_quiet') as mutate:
                notes = main._reset_to_base_branch()
            mutate.assert_not_called()
            self.assertIn('preserved', ' '.join(notes))
            self.assertEqual((repo / 'app').read_text(), 'human edit')
            self.assertEqual((repo / 'secret.txt').read_text(), 'synthetic-secret')
