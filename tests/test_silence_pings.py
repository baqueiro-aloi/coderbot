"""Silence check-ins: the back-off schedule, what restarts it, and what each check-in
says when the ball is on the user's side vs. the bot's."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"gdoc_client": Mock(), "task_source": Mock(), "gmail_client": Mock()}):
    import main

import config

main.config.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"

SCHEDULE = [1800, 3600, 7200, 10800, 18000, 28800]


def schedule(seconds=SCHEDULE):
    return patch.object(main.config, "PING_SCHEDULE_SECONDS", list(seconds))


class ScheduleParsing(unittest.TestCase):
    def test_default_is_the_decaying_backoff(self):
        self.assertEqual(config._parse_durations("30m,1h,2h,3h,5h,8h"), SCHEDULE)

    def test_units_and_spacing(self):
        self.assertEqual(config._parse_durations(" 90s, 2h ,1d,45"), [90, 7200, 86400, 45])

    def test_off_disables(self):
        for spec in ("off", "OFF", "none", "0", ""):
            self.assertEqual(config._parse_durations(spec), [], spec)

    def test_bad_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bad duration"):
            config._parse_durations("30m,soon")
        with self.assertRaisesRegex(ValueError, "bad duration"):
            config._parse_durations("0m")


class Due(unittest.TestCase):
    def test_intervals_back_off_and_last_one_repeats(self):
        with schedule():
            self.assertEqual([main._ping_interval(i) for i in range(8)],
                             SCHEDULE + [28800, 28800])

    def test_first_ping_after_first_interval_of_silence(self):
        state = {"state": "WAIT_REVIEW", "thread_id": "t", "last_contact": 1000.0}
        with schedule():
            self.assertFalse(main._ping_due(state, 1000.0 + 1799))
            self.assertTrue(main._ping_due(state, 1000.0 + 1800))

    def test_later_pings_count_from_the_previous_ping(self):
        state = {"state": "WAIT_REVIEW", "thread_id": "t", "last_contact": 0.0,
                 "ping_count": 1, "last_ping_at": 1800.0}
        with schedule():
            self.assertFalse(main._ping_due(state, 1800.0 + 3599))
            self.assertTrue(main._ping_due(state, 1800.0 + 3600))

    def test_never_when_disabled_idle_or_threadless(self):
        with schedule([]):
            self.assertFalse(main._ping_due(
                {"state": "WAIT_REVIEW", "thread_id": "t", "last_contact": 0.0}, 1e9))
        with schedule():
            self.assertFalse(main._ping_due({"state": "IDLE", "thread_id": "t",
                                             "last_contact": 0.0}, 1e9))
            self.assertFalse(main._ping_due({"state": "WAIT_REVIEW", "last_contact": 0.0}, 1e9))

    def test_legacy_task_without_clock_starts_it_instead_of_pinging(self):
        state = {"state": "IMPLEMENTING", "thread_id": "t"}
        with schedule():
            self.assertFalse(main._ping_due(state, 5000.0))
        self.assertEqual(state["last_contact"], 5000.0)
        with schedule():
            self.assertTrue(main._ping_due(state, 5000.0 + 1800))


class ClockResets(unittest.TestCase):
    def test_every_real_email_restarts_the_schedule(self):
        state = {"state": "WAIT_REVIEW", "thread_id": "t", "last_contact": 1.0,
                 "ping_count": 3, "last_ping_at": 2.0}
        with patch.object(main.gmail_client, "send", return_value="t"):
            main.email(state, "PR ready", "body")
        self.assertGreater(state["last_contact"], 2.0)
        self.assertNotIn("ping_count", state)
        self.assertNotIn("last_ping_at", state)
        self.assertEqual(state["last_email"]["body"], "body")

    def test_a_consumed_reply_restarts_the_schedule(self):
        state = {"state": "WAIT_APPROVAL", "thread_id": "t", "last_contact": 1.0,
                 "ping_count": 2, "last_ping_at": 2.0}
        with patch.object(main.gmail_client, "poll_reply", return_value=("m1", "approved")), \
             patch.object(main.gmail_client, "foreign_command", return_value=None), \
             patch.object(main.gmail_client, "mark_processed"), \
             patch.object(main, "_handle_reply"):
            main.handle_wait(state)
        self.assertGreater(state["last_contact"], 2.0)
        self.assertNotIn("ping_count", state)

    def test_status_on_the_task_thread_counts_as_contact(self):
        state = {"state": "WAIT_REVIEW", "thread_id": "t", "last_contact": 1.0, "ping_count": 1,
                 "last_ping_at": 2.0}
        with patch.object(main.gmail_client, "poll_command",
                          return_value=("m1", "t", "STATUS", False, "")), \
             patch.object(main.gmail_client, "mark_processed"), \
             patch.object(main, "_send_status"):
            self.assertFalse(main.check_commands(state))
        self.assertNotIn("ping_count", state)
        # ...but STATUS on some other thread leaves the task thread's clock alone.
        state.update({"last_contact": 1.0, "ping_count": 1, "last_ping_at": 2.0})
        with patch.object(main.gmail_client, "poll_command",
                          return_value=("m2", "other", "STATUS", False, "")), \
             patch.object(main.gmail_client, "mark_processed"), \
             patch.object(main, "_send_status"):
            main.check_commands(state)
        self.assertEqual(state["ping_count"], 1)

    def test_ping_bookkeeping_is_task_scoped(self):
        for key in main.PING_KEYS:
            self.assertIn(key, main.RESET_KEYS)


class Sending(unittest.TestCase):
    def base(self, **extra):
        state = {"state": "WAIT_REVIEW", "thread_id": "t", "item": "Add widgets",
                 "slug": "widgets", "pr_url": "https://github.com/o/r/pull/7",
                 "last_contact": 0.0, "last_email": {"subject": "s", "body": "b", "sent_at": 0.0}}
        state.update(extra)
        return state

    def test_sends_on_thread_without_touching_last_email(self):
        state = self.base()
        with schedule(), patch.object(main.gmail_client, "send") as send, \
             patch.object(main, "code_review_check", return_value=None), \
             patch.object(main.time, "time", return_value=1800.0):
            main._maybe_ping(state)
        send.assert_called_once()
        subj, body, thread = send.call_args.args[:3]
        self.assertEqual(thread, "t")
        self.assertIn("check-in", subj)
        self.assertIn("Check-in 1", body)
        self.assertIn("next one comes in about 1 h", body)
        self.assertEqual(state["ping_count"], 1)
        self.assertEqual(state["last_ping_at"], 1800.0)
        self.assertEqual(state["last_email"]["body"], "b")  # a check-in is not "the last email"
        self.assertEqual(state["last_contact"], 0.0)

    def test_not_due_sends_nothing(self):
        state = self.base()
        with schedule(), patch.object(main.gmail_client, "send") as send, \
             patch.object(main.time, "time", return_value=1799.0):
            main._maybe_ping(state)
        send.assert_not_called()
        self.assertNotIn("ping_count", state)

    def test_send_failure_never_raises_and_retries_next_tick(self):
        state = self.base()
        with schedule(), patch.object(main.gmail_client, "send", side_effect=RuntimeError("gmail")), \
             patch.object(main, "code_review_check", return_value=None), \
             patch.object(main.time, "time", return_value=1800.0):
            main._maybe_ping(state)  # must not raise
        self.assertNotIn("ping_count", state)


class BotSideBodies(unittest.TestCase):
    def test_wait_review_describes_the_action_wait(self):
        state = {"state": "WAIT_REVIEW", "item": "Add widgets", "pr_url": "https://x/pull/7",
                 "review_since": 1000.0, "review_round": 2, "last_contact": 1000.0,
                 "review_run_link": "run-1"}
        with schedule(), patch.object(main.config, "REVIEW_WAIT_TIMEOUT_SECONDS", 2700), \
             patch.object(main, "code_review_check",
                          return_value={"bucket": "pending", "link": "run-2"}):
            body = main._ping_body(state, 1000.0 + 1800, 1)
        self.assertIn("ball is in my court", body)
        self.assertIn("'Code Review' GitHub Action", body)
        self.assertIn("https://x/pull/7", body)
        self.assertIn("30 min so far", body)
        self.assertIn("another 15 min", body)
        self.assertIn("run as: pending", body)
        self.assertIn("round 2 of at most", body)

    def test_wait_review_notes_an_unregistered_or_stale_run(self):
        state = {"state": "WAIT_REVIEW", "pr_url": "u", "review_run_link": "run-1",
                 "last_contact": 0.0}
        with schedule(), patch.object(main, "code_review_check", return_value=None):
            self.assertIn("does not report a Code Review run", main._ping_body(state, 1800.0, 1))
        with schedule(), patch.object(main, "code_review_check",
                                      return_value={"bucket": "pass", "link": "run-1"}):
            self.assertIn("run I already processed", main._ping_body(state, 1800.0, 1))

    def test_wait_review_survives_a_gh_failure(self):
        state = {"state": "WAIT_REVIEW", "pr_url": "u", "last_contact": 0.0}
        with schedule(), patch.object(main, "code_review_check", side_effect=RuntimeError("gh")):
            body = main._ping_body(state, 1800.0, 1)
        self.assertIn("does not report", body)

    def test_agent_phase_describes_the_step_and_failures(self):
        state = {"state": "IMPLEMENTING", "item": "Add widgets", "branch": "bot-widgets",
                 "last_contact": 0.0, "last_transition": 100.0, "failures": {"IMPLEMENTING": 2}}
        with schedule(), patch.object(main.config, "MAX_STATE_FAILURES", 5):
            body = main._ping_body(state, 3700.0, 2)
        self.assertIn("implementing the approved proposal on branch bot-widgets", body)
        self.assertIn("This step started at", body)
        self.assertIn("1 h ago", body)
        self.assertIn("last 2 attempt(s) at this step failed", body)
        self.assertIn("after 5 in a row", body)
        self.assertIn("nothing is needed from you", body)
        self.assertNotIn("For reference", body)

    def test_thread_counts_are_filled_in(self):
        state = {"state": "ADDRESS_REVIEW", "pr_url": "u", "review_threads": [{}, {}, {}],
                 "last_contact": 0.0}
        with schedule():
            self.assertIn("3 unresolved thread(s)", main._ping_body(state, 1800.0, 1))

    def test_every_phase_has_a_description(self):
        for phase in main.PHASES:
            if phase != "IDLE":
                self.assertIn(phase, main._PHASE_ACTIVITY, phase)
        for wait in main.WAITS:
            self.assertTrue(wait in main.USER_SIDE_WAITS or wait == "WAIT_REVIEW", wait)


class UserSideBodies(unittest.TestCase):
    def body(self, **state):
        state.setdefault("last_contact", 0.0)
        state.setdefault("last_email", {"subject": "earlier", "body": "THE EARLIER BODY",
                                        "sent_at": 0.0})
        with schedule():
            return main._ping_body(state, 1800.0, 1)

    def test_approval(self):
        body = self.body(state="WAIT_APPROVAL", item="t")
        self.assertIn("ball is in your court", body)
        self.assertIn("explicit approval", body)
        self.assertIn("'abort'", body)
        self.assertIn("Nothing has changed on my side", body)
        self.assertIn("THE EARLIER BODY", body)

    def test_merge_and_blocked_merge(self):
        body = self.body(state="WAIT_MERGE", pr_url="https://x/pull/7")
        self.assertIn("Reply 'merge'", body)
        self.assertIn("https://x/pull/7", body)
        self.assertNotIn("merge anyway", body)
        body = self.body(state="WAIT_MERGE", pr_url="u", pr_thread_notified=True)
        self.assertIn("merge anyway", body)

    def test_question_is_restated_verbatim(self):
        body = self.body(state="WAIT_REPLY", return_state="IMPLEMENTING",
                         pending_question="Which port should the server use?")
        self.assertIn("question I asked during IMPLEMENTING", body)
        self.assertIn("Which port should the server use?", body)

    def test_stuck_restates_options_and_error(self):
        body = self.body(state="WAIT_STUCK", stuck_return="E2E", stuck_error="boom")
        self.assertIn("stuck on (E2E)", body)
        for word in ("'retry'", "'abort'", "'complete'", "instructions"):
            self.assertIn(word, body)
        self.assertIn("boom", body)

    def test_dirty_tree(self):
        body = self.body(state="WAIT_CLEAN")
        self.assertIn("clean working tree", body)
        self.assertIn("reply to this thread", body)


class StatusSnapshot(unittest.TestCase):
    def test_status_lists_contact_and_checkins(self):
        state = {"state": "WAIT_REVIEW", "last_contact": 0.0, "ping_count": 2, "last_ping_at": 5400.0}
        with patch.object(main.gmail_client, "send") as send, patch.object(main, "_load_holds", return_value=[]):
            main._send_status(state, "t")
        body = send.call_args.args[1]
        self.assertIn("Last real email on the task thread", body)
        self.assertIn("check-ins sent since then: 2", body)


class DurationFormat(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(main._fmt_dur(0), "0 min")
        self.assertEqual(main._fmt_dur(59), "0 min")
        self.assertEqual(main._fmt_dur(1800), "30 min")
        self.assertEqual(main._fmt_dur(3600), "1 h")
        self.assertEqual(main._fmt_dur(5400), "1 h 30 min")
        self.assertEqual(main._fmt_dur(90000), "1 d 1 h")


if __name__ == "__main__":
    unittest.main()
