import json
from pathlib import Path
import tempfile
import unittest
import sys
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main
import task_phases


class TaskPhaseTests(unittest.TestCase):
    def test_phase_ownership_is_explicit_and_conflicts_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] Implement\n- [ ] [codebot:approval] Decide\n"
                            "- [ ] [codebot:verification] Reconcile\n- [ ] [codebot:final-checks] Run\n")
            plan = task_phases.inspect(root, "task")
            self.assertEqual(plan["implementation"], ["Implement"])
            self.assertEqual(len(plan["approval"]), 1)
            self.assertEqual(len(plan["verification"]), 1)
            path.write_text("- [ ] [codebot:approval] [codebot:final-checks] Invalid\n")
            with self.assertRaises(ValueError):
                task_phases.inspect(root, "task")

    def test_approval_and_new_tasks_pause_instead_of_returning_to_work(self):
        for task in ("[codebot:approval] Approve", "New ordinary task"):
            with self.subTest(task=task), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                path.write_text("- [x] Implement\n- [ ] " + task + "\n")
                state = {"state": "VERIFYING", "slug": "task", "item": "task", "session_id": "sid"}
                if task == "New ordinary task":
                    state["verified_task_inventory"] = ["Implement"]
                with patch.object(main.config, "REPO_PATH", Path(root)), patch.object(main, "save_state"), \
                     patch.object(main, "email") as email, patch.object(main.agent_runner, "resume") as agent:
                    main.do_verify(state)
                self.assertEqual(state["state"], "WAIT_REPLY")
                self.assertEqual(state["return_state"], "VERIFYING")
                self.assertNotIn("implementation_return_round", state)
                agent.assert_not_called()
                email.assert_called_once()

    def test_agent_cannot_expand_scope_during_implementation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] Implement\n- [ ] Approve again\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task",
                     "approved_task_inventory": ["Implement"]}
            with patch.object(main.config, "REPO_PATH", Path(root)), patch.object(main, "save_state"), \
                 patch.object(main, "email"), patch.object(main, "_scrub_evidence_from_repo") as scrub:
                main._complete_implementation(state, SimpleNamespace(output="done"))
            self.assertEqual(state["state"], "WAIT_REPLY")
            self.assertEqual(state["verification_blocker"]["kind"], "scope drift")
            scrub.assert_not_called()

    def test_approved_implementation_proceeds_to_evidence_reconciliation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            pending = "- [x] Implement\n- [ ] [codebot:verification] Reconcile integrated demo\n"
            path.write_text(pending)
            application = Path(root) / "application.py"
            application.write_text("existing implementation")
            inventory = task_phases.inventory(root, "task")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task",
                     "session_id": "sid", "approved_task_inventory": inventory}
            def commands(argv):
                if argv[1] == "validate":
                    return "valid"
                progress = task_phases.inspect(root, "task")
                remaining = progress["total"] - progress["complete"]
                return json.dumps({"state": "ready" if remaining else "all_done", "progress": {
                    "total": progress["total"], "complete": progress["complete"], "remaining": remaining}})
            def reconcile(session, prompt):
                self.assertEqual(session, "sid")
                self.assertIn("Reconcile integrated demo", prompt)
                self.assertIn("Never credit checks, reviews or demos", prompt)
                self.assertIn("Separate historical", prompt)
                path.write_text(pending.replace("- [ ]", "- [x]"))
                return SimpleNamespace(output='QUALITY_GATE: {"status":"pass",'
                    '"commands":["demo: pass"],"openspec":"pass","tasks":"2/2"}')
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "_run_checked", side_effect=commands), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "handle_result", return_value=False), \
                 patch.object(main, "content_snapshot", return_value="integrated"), \
                 patch.object(main, "trail"), patch.object(main, "announce_milestone"), \
                 patch.object(main, "save_state"), patch.object(main, "email") as email, \
                 patch.object(main.agent_runner, "resume", side_effect=reconcile) as agent:
                main._complete_implementation(state, SimpleNamespace(output="Done", attachments=[]))
                self.assertEqual(state["state"], "VERIFYING")
                self.assertEqual(path.read_text(), pending)
                self.assertEqual(state["verified_task_inventory"], inventory)
                main.do_verify(state)
            agent.assert_called_once()
            email.assert_not_called()
            self.assertEqual(state["state"], "INTERNAL_REVIEW")
            self.assertEqual(state["quality_report"]["tasks"], "2/2")
            self.assertEqual(application.read_text(), "existing implementation")

    def test_missing_evidence_blocks_after_verifier_runs_without_false_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            pending = "- [x] Implement\n- [ ] [codebot:verification] Reconcile new demo\n"
            path.write_text(pending)
            state = {"state": "VERIFYING", "slug": "task", "item": "task", "session_id": "sid",
                     "verification_guidance": "Verify existing implementation",
                     "quality_controller_validated": True, "quality_snapshot": "same",
                     "quality_report": {"status": "pass"}}
            result = SimpleNamespace(output='Missing demo recording for the integrated commit.\n'
                'QUALITY_GATE: {"status":"pass","commands":["old checks: pass"],'
                '"openspec":"pass","tasks":"2/2"}')
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "save_state"), patch.object(main, "email") as email, \
                 patch.object(main, "handle_result", return_value=False), \
                 patch.object(main, "content_snapshot", return_value="same"), \
                 patch.object(main, "_run_checked") as commands, \
                 patch.object(main, "_advance_verified") as advance, \
                 patch.object(main.agent_runner, "resume", return_value=result) as agent:
                main.do_verify(state)
            agent.assert_called_once()
            commands.assert_not_called()
            advance.assert_not_called()
            email.assert_called_once()
            self.assertEqual(state["state"], "WAIT_REPLY")
            self.assertEqual(state["return_state"], "VERIFYING")
            self.assertEqual(state["verification_blocker"]["kind"], "verification evidence")
            self.assertIn("Missing demo recording", state["pending_question"])
            self.assertIn("No new spec approval", state["pending_question"])
            self.assertNotIn("implementation_return_round", state)
            self.assertEqual(path.read_text(), pending)

    def test_pending_approval_still_blocks_completed_implementation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] Implement\n- [ ] [codebot:approval] Approve\n"
                            "- [ ] [codebot:verification] Reconcile\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                     "progress": {"total": 3, "complete": 1, "remaining": 2}})), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "save_state"), patch.object(main, "email"), \
                 patch.object(main, "announce_milestone") as announce:
                main._complete_implementation(state, SimpleNamespace(output="Done", attachments=[]))
            self.assertEqual(state["state"], "WAIT_REPLY")
            self.assertEqual(state["verification_blocker"]["kind"], "approval")
            announce.assert_not_called()

    def test_controller_unknown_check_cannot_be_overridden_by_agent_pass(self):
        state = {"state": "VERIFYING", "slug": "task", "item": "task",
                 "focused_check_results": [{"check": "contracts", "status": "unknown", "exit_code": 137}]}
        output = 'CHECK_PLAN: {"version":1,"checks":[{"id":"contracts","argv":["bash","checks.sh"]}]}\n'
        output += 'QUALITY_GATE: {"status":"pass","commands":["focused: pass"],"openspec":"pass","tasks":"1/1"}'
        with patch.object(main, "_verify_preflight", return_value=False), \
             patch.object(main, "handle_result", return_value=False), patch.object(main, "save_state"), \
             patch.object(main, "email"), patch.object(main, "_run_checked") as commands:
            main._complete_verify(state, SimpleNamespace(output=output))
        self.assertEqual(state["state"], "WAIT_REPLY")
        self.assertEqual(state["verification_blocker"]["kind"], "check infrastructure")
        self.assertNotIn("quality_report", state)
        commands.assert_not_called()

    def test_clean_review_is_reused_only_on_exact_snapshot(self):
        for snapshot, expected in (("same", "E2E"), ("changed", "INTERNAL_REVIEW")):
            with self.subTest(snapshot=snapshot), tempfile.TemporaryDirectory() as root:
                state = {"state": "VERIFYING", "slug": "task", "item": "task", "reviewed_snapshot": "same",
                         "internal_review_report": {"status": "pass", "critical": 0, "important": 0}}
                output = 'QUALITY_GATE: {"status":"pass","commands":["focused: pass"],"openspec":"pass","tasks":"1/1"}'
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                     patch.object(main, "content_snapshot", return_value=snapshot), \
                     patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "all_done",
                         "progress": {"total": 1, "complete": 1, "remaining": 0}})]):
                    main._complete_verify(state, SimpleNamespace(output=output))
                self.assertEqual(state["state"], expected)

    def test_agent_counts_cannot_disagree_with_actual_checklist(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] Implement\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            output = 'QUALITY_GATE: {"status":"pass","commands":["focused: pass"],"openspec":"pass","tasks":"45/45"}'
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "_gate_failed") as gate, \
                 patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "all_done",
                     "progress": {"total": 1, "complete": 1, "remaining": 0}})]):
                main._complete_verify(state, SimpleNamespace(output=output))
            self.assertEqual(state["state"], "VERIFYING")
            self.assertNotIn("quality_report", state)
            self.assertIn("counts", gate.call_args.args[3])

    def test_implementation_can_defer_only_explicit_controller_tasks(self):
        for deterministic in (False, True):
            with self.subTest(deterministic=deterministic), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                path.write_text("- [x] 1. Implementation\n- [ ] 2. [codebot:final-checks] Run suite\n")
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main.config, "DETERMINISTIC_CHECKS", deterministic), \
                     patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                         "progress": {"total": 2, "complete": 1, "remaining": 1}})), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), patch.object(main, "trail"), \
                     patch.object(main, "_enter_stuck") as stuck, patch.object(main, "announce_milestone") as announce:
                    main._complete_implementation(state, SimpleNamespace(output="Done", attachments=[]))
                if deterministic:
                    self.assertEqual(state["state"], "VERIFYING")
                    announce.assert_called_once()
                    stuck.assert_not_called()
                else:
                    stuck.assert_called_once()
                    announce.assert_not_called()

    def test_partial_turns_in_both_paths_preserve_evidence_and_only_final_turn_announces(self):
        for via_reply in (False, True):
            with self.subTest(via_reply=via_reply), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                path.write_text("- [x] 1. First change\n- [ ] 2. Second change\n")
                evidence = Path(root) / "result.txt"
                evidence.write_text("focused checks passed")
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task",
                         "branch": "feature", "session_id": "session"}
                partial = SimpleNamespace(output="First change done\nE2E_SPEC: first.spec.ts",
                                          attachments=[str(evidence)])
                complete = SimpleNamespace(output="Second change done\nE2E_SPEC: second.spec.ts",
                                           attachments=[])
                saved = []
                def instructions(*args):
                    progress = task_phases.inspect(root, "task")
                    remaining = progress["total"] - progress["complete"]
                    return json.dumps({"state": "ready" if remaining else "all_done", "progress": {
                        "total": progress["total"], "complete": progress["complete"], "remaining": remaining}})
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main, "_run_checked", side_effect=instructions), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                     patch.object(main, "content_snapshot", return_value="snapshot"), \
                     patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                     patch.object(main, "save_state", side_effect=lambda s: saved.append(json.loads(json.dumps(s)))), \
                     patch.object(main, "announce_milestone") as announce, \
                     patch.object(main.agent_runner, "resume", side_effect=[partial, complete]) as resume:
                    if via_reply:
                        main._continue_implementing(state, partial)
                    else:
                        main.do_implement(state)
                    self.assertEqual(state["state"], "IMPLEMENTING")
                    self.assertEqual(state["implementation_turn"], 1)
                    announce.assert_not_called()
                    self.assertEqual(state["implementation_attachments"], [str(evidence)])
                    state = saved[-1]  # restart resumes the saved continuation
                    path.write_text("- [x] 1. First change\n- [x] 2. Second change\n")
                    if via_reply:
                        main._continue_implementing(state, complete)
                    else:
                        main.do_implement(state)
                        self.assertIn("Implementation continuation: 1", resume.call_args.args[1])
                        self.assertNotEqual(resume.call_args_list[0].args[1], resume.call_args.args[1])
                    self.assertEqual(state["state"], "VERIFYING")
                    self.assertEqual(len(state["e2e_specs"]), 2)
                    announce.assert_called_once()

    def test_missing_empty_or_inconsistent_plan_never_advances(self):
        for content, progress in ((None, {}), ("No tasks", {}),
                ("- [ ] 1. Pending\n", {"total": 1, "complete": 1, "remaining": 0})):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "openspec/changes/task/tasks.md"
                path.parent.mkdir(parents=True)
                if content is not None:
                    path.write_text(content)
                state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
                with patch.object(main.config, "REPO_PATH", Path(root)), \
                     patch.object(main, "_run_checked", return_value=json.dumps({"state": "all_done", "progress": progress})), \
                     patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                     patch.object(main, "_enter_stuck") as stuck, patch.object(main, "announce_milestone") as announce:
                    main._complete_implementation(state, SimpleNamespace(output="Finished", attachments=[]))
                stuck.assert_called_once()
                announce.assert_not_called()
                self.assertNotEqual(state["state"], "VERIFYING")

    def test_no_progress_pauses_but_partial_repository_changes_reset_counter(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Large change\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task"}
            result = SimpleNamespace(output="Still working", attachments=[])
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "QUALITY_GATE_MAX_ROUNDS", 2), \
                 patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                     "progress": {"total": 1, "complete": 0, "remaining": 1}})), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "content_snapshot", side_effect=["a", "a", "b", "b", "b"]), \
                 patch.object(main, "save_state"), patch.object(main, "email") as email, \
                 patch.object(main.diagnostics, "report", return_value=Path(root) / "report.txt"):
                for _ in range(3):
                    main._complete_implementation(state, result)
                self.assertEqual(state["implementation_no_progress"], 0)
                for _ in range(2):
                    main._complete_implementation(state, result)
            self.assertEqual(state["state"], "WAIT_REPLY")
            self.assertIn("Large change", state["pending_question"])
            email.assert_called_once()

    def test_new_continuation_does_not_replay_completed_partial_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Pending\n")
            state = {"state": "IMPLEMENTING", "slug": "task", "item": "task", "branch": "feature", "session_id": "sid"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DATA_DIR", Path(root) / "data"), \
                 patch.object(main.config, "AGENT", "opencode"), \
                 patch.object(main, "_run_checked", return_value=json.dumps({"state": "ready",
                     "progress": {"total": 1, "complete": 0, "remaining": 1}})), \
                 patch.object(main, "_scrub_evidence_from_repo", return_value=[]), \
                 patch.object(main, "handle_result", return_value=False), \
                 patch.object(main, "save_state"), patch.object(main, "content_snapshot", return_value="a"), \
                 patch.object(main.agent_runner, "_opencode", return_value=main.agent_runner.OpenCodeResult("sid", "partial")) as run:
                main.agent_runner.set_task_context(state)
                try:
                    main.do_implement(state)
                    reloaded = json.loads(json.dumps(state))
                    main.agent_runner.set_task_context(reloaded)
                    main.do_implement(reloaded)
                finally:
                    main.agent_runner.set_task_context(None)
            self.assertEqual(run.call_count, 2)

    def test_pending_implementation_returns_to_work_without_consuming_gate_retries(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [ ] 1. Implement cancellation\n- [ ] 2. [codebot:final-checks] Run suite\n")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"):
                main._complete_verify(state, SimpleNamespace(output="incomplete"))
            self.assertEqual(state["state"], "IMPLEMENTING")
            self.assertNotIn("verify_round", state)
            self.assertIn("Implement cancellation", state["implementation_feedback"])

    def test_explicit_controller_task_can_wait_until_final_checks_pass(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openspec/changes/task/tasks.md"
            path.parent.mkdir(parents=True)
            path.write_text("- [x] 1. Implement\n- [ ] 2. [codebot:final-checks] Run suite\n")
            import subprocess
            from execution_store import ExecutionStore
            subprocess.run(["git", "init", "-q", root], check=True)
            for key, value in (("user.name", "Fixture"), ("user.email", "fixture@local.invalid")):
                subprocess.run(["git", "config", key, value], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            ledger = tempfile.TemporaryDirectory()
            self.addCleanup(ledger.cleanup)
            database = ExecutionStore(Path(ledger.name) / "db")
            state = {"state": "VERIFYING", "slug": "task", "item": "task"}
            output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
                "commands": ["focused: pass"], "tasks": "1/2", "deferred": 1})
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), \
                 patch.object(main, "content_snapshot", return_value="checked-content"), \
                 patch.object(main, "handle_result", return_value=False), patch.object(main, "trail"), \
                 patch.object(main, "_run_checked", side_effect=["valid", json.dumps({"state": "ready",
                     "progress": {"total": 2, "complete": 1, "remaining": 1}})]):
                main._complete_verify(state, SimpleNamespace(output=output))
            self.assertEqual(state["state"], "INTERNAL_REVIEW")
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main, "_gate_failed"), \
                 patch.object(main.final_checks, "run", return_value={"status": "indeterminate", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(len(task_phases.inspect(root, "task")["final_checks"]), 1)
            with patch.object(main.config, "REPO_PATH", Path(root)), \
                 patch.object(main.config, "DETERMINISTIC_CHECKS", True), patch.object(main, "save_state"), \
                 patch.object(main, "announce_milestone"), \
                 patch.object(main.phase_checkpoint, "store", return_value=database), \
                 patch.object(main.final_checks, "run", return_value={"status": "pass", "checks": []}):
                main.do_e2e(state)
            self.assertEqual(task_phases.inspect(root, "task")["complete"], 2)
            self.assertEqual(state["state"], "ARCHIVING")

    def test_incomplete_count_cannot_pass_without_explicit_defer_count(self):
        output = 'QUALITY_GATE: ' + json.dumps({"status": "pass", "openspec": "pass",
            "commands": ["focused: pass"], "tasks": "1/2"})
        self.assertIsNone(main.parse_quality_gate(output)[0])
