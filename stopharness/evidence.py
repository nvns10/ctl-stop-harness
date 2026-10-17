"""Evidence bundle: raw event logs, results, a hashed manifest and a signature.

Limits (stated in every manifest): HMAC-SHA256 with a shared key proves the bundle was not
altered after signing by someone without the key. It does not prove the collector that
produced the events was honest or uncompromised, and the default demo key proves nothing
about origin. Asymmetric signing and collector attestation are future work.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from .model import Event
from .runner import RunResult

DEMO_KEY = b"ctl-stop-harness-demo-key-not-for-assurance"
KEY_ENV = "CTL_STOP_SIGNING_KEY"

LIMITS_NOTE = (
    "HMAC-SHA256 detects alteration after signing. It does not prove the collector was honest "
    "or uncompromised. The default demo key gives no assurance about origin."
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_key(key: bytes | None = None) -> tuple[bytes, str]:
    if key is not None:
        return key, "supplied"
    env = os.environ.get(KEY_ENV)
    if env:
        return env.encode(), "env"
    return DEMO_KEY, "demo"


def write_bundle(result: RunResult, out_dir: str | Path, key: bytes | None = None) -> Path:
    out = Path(out_dir)
    (out / "events").mkdir(parents=True, exist_ok=True)
    signing_key, key_kind = resolve_key(key)

    for t in result.trials:
        with (out / "events" / f"{t.trial_id}.jsonl").open("w") as fh:
            header = {
                "_trial": t.trial_id,
                "control_id": t.control_id,
                "condition": t.condition,
                "scenario": {"in_flight": t.scenario.in_flight, "queued": t.scenario.queued},
                "activity_confirmed": t.activity_confirmed,
                "stop_ack": None
                if t.ack is None
                else {"accepted": t.ack.accepted, "ts_ns": t.ack.ts_ns, "initiator": t.ack.initiator,
                      "control_event_id": t.ack.control_event_id, "detail": t.ack.detail},
                "degraded_ts_ns": t.degraded_ts_ns,
                "observed_until_ns": t.observed_until_ns,
            }
            fh.write(json.dumps(header, sort_keys=True) + "\n")
            for e in t.events:
                fh.write(json.dumps(e.to_dict(), sort_keys=True) + "\n")

    (out / "results.json").write_text(
        json.dumps({"outcomes": [o.to_dict() for o in result.outcomes]}, indent=2, sort_keys=True)
    )

    files = {
        str(p.relative_to(out)): _sha256(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name not in ("manifest.json", "manifest.sig", "report.md")
    }
    manifest = {
        **result.meta,
        "files": files,
        "signing": {"algorithm": "HMAC-SHA256", "key_kind": key_kind, "limits": LIMITS_NOTE},
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
    (out / "manifest.json").write_bytes(manifest_bytes)
    (out / "manifest.sig").write_text(hmac.new(signing_key, manifest_bytes, hashlib.sha256).hexdigest())
    return out


def verify_bundle(bundle_dir: str | Path, key: bytes | None = None) -> list[str]:
    """Return a list of problems; empty means the bundle matches its manifest and signature."""
    out = Path(bundle_dir)
    problems: list[str] = []
    mpath, spath = out / "manifest.json", out / "manifest.sig"
    if not mpath.exists() or not spath.exists():
        return ["manifest.json or manifest.sig is missing"]
    manifest_bytes = mpath.read_bytes()
    signing_key, _ = resolve_key(key)
    expected = hmac.new(signing_key, manifest_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, spath.read_text().strip()):
        problems.append("signature does not match the manifest (altered, or wrong key)")
    manifest = json.loads(manifest_bytes)
    listed = manifest.get("files", {})
    for rel, digest in listed.items():
        p = out / rel
        if not p.exists():
            problems.append(f"listed file is missing: {rel}")
        elif _sha256(p) != digest:
            problems.append(f"hash mismatch: {rel}")
    on_disk = {
        str(p.relative_to(out))
        for p in out.rglob("*")
        if p.is_file() and p.name not in ("manifest.json", "manifest.sig", "report.md")
    }
    for extra in sorted(on_disk - set(listed)):
        problems.append(f"file not listed in manifest: {extra}")
    return problems
