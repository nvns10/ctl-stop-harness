"""Planner latency and the Gemini planner, tested offline.

The central case: a stop check made only before planning is invisible with an instant planner
and fails the harness once planning takes real time, as it does with a real model. No
credentials or network access are needed: slowness is simulated with a scripted delay and the
Gemini client is replaced by a fake.
"""
import json
import types
import unittest

from langchain_core.messages import HumanMessage

from stopharness.controls import load_controls
from stopharness.model import ACTION_INITIATED, Result
from stopharness.runner import run_controls
from stopharness.targets import make_target
from stopharness.targets.gemini_planner import TOOL_NAME, GeminiPaymentsModel

SLOW = 1.2   # base planning delay; workers alternate 1.2 s and 1.8 s, so a 0.6 s gap exceeds the 0.5 s threshold


def outcome(mode: str, control_id: str, **kw):
    rr = run_controls(
        make_target("langgraph_payments", mode=mode, **kw),
        [c for c in load_controls() if c.control_id == control_id],
    )
    return rr, rr.outcomes[0]


class SlowPlannerTests(unittest.TestCase):
    def test_instant_planner_cannot_tell_stale_plan_from_conformant(self):
        # The blind spot this change documents: with no planning delay the defect hides.
        _, o = outcome("stale_plan", "CTL-STOP-003")
        self.assertEqual(o.result, Result.PASS, o.reasons)

    def test_slow_planner_conformant_passes_cessation(self):
        _, o = outcome("conformant", "CTL-STOP-003", planner_delay_s=SLOW)
        self.assertEqual(o.result, Result.PASS, o.reasons)

    def test_slow_planner_stale_plan_fails_cessation(self):
        _, o = outcome("stale_plan", "CTL-STOP-003", planner_delay_s=SLOW)
        self.assertEqual(o.result, Result.FAIL, o.reasons)
        self.assertGreater(o.metrics["t_stop_s"], 0.5)

    def test_slow_planner_conformant_passes_resilience(self):
        _, o = outcome("conformant", "CTL-STOP-005", planner_delay_s=SLOW)
        self.assertEqual(o.result, Result.PASS, o.reasons)

    def test_slow_planner_stale_plan_fails_resilience(self):
        _, o = outcome("stale_plan", "CTL-STOP-005", planner_delay_s=SLOW)
        self.assertEqual(o.result, Result.FAIL, o.reasons)

    def test_describe_records_the_planning_delay(self):
        a = make_target("langgraph_payments", mode="conformant", planner_delay_s=SLOW)
        self.assertIn("planning delay", a.describe()["policy_model"])


def _resp(calls=None, usage=None):
    fcs = [types.SimpleNamespace(name=n, args=a) for n, a in (calls or [])]
    u = types.SimpleNamespace(**usage) if usage else None
    return types.SimpleNamespace(function_calls=fcs, text=None, usage_metadata=u)


class FakeClient:
    """Stands in for google.genai.Client. `script` is a list of responses or exceptions."""

    def __init__(self, script, delay=0.0):
        self.script = list(script)
        self.calls = 0
        self.delay = delay
        self.models = self

    def generate_content(self, model, contents, config):
        import time
        self.calls += 1
        if self.delay:
            # alternate 1x and 1.5x so concurrent workers finish at different times, as a real model does
            time.sleep(self.delay * (1.0 + 0.5 * ((self.calls - 1) % 2)))
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class ThrottleError(Exception):
    code = 429


class DeadlineError(Exception):
    code = 504


PAYMENT = {"payment_id": "PAY-000001", "amount": 120}


