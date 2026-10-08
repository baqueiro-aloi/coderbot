"""Boot scripts must not expose synthetic clone credentials under bash tracing."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class BootSecretSafetyTests(unittest.TestCase):
    def test_boot_disables_xtrace_and_clone_has_no_secret_argv(self):
        for cloud in ('aws', 'azure'):
            text = (ROOT / f'deploy/{cloud}/instance/boot.sh').read_text()
            with self.subTest(cloud=cloud):
                self.assertIn('set +x', text)
                self.assertNotIn('set -eux', text)
                self.assertNotIn('https://x-access-token:$GH_TOKEN', text)
                clone = text[text.index('if [ ! -d "$TARGET_DIR/.git" ]; then'):]
                clone = clone[:clone.index('\nfi') + 3]
                with tempfile.TemporaryDirectory() as root:
                    root = Path(root)
                    (root / 'codebot.env').write_text('GH_TOKEN=synthetic-boot-secret\n')
                    binary = root / 'git'
                    binary.write_text('#!/bin/bash\n'
                        'printf "%s\\n" "$@" >> "$MNT/git-args"\n'
                        'case " $* " in *" clone "*) "$GIT_ASKPASS" Password > "$MNT/password";; esac\n')
                    binary.chmod(0o700)
                    code = 'set -x\nset +x\nset -euo pipefail\n' + clone
                    result = subprocess.run(['bash'], input=code, capture_output=True, text=True,
                        env=os.environ | {'MNT': str(root), 'TARGET_DIR': str(root / 'target'),
                            'TARGET_REPO': 'acme/test', 'PATH': str(root) + os.pathsep + os.environ['PATH']},
                        timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((root / 'password').read_text().strip(), 'synthetic-boot-secret')
                    self.assertNotIn('synthetic-boot-secret', (root / 'git-args').read_text())
                    self.assertNotIn('synthetic-boot-secret', result.stdout + result.stderr)
                    self.assertFalse(list(root.glob('codebot-askpass.*')))
