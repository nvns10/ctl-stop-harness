"""Run the conformance controls as an Inspect task.

Inspect is used as the execution substrate: it schedules samples, records transcripts and
produces its standard log. It is NOT the assurance boundary. The decision rules live in
`stopharness.analysis` and are applied by `evaluate_control`; the Inspect scorer only calls
that function. Raw trial evidence is stored on the sample so the same bundle and signing
path (`write_bundle`) can be used from an Inspect log.

Each sample is one control. Run with max_samples=1 so timing-sensitive trials never overlap.
"""
from __future__ import annotations

import asyncio
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import SampleScore, Score, Target, metric, scorer
from inspect_ai.solver import Generate, TaskState, solver

from .controls import ControlDef, load_controls
from .model import Result, trial_from_dict, trial_to_dict
from .runner import evaluate_control, execute_control
from .targets import make_target

_VALUE = {"PASS": 1.0, "FAIL": 0.0, "INCONCLUSIVE": 0.0}


@metric
def conformance():
    """Share of controls that PASS, plus counts. INCONCLUSIVE counts as not passed."""
    def compute(scores: list[SampleScore]):
        vals = [(getattr(s, "score", s)).metadata["result"] for s in scores]  # Score or SampleScore
        n = len(vals) or 1
        return {
            "pass_rate": vals.count("PASS") / n,
            "fail": float(vals.count("FAIL")),
            "inconclusive": float(vals.count("INCONCLUSIVE")),
        }
    return compute


@solver
def collect_evidence(target: str, mode: str, trials: int | None = None):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        ctl = _by_id(state.metadata["control_id"])
        adapter = make_target(target, mode)
        collected = await asyncio.to_thread(execute_control, adapter, ctl, trials=trials)
        state.store.set("trials", [trial_to_dict(t) for t in collected])
        state.store.set("declared", adapter.describe())
        state.output.completion = f"collected {len(collected)} trial(s) for {ctl.control_id}"
        return state
    return solve


@scorer(metrics=[conformance()])
def stop_conformance():
    async def score(state: TaskState, target: Target) -> Score:
        ctl = _by_id(state.metadata["control_id"])
        trials = [trial_from_dict(d) for d in state.store.get("trials")]
        outcome = evaluate_control(ctl, trials, state.store.get("declared"))
        return Score(
            value=_VALUE[outcome.result.value],
            answer=outcome.result.value,
            explanation="; ".join(outcome.reasons) or "no reasons recorded",
            metadata={"result": outcome.result.value, "outcome": outcome.to_dict()},
        )
    return score


_CONTROLS: dict[str, ControlDef] = {}


def _by_id(control_id: str) -> ControlDef:
    if not _CONTROLS:
        _CONTROLS.update({c.control_id: c for c in load_controls()})
    return _CONTROLS[control_id]


@task
def kill_switch_conformance(target: str = "sim_payments", mode: str = "conformant",
                            controls: str = "", trials: int = 0):
    """controls: comma-separated control ids (default all). trials: 0 means control default."""
    ids = [c.strip() for c in controls.split(",") if c.strip()] or [c.control_id for c in load_controls()]
    return Task(
        dataset=MemoryDataset([
            Sample(input=f"Run {cid} against {target} ({mode})", id=cid, metadata={"control_id": cid})
            for cid in ids
        ]),
        solver=collect_evidence(target, mode, trials or None),
        scorer=stop_conformance(),
        metadata={"target": target, "mode": mode},
    )


def run_inspect(target: str, mode: str, controls: str = "", trials: int = 0, log_dir: str = "inspect_logs"):
    """Convenience wrapper: runs the task with a mock model and returns {control_id: Result}."""
    from inspect_ai import eval as inspect_eval
    logs = inspect_eval(
        kill_switch_conformance(target=target, mode=mode, controls=controls, trials=trials),
        model="mockllm/model", max_samples=1, log_dir=log_dir, display="none",
    )
    out: dict[str, Result] = {}
    for s in logs[0].samples or []:
        out[str(s.id)] = Result(s.scores["stop_conformance"].metadata["result"])
    return out, logs[0]
