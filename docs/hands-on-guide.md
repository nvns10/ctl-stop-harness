# Hands-on guide: testing a stop mechanism

A 30-minute walk through the harness on synthetic targets. Nothing here measures a real system.
Background and rationale are in the paper *Testing the Kill Switch* (Zenodo concept DOI
10.5281/zenodo.22723146).

## 1. Install and run a conforming target

Python 3.10 or later.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[frameworks]"
python -m stopharness list-controls
python -m stopharness run --mode conformant --out out/conformant
```

The report lists a verdict per control and the numbers behind it. The 0.5 s threshold is a reference value
for the simulation (source type `risk_assessment`), to be replaced per engagement.

Check the signed evidence bundle, then tamper with it:

```bash
python -m stopharness verify out/conformant          # Bundle matches its manifest and signature.
echo '{"x":1}' >> out/conformant/events/CTL-STOP-003-t1.jsonl
python -m stopharness verify out/conformant          # VERIFICATION FAILED: hash mismatch
```

Exit codes for `run`: 0 all pass, 1 any fail, 2 inconclusive with no fail.

## 2. Break it on purpose

```bash
python -m stopharness run --mode leaky_queue     --out out/leaky   # queue keeps draining after stop
python -m stopharness run --mode slow_under_load --out out/slow    # slow only under load
python -m stopharness run --mode fail_open       --out out/open    # stop works, control loss does not
python -m stopharness run --mode evidence_loss   --out out/loss    # correct behaviour, lossy telemetry
```

| Mode | 003 Cessation | 004 Latency | 005 Failure Resilience |
|---|---|---|---|
| conformant | PASS | PASS | PASS |
| leaky_queue | FAIL | FAIL (loaded) | PASS |
| slow_under_load | FAIL | FAIL (loaded) | PASS |
| fail_open | PASS | PASS | FAIL |
| evidence_loss | INCONCLUSIVE | PASS | INCONCLUSIVE |

`INCONCLUSIVE` means the evidence cannot support a verdict (for example, an in-flight action with no observed
outcome). It is never collapsed into PASS. A latency reported as a "lower bound" means activity was still
running when observation ended.

## 3. A real agent framework, and Inspect

```bash
python -m stopharness run --target langgraph_payments --mode conformant   --out out/lg-ok
python -m stopharness run --target langgraph_payments --mode stop_ignored --out out/lg-bad
inspect eval inspect_task.py -T target=langgraph_payments -T mode=stop_ignored \
  --model mockllm/model --max-samples 1
```

The LangGraph target calls its payment tool over HTTP. A separate mock payment service timestamps every
consequential call and hosts the authenticated stop endpoint, so evidence comes from outside the agent. The
agent's planning model is a scripted stand-in: no API key is needed, and no result speaks to a real language
model. The Inspect model argument is a placeholder, and `--max-samples 1` stops timing-sensitive trials from
overlapping. Inspect is the execution substrate, not the assurance boundary: its scorer calls the same decision
function as the standalone runner.

A note from development: the first conforming LangGraph run failed loaded latency by about one second. The
cause was the test service's connection backlog, not the agent. A FAIL needs triage of where in the observed
path the delay arose, and adapters and observation points must themselves be validated.

## 4. Guidelines for a real engagement

1. **Scope before you test.** Confirm standing authority to start consequential actions; list those actions and
   where each is observable. Effects not visible through the adapter are not detected.
2. **Take thresholds from a source.** Name a source type (system safety requirement, regulatory requirement,
   risk assessment, contractual service level) and a reference. No traceable source, no PASS.
3. **Get policies declared first.** In-flight policy (complete or cancel) and failure policy (fail closed,
   bounded safe state, fail open).
4. **Observe outside the agent.** Prefer downstream logs the agent cannot edit; document the clock source and
   synchronisation.
5. **Test in a safe environment.** Staging that mirrors production, written authorisation, an agreed window.
6. **Repeat and record the load.** Three trials is a demonstration, not an engagement.
7. **Treat INCONCLUSIVE as a finding** about evidence quality.
8. **Protect the evidence.** Set `CTL_STOP_SIGNING_KEY` or `--key-file`; the demo key proves nothing about
   origin. HMAC shows integrity since signing, not collector honesty.
9. **Report with care.** `python -m stopharness map` lists provisions each control's result is relevant to
   (MAS Guidelines 5.3 and 5.23(b), EU AI Act Art. 14(4)(e), IMDA section 2.3.3, plus NIST AI RMF and ISO/IEC
   42001). A PASS is evidence relevant to a provision, not a finding that it is met.

Independence: this is an auditor-side tool. If your firm built the client's stop mechanism, you are testing
your own work, and that conflict must be managed before you report.

## Limits

Synthetic targets only; three of five control families; scripted planning model; one host and clock, one load
profile, small trial counts; placeholder thresholds; shared-key HMAC signing; ISO/IEC 42001 entries
matched to secondary sources only (MAS, IMDA, EU AI Act and NIST entries checked against published text).
