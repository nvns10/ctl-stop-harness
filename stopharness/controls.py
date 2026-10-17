"""Machine-readable control definitions (schema follows section 4.7 of the working paper)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONTROLS_DIR = Path(__file__).parent / "controls"

# A threshold must trace to an identified source; an auditee-chosen number is not enough.
ALLOWED_THRESHOLD_SOURCES = {
    "system_safety_requirement",
    "regulatory_requirement",
    "risk_assessment",
    "contractual_sla",
}


@dataclass
class ControlDef:
    raw: dict[str, Any]

    @property
    def control_id(self) -> str:
        return self.raw["control_id"]

    @property
    def family(self) -> str:
        return self.raw["family"]

    @property
    def threshold_s(self) -> float:
        return float(self.raw["threshold"]["max_seconds"])

    @property
    def window_s(self) -> float:
        return float(self.raw["post_stop_window_s"])

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def threshold_traceability(self) -> tuple[bool, str]:
        t = self.raw.get("threshold", {})
        src = t.get("source")
        ref = (t.get("source_ref") or "").strip()
        if src not in ALLOWED_THRESHOLD_SOURCES:
            return False, f"threshold source {src!r} is not an accepted source type"
        if not ref:
            return False, "threshold has a source type but no source reference"
        return True, ""


def load_controls(ids: list[str] | None = None) -> list[ControlDef]:
    controls: list[ControlDef] = []
    for path in sorted(CONTROLS_DIR.glob("*.yaml")):
        with path.open() as fh:
            controls.append(ControlDef(yaml.safe_load(fh)))
    if ids:
        wanted = {i.upper() for i in ids}
        controls = [c for c in controls if c.control_id.upper() in wanted]
    return controls
