"""Human-readable report. Keeps 'tool observed' separate from 'auditor concluded'."""
from __future__ import annotations

from .model import Result
from .runner import RunResult


def _fmt(v) -> str:
    return f"{v:.3f}s" if isinstance(v, float) else str(v)


def render_report(result: RunResult) -> str:
    meta = result.meta
    tgt = meta["target"]
    lines = [
        "# Stop-mechanism conformance report",
        "",
        f"Harness {meta['harness_version']} | run {meta['created_utc']} | Python {meta['python']}",
        f"Target: {tgt['system']} {tgt['version']} (synthetic: {tgt.get('synthetic', False)})",
        f"Declared in-flight policy: {tgt['inflight_policy']} | declared failure policy: {tgt['failure_policy']}",
        f"Time source: {tgt['time_source']}",
        "",
        "## Tool observed",
        "",
        "| Control | Family | Result |",
        "|---|---|---|",
    ]
    for o in result.outcomes:
        lines.append(f"| {o.control_id} | {o.family} | {o.result.value} |")
    lines.append("")

    limits = {c["control_id"]: c["limits"] for c in meta["controls"]}
    src = {c["control_id"]: c for c in meta["controls"]}
    for o in result.outcomes:
        lines += [f"### {o.control_id} ({o.family}): {o.result.value}", ""]
        c = src[o.control_id]
        lines.append(f"- Approved threshold: {c['threshold_s']}s (source: {c['threshold_source']}; {c['threshold_source_ref']})")
        for k, v in o.metrics.items():
            if k == "conditions":
                for name, s in v.items():
                    lines.append(f"- {name}: n={s['n']}, p50={s['p50']}s, p95={s['p95']}s, max={s['max']}s")
            elif k not in ("stop_ts_ns", "last_consequential_ts_ns"):
                lines.append(f"- {k}: {_fmt(v)}")
        if o.result is not Result.PASS:
            lines.append("- Reasons:")
            lines += [f"  - {r}" for r in o.reasons]
        lines.append(f"- Evidence trials: {', '.join(o.trial_ids)}")
        lines.append(f"- Limits of this check: {limits[o.control_id]}")
        lines.append("")

    lines += [
        "## Auditor concluded",
        "",
        "_To be completed by the auditor. A PASS here is evidence relevant to a control, not a "
        "finding of compliance with any framework._",
        "",
        "Conclusion: ",
        "",
        "Residual limitations noted: ",
        "",
    ]
    return "\n".join(lines)
