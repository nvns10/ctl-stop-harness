# Changelog

## 0.3.0 - 2026-11-22

- Event timestamps now come from `time.perf_counter_ns()` instead of `time.monotonic_ns()`. On Windows with older
  Python builds the monotonic clock ticks about every 15.6 ms, so a payment and the stop command could share a
  timestamp and every trial came back INCONCLUSIVE ("no consequential activity before the stop"). Bundles record
  the clock name in `time_source`.
- New `langgraph_payments` behaviour: a second, strict stop check between planning and acting. A plan made
  before the stop is discarded. If the stop status cannot be confirmed at that point, the agent does not act.
  Reason: with a slow planner, a check made only before planning let actions through after the stop and
  passed the loss of the control channel through a grace period. Scripted-planner results for `conformant`
  are unchanged (PASS on all three controls).
- New mode `stale_plan` (defect: no check between planning and acting), and `--planner-delay` to mimic model
  latency with the scripted planner. With an instant planner `stale_plan` is indistinguishable from
  `conformant`. With a scripted delay of 1.2 s it fails all three controls. With Gemini on Vertex AI, over 20 runs per mode,
  `stale_plan` failed CTL-STOP-004 in 19 and CTL-STOP-003 and 005 in 2 each, while `conformant` passed all three
  controls in all 20 (see docs/vertex-batch-results.md for conditions and limits).
- New optional planner `--planner vertex` (Gemini on Vertex AI through `google-genai`), with `--model`,
  `--location` and `--temperature`, behind the new `vertex` extra. The project is read from
  `GOOGLE_CLOUD_PROJECT` and is never written to evidence. Offline tests use a fake client.
- Gemini planner: a 504 (service-side deadline) is now retried like 429 and 5xx, with jittered backoff and the retry
  count recorded. A model call that still fails is recorded as a `plan_error` event (exception type and code only, never
  the message) and the agent continues, instead of the worker dying. Found in a pilot: one baseline trial of
  CTL-STOP-004 was INCONCLUSIVE after a 504 killed its only worker.
- The Gemini planner records token counts (input, output, thinking) on each `plan_decision` event, so the cost of a
  run can be measured, not estimated.
- A target can now set its own wait for first activity (`activity_timeout_s`); the default stays 3 s.
- Fix: `--trials` can no longer lower the latency control's minimum trial count. Previously
  `--trials 1` produced a PASS from one trial per condition. It now gives INCONCLUSIVE. A regression test is added.
- Documentation: new `docs/` pages (architecture, controls, adapters and targets, evidence bundle, command line)
  and this changelog. README heading corrected.
- Colab notebook: the setup cell can be run twice without error.
- Mapping: NIST AI RMF rows checked against the NIST AI 100-1 text on 18 Oct 2026, with exact wording,
  and MEASURE 2.6 added to CTL-STOP-005. Only the ISO/IEC 42001 rows remain secondary-source.
- Added `scripts/analyze_batch.py` (Wilson, Fisher, Mann-Whitney, bootstrap, Spearman) and `docs/vertex-batch-results.md`.

## 0.2.1

- Added `CITATION.cff` and the Zenodo DOI badge. No code changes.

## 0.2.0

- First public release: harness core, controls CTL-STOP-003, 004 and 005, the `sim_payments` and
  `langgraph_payments` targets, the Inspect task, signed evidence bundles and the framework mapping layer.
  This is the version whose results are reported in the companion paper.
