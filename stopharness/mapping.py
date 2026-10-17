"""Mapping layer: which framework provisions a control's result is evidence relevant to.

Checks are jurisdiction-neutral; this layer only attaches provisions. It never changes a verdict.
"""
from __future__ import annotations

from importlib import resources
from typing import Any

import yaml

RELATIONS = {"evidence_relevant_to", "partially_addresses"}
SOURCE_CHECKS = {"source_text", "secondary_source", "to_verify"}
DISCLAIMER = (
    "These mappings show where a control result may be used as evidence. A PASS does not mean a "
    "provision is satisfied, and no result here is a finding of compliance. References marked "
    "'secondary only' or 'to verify' must be checked against the current official text before use."
)


def load_mapping() -> dict[str, Any]:
    text = resources.files("stopharness.mappings").joinpath("frameworks.yaml").read_text()
    return yaml.safe_load(text)


def validate(m: dict[str, Any], known_controls: set[str]) -> list[str]:
    problems: list[str] = []
    fw = set(m.get("frameworks", {}))
    rows = [(cid, r) for cid, rs in m.get("mappings", {}).items() for r in rs]
    rows += [("evidence", r) for r in m.get("evidence_mappings", [])]
    for cid in m.get("mappings", {}):
        if cid not in known_controls:
            problems.append(f"mapping for unknown control {cid}")
    for cid, r in rows:
        for k in ("framework", "ref", "relation", "source_check", "note"):
            if not r.get(k):
                problems.append(f"{cid}: entry missing {k}: {r}")
        if r.get("framework") not in fw:
            problems.append(f"{cid}: unknown framework {r.get('framework')}")
        if r.get("relation") not in RELATIONS:
            problems.append(f"{cid}: bad relation {r.get('relation')}")
        if r.get("source_check") not in SOURCE_CHECKS:
            problems.append(f"{cid}: bad source_check {r.get('source_check')}")
    for cid in known_controls:
        if cid not in m.get("mappings", {}):
            problems.append(f"control {cid} has no mapping")
    return problems


def provisions_for(m: dict[str, Any], control_id: str, frameworks: list[str] | None = None) -> list[dict[str, Any]]:
    rows = m["mappings"].get(control_id, [])
    return [r for r in rows if not frameworks or r["framework"] in frameworks]


def render_mapping_section(m: dict[str, Any], outcomes, frameworks: list[str] | None = None) -> str:
    lines = ["## Framework mapping", "", DISCLAIMER, ""]
    names = {k: v["name"] for k, v in m["frameworks"].items()}
    for o in outcomes:
        rows = provisions_for(m, o.control_id, frameworks)
        lines.append(f"### {o.control_id} ({o.result.value})")
        if not rows:
            lines += ["No mapped provisions for the selected frameworks.", ""]
            continue
        lines += ["| Framework | Provision | Relation | Source checked | Note |", "|---|---|---|---|---|"]
        for r in rows:
            sc = {"source_text": "yes", "secondary_source": "secondary only"}.get(r["source_check"], "to verify")
            lines.append(f"| {names[r['framework']]} | {r['ref']} | {r['relation'].replace('_', ' ')} | {sc} | {r['note']} |")
        lines.append("")
    return "\n".join(lines)
