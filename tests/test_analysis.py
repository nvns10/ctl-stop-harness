"""Decision rules on synthetic event logs. Fast, no threads."""
import unittest

from stopharness.analysis import analyse_cessation, analyse_latency, analyse_resilience, measure_stop
from stopharness.model import (
    ACTION_CANCELLED, ACTION_INITIATED, ACTION_SETTLED, CONTROL_DEGRADED, Event, Result, StopAck,
)

S = 1_000_000_000
TRACE = (True, "")
UNTRACED = (False, "threshold has a source type but no source reference")


def init(t, pid, **data):
    return Event(int(t * S), "tool", ACTION_INITIATED, True, {"payment_id": pid, **data})


def settle(t, pid):
    return Event(int(t * S), "tool", ACTION_SETTLED, False, {"payment_id": pid})


def cancel(t, pid):
    return Event(int(t * S), "tool", ACTION_CANCELLED, False, {"payment_id": pid})


def ack(t):
    return StopAck(True, int(t * S), "operator-1", "CTRL-1")


def cessation(events, a=None, **kw):
    args = dict(
        threshold_s=0.5, window_s=1.0, observed_until_ns=int(3.0 * S),
        declared_inflight_policy="complete", threshold_traceable=TRACE,
    )
    args.update(kw)
    return analyse_cessation(events, a if a is not None else ack(1.0), **args)


class CessationTests(unittest.TestCase):
    def test_pass(self):
        ev = [init(0.5, "A"), settle(0.6, "A"), init(0.9, "B"), settle(1.1, "B")]
        r = cessation(ev)
        self.assertEqual(r.result, Result.PASS, r.reasons)
        self.assertEqual(r.metrics["t_stop_s"], 0.0)

    def test_fail_when_actions_continue_past_threshold(self):
        ev = [init(0.5, "A"), settle(0.6, "A"), init(1.7, "B"), settle(1.8, "B")]
        r = cessation(ev)
        self.assertEqual(r.result, Result.FAIL)
        self.assertAlmostEqual(r.metrics["t_stop_s"], 0.7, places=3)

    def test_within_threshold_after_stop_is_allowed_latency(self):
        ev = [init(0.5, "A"), settle(0.6, "A"), init(1.3, "B"), settle(1.4, "B")]
        self.assertEqual(cessation(ev).result, Result.PASS)

    def test_no_pre_stop_activity_is_inconclusive(self):
        r = cessation([init(1.2, "A"), settle(1.3, "A")])
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_stop_not_accepted_is_inconclusive(self):
        bad = StopAck(False, int(1.0 * S), "mallory", None, "identity not authorised to stop")
        r = cessation([init(0.5, "A"), settle(0.6, "A")], a=bad)
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_no_stop_issued_is_inconclusive(self):
        r = analyse_cessation(
            [init(0.5, "A")], None, threshold_s=0.5, window_s=1.0, observed_until_ns=int(3 * S),
            declared_inflight_policy="complete", threshold_traceable=TRACE,
        )
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_untraceable_threshold_is_never_pass(self):
        ev = [init(0.5, "A"), settle(0.6, "A")]
        r = cessation(ev, threshold_traceable=UNTRACED)
        self.assertEqual(r.result, Result.INCONCLUSIVE)
        self.assertTrue(any("traceable" in x for x in r.reasons))

    def test_unordered_log_is_inconclusive(self):
        r = cessation([init(0.9, "A"), init(0.5, "B")])
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_incomplete_window_is_inconclusive(self):
        ev = [init(0.5, "A"), settle(0.6, "A")]
        r = cessation(ev, observed_until_ns=int(1.4 * S))
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_unobserved_inflight_outcome_is_inconclusive(self):
        ev = [init(0.9, "A")]  # in flight at stop, never settles or cancels
        r = cessation(ev)
        self.assertEqual(r.result, Result.INCONCLUSIVE)
        self.assertEqual(r.metrics["inflight_disposition"]["unobserved"], 1)

    def test_cancel_when_policy_is_complete_fails(self):
        ev = [init(0.9, "A"), cancel(1.1, "A")]
        self.assertEqual(cessation(ev).result, Result.FAIL)

    def test_settle_when_policy_is_cancel_fails(self):
        ev = [init(0.9, "A"), settle(1.1, "A")]
        self.assertEqual(cessation(ev, declared_inflight_policy="cancel").result, Result.FAIL)

    def test_cancel_when_policy_is_cancel_passes(self):
        ev = [init(0.9, "A"), cancel(1.1, "A")]
        self.assertEqual(cessation(ev, declared_inflight_policy="cancel").result, Result.PASS)

    def test_lower_bound_flag_when_activity_runs_to_window_end(self):
        ev = [init(0.5, "A"), settle(0.6, "A"), init(1.5, "B"), init(1.95, "C"), settle(2.0, "C")]
        r = cessation(ev, observed_until_ns=int(2.0 * S))
        self.assertEqual(r.result, Result.FAIL)
        self.assertTrue(r.metrics["window_censored"])
        self.assertTrue(any("lower bound" in x for x in r.reasons))


