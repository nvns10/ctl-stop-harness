# Command line reference

Invoke with `python -m stopharness <command>`.

## `run`

Runs controls against a target, writes a bundle and a report, prints the report.

```
python -m stopharness run [--target T] [--mode M] [--inflight-policy P] [--controls IDS]
                          [--trials N] [--out DIR] [--key-file FILE]
                          [--frameworks IDS] [--no-mapping]
```

| Flag | Default | Meaning |
|---|---|---|
| `--target` | `sim_payments` | `sim_payments` or `langgraph_payments` |
| `--mode` | `conformant` | Behaviour of the target. `sim_payments`: conformant, leaky_queue, slow_under_load, fail_open, evidence_loss. `langgraph_payments`: conformant, stop_ignored, fail_open |
| `--inflight-policy` | `complete` | `complete` or `cancel`. The declared policy of `sim_payments`. The LangGraph target ignores it |
| `--controls` | all | Comma-separated ids, for example `CTL-STOP-003,CTL-STOP-005`. Matching is case-insensitive. No match exits with 3 |
| `--trials` | control default | Latency trials per condition. Can raise the count, cannot go below the control's minimum |
| `--out` | `evidence-bundle` | Bundle directory |
| `--key-file` | none | Signing key file. Default is the `CTL_STOP_SIGNING_KEY` variable, then the demo key |
| `--frameworks` | all | Limit the report's mapping to some of `mas_airg`, `eu_ai_act`, `iso_42001`, `nist_ai_rmf`, `imda_mgf` |
| `--no-mapping` | off | Leave the framework mapping out of the report |

Progress goes to stderr, the report to stdout.

**Exit codes.** 0 every control passed. 1 at least one FAIL. 2 no FAIL, at least one INCONCLUSIVE.
3 no matching controls.

A mode the target does not have raises a `ValueError` that lists the valid modes, before anything runs.

## `verify`

```
python -m stopharness verify BUNDLE_DIR [--key-file FILE]
```

Checks the signature, every hash in the manifest, and that no unlisted file is present. Exit 0 if it
matches, 1 otherwise with one line per problem. See [evidence-bundle.md](evidence-bundle.md).

## `list-controls`

Prints each control id, family and title.

## `map`

```
python -m stopharness map [--frameworks IDS]
```

Validates `mappings/frameworks.yaml` (known controls, known frameworks, valid relations and source
checks, every control mapped) and lists the provisions for each control. Rows are flagged
`[secondary only]` or `[to verify]` when the provision was not checked against the official text.
Exit 1 if the mapping is invalid.

## Inspect

```
inspect eval inspect_task.py -T target=langgraph_payments -T mode=stop_ignored -T trials=3 \
        --model mockllm/model --max-samples 1 --display plain
```

| Task argument | Default | Meaning |
|---|---|---|
| `target` | `sim_payments` | As above |
| `mode` | `conformant` | As above |
| `controls` | all | Comma-separated control ids |
| `trials` | 0 | 0 means the control default |

Always pass `--max-samples 1`. The model is a placeholder. The result lines are `pass_rate` (share of
controls that passed), `fail` and `inconclusive`. From Python, `run_inspect(target, mode)` returns the
verdicts per control and the Inspect log.

## Environment and files

| Item | Role |
|---|---|
| `CTL_STOP_SIGNING_KEY` | Signing key for `run` and `verify` when `--key-file` is not given |
| `stopharness/controls/*.yaml` | Control definitions |
| `stopharness/mappings/frameworks.yaml` | Framework mapping |

## Python use

```python
from stopharness.controls import load_controls
from stopharness.runner import run_controls
from stopharness.targets import make_target
from stopharness.evidence import write_bundle, verify_bundle

result = run_controls(make_target("sim_payments", mode="leaky_queue"), load_controls(), trials=3)
for o in result.outcomes:
    print(o.control_id, o.result.value, o.reasons)
write_bundle(result, "out/leaky")
assert verify_bundle("out/leaky") == []
```
