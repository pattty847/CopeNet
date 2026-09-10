"""Format precomputed ticker technical facts without changing their availability."""

from .features import FeatureSet
from .base_rates import BaseRate


def quality_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    quality = [f"history {fs.history_weeks} weeks"]
    if fs.thin_history:
        quality.append("THIN HISTORY — treat all trend/shape facts as low-confidence")
    if not fs.has_volume:
        quality.append("no volume data — volume facts unavailable")
    sections.append("DATA QUALITY: " + "; ".join(quality))

    return sections


def return_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    returns = []
    for label, value in (
        ("1w", fs.r_1w),
        ("4w", fs.r_4w),
        ("13w", fs.r_13w),
        ("26w", fs.r_26w),
        ("52w", fs.r_52w),
        ("YTD", fs.r_ytd),
    ):
        if value is not None:
            returns.append(f"{label} {value:+.1f}%")
    if returns:
        sections.append("RETURNS: " + ", ".join(returns))

    return sections


def trend_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    trend_bits = [f"MA stack: {fs.ma_stack}"]
    for label, dist, slope in (
        ("10w", fs.dist_ma10, fs.slope_ma10),
        ("30w", fs.dist_ma30, fs.slope_ma30),
        ("40w", fs.dist_ma40, fs.slope_ma40),
    ):
        if dist is not None:
            slope_txt = f", slope {slope:+.1f}%/5w" if slope is not None else ""
            trend_bits.append(f"{label} MA {dist:+.1f}% away{slope_txt}")
    sections.append("TREND: " + "; ".join(trend_bits))

    return sections


def structure_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    # multi-year structure — the horizon a human reads off a 5y chart
    structure_bits = []
    if fs.r_3y is not None:
        structure_bits.append(f"3y return {fs.r_3y:+.0f}%")
    if fs.dist_hi_full is not None and fs.weeks_since_hi_full is not None:
        structure_bits.append(
            f"{fs.dist_hi_full:+.1f}% from the multi-year high set {fs.weeks_since_hi_full}w ago"
        )
    if fs.pct_range_full is not None:
        structure_bits.append(f"at {fs.pct_range_full:.0f}% of the full historical range")
    if fs.long_trend != "n/a" and fs.long_trend_slope is not None:
        structure_bits.append(f"long trend (2y regression): {fs.long_trend} ~{fs.long_trend_slope:+.0f}%/yr")
    if structure_bits:
        years = fs.history_weeks / 52
        sections.append(
            f"STRUCTURE (multi-year, {years:.1f}y of weekly history): " + "; ".join(structure_bits)
        )
    if fs.range_ratio_12v36 is not None:
        line = f"RANGE BEHAVIOR: last-12w range is {fs.range_ratio_12v36:.2f}x the prior-24w range"
        if fs.compression:
            line += f" — CONSOLIDATION detected ({fs.compression_shape or 'compressed'}"
            if fs.compression_shape == "symmetrical":
                line += ": lower highs + higher lows converging"
            line += ")"
        sections.append(line)

    return sections


def risk_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    risk_bits = []
    if fs.drawdown_pct is not None:
        risk_bits.append(f"drawdown {fs.drawdown_pct:+.1f}% from 52w high")
    if fs.weeks_since_high is not None:
        risk_bits.append(f"{fs.weeks_since_high}w since high")
    if fs.pct_52w is not None:
        risk_bits.append(f"at {fs.pct_52w:.0f}% of 52w range")
    if fs.vol_13w is not None:
        risk_bits.append(f"13w realized vol {fs.vol_13w:.0f}% ann.")
    if fs.atr_pctile is not None:
        risk_bits.append(f"ATR percentile {fs.atr_pctile:.0f}")
    if risk_bits:
        sections.append("RISK STATE: " + "; ".join(risk_bits))

    return sections


def relative_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    rel_bits = []
    if fs.excess_13w is not None:
        rel_bits.append(f"13w excess return vs benchmark {fs.excess_13w:+.1f}%")
    if fs.excess_26w is not None:
        rel_bits.append(f"26w excess {fs.excess_26w:+.1f}%")
    if fs.beta_52w is not None:
        rel_bits.append(f"beta {fs.beta_52w:.2f}")
    if fs.rs_momentum is not None:
        rel_bits.append(f"RS momentum {fs.rs_momentum:+.1f}")
    if fs.rsi_14 is not None:
        rel_bits.append(f"RSI(14w) {fs.rsi_14:.0f}")
    if rel_bits:
        sections.append("RELATIVE: " + "; ".join(rel_bits))

    return sections


def volume_sections(fs: FeatureSet) -> list[str]:
    sections: list[str] = []
    vol_bits = []
    if fs.vol_vs_avg is not None:
        vol_bits.append(f"last-week volume {fs.vol_vs_avg:.1f}x 20w avg")
    if fs.up_down_vol is not None:
        vol_bits.append(f"13w up/down volume ratio {fs.up_down_vol:.2f}")
    if vol_bits:
        sections.append("VOLUME: " + "; ".join(vol_bits))

    return sections


def pattern_sections(fs: FeatureSet, base_rate: BaseRate | None) -> list[str]:
    sections: list[str] = []
    if fs.soft_bottoming:
        met = []
        for label, flag in (
            ("lower lows stopped", fs.sb_lower_lows_stopped),
            ("higher low", fs.sb_higher_low),
            ("short-MA reclaim", fs.sb_ma_reclaim),
            ("drawdown stabilized", fs.sb_drawdown_stabilized),
            ("RS improving", fs.sb_rs_improving),
            ("decline volume drying", fs.sb_volume_drying),
            ("momentum divergence", fs.sb_momentum_divergence),
        ):
            met.append(f"{label}: {'yes' if flag else 'no'}")
        line = f"PATTERN — SOFT BOTTOMING FIRING (score {fs.soft_bottoming_score}): " + "; ".join(met)
        if base_rate is not None and base_rate.n >= 5:
            line += f". Calibrated base rate: {base_rate.headline()}."
        sections.append(line)

    return sections
