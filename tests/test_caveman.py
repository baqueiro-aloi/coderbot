"""Exact opt-in and harness isolation for the managed Caveman plugin."""
import ast
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_runner
import claude_runner
import config
from scripts.setup_catalog import BY_KEY, validate_value
from scripts.setup import fields_for


class CavemanTests(unittest.TestCase):
    def test_runtime_opt_in_is_exact(self):
        # Evaluate the real assignment without re-importing config's durable state.
        tree = ast.parse(Path(config.__file__).read_text())
        expr = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "USE_CAVEMAN"
                            for t in n.targets))
        code = compile(ast.Expression(expr), config.__file__, "eval")
        for value in (None, "", "true", "TRUE", "True", "false", "yes", "1",
                      " true", "true ", "anything"):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True):
                if value is not None:
                    os.environ["USE_CAVEMAN"] = value
                self.assertEqual(eval(code, {"os": os}), value == "true")

    def test_setting_is_available_for_both_agents_and_accepts_disabled_values(self):
        setting = BY_KEY["USE_CAVEMAN"]
        self.assertEqual(setting.default, "false")
        for agent in ("claude", "opencode"):
            self.assertIn(setting, fields_for("Agent", {"CODEBOT_AGENT": agent}))
        for value in ("true", "false", "", "TRUE", "yes", "1", " true ", "other"):
            self.assertIsNone(validate_value(setting, value))

    def test_claude_new_resume_and_utility_plugin_wiring(self):
        response = subprocess.CompletedProcess(
            [], 0, json.dumps({"session_id": "s", "result": "done"}), "")
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.object(config, "USE_CAVEMAN", enabled), \
                 patch.object(claude_runner, "_run", return_value=response) as run:
                claude_runner.run("start")
                claude_runner.resume("s", "continue")
                claude_runner.run("classify", contract=False)
                for call in run.call_args_list[:2]:
                    self.assertEqual(str(config.CAVEMAN_PLUGIN_DIR) in call.args[0], enabled)
                self.assertNotIn("--plugin-dir", run.call_args_list[2].args[0])

    def test_claude_environment_overrides_inherited_default(self):
        for enabled, tools, expected in ((True, False, "caveman"), (False, False, "off"),
                                          (True, True, "off")):
            with self.subTest(enabled=enabled, tools=tools), \
                 patch.object(config, "USE_CAVEMAN", enabled), \
                 patch.dict(os.environ, {"CAVEMAN_DEFAULT_MODE": "ultracave"}), \
                 patch.object(claude_runner.operations, "run") as run:
                claude_runner._run(["claude", *(["--tools", ""] if tools else [])])
                self.assertEqual(run.call_args.kwargs["env"]["CAVEMAN_DEFAULT_MODE"], expected)
                self.assertEqual(os.environ["CAVEMAN_DEFAULT_MODE"], "ultracave")

    def test_opencode_plugin_skills_command_and_isolation(self):
        plugin = str(config.CAVEMAN_PLUGIN_DIR / "src/plugins/opencode")
        skills = str(config.CAVEMAN_PLUGIN_DIR / "skills")
        for enabled in (False, True):
            for role in ("coding", "utility", "conversation"):
                with self.subTest(enabled=enabled, role=role), \
                     patch.object(config, "USE_CAVEMAN", enabled), \
                     patch.dict(os.environ, {"OPENCODE_CONFIG_CONTENT": "{}",
                                             "CAVEMAN_DEFAULT_MODE": "ultracave"}):
                    utility = agent_runner._utility.set(role == "utility")
                    lateral = agent_runner._lateral.set(role == "conversation")
                    try:
                        env = agent_runner._opencode_environment()
                    finally:
                        agent_runner._utility.reset(utility)
                        agent_runner._lateral.reset(lateral)
                    inline = json.loads(env["OPENCODE_CONFIG_CONTENT"])
                    active = enabled and role == "coding"
                    self.assertEqual(plugin in inline["plugin"], active)
                    self.assertEqual(skills in inline["skills"]["paths"], active)
                    self.assertEqual("caveman" in inline.get("command", {}), active)
                    self.assertEqual(env["CAVEMAN_DEFAULT_MODE"], "caveman" if active else "off")
                    if role == "conversation":
                        self.assertEqual(inline["permission"], {"*": "deny"})

    def test_opencode_merges_without_duplicating_managed_paths(self):
        plugin = str(config.CAVEMAN_PLUGIN_DIR / "src/plugins/opencode")
        skills = str(config.CAVEMAN_PLUGIN_DIR / "skills")
        supplied = {"plugin": ["custom-plugin", plugin],
                    "skills": {"paths": ["/custom/skills", skills]},
                    "command": {"custom": {"template": "keep"}}}
        with patch.object(config, "USE_CAVEMAN", True), \
             patch.dict(os.environ, {"OPENCODE_CONFIG_CONTENT": json.dumps(supplied)}):
            inline = json.loads(agent_runner._opencode_environment()["OPENCODE_CONFIG_CONTENT"])
        self.assertEqual(inline["plugin"].count(plugin), 1)
        self.assertEqual(inline["skills"]["paths"].count(skills), 1)
        self.assertIn("custom-plugin", inline["plugin"])
        self.assertIn("/custom/skills", inline["skills"]["paths"])
        self.assertEqual(inline["command"]["custom"], {"template": "keep"})


if __name__ == "__main__":
    unittest.main()
