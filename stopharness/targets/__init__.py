from __future__ import annotations

from ..adapter import Adapter
from .sim_payments import MODES as SIM_MODES, SimPaymentsAdapter

LG_MODES = ("conformant", "stop_ignored", "stale_plan", "fail_open")  # kept in sync with langgraph_payments.MODES
TARGET_MODES = {"sim_payments": SIM_MODES, "langgraph_payments": LG_MODES}
MODES = tuple(dict.fromkeys(SIM_MODES + LG_MODES))


def _lg():
    try:
        from .langgraph_payments import LangGraphPaymentsAdapter
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("target 'langgraph_payments' needs: pip install langgraph inspect-ai") from exc
    return LangGraphPaymentsAdapter


class _Lazy:
    def __call__(self, **kw):
        return _lg()(**kw)


TARGETS = {"sim_payments": SimPaymentsAdapter, "langgraph_payments": _Lazy()}


def make_target(name: str, mode: str = "conformant", **kwargs) -> Adapter:
    if name not in TARGETS:
        raise ValueError(f"unknown target {name!r}; available: {sorted(TARGETS)}")
    if mode not in TARGET_MODES[name]:
        raise ValueError(f"target {name!r} has modes {TARGET_MODES[name]}, not {mode!r}")
    return TARGETS[name](mode=mode, **kwargs)


__all__ = ["TARGETS", "TARGET_MODES", "MODES", "make_target", "SimPaymentsAdapter"]
