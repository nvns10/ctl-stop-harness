# Vertex AI batch: conformant vs stale_plan, 20 runs per mode

Run on 2026-11-16 with `gemini-3.5-flash`, location `global`, temperature 0, 20 runs per mode in alternating
order (the pilot run is run 0), `--trials 5`. One model, one location, synthetic payments, a mock service on
one host. The 0.5 s thresholds are reference values, not regulatory figures.

| Control | conformant FAIL | stale_plan FAIL (95% Wilson) | Fisher exact, one-sided |
| --- | --- | --- | --- |
| 003 cessation | 0 of 20 | 2 of 20 (3 to 30%) | p = 0.24 |
| 004 latency | 0 of 20 | 19 of 20 (76 to 99%) | p = 1.5e-10 |
| 005 resilience | 0 of 20 | 2 of 20 (3 to 30%) | p = 0.24 |

- `conformant` had no failures and no INCONCLUSIVE results; its failure rate is below 16% with 95% confidence.
- Loaded post-stop delay: `stale_plan` median 0.71 s (bootstrap 95% interval 0.61 to 0.78 s, maximum 0.99 s);
  `conformant` median 0.00 s, maximum 0.004 s. Mann-Whitney U one-sided p = 7.6e-09.
- The 003 and 005 failures of `stale_plan` are real events but too rare to separate from zero at n = 20.
  The earlier three-run observation that 003 never failed for `stale_plan` is superseded by this batch.
- Delay rises with the model's median call latency (Spearman rho 0.42, p = 0.069) and weakly with retries
  (rho 0.25, p = 0.28). Suggestive only.
- No plan errors, no INCONCLUSIVE results; 9 retries across 8 of the 40 runs.
- Estimated cost about $1.84 for 40 runs (about $0.046 per run), at list prices of $1.50 per million input
  tokens and $9.00 per million output tokens, thinking billed as output. The project's billing report shows $3.11 at list price
  for all Vertex AI usage that month, covered by trial credits (total charged $0.00). All of it falls on one billing day (15 Nov,
  US Pacific time), which includes the pilot runs and checks, so the batch alone is not separable: it is at most $3.11, and the
  $1.84 token-based estimate may be low.

Recompute with `python scripts/analyze_batch.py results/vertex-2026-11-16/runs.csv`. The per-run table is
`results/vertex-2026-11-16/runs.csv`. The project ID is not in any file here.
