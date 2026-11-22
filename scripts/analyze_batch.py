"""Analyse a batch of Vertex AI runs (conformant vs stale_plan).

Input: a runs.csv with one row per run (columns: run_id, mode, v003, v004, v005, loaded_max_stop_s,
plan_lat_median_s, plan_lat_max_s, plan_retries, plan_errors, input_tokens, output_tokens, thought_tokens,
est_cost_usd, exit_code). Output: printed tables. Needs pandas, numpy, scipy.

    python scripts/analyze_batch.py results/vertex-2026-11-16/runs.csv
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(c - h, 0.0), 3), round(c + h, 3))


def boot_ci(x, rng, f=np.median, n=10000):
    x = np.asarray(x, float)
    s = [f(rng.choice(x, len(x))) for _ in range(n)]
    return np.round(np.percentile(s, [2.5, 97.5]), 4)


def main(path):
    df = pd.read_csv(path)
    con = df[df["mode"] == "conformant"]
    stl = df[df["mode"] == "stale_plan"]
    print(len(df), "rows;", df["mode"].value_counts().to_dict())

    print("\n== FAIL counts and Wilson 95% intervals ==")
    for ctl in ["v003", "v004", "v005"]:
        for name, d in [("conformant", con), ("stale_plan", stl)]:
            k = int((d[ctl] == "FAIL").sum())
            inc = int((d[ctl] == "INCONCLUSIVE").sum())
            print(f"{ctl} {name:10s} FAIL {k}/{len(d)}  INCONCLUSIVE {inc}  CI {wilson(k, len(d))}")

    print("\n== Fisher exact, one-sided (stale_plan fails more) ==")
    for ctl in ["v003", "v004", "v005"]:
        a = int((stl[ctl] == "FAIL").sum())
        c = int((con[ctl] == "FAIL").sum())
        _, p = stats.fisher_exact([[a, len(stl) - a], [c, len(con) - c]], alternative="greater")
        print(f"{ctl}: stale {a}/{len(stl)} vs conformant {c}/{len(con)}  p={p:.2e}")

    print("\n== loaded_max_stop_s ==")
    rng = np.random.default_rng(0)
    for name, d in [("conformant", con), ("stale_plan", stl)]:
        x = d["loaded_max_stop_s"].dropna()
        print(f"{name:10s} median {x.median():.4f}  95% bootstrap CI {boot_ci(x, rng)}  max {x.max():.4f}")
    u, p = stats.mannwhitneyu(stl["loaded_max_stop_s"].dropna(), con["loaded_max_stop_s"].dropna(),
                              alternative="greater")
    print(f"Mann-Whitney U={u:.1f}, one-sided p={p:.2e}")

    print("\n== Spearman, stale_plan ==")
    for col in ["plan_lat_median_s", "plan_lat_max_s", "plan_retries"]:
        s = stl[["loaded_max_stop_s", col]].dropna()
        if s[col].nunique() > 1:
            r, p = stats.spearmanr(s["loaded_max_stop_s"], s[col])
            print(f"loaded_max_stop_s vs {col}: rho={r:.2f}, p={p:.3f}")
        else:
            print(f"{col}: constant, skipped")

    print("\n== Data quality and spend (estimate at list prices) ==")
    print("plan_errors:", int(df["plan_errors"].sum()), "| plan_retries:", int(df["plan_retries"].sum()),
          "| nonzero exit codes:", int((df["exit_code"] != 0).sum()))
    print(f"estimated spend ${df['est_cost_usd'].sum():.2f} "
          f"(input {int(df['input_tokens'].sum()):,}, output {int(df['output_tokens'].sum()):,}, "
          f"thinking {int(df['thought_tokens'].sum()):,} tokens)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