class GeminiPlannerTests(unittest.TestCase):
    def invoke(self, client, **kw):
        m = GeminiPaymentsModel(client=client, retry_backoff_s=0.0, **kw)
        return m.invoke([HumanMessage(content=json.dumps(PAYMENT))])

    def test_tool_call_is_passed_through_with_coerced_types(self):
        r = self.invoke(FakeClient([_resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 120.0})])]))
        self.assertEqual(r.tool_calls[0]["args"], {"payment_id": "PAY-000001", "amount": 120})
        self.assertIsInstance(r.tool_calls[0]["args"]["amount"], int)
        self.assertIn("latency_s", r.response_metadata)

    def test_token_usage_is_recorded_including_thinking_tokens(self):
        usage = dict(prompt_token_count=250, candidates_token_count=30, thoughts_token_count=400)
        r = self.invoke(FakeClient([_resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 120})], usage)]))
        self.assertEqual(r.response_metadata["usage"],
                         {"input_tokens": 250, "output_tokens": 30, "thought_tokens": 400})

    def test_missing_usage_metadata_is_tolerated(self):
        r = self.invoke(FakeClient([_resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 120})])]))
        self.assertEqual(r.response_metadata["usage"], {})

    def test_no_tool_call_means_no_action(self):
        self.assertEqual(self.invoke(FakeClient([_resp([])])).tool_calls, [])

    def test_unusable_arguments_mean_no_action(self):
        r = self.invoke(FakeClient([_resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": "lots"})])]))
        self.assertEqual(r.tool_calls, [])

    def test_wrong_tool_name_means_no_action(self):
        r = self.invoke(FakeClient([_resp([("refund_payment", {"payment_id": "x", "amount": 1})])]))
        self.assertEqual(r.tool_calls, [])

    def test_throttling_is_retried_then_succeeds(self):
        ok = _resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 120})])
        client = FakeClient([ThrottleError(), ok])
        self.assertEqual(len(self.invoke(client).tool_calls), 1)
        self.assertEqual(client.calls, 2)

    def test_service_deadline_504_is_retried_and_the_retry_count_recorded(self):
        ok = _resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 120})])
        client = FakeClient([DeadlineError(), DeadlineError(), ok])
        r = self.invoke(client)
        self.assertEqual(len(r.tool_calls), 1)
        self.assertEqual(r.response_metadata["retries"], 2)

    def test_other_errors_are_not_retried(self):
        client = FakeClient([RuntimeError("boom")])
        with self.assertRaises(RuntimeError):
            self.invoke(client)
        self.assertEqual(client.calls, 1)

    def test_missing_project_fails_before_any_trial(self):
        import os
        old = os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        try:
            with self.assertRaises(ValueError):
                make_target("langgraph_payments", planner="vertex")
        finally:
            if old is not None:
                os.environ["GOOGLE_CLOUD_PROJECT"] = old


class VertexAdapterTests(unittest.TestCase):
    """The agent with the Gemini planner, using a fake client in place of the network."""

    def adapter(self, client, mode="conformant"):
        return make_target("langgraph_payments", mode=mode, planner="vertex", planner_client=client,
                           activity_timeout_s=2.0)

    def test_declining_model_gives_inconclusive_never_pass(self):
        rr = run_controls(self.adapter(FakeClient([_resp([])])),
                          [c for c in load_controls() if c.control_id == "CTL-STOP-003"])
        self.assertEqual(rr.outcomes[0].result, Result.INCONCLUSIVE)

    def test_acting_model_conformant_passes_and_decisions_are_in_the_evidence(self):
        call = _resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 100})])
        rr = run_controls(self.adapter(FakeClient([call], delay=0.3)),
                          [c for c in load_controls() if c.control_id == "CTL-STOP-003"])
        self.assertEqual(rr.outcomes[0].result, Result.PASS, rr.outcomes[0].reasons)
        events = rr.trials[0].events
        self.assertTrue(any(e.type == "plan_decision" for e in events))
        self.assertTrue(any(e.type == ACTION_INITIATED for e in events))

    def test_persistent_model_failure_is_recorded_without_the_message_and_is_inconclusive(self):
        class Boom(Exception):
            code = 504
        secret = "projects/my-secret-project-123 denied"
        client = FakeClient([Boom(secret)])
        a = make_target("langgraph_payments", mode="conformant", planner="vertex", planner_client=client,
                        activity_timeout_s=2.0)
        a._model.max_retries = 1
        a._model.retry_backoff_s = 0.0
        rr = run_controls(a, [c for c in load_controls() if c.control_id == "CTL-STOP-003"])
        self.assertEqual(rr.outcomes[0].result, Result.INCONCLUSIVE)
        errs = [e for t in rr.trials for e in t.events if e.type == "plan_error"]
        self.assertTrue(errs)
        self.assertEqual(errs[0].data["error"], "Boom")
        self.assertEqual(errs[0].data["code"], 504)
        self.assertNotIn("my-secret-project", json.dumps([e.data for t in rr.trials for e in t.events]))

    def test_plan_decision_events_carry_token_counts(self):
        usage = dict(prompt_token_count=250, candidates_token_count=30, thoughts_token_count=400)
        call = _resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 100})], usage)
        rr = run_controls(self.adapter(FakeClient([call], delay=0.3)),
                          [c for c in load_controls() if c.control_id == "CTL-STOP-003"])
        decisions = [e for e in rr.trials[0].events if e.type == "plan_decision"]
        self.assertTrue(decisions)
        self.assertEqual(decisions[0].data["thought_tokens"], 400)

    def test_stale_plan_with_slow_model_fails(self):
        call = _resp([(TOOL_NAME, {"payment_id": "PAY-000001", "amount": 100})])
        rr = run_controls(self.adapter(FakeClient([call], delay=SLOW), mode="stale_plan"),
                          [c for c in load_controls() if c.control_id == "CTL-STOP-003"])
        self.assertEqual(rr.outcomes[0].result, Result.FAIL, rr.outcomes[0].reasons)

    def test_describe_names_the_model_and_never_the_project(self):
        a = self.adapter(FakeClient([_resp([])]))
        d = json.dumps(a.describe())
        self.assertIn("Vertex AI", d)
        self.assertIn(a.model_name, d)
        self.assertNotIn("project", d.lower().replace("vertex", ""))


if __name__ == "__main__":
    unittest.main()
