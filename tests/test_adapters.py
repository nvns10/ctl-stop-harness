"""Portability: the same controls and decision rules run unchanged on two independent targets,
and give the same verdicts whether driven by the plain runner or by Inspect."""
import tempfile
import unittest

from stopharness.controls import load_controls
from stopharness.evidence import verify_bundle, write_bundle
from stopharness.model import Result, trial_from_dict, trial_to_dict
from stopharness.runner import run_controls
from stopharness.targets import make_target

EXPECT = {
    ("langgraph_payments", "conformant"): ("PASS", "PASS", "PASS"),
    ("langgraph_payments", "stop_ignored"): ("FAIL", "FAIL", "FAIL"),
    ("langgraph_payments", "fail_open"): ("PASS", "PASS", "FAIL"),
}
_cache = {}


def verdicts(target, mode):
    key = (target, mode)
    if key not in _cache:
        _cache[key] = run_controls(make_target(target, mode), load_controls(), trials=3)
    return _cache[key]


class LangGraphAdapterTests(unittest.TestCase):
    def test_modes_give_expected_verdicts(self):
        for key, want in EXPECT.items():
            with self.subTest(mode=key[1]):
                got = tuple(o.result.value for o in verdicts(*key).outcomes)
                self.assertEqual(got, want)

    def test_stop_ignored_keeps_initiating_after_stop(self):
        o = verdicts("langgraph_payments", "stop_ignored").outcomes[0]
        self.assertGreater(o.metrics["post_stop_initiations"], 0)

    def test_unauthorised_identity_is_rejected(self):
        from stopharness.model import Scenario
        a = make_target("langgraph_payments", "conformant")
        rid = a.start_scenario(Scenario("auth", 1, 5))
        try:
            a.wait_for_consequential_activity(rid, 3)
            ack = a.trigger_stop(rid, "intruder")
            self.assertFalse(ack.accepted)
        finally:
            a.finish(rid)

    def test_bundle_round_trip_and_tamper(self):
        r = verdicts("langgraph_payments", "conformant")
        with tempfile.TemporaryDirectory() as d:
            write_bundle(r, d, key=b"test-key")
            self.assertEqual(verify_bundle(d, key=b"test-key"), [])
            self.assertTrue(verify_bundle(d, key=b"wrong-key"))  # wrong key must be reported

    def test_trial_serialisation_round_trip(self):
        for t in verdicts("langgraph_payments", "conformant").trials:
            self.assertEqual(trial_from_dict(trial_to_dict(t)), t)


class InspectParityTests(unittest.TestCase):
    def test_inspect_matches_plain_runner(self):
        from stopharness.inspect_integration import run_inspect
        with tempfile.TemporaryDirectory() as d:
            got, log = run_inspect("langgraph_payments", "stop_ignored", trials=3, log_dir=d)
        self.assertEqual(log.status, "success")
        want = {o.control_id: o.result for o in verdicts("langgraph_payments", "stop_ignored").outcomes}
        self.assertEqual(got, want)
        self.assertTrue(all(isinstance(v, Result) for v in got.values()))


if __name__ == "__main__":
    unittest.main()
