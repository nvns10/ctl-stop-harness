"""Orchestrates trials against an adapter and turns them into outcomes.

Collection (`execute_control`) and decision (`evaluate_control`) are separate so that a
different execution substrate, such as an Inspect task, can collect the evidence while the
decision engine stays the same.
"""
from __future__ import annotations

import datetime as dt
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import __version__
from .adapter import Adapter
from .analysis import (
    analyse_cessation,
    analyse_latency,
    analyse_resilience,
    measure_stop,
)
from .controls import ControlDef
from .model import Outcome, Scenario, TrialData

ACTIVITY_TIMEOUT_S = 3.0


@dataclass
class RunResult:
    outcomes: list[Outcome]
    trials: list[TrialData]
    meta: dict[str, Any] = field(default_factory=dict)


def _run_trial(
    adapter: Adapter,
    trial_id: str,
    control_id: str,
    condition: str,
    scenario: Scenario,
    *,
    window_s: float,
    action: str,
    degrade_mode: str | None = None,
) -> TrialData:
    run_id = adapter.start_scenario(scenario)
    ack = None
    degraded_ts = None
    try:
        active = adapter.wait_for_consequential_activity(run_id, ACTIVITY_TIMEOUT_S)
        if active:
            if action == "stop":
                ack = adapter.trigger_stop(run_id, adapter.describe()["identity"])
            else:
                adapter.degrade_control_path(run_id, degrade_mode or "control_unreachable")
        time.sleep(window_s)
        observed_until = adapter.now_ns()
        events = adapter.get_events(run_id)
        if action == "degrade":
            degraded = [e for e in events if e.type == "control_path_degraded"]
            degraded_ts = degraded[0].ts_ns if degraded else None
    finally:
        adapter.finish(run_id)
    return TrialData(trial_id, control_id, condition, run_id, scenario, active, ack, degraded_ts, observed_until, events)


def execute_control(
    adapter: Adapter,
    ctl: ControlDef,
    *,
    trials: int | None = None,
    progress: Callable[[str], None] = lambda _m: None,
) -> list[TrialData]:
    """Collect the evidence for one control. No decisions are made here."""
    out: list[TrialData] = []
    if ctl.family == "cessation":
        sc = ctl.get("scenario", {})
        progress(f"{ctl.control_id}: cessation trial")
        out.append(_run_trial(
            adapter, f"{ctl.control_id}-t1", ctl.control_id, "default",
            Scenario("cessation", sc.get("in_flight", 2), sc.get("queued", 30)),
            window_s=ctl.window_s, action="stop",
        ))
    elif ctl.family == "latency":
        n = trials or int(ctl.get("min_trials_per_condition", 3))
        for cond, sc in ctl.get("conditions", {}).items():
            for i in range(1, n + 1):
                progress(f"{ctl.control_id}: {cond} trial {i}/{n}")
                out.append(_run_trial(
                    adapter, f"{ctl.control_id}-{cond}-t{i}", ctl.control_id, cond,
                    Scenario(cond, sc["in_flight"], sc["queued"]),
                    window_s=ctl.window_s, action="stop",
                ))
    elif ctl.family == "failure_resilience":
        sc = ctl.get("scenario", {})
        mode = ctl.get("trigger", {}).get("degrade_mode", "control_unreachable")
        progress(f"{ctl.control_id}: degraded control path trial")
        out.append(_run_trial(
            adapter, f"{ctl.control_id}-t1", ctl.control_id, "degraded",
            Scenario("resilience", sc.get("in_flight", 2), sc.get("queued", 30)),
            window_s=ctl.window_s, action="degrade", degrade_mode=mode,
        ))
    else:
        raise ValueError(f"unsupported control family {ctl.family!r}")
    return out


def evaluate_control(
    ctl: ControlDef,
    trials: list[TrialData],
    declared: dict[str, Any],
    *,
    min_trials_override: int | None = None,
) -> Outcome:
    """Apply the decision rules to collected trials. Pure: no adapter access."""
    trace = ctl.threshold_traceability()
    ids = [t.trial_id for t in trials]
    if ctl.family == "cessation":
        t = trials[0]
        a = analyse_cessation(
            t.events, t.ack,
            threshold_s=ctl.threshold_s, window_s=ctl.window_s,
            observed_until_ns=t.observed_until_ns,
            declared_inflight_policy=declared["inflight_policy"],
            threshold_traceable=trace,
        )
        return Outcome(ctl.control_id, ctl.family, a.result, _with_ack(a.metrics, t), a.reasons, ids)
    if ctl.family == "latency":
        per_condition: dict[str, list[dict[str, Any]]] = {}
        for t in trials:
            per_condition.setdefault(t.condition, []).append(
                measure_stop(t.events, t.ack, ctl.window_s, t.observed_until_ns)
            )
        a = analyse_latency(
            per_condition,
            threshold_s=ctl.threshold_s,
            statistic=ctl.get("metric", {}).get("statistic", "max"),
            min_trials=min_trials_override or int(ctl.get("min_trials_per_condition", 3)),
            threshold_traceable=trace,
        )
        return Outcome(ctl.control_id, ctl.family, a.result, a.metrics, a.reasons, ids)
    if ctl.family == "failure_resilience":
        t = trials[0]
        a = analyse_resilience(
            t.events,
            degraded_ts_ns=t.degraded_ts_ns,
            observed_until_ns=t.observed_until_ns,
            threshold_s=ctl.threshold_s, window_s=ctl.window_s,
            declared_policy=declared["failure_policy"],
            acceptable=list(ctl.get("acceptable_policies", ["fail_closed"])),
            threshold_traceable=trace,
        )
        return Outcome(ctl.control_id, ctl.family, a.result, a.metrics, a.reasons, ids)
    raise ValueError(f"unsupported control family {ctl.family!r}")


def build_meta(adapter: Adapter, controls: list[ControlDef]) -> dict[str, Any]:
    return {
        "harness_version": __version__,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "target": adapter.describe(),
        "controls": [
            {
                "control_id": c.control_id,
                "threshold_s": c.threshold_s,
                "threshold_source": c.raw["threshold"].get("source"),
                "threshold_source_ref": c.raw["threshold"].get("source_ref"),
                "limits": " ".join(str(c.get("limits", "")).split()),
            }
            for c in controls
        ],
    }


def run_controls(
    adapter: Adapter,
    controls: list[ControlDef],
    *,
    trials: int | None = None,
    progress: Callable[[str], None] = lambda _m: None,
) -> RunResult:
    declared = adapter.describe()
    outcomes: list[Outcome] = []
    all_trials: list[TrialData] = []
    for ctl in controls:
        collected = execute_control(adapter, ctl, trials=trials, progress=progress)
        all_trials.extend(collected)
        outcomes.append(evaluate_control(ctl, collected, declared, min_trials_override=None))
    return RunResult(outcomes, all_trials, build_meta(adapter, controls))


def _with_ack(metrics: dict[str, Any], t: TrialData) -> dict[str, Any]:
    out = dict(metrics)
    if t.ack is not None:
        out["stop_initiator"] = t.ack.initiator
        out["control_event_id"] = t.ack.control_event_id
    return out
