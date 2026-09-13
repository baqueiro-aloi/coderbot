"""The task_source façade dispatches every backlog call to the configured backend."""
import sys
import unittest
from unittest.mock import MagicMock, patch

import config
import task_source


class Dispatch(unittest.TestCase):
    CALLS = [("list_pending_items", ()), ("claim_task", ("t", "id")),
             ("unclaim_task", ("t", None)), ("hold_task", ("t", "id")),
             ("unhold_task", ("t", None)), ("mark_done", ("t", "id")),
             ("ensure_item", ("t",)), ("note_pr", ("t", "id", "https://pr")),
             ("validate", ()), ("describe", ())]

    def check(self, source, module_name):
        backend = MagicMock()
        with patch.object(config, "TASK_SOURCE", source), \
             patch.dict(sys.modules, {module_name: backend}):
            for name, args in self.CALLS:
                getattr(task_source, name)(*args)
                target = getattr(backend, name)
                if name in ("claim_task", "unclaim_task", "hold_task", "unhold_task",
                            "mark_done"):
                    target.assert_called_once_with(args[0], item_id=args[1])
                else:
                    target.assert_called_once_with(*args)

    def test_gdoc(self):
        self.check("gdoc", "gdoc_client")

    def test_github(self):
        self.check("github", "github_projects_client")

    def test_unknown_source_raises(self):
        with patch.object(config, "TASK_SOURCE", "jira"):
            with self.assertRaisesRegex(RuntimeError, "CODEBOT_TASK_SOURCE.*gdoc, github"):
                task_source.list_pending_items()

    def test_normalize_is_shared(self):
        self.assertEqual(task_source.normalize("  A  b "), "a b")


if __name__ == "__main__":
    unittest.main()
