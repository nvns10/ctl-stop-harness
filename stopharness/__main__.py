"""Command line: run controls against a target, verify evidence bundles, list controls."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .controls import load_controls
from .evidence import verify_bundle, write_bundle
from .mapping import load_mapping, provisions_for, render_mapping_section, validate
from .model import Result
from .report import render_report
from .runner import run_controls
from .targets import MODES, TARGETS, make_target


def _key(path: str | None) -> bytes | None:
    return Path(path).read_bytes().strip() if path else None


def cmd_run(a: argparse.Namespace) -> int:
    extra: dict = {}
    if a.target == "langgraph_payments":
        extra = dict(planner=a.planner, planner_delay_s=a.planner_delay, model=a.model,
                     location=a.location, temperature=a.temperature)
    elif a.planner != "scripted" or a.planner_delay or a.model or a.location:
        print(f"planner options apply only to --target langgraph_payments, not {a.target}", file=sys.stderr)
        return 3
    adapter = make_target(a.target, mode=a.mode, inflight_policy=a.inflight_policy, **extra)
    controls = load_controls(a.controls.split(",") if a.controls else None)
    if not controls:
        print("no matching controls", file=sys.stderr)
        return 3
    result = run_controls(adapter, controls, trials=a.trials, progress=lambda m: print(f"  {m}", file=sys.stderr))
    out = write_bundle(result, a.out, _key(a.key_file))
    report = render_report(result)
    if not a.no_mapping:
        fws = a.frameworks.split(",") if a.frameworks else None
        report += "\n" + render_mapping_section(load_mapping(), result.outcomes, fws)
    (out / "report.md").write_text(report)
    print(report)
    print(f"Evidence bundle written to {out}", file=sys.stderr)
    results = [o.result for o in result.outcomes]
    if Result.FAIL in results:
        return 1
    if Result.INCONCLUSIVE in results:
        return 2
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    problems = verify_bundle(a.bundle, _key(a.key_file))
    if problems:
        print("VERIFICATION FAILED")
        for p in problems:
            print(f" - {p}")
        return 1
    print("Bundle matches its manifest and signature.")
    return 0


def cmd_list(_a: argparse.Namespace) -> int:
    for c in load_controls():
        print(f"{c.control_id}  {c.family:<18} {c.raw.get('title', '')}")
    return 0


def cmd_map(a: argparse.Namespace) -> int:
    m = load_mapping()
    problems = validate(m, {c.control_id for c in load_controls()})
    if problems:
        print("MAPPING INVALID")
        for x in problems:
            print(f" - {x}")
        return 1
    fws = a.frameworks.split(",") if a.frameworks else None
    for c in load_controls():
        print(f"{c.control_id}  {c.family}")
        for r in provisions_for(m, c.control_id, fws):
            flag = {"source_text": "", "secondary_source": "  [secondary only]"}.get(r["source_check"], "  [to verify]")
            print(f"    {r['framework']:<12} {r['ref']:<28} {r['relation']}{flag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="stopharness", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run controls against a target")
    r.add_argument("--target", default="sim_payments", choices=sorted(TARGETS))
    r.add_argument("--mode", default="conformant", choices=MODES, help="behaviour of the simulated target")
    r.add_argument("--inflight-policy", default="complete", choices=["complete", "cancel"])
    r.add_argument("--planner", default="scripted", choices=["scripted", "vertex"],
                   help="langgraph_payments only: scripted stand-in or Gemini on Vertex AI")
    r.add_argument("--planner-delay", type=float, default=0.0,
                   help="scripted planner only: fixed planning delay in seconds, to mimic model latency")
    r.add_argument("--model", help="vertex planner: model id (default set in gemini_planner.py)")
    r.add_argument("--location", help="vertex planner: location (default global, or GOOGLE_CLOUD_LOCATION)")
    r.add_argument("--temperature", type=float, default=0.0, help="vertex planner: sampling temperature")
    r.add_argument("--controls", help="comma-separated control ids, e.g. CTL-STOP-003,CTL-STOP-005")
    r.add_argument("--trials", type=int, help="trials per condition for latency (default from control)")
    r.add_argument("--out", default="evidence-bundle")
    r.add_argument("--key-file", help="signing key file (default: CTL_STOP_SIGNING_KEY, then demo key)")
    r.add_argument("--frameworks", help="comma-separated framework ids for the report mapping (default: all)")
    r.add_argument("--no-mapping", action="store_true", help="omit the framework mapping section")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="verify an evidence bundle")
    v.add_argument("bundle")
    v.add_argument("--key-file")
    v.set_defaults(func=cmd_verify)

    l = sub.add_parser("list-controls", help="list available controls")
    l.set_defaults(func=cmd_list)

    mp = sub.add_parser("map", help="show and validate the control-to-framework mapping")
    mp.add_argument("--frameworks")
    mp.set_defaults(func=cmd_map)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
