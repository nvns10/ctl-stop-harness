# Changelog

## Unreleased

- Fix: `--trials` can no longer lower the latency control's minimum trial count. Previously
  `--trials 1` produced a PASS from one trial per condition. It now gives INCONCLUSIVE. A regression test is added.
- Documentation: new `docs/` pages (architecture, controls, adapters and targets, evidence bundle, command line)
  and this changelog. README heading corrected.
- Colab notebook: the setup cell can be run twice without error.
- Mapping: NIST AI RMF rows checked against the NIST AI 100-1 text on 18 Oct 2026, with exact wording,
  and MEASURE 2.6 added to CTL-STOP-005. Only the ISO/IEC 42001 rows remain secondary-source.

## 0.2.1

- Added `CITATION.cff` and the Zenodo DOI badge. No code changes.

## 0.2.0

- First public release: harness core, controls CTL-STOP-003, 004 and 005, the `sim_payments` and
  `langgraph_payments` targets, the Inspect task, signed evidence bundles and the framework mapping layer.
  This is the version whose results are reported in the companion paper.
