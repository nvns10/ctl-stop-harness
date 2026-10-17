"""Core data types shared by the harness, adapters and checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


def combine(results: Iterable[Result]) -> Result:
    """Any FAIL dominates, then any INCONCLUSIVE; PASS only if every input passes.

    Insufficient evidence is never collapsed into PASS.
    """
    rs = list(results)
    if any(r is Result.FAIL for r in rs):
        return Result.FAIL
    if not rs or any(r is Result.INCONCLUSIVE for r in rs):
        return Result.INCONCLUSIVE
    return Result.PASS


# Event vocabulary understood by the checks. Adapters map their own telemetry to these.
ACTION_INITIATED = "action_initiated"   # a consequential action begins (source: tool)
ACTION_SETTLED = "action_settled"       # an in-flight action completes
ACTION_CANCELLED = "action_cancelled"   # an in-flight action is cancelled
STOP_ACCEPTED = "stop_accepted"         # control plane registered a valid stop (source: control)
CONTROL_DEGRADED = "control_path_degraded"  # adapter confirms the control path was degraded
SAFE_STATE_ENTERED = "safe_state_entered"   # system reports it entered a bounded safe state


@dataclass(frozen=True)
class Event:
    ts_ns: int
    source: str            # agent | tool | queue | control | authz
    type: str
    consequential: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_ns": self.ts_ns,
            "source": self.source,
            "type": self.type,
            "consequential": self.consequential,
            "data": self.data,
        }


@dataclass(frozen=True)
class StopAck:
    accepted: bool
    ts_ns: int | None
    initiator: str
    control_event_id: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    in_flight: int = 1
    queued: int = 0


@dataclass
class TrialData:
    trial_id: str
    control_id: str
    condition: str
    run_id: str
    scenario: Scenario
    activity_confirmed: bool
    ack: StopAck | None
    degraded_ts_ns: int | None
    observed_until_ns: int
    events: list[Event]


@dataclass
class Outcome:
    control_id: str
    family: str
    result: Result
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    trial_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "family": self.family,
            "result": self.result.value,
            "metrics": self.metrics,
            "reasons": self.reasons,
            "trial_ids": self.trial_ids,
        }


def trial_to_dict(t: "TrialData") -> dict[str, Any]:
    return {
        "trial_id": t.trial_id,
        "control_id": t.control_id,
        "condition": t.condition,
        "run_id": t.run_id,
        "scenario": {"name": t.scenario.name, "in_flight": t.scenario.in_flight, "queued": t.scenario.queued},
        "activity_confirmed": t.activity_confirmed,
        "ack": None if t.ack is None else {
            "accepted": t.ack.accepted, "ts_ns": t.ack.ts_ns, "initiator": t.ack.initiator,
            "control_event_id": t.ack.control_event_id, "detail": t.ack.detail,
        },
        "degraded_ts_ns": t.degraded_ts_ns,
        "observed_until_ns": t.observed_until_ns,
        "events": [e.to_dict() for e in t.events],
    }


def trial_from_dict(d: dict[str, Any]) -> "TrialData":
    a = d["ack"]
    return TrialData(
        trial_id=d["trial_id"], control_id=d["control_id"], condition=d["condition"], run_id=d["run_id"],
        scenario=Scenario(**d["scenario"]),
        activity_confirmed=d["activity_confirmed"],
        ack=None if a is None else StopAck(**a),
        degraded_ts_ns=d["degraded_ts_ns"],
        observed_until_ns=d["observed_until_ns"],
        events=[Event(**e) for e in d["events"]],
    )
