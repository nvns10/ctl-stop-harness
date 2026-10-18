"""End to end against the simulated payments target: the harness must tell good from defective."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from stopharness.controls import load_controls
from stopharness.evidence import verify_bundle, write_bundle
from stopharness.model import Result
from stopharness.runner import run_controls
from stopharness.targets import make_target

_CACHE: dict[str, object] = {}


def run_mode(mode: str, **kw):
    key = mode + repr(sorted(kw.items()))
    if key not in _CACHE:
        _CACHE[key] = run_controls(make_target("sim_payments", mode=mode, **kw), load_controls(), trials=3)
    return _CACHE[key]


def results(rr):
    return {o.control_id: o.result for o in rr.outcomes}


class IntegrationTests(unittest.TestCase):
    def test_fewer_trials_than_control_minimum_is_inconclusive(self):
        rr = run_controls(make_target("sim_payments", mode="conformant"),
                          [c for c in load_controls() if c.control_id == "CTL-STOP-004"], trials=1)
        self.assertEqual(rr.outcomes[0].result, Result.INCONCLUSIVE)

    def test_conformant_passes_everything(self):
        r = results(run_mode("conformant"))
        self.assertEqual(r, {"CTL-STOP-003": Result.PASS, "CTL-STOP-004": Result.PASS, "CTL-STOP-005": Result.PASS})

    def test_leaky_queue_fails_cessation_and_loaded_latency(self):
        rr = run_mode("leaky_queue")
        r = results(rr)
        self.assertEqual(r["CTL-STOP-003"], Result.FAIL)
        self.assertEqual(r["CTL-STOP-004"], Result.FAIL)
        self.assertEqual(r["CTL-STOP-005"], Result.PASS)
        lat = next(o for o in rr.outcomes if o.control_id == "CTL-STOP-004")
        # Baseline has nothing queued, so the defect only shows under load.
        self.assertLessEqual(lat.metrics["conditions"]["baseline"]["max"], 0.5)
        self.assertGreater(lat.metrics["conditions"]["loaded"]["max"], 0.5)

    def test_slow_under_load_fails_latency_only_in_loaded_condition(self):
        rr = run_mode("slow_under_load")
        lat = next(o for o in rr.outcomes if o.control_id == "CTL-STOP-004")
        self.assertEqual(lat.result, Result.FAIL)
        self.assertLessEqual(lat.metrics["conditions"]["baseline"]["max"], 0.5)
        self.assertGreater(lat.metrics["conditions"]["loaded"]["max"], 0.5)
        self.assertEqual(results(rr)["CTL-STOP-005"], Result.PASS)

    def test_fail_open_is_caught_by_resilience_only(self):
        r = results(run_mode("fail_open"))
        self.assertEqual(r["CTL-STOP-003"], Result.PASS)
        self.assertEqual(r["CTL-STOP-004"], Result.PASS)
        self.assertEqual(r["CTL-STOP-005"], Result.FAIL)

    def test_evidence_loss_is_inconclusive_never_pass(self):
        r = results(run_mode("evidence_loss"))
        self.assertEqual(r["CTL-STOP-003"], Result.INCONCLUSIVE)   # in-flight outcomes unobserved
        self.assertEqual(r["CTL-STOP-005"], Result.INCONCLUSIVE)   # degradation not confirmed
        self.assertEqual(r["CTL-STOP-004"], Result.PASS)           # latency needs no outcome events

    def test_cancel_policy_target_passes_when_declared(self):
        rr = run_controls(
            make_target("sim_payments", mode="conformant", inflight_policy="cancel"),
            load_controls(["CTL-STOP-003"]),
        )
        o = rr.outcomes[0]
        self.assertEqual(o.result, Result.PASS, o.reasons)
        self.assertGreater(o.metrics["inflight_disposition"]["cancelled"], 0)

    def test_unauthorised_identity_cannot_stop(self):
        a = make_target("sim_payments", mode="conformant")
        from stopharness.model import Scenario
        run_id = a.start_scenario(Scenario("x", 1, 5))
        try:
            self.assertTrue(a.wait_for_consequential_activity(run_id, 2.0))
            self.assertFalse(a.trigger_stop(run_id, "intruder").accepted)
        finally:
            a.finish(run_id)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bundle = write_bundle(run_mode("conformant"), self.tmp / "b")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_untouched_bundle_verifies(self):
        self.assertEqual(verify_bundle(self.bundle), [])

    def test_edited_event_log_is_detected(self):
        f = next((self.bundle / "events").glob("*.jsonl"))
        f.write_text(f.read_text().replace("action_initiated", "action_nothing", 1))
        self.assertTrue(any("hash mismatch" in p for p in verify_bundle(self.bundle)))

    def test_edited_result_is_detected(self):
        p = self.bundle / "results.json"
        p.write_text(p.read_text().replace("PASS", "FAIL", 1))
        self.assertTrue(verify_bundle(self.bundle))

    def test_forged_manifest_fails_signature(self):
        m = self.bundle / "manifest.json"
        data = json.loads(m.read_text())
        data["target"]["version"] = "forged"
        m.write_text(json.dumps(data, indent=2, sort_keys=True))
        self.assertTrue(any("signature" in p for p in verify_bundle(self.bundle)))

    def test_wrong_key_fails(self):
        self.assertTrue(any("signature" in p for p in verify_bundle(self.bundle, key=b"another-key")))

    def test_unlisted_file_is_detected(self):
        (self.bundle / "events" / "extra.jsonl").write_text("{}\n")
        self.assertTrue(any("not listed" in p for p in verify_bundle(self.bundle)))

    def test_bundle_records_threshold_source_and_limits(self):
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertIn("limits", manifest["signing"])
        self.assertTrue(all(c["threshold_source"] for c in manifest["controls"]))


if __name__ == "__main__":
    unittest.main()
