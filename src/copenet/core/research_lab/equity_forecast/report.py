"""Human-readable baseline experiment report."""

from __future__ import annotations

from typing import Any


def render_report(
    manifest: dict[str, Any],
    results: dict[str, Any],
    contribution_summary: dict[str, Any],
) -> str:
    lines = [
        "# BASELINE EQUITY FORECAST V1",
        "",
        f"Dataset period: {manifest['coverage']['dataset_start']}–{manifest['coverage']['dataset_end']}",
        f"Out-of-sample evaluation: {manifest['coverage']['evaluation_start']}–{manifest['coverage']['evaluation_end']}",
        f"Assets: {' '.join(manifest['config']['symbols'])}",
        f"Primary target: 12M excess total return vs {manifest['config']['benchmark']}",
        "",
        "## Timing policy",
        "",
        "Prediction anchors are the first trading session on or after Feb/May/Aug/Nov 15. "
        "The knowledge cutoff is the end of the prior calendar day. Financial snapshots are "
        "resolved independently with `as_of=knowledge_cutoff`; every included filing date is "
        "on or before that cutoff. The current SEC contract is date-granular, not acceptance-time granular.",
        "",
        "A training observation is eligible only when its 12-month label end precedes the new "
        "prediction timestamp. Imputation and scaling are refit inside each expanding fold.",
        "",
        "## Model results",
        "",
        "| Feature set / model | MAE | RMSE | R² | Rank IC | Direction | Top-1 CAGR | Top-2 CAGR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, value in sorted(results.items()):
        if not value["rankable"]:
            lines.append(
                f"| {key} | {value['mae']:.3f} | {value['rmse']:.3f} | {value['r2']:.3f} | n/a | {value['directional_accuracy']:.1%} | n/a | n/a |"
            )
            continue
        lines.append(
            f"| {key} | {value['mae']:.3f} | {value['rmse']:.3f} | {value['r2']:.3f} | "
            f"{value['ranking'].get('rank_correlation', 0):.3f} | {value['directional_accuracy']:.1%} | "
            f"{value['top_1_strategy']['cagr']:.1%} | {value['top_2_strategy']['cagr']:.1%} |"
        )
    if results:
        best_key = min((key for key in results if results[key]["rankable"]), key=lambda key: results[key]["mae"])
        best = results[best_key]
        lines.extend([
            "",
            "## Lowest-MAE exploratory configuration",
            "",
            f"{best_key}: MAE {best['mae']:.3f}, rank IC {best['ranking'].get('rank_correlation', 0):.3f}, "
            f"top-1 strategy CAGR {best['top_1_strategy']['cagr']:.1%} after costs, versus "
            f"{manifest['config']['benchmark']} {best['top_1_strategy']['benchmark_cagr']:.1%}.",
            f"The most frequently selected ticker accounts for {best['top_1_strategy']['largest_selection_share']:.1%} "
            "of top-1 periods; treat a concentrated result as an asset-specific outcome, not broad evidence of signal.",
        ])
        naive = results.get("fundamentals_only:naive")
        robust = bool(naive and best["mae"] < naive["mae"] and best["r2"] > 0)
        lines.extend([
            "",
            "## Out-of-sample conclusion",
            "",
            (
                "This run shows preliminary forecasting signal under the declared rule."
                if robust
                else "No robust forecasting signal was established: every learned configuration has negative out-of-sample R², and the lowest-MAE learned configuration does not beat the naive historical-mean forecast."
            ),
        ])
        importance_rows = contribution_summary.get(best_key, [])
        if importance_rows:
            strongest = ", ".join(
                f"{row['feature']} ({row['mean_absolute']:.3f})" for row in importance_rows[:5]
            )
            weakest = ", ".join(
                f"{row['feature']} ({row['mean_absolute']:.3f})" for row in importance_rows[-5:]
            )
            lines.extend([
                "",
                "## Feature contribution diagnostics",
                "",
                f"For {best_key}, strongest mean absolute fold contributions: {strongest}.",
                f"Weakest mean absolute fold contributions: {weakest}.",
                "Linear values are coefficients after fold-local scaling; tree values are impurity importances. These are predictive diagnostics, not causal effects.",
            ])
    lines.extend(["", "## Data quality", ""])
    for symbol, quality in manifest["data_quality"].items():
        lines.append(
            f"- {symbol}: {quality['prediction_observations']} observations; "
            f"{quality['missing_feature_pct']:.1%} fundamental-feature missingness; "
            f"{quality['filings_used']} filing accessions; {quality['excluded_observations']} excluded."
        )
    lines.extend(["", "## Static strategy controls", ""])
    for name, control in manifest.get("strategy_controls", {}).items():
        lines.append(f"- {name}: {control['cagr']:.1%} CAGR over {control['periods']} realized quarters.")
    lines.extend([
        "",
        "## Warnings",
        "",
        "- Five securities produce a very small cross-section. Results are exploratory and unstable.",
        "- The universe is a hand-picked set of present-day mega-cap survivors/winners, not a point-in-time investable universe. Strategy performance cannot establish security-selection alpha.",
        "- The lowest-MAE configuration was selected after comparing multiple model/feature specifications on the same OOS history; it is not a pristine final holdout result.",
        "- Quarterly 12-month labels overlap. Ranking diagnostics use them, but strategy CAGR uses only next-anchor holding returns.",
        "- The portfolio is a quarterly rank-rebalance proxy that exits roughly three months into a 12-month forecast, not a direct 12-month holding implementation.",
        "- Portfolio max drawdown uses quarterly rebalance endpoints and can understate intraperiod drawdown. Turnover uses target-weight changes rather than drifted pre-trade weights.",
        "- Company Facts may correct same-accession content without exposing the historical API version; formal amendments remain point-in-time safe.",
        "- Historical share dilution is omitted because share series are not normalized across splits.",
        "- No hyperparameter search was performed.",
        "- Negative out-of-sample R² or failure to beat the naive MAE means the experiment has not established robust forecasting signal, even if a concentrated ranking portfolio performed well.",
    ])
    return "\n".join(lines) + "\n"
