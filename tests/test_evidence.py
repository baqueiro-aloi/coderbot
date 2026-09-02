"""Regression tests for evidence collection input and recording wiring."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import evidence


class EvidenceTests(unittest.TestCase):
    def test_reported_specs_strip_markdown_code_delimiters(self):
        output = "summary\nE2E_SPEC: `dynamic-page-title.spec.ts`\n"

        self.assertEqual(evidence.reported_specs(output), ["dynamic-page-title.spec.ts"])

    def test_recorder_normalizes_persisted_markdown_spec_name(self):
        with patch("evidence._record_playwright_video", return_value=[]) as record:
            evidence.record_evidence(["dynamic-page-title.spec.ts`"], "playwright")

        self.assertEqual(record.call_args.args[0], ["dynamic-page-title.spec.ts"])

    def test_playwright_recorder_uses_target_video_environment_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            e2e_dir = Path(tmp)
            with patch.object(evidence, "E2E_DIR", e2e_dir), \
                 patch("evidence.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                evidence._record_playwright_video(["dynamic-page-title.spec.ts"])

        # @evidence demo test first, then the full spec when no clip appeared.
        commands = [c.args[0] for c in run.call_args_list]
        self.assertEqual(commands, [
            ["./run.sh", "dynamic-page-title.spec.ts", "--grep", "@evidence"],
            ["./run.sh", "dynamic-page-title.spec.ts"]])
        self.assertEqual(run.call_args.kwargs["env"]["PICA_E2E_VIDEO"], "on")
        self.assertEqual(run.call_args.kwargs["env"]["PW_VIDEO"], "on")

    def test_evidence_clip_stops_after_demo_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            e2e_dir = Path(tmp)
            results = e2e_dir / "test-results"
            results.mkdir()

            def fake_run(cmd, **kwargs):
                (results / "demo.webm").write_bytes(b"video")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(evidence, "E2E_DIR", e2e_dir), \
                 patch("evidence.subprocess.run", side_effect=fake_run) as run, \
                 patch("evidence._stitch_to_mp4", return_value=None):
                clips = evidence._record_playwright_video(["a.spec.ts"])

        self.assertEqual(run.call_count, 1)
        self.assertEqual([c.name for c in clips], ["demo.webm"])

    def test_suite_timeout_tears_down_stack_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            e2e_dir = Path(tmp)
            (e2e_dir / "docker-compose.e2e.yaml").write_text("services: {}\n")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                if cmd[0] == "./run.sh":
                    raise subprocess.TimeoutExpired(cmd, 1, output="partial", stderr="")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(evidence, "E2E_DIR", e2e_dir), \
                 patch.object(evidence.config, "E2E_TIMEOUT_SECONDS", 1), \
                 patch("evidence.subprocess.run", side_effect=fake_run):
                passed, output = evidence.run_suite()

        self.assertFalse(passed)
        self.assertIn("TIMED OUT", output)
        self.assertIn("partial", output)
        self.assertEqual(calls[1][:4], ["docker", "compose", "-f", "docker-compose.e2e.yaml"])

    def test_teardown_is_noop_without_compose_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(evidence, "E2E_DIR", Path(tmp)), \
             patch("evidence.subprocess.run") as run:
            evidence._teardown_stack()
        run.assert_not_called()

    def test_stitched_video_lands_in_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            clip = Path(tmp) / "a.webm"
            clip.write_bytes(b"video")

            def fake_ffmpeg(cmd, **kwargs):
                Path(cmd[-1]).write_bytes(b"mp4")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(evidence.config, "DATA_DIR", data_dir), \
                 patch("evidence.shutil.which", return_value="/usr/bin/ffmpeg"), \
                 patch("evidence.subprocess.run", side_effect=fake_ffmpeg):
                out = evidence._stitch_to_mp4([clip])

            self.assertEqual(out, data_dir / "evidence.mp4")
            self.assertEqual(out.read_bytes(), b"mp4")

    def test_agent_playwright_clips_are_stitched(self):
        with tempfile.TemporaryDirectory() as tmp:
            clips = [Path(tmp) / "first.webm", Path(tmp) / "second.webm"]
            for clip in clips:
                clip.write_bytes(b"video")
            expected = Path(tmp) / "evidence.mp4"
            with patch("evidence._stitch_to_mp4", return_value=expected) as stitch:
                self.assertEqual(evidence.stitch_playwright_clips(clips), expected)

        self.assertEqual(stitch.call_args.args[0], clips)


if __name__ == "__main__":
    unittest.main()
