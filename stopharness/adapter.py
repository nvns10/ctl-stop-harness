"""Adapter capability contract.

The harness addresses an adapter, and the adapter addresses a deployment's own control
surfaces. Four interface groups, as in the working paper: Control, Observability,
Identity and Evidence. Test logic never reaches past this contract.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from .model import Event, Scenario, StopAck


class Adapter(ABC):
    """Fixed interface every deployment-specific adapter implements once."""

    # ---- Control: start, stop, degrade ------------------------------------------------
    @abstractmethod
    def start_scenario(self, scenario: Scenario) -> str:
        """Start a controlled task and return a run id."""

    @abstractmethod
    def trigger_stop(self, run_id: str, identity: str) -> StopAck:
        """Issue an authenticated stop through the approved stop mechanism."""

    @abstractmethod
    def degrade_control_path(self, run_id: str, mode: str) -> None:
        """Deliberately degrade the stop mechanism's control path (test environment only).

        The adapter MUST emit a CONTROL_DEGRADED control event once the degradation is in
        effect, so the harness can confirm the condition it claims to be testing.
        """

    @abstractmethod
    def finish(self, run_id: str) -> None:
        """Tear down the run. Called after evidence has been collected."""

    # ---- Observability ----------------------------------------------------------------
    @abstractmethod
    def wait_for_consequential_activity(self, run_id: str, timeout_s: float) -> bool:
        """Block until consequential activity is observed, or the timeout elapses."""

    # ---- Evidence ---------------------------------------------------------------------
    @abstractmethod
    def get_events(self, run_id: str) -> list[Event]:
        """Return agent, tool, queue, control and authorization events, time ordered."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """System and configuration version plus the DECLARED containment policy.

        Expected keys: system, version, inflight_policy ("complete" | "cancel"),
        failure_policy ("fail_closed" | "bounded_safe_state" | "fail_open"),
        time_source, identity (an identity authorised to stop the system).
        """

    def now_ns(self) -> int:
        """Synchronised time source shared with event timestamps."""
        return time.perf_counter_ns()
