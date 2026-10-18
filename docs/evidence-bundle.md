# Evidence bundle

Every `run` writes a bundle: the raw events, the verdicts, a hashed manifest, a signature and a report.

```
out/conformant/
  events/
    CTL-STOP-003-t1.jsonl
    CTL-STOP-004-baseline-t1.jsonl   ...one file per trial
  results.json
  manifest.json
  manifest.sig
  report.md
```

## Files

**`events/<trial_id>.jsonl`.** One JSON object per line. Keys are sorted. The first line is a header
and the rest are events in time order.

Header keys: `_trial`, `control_id`, `condition`, `scenario` (`in_flight`, `queued`),
`activity_confirmed`, `stop_ack` (or null), `degraded_ts_ns`, `observed_until_ns`.
`stop_ack` holds `accepted`, `ts_ns`, `initiator`, `control_event_id`, `detail`.

Event keys: `ts_ns` (monotonic nanoseconds), `source` (`agent`, `tool`, `queue`, `control`, `authz`),
`type`, `consequential` (boolean) and `data` (free-form object).

**`results.json`.** `{"outcomes": [...]}`. Each outcome has `control_id`, `family`, `result`, `metrics`,
`reasons` and `trial_ids`.

**`manifest.json`.** Run metadata plus the file hashes:

| Key | Content |
|---|---|
| `harness_version`, `created_utc`, `python` | Provenance of the run |
| `target` | The adapter's `describe()` output, including the declared policies and identity |
| `controls` | Per control: `control_id`, `threshold_s`, `threshold_source`, `threshold_source_ref`, `limits` |
| `files` | Map of relative path to SHA-256, for every file except `manifest.json`, `manifest.sig` and `report.md` |
| `signing` | `algorithm` (HMAC-SHA256), `key_kind` (`supplied`, `env` or `demo`), `limits` |

**`manifest.sig`.** Hex HMAC-SHA256 of the exact bytes of `manifest.json`.

**`report.md`.** The human report. See the caveat below.

## Keys

The signing key is chosen in this order: a key passed in code, then the `CTL_STOP_SIGNING_KEY` environment
variable, then a built-in demo key. `--key-file` reads a key from a file and strips surrounding whitespace.
The `key_kind` in the manifest records which was used. A bundle signed with the demo key shows
`"key_kind": "demo"` and gives no assurance about origin, because the key is public.

## Verifying

```
python -m stopharness verify out/conformant                  # demo key
python -m stopharness verify out/conformant --key-file k.txt # your key
```

Exit code 0 means the bundle matches. Exit code 1 prints one line per problem:

| Message | Meaning |
|---|---|
| `manifest.json or manifest.sig is missing` | The bundle is incomplete |
| `signature does not match the manifest (altered, or wrong key)` | The manifest changed, or the wrong key was used |
| `listed file is missing: <path>` | A hashed file was deleted |
| `hash mismatch: <path>` | A hashed file was changed |
| `file not listed in manifest: <path>` | A file was added after signing |

### Verifying without this tool

The check needs only the standard library:

```python
import hashlib, hmac, json, pathlib
b = pathlib.Path("out/conformant")
key = b"your key bytes"                      # the demo key is in stopharness/evidence.py
manifest = (b / "manifest.json").read_bytes()
sig = (b / "manifest.sig").read_text().strip()
assert hmac.compare_digest(hmac.new(key, manifest, hashlib.sha256).hexdigest(), sig)
for rel, digest in json.loads(manifest)["files"].items():
    assert hashlib.sha256((b / rel).read_bytes()).hexdigest() == digest, rel
```

## What signing proves, and what it does not

- **Proves.** Someone without the key has not changed the manifest or any hashed file since signing.
- **Does not prove.** That the collector was honest or uncompromised. A party who controls the collector can
  produce a clean bundle for a system that failed.
- **Does not prove origin** when the demo key is used.
- **Shared key.** HMAC needs the same key to sign and verify, so anyone who can verify can also forge.
  Asymmetric signatures and collector attestation are future work.
- **Clock.** Timestamps come from one monotonic clock on one host. A real deployment needs synchronised,
  documented time sources across components.

### `report.md` is not covered by the signature

`report.md` is deliberately left out of the manifest, because the auditor completes the "Auditor concluded"
section by hand. The consequence is that `verify` does not detect edits to the report. Treat `results.json`
and the event files as the evidence, and regenerate the tool-observed part of the report from them when it matters.

## Using a bundle as evidence

1. Verify it with the key the collector used, obtained through a channel you trust.
2. Read `manifest.json` first: target version, declared policies, threshold and its source.
3. Check that the threshold source is real, not the reference-value text.
4. Re-read the event files for the trials behind any verdict you rely on.
5. Complete the "Auditor concluded" section yourself. A PASS is evidence relevant to a control.
   It is not a finding of compliance.