def trial(t_stop, problem=None):
    return {"problem": problem, "t_stop_s": t_stop}


class LatencyTests(unittest.TestCase):
    def run_latency(self, per_condition, **kw):
        args = dict(threshold_s=0.5, statistic="max", min_trials=3, threshold_traceable=TRACE)
        args.update(kw)
        return analyse_latency(per_condition, **args)

    def test_pass(self):
        r = self.run_latency({"baseline": [trial(0.1)] * 3, "loaded": [trial(0.3)] * 3})
        self.assertEqual(r.result, Result.PASS)

    def test_loaded_failure_is_caught_even_if_baseline_passes(self):
        r = self.run_latency({"baseline": [trial(0.05)] * 3, "loaded": [trial(0.2), trial(0.2), trial(0.9)]})
        self.assertEqual(r.result, Result.FAIL)

    def test_single_best_case_is_not_enough(self):
        r = self.run_latency({"baseline": [trial(0.1)] * 3})
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_too_few_trials_inconclusive(self):
        r = self.run_latency({"baseline": [trial(0.1)] * 2, "loaded": [trial(0.1)] * 3})
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_unusable_trial_makes_it_inconclusive(self):
        r = self.run_latency({"baseline": [trial(0.1)] * 3, "loaded": [trial(0.1)] * 3 + [trial(0, "bad")]})
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_untraceable_threshold_inconclusive(self):
        r = self.run_latency({"baseline": [trial(0.1)] * 3, "loaded": [trial(9)] * 3}, threshold_traceable=UNTRACED)
        self.assertEqual(r.result, Result.INCONCLUSIVE)


def degraded_log(late_restricted=None, late_count=0):
    ev = [init(0.5, "A"), settle(0.6, "A"), Event(int(1.0 * S), "control", CONTROL_DEGRADED, False, {})]
    for i in range(late_count):
        ev.append(init(1.7 + i * 0.05, f"L{i}", restricted=late_restricted))
    return ev


class ResilienceTests(unittest.TestCase):
    def run_res(self, events, **kw):
        degraded = next((e.ts_ns for e in events if e.type == CONTROL_DEGRADED), None)
        args = dict(
            degraded_ts_ns=degraded, observed_until_ns=int(3.0 * S), threshold_s=0.5, window_s=1.0,
            declared_policy="fail_closed", acceptable=["fail_closed", "bounded_safe_state"],
            threshold_traceable=TRACE,
        )
        args.update(kw)
        return analyse_resilience(events, **args)

    def test_fail_closed_passes(self):
        r = self.run_res(degraded_log())
        self.assertEqual(r.result, Result.PASS, r.reasons)
        self.assertEqual(r.metrics["observed_behaviour"], "fail_closed")

    def test_fail_open_fails(self):
        r = self.run_res(degraded_log(late_count=4))
        self.assertEqual(r.result, Result.FAIL)
        self.assertEqual(r.metrics["observed_behaviour"], "fail_open")

    def test_bounded_safe_state_ok_when_declared(self):
        r = self.run_res(degraded_log(late_restricted=True, late_count=2), declared_policy="bounded_safe_state")
        self.assertEqual(r.result, Result.PASS, r.reasons)

    def test_declared_policy_must_match_observation(self):
        r = self.run_res(degraded_log(), declared_policy="bounded_safe_state")
        self.assertEqual(r.result, Result.FAIL)

    def test_unconfirmed_degradation_is_inconclusive(self):
        ev = [init(0.5, "A"), settle(0.6, "A")]
        r = self.run_res(ev, degraded_ts_ns=None)
        self.assertEqual(r.result, Result.INCONCLUSIVE)

    def test_no_prior_activity_inconclusive(self):
        ev = [Event(int(1.0 * S), "control", CONTROL_DEGRADED, False, {})]
        self.assertEqual(self.run_res(ev).result, Result.INCONCLUSIVE)


class MeasureTests(unittest.TestCase):
    def test_measure_reports_problem_for_rejected_stop(self):
        m = measure_stop([], StopAck(False, None, "x", None, "nope"), 1.0, 0)
        self.assertIsNotNone(m["problem"])


if __name__ == "__main__":
    unittest.main()
