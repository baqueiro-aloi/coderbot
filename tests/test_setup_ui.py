"""Exercise the real Textual wizard without changing the repository's .env."""
import tempfile
import unittest
from pathlib import Path

from scripts.setup_env import EnvFile

try:
    from scripts.setup_ui import SetupApp
    from textual.widgets import Input, Static
except ImportError:
    SetupApp = None


@unittest.skipIf(SetupApp is None, "host Textual dependency not installed")
class Wizard(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_advanced_search_and_confirmed_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "project"
            repo.mkdir()
            (repo / ".git").mkdir()
            path = Path(tmp) / ".env"
            path.write_text("# preserve\nGH_TOKEN=secret\nCODEBOT_DOC_ID=doc-id\n"
                            "CODEBOT_USER_EMAIL=user@example.org\n"
                            "CLAUDE_CODE_OAUTH_TOKEN=secret\nUNKNOWN_EXTRA=kept\n")
            app = SetupApp(EnvFile(path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#setting-CODEBOT_REPO_PATH", Input).value = str(repo)
                for step in range(5):
                    for _attempt in range(3):
                        await pilot.click("#next")
                        await pilot.pause()
                        if app.page == step + 1:
                            break
                    self.assertEqual(app.page, step + 1,
                                     f"stuck leaving {step}: {app.query_one('#message', Static).render()}")
                self.assertEqual(app.page, 5, str(app.query_one("#message", Static).render()))
                app.query_one("#search", Input).value = "CODEBOT_GH_LABEL_PREFIX"
                await pilot.pause()
                app.query_one("#setting-CODEBOT_GH_LABEL_PREFIX", Input).value = "robot"
                await pilot.click("#next")
                await pilot.pause()
                self.assertEqual(app.page, 6)
                self.assertIn("GH_TOKEN: (set)", app.env.preview({"GH_TOKEN": "different"}))
                await pilot.click("#save")
                await pilot.pause()
            self.assertIn("CODEBOT_GH_LABEL_PREFIX=robot\n", path.read_text())
            self.assertIn("UNKNOWN_EXTRA=kept\n", path.read_text())
            self.assertIn("GH_TOKEN=secret\n", path.read_text())
            self.assertIn("# preserve\n", path.read_text())


if __name__ == "__main__":
    unittest.main()
