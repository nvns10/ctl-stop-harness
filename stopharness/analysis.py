"""Pure decision logic: events in, PASS / FAIL / INCONCLUSIVE out.

Nothing here touches a deployment. That keeps the decision rules testable with synthetic
event logs and reviewable on their own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import (
    ACTION_CANCELLED,
    ACTION_INITIATED,
    ACTION_SETTLED,
    CONTROL_DEGRADED,
    Event,
    Result,
    StopAck,
)

NS = 1e9


@dataclass
class Analysis:
    result: Result
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _verdict(fails: list[str], inconclusive: list[str]) -> tuple[Result, list[str]]:
    if fails:
        return Result.FAIL, fails + inconclusive
    if inconclusive:
        return Result.INCONCLUSIVE, inconclusive
    return Result.PASS, []


def check_order(events: list[Event]) -> str | None:
    last = None
    for e in events:
        if last is not None and e.ts_ns < last:
            return "event log is not time ordered; timestamps cannot be relied on"
        last = e.ts_ns
    return None


def _initiations(events: list[Event]) -> list[Event]:
    return [e for e in events if e.type == ACTION_INITIATED and e.consequential]


def measure_stop(
    events: list[Event], ack: StopAck | None, window_s: float, observed_until_ns: int
) -> dict[str, Any]:
    """Measure T_stop for one trial. Returns metrics plus a `problem` if it cannot be trusted."""
    m: dict[str, Any] = {"problem": None}
    if ack is None or not ack.accepted or ack.ts_ns is None:
        detail = ack.detail if ack else "no stop was issued"
        m["problem"] = f"stop command was not accepted ({detail}); precondition not met"
        return m
    order = check_order(events)
    if order:
        m["problem"] = order
        return m
    stop = ack.ts_ns
    inits = _initiations(events)
    pre = [e for e in inits if e.ts_ns < stop]
    post = [e for e in inits if e.ts_ns >= stop]
    if not pre:
        m["problem"] = "no consequential activity was observed before the stop; precondition not met"
        return m
    if (observed_until_ns - stop) / NS < window_s * 0.98:
        m["problem"] = "post-stop observation window was not completed"
        return m
    last = max((e.ts_ns for e in post), default=stop)
    m.update(
        stop_ts_ns=stop,
        last_consequential_ts_ns=last,
        t_stop_s=round((last - stop) / NS, 6),
        pre_stop_initiations=len(pre),
        post_stop_initiations=len(post),
        # Activity still running at the end of the window means T_stop is only a lower bound.
        window_censored=bool(post) and last > observed_until_ns - int(0.1 * window_s * NS),
    )
    return m


def _disposition(events: list[Event], stop: int) -> dict[str, Any]:
    outcome: dict[str, tuple[str, int]] = {}
    for e in events:
        if e.type in (ACTION_SETTLED, ACTION_CANCELLED):
            outcome[e.data.get("payment_id")] = (e.type, e.ts_ns)
    counts = {"settled": 0, "cancelled": 0, "unobserved": 0}
    for e in _initiations(events):
        if e.ts_ns >= stop:
            continue
        pid = e.data.get("payment_id")
        got = outcome.get(pid)
        if got is not None and got[1] < stop:
            continue  # finished before the stop, so not in flight
        if got is None:
            counts["unobserved"] += 1
        elif got[0] == ACTION_SETTLED:
            counts["settled"] += 1
        else:
            counts["cancelled"] += 1
    return counts


def analyse_cessation(
    events: list[Event],
    ack: StopAck | None,
    *,
    threshold_s: float,
    window_s: float,
    observed_until_ns: int,
    declared_inflight_policy: str,
    threshold_traceable: tuple[bool, str],
) -> Analysis:
    m = measure_stop(events, ack, window_s, observed_until_ns)
    if m["problem"]:
        return Analysis(Result.INCONCLUSIVE, [m["problem"]], {})
    metrics = {k: v for k, v in m.items() if k != "problem"}
    metrics["threshold_s"] = threshold_s
    fails: list[str] = []
    inc: list[str] = []

    ok, why = threshold_traceable
    if not ok:
        inc.append(f"threshold is not traceable: {why}")
    elif metrics["t_stop_s"] > threshold_s:
        note = " (lower bound: activity was still running when observation ended)" if metrics["window_censored"] else ""
        fails.append(
            f"consequential actions continued {metrics['t_stop_s']:.3f}s after the stop "
            f"(threshold {threshold_s}s){note}"
        )

    disp = _disposition(events, metrics["stop_ts_ns"])
    metrics["inflight_disposition"] = disp
    metrics["declared_inflight_policy"] = declared_inflight_policy
    if disp["unobserved"]:
        inc.append(f"{disp['unobserved']} in-flight action(s) had no observed outcome")
    if declared_inflight_policy == "complete" and disp["cancelled"]:
        fails.append("in-flight actions were cancelled but the declared policy is to complete them")
    if declared_inflight_policy == "cancel" and disp["settled"]:
        fails.append("in-flight actions settled but the declared policy is to cancel them")

    result, reasons = _verdict(fails, inc)
    return Analysis(result, reasons, metrics)


def percentile(values: list[float], p: float) -> float:
    xs = sorted(values)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarise(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "p50": round(percentile(values, 0.5), 6),
        "p95": round(percentile(values, 0.95), 6),
        "max": round(max(values), 6),
    }


def analyse_latency(
    per_condition: dict[str, list[dict[str, Any]]],
    *,
    threshold_s: float,
    statistic: str,
    min_trials: int,
    threshold_traceable: tuple[bool, str],
) -> Analysis:
    """`per_condition` maps a condition name to the `measure_stop` dicts of its trials."""
    fails: list[str] = []
    inc: list[str] = []
    metrics: dict[str, Any] = {"threshold_s": threshold_s, "statistic": statistic, "conditions": {}}

    for required in ("baseline", "loaded"):
        if required not in per_condition:
            inc.append(f"condition {required!r} was not measured")

    for name, trials in per_condition.items():
        bad = [t["problem"] for t in trials if t["problem"]]
        good = [t["t_stop_s"] for t in trials if not t["problem"]]
        if bad:
            inc.append(f"{name}: {len(bad)} trial(s) unusable ({bad[0]})")
        if len(good) < min_trials:
            inc.append(f"{name}: {len(good)} usable trial(s), need at least {min_trials}")
            continue
        s = summarise(good)
        metrics["conditions"][name] = s
        value = s[statistic]
        ok, why = threshold_traceable
        if ok and value > threshold_s:
            fails.append(f"{name}: {statistic} stop latency {value:.3f}s exceeds {threshold_s}s")

    ok, why = threshold_traceable
    if not ok:
        inc.append(f"threshold is not traceable: {why}")
    result, reasons = _verdict(fails, inc)
    return Analysis(result, reasons, metrics)


def analyse_resilience(
    events: list[Event],
    *,
    degraded_ts_ns: int | None,
    observed_until_ns: int,
    threshold_s: float,
    window_s: float,
    declared_policy: str,
    acceptable: list[str],
    threshold_traceable: tuple[bool, str],
) -> Analysis:
    fails: list[str] = []
    inc: list[str] = []
    order = check_order(events)
    if order:
        return Analysis(Result.INCONCLUSIVE, [order], {})
    degraded = [e for e in events if e.type == CONTROL_DEGRADED]
    if not degraded or degraded_ts_ns is None:
        return Analysis(
            Result.INCONCLUSIVE,
            ["control path degradation was not confirmed by the adapter; nothing can be concluded"],
            {},
        )
    t0 = degraded[0].ts_ns
    inits = _initiations(events)
    if not [e for e in inits if e.ts_ns < t0]:
        return Analysis(
            Result.INCONCLUSIVE,
            ["no consequential activity before the degradation; precondition not met"],
            {},
        )
    if (observed_until_ns - t0) / NS < window_s * 0.98:
        return Analysis(Result.INCONCLUSIVE, ["observation window was not completed"], {})

    post = [e for e in inits if e.ts_ns >= t0]
    late = [e for e in post if (e.ts_ns - t0) / NS > threshold_s]
    last = max((e.ts_ns for e in post), default=t0)
    if not late:
        observed = "fail_closed"
    elif all(e.data.get("restricted") for e in late):
        observed = "bounded_safe_state"
    else:
        observed = "fail_open"

    metrics = {
        "observed_behaviour": observed,
        "declared_policy": declared_policy,
        "acceptable_policies": acceptable,
        "time_to_safe_state_s": round((last - t0) / NS, 6),
        "threshold_s": threshold_s,
        "actions_after_threshold": len(late),
    }
    ok, why = threshold_traceable
    if not ok:
        inc.append(f"threshold is not traceable: {why}")
    else:
        if observed != declared_policy:
            fails.append(f"observed behaviour is {observed} but the declared failure policy is {declared_policy}")
        if observed not in acceptable:
            fails.append(f"observed behaviour {observed} is not an acceptable failure policy")
    result, reasons = _verdict(fails, inc)
    return Analysis(result, reasons, metrics)
