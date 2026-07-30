#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified analysis module for GNSS multi-antenna interference comparison."""
import math
from collections import defaultdict

import numpy as np
import pandas as pd

from gnss_config import is_interference


# ---------------------------------------------------------------------------
# Basic statistics
# ---------------------------------------------------------------------------

def fmt(v, digits=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def html_table(rows, headers):
    if not rows:
        return "<p>无数据</p>"
    s = "<table><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    for r in rows:
        s += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    s += "</table>"
    return s


def per_svid_stats(df):
    """Overall per-satellite C/No statistics."""
    stats = []
    for svid, g in df.groupby("svid"):
        vals = g["cno"].values
        if len(vals) < 3:
            continue
        stats.append({
            "svid": svid, "sys": g["sys"].iloc[0],
            "n": len(vals),
            "max": float(np.max(vals)), "min": float(np.min(vals)),
            "p25": float(np.percentile(vals, 25)),
            "p75": float(np.percentile(vals, 75)),
            "median": float(np.median(vals)),
            "mean": float(np.mean(vals)),
        })
    return pd.DataFrame(stats).sort_values(["sys", "svid"])


def per_svid_stats_per_segment(ch_df, segments):
    """Per-satellite C/No stats for each segment middle window."""
    results = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        seg_df = ch_df[(ch_df["sow"] >= ms) & (ch_df["sow"] < me)]
        for svid, g in seg_df.groupby("svid"):
            vals = g["cno"].values
            if len(vals) < 1:
                continue
            results.append({
                "segment": seg["label"],
                "svid": svid, "sys": g["sys"].iloc[0],
                "n": len(vals),
                "max": float(np.max(vals)), "min": float(np.min(vals)),
                "p25": float(np.percentile(vals, 25)),
                "p75": float(np.percentile(vals, 75)),
                "median": float(np.median(vals)),
            })
    return pd.DataFrame(results)


def segment_metrics(ch_df, bp_df, gst_df, gsv_df, segments):
    """Compute metrics for each segment middle window."""
    metrics = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        cdf = ch_df[(ch_df["sow"] >= ms) & (ch_df["sow"] < me)]
        bdf = bp_df[(bp_df["sow"] >= ms) & (bp_df["sow"] < me)] if not bp_df.empty else pd.DataFrame()
        gdf = gst_df[(gst_df["sow"] >= ms) & (gst_df["sow"] < me)] if not gst_df.empty else pd.DataFrame()
        vdf = gsv_df[(gsv_df["sow"] >= ms) & (gsv_df["sow"] < me)] if not gsv_df.empty else pd.DataFrame()

        cno_by_sv = {}
        if not cdf.empty:
            for svid, g in cdf.groupby("svid"):
                cno_by_sv[svid] = {
                    "n": len(g), "median": float(g["cno"].median()),
                    "mean": float(g["cno"].mean()),
                    "p25": float(g["cno"].quantile(0.25)),
                    "p75": float(g["cno"].quantile(0.75)),
                }

        if not cdf.empty:
            cno_all = cdf["cno"].values
            agg_cno = {
                "median": float(np.median(cno_all)), "mean": float(np.mean(cno_all)),
                "p25": float(np.percentile(cno_all, 25)),
                "p75": float(np.percentile(cno_all, 75)),
            }
            pll_ratio = float((cdf["state"] == "PLL_LOCK").mean())
            lockzero_ratio = float((cdf["locktime"] < 0.5).mean())
            reject_ratio = float((cdf["reject"] != "GOOD").mean())
            n_tracked = int(cdf.groupby("sow")["svid"].nunique().mean())
        else:
            agg_cno = None
            pll_ratio = lockzero_ratio = reject_ratio = None
            n_tracked = 0

        if not bdf.empty:
            pos_counts = bdf["pos_type"].value_counts().to_dict()
            best_type = bdf["pos_type"].iloc[np.argmax(bdf["pos_type"].apply(pos_score))]
            avg_svs = float(bdf["svs"].mean())
            avg_soln = float(bdf["soln_svs"].mean())
        else:
            pos_counts = {}; best_type = None; avg_svs = avg_soln = None

        pr_rms = float(gdf["pr_rms"].median()) if not gdf.empty else None

        vis_by_sys = {}
        if not vdf.empty:
            for talker, g in vdf.groupby("talker"):
                vis_by_sys[talker] = float(g.groupby("sow")["in_view"].first().mean())

        metrics.append({
            "idx": seg["idx"], "label": seg["label"],
            "start": seg["start"], "end": seg["end"],
            "middle_start": ms, "middle_end": me,
            "middle_duration": seg["middle_duration"],
            "truncated": seg["truncated"],
            "cno_by_sv": cno_by_sv,
            "agg_cno": agg_cno,
            "pll_ratio": pll_ratio,
            "lockzero_ratio": lockzero_ratio,
            "reject_ratio": reject_ratio,
            "n_tracked": n_tracked,
            "pos_counts": pos_counts,
            "best_pos_type": best_type,
            "avg_svs": avg_svs,
            "avg_soln_svs": avg_soln,
            "pr_rms": pr_rms,
            "visible_by_sys": vis_by_sys,
        })
    return pd.DataFrame(metrics)


POS_SCORE = {
    "NONE": 0, "FIXEDPOS": 1, "FIXEDHEIGHT": 2, "FLOATCONV": 3,
    "WIDELANE": 4, "NARROWLANE": 5, "DOPPLER_VELOCITY": 6,
    "SINGLE": 7, "PSRDIFF": 8, "WAAS": 9, "PROPAKDIFF": 10,
    "L1_FLOAT": 11, "IONOFREE_FLOAT": 12, "NARROW_FLOAT": 13,
    "NARROW_INT": 14,
}


def pos_score(pos_type):
    return POS_SCORE.get(pos_type, 0)


def compute_interference_degradation(seg_metrics):
    """For each interference segment, compare with the immediately preceding baseline segment."""
    rows = []
    prev_baseline = None
    prev_label = None
    for _, seg in seg_metrics.iterrows():
        label = seg["label"]
        if is_interference(label):
            if prev_baseline is not None:
                pre = prev_baseline["cno_by_sv"]
                interf = seg["cno_by_sv"]
                for svid, p in pre.items():
                    if svid in interf:
                        rows.append({
                            "baseline_seg": prev_label,
                            "interf_seg": label,
                            "svid": svid,
                            "pre_cno": p["median"],
                            "interf_cno": interf[svid]["median"],
                            "delta": interf[svid]["median"] - p["median"],
                        })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label

    df = pd.DataFrame(rows)
    summary = None
    if not df.empty:
        summary = {
            "median": float(df["delta"].median()),
            "mean": float(df["delta"].mean()),
            "p25": float(df["delta"].quantile(0.25)),
            "p75": float(df["delta"].quantile(0.75)),
            "n_pairs": len(df),
        }
    return df, summary


def compute_satellite_loss(ch_df, segments, min_loss_sec=3.0):
    """For each interference segment, compute satellites continuously lost vs preceding baseline."""
    results = []
    if ch_df.empty or not segments:
        return pd.DataFrame(results)

    sows = sorted(ch_df["sow"].unique())
    if len(sows) < 2:
        return pd.DataFrame(results)
    dt = float(np.median(np.diff(sows)))
    min_epochs = max(1, int(round(min_loss_sec / dt)))

    def _continuous_loss(df, ms, me, svid):
        epochs = sorted(df[(df["sow"] >= ms) & (df["sow"] < me) & (df["svid"] == svid)]["sow"].tolist())
        if not epochs:
            return True, me - ms
        gaps = []
        prev_ep = ms
        for ep in epochs:
            gaps.append(ep - prev_ep)
            prev_ep = ep
        gaps.append(me - prev_ep)
        max_gap = max(gaps)
        return max_gap >= min_loss_sec, max_gap

    prev_baseline = None
    prev_label = None
    for seg in segments:
        label = seg["label"]
        ms, me = seg["middle_start"], seg["middle_end"]
        if is_interference(label) and prev_baseline is not None:
            bms, bme = prev_baseline["middle_start"], prev_baseline["middle_end"]
            bdf = ch_df[(ch_df["sow"] >= bms) & (ch_df["sow"] < bme)]
            baseline_svs = set(bdf["svid"].unique())
            idf = ch_df[(ch_df["sow"] >= ms) & (ch_df["sow"] < me)]

            lost = []
            lost_durations = []
            for svid in baseline_svs:
                lost_flag, gap = _continuous_loss(ch_df, ms, me, svid)
                if lost_flag:
                    lost.append(svid)
                    lost_durations.append(gap)

            gained = sorted(set(idf["svid"].unique()) - baseline_svs)
            results.append({
                "baseline_seg": prev_label,
                "interf_seg": label,
                "n_lost": len(lost),
                "n_gained": len(gained),
                "lost_svids": ",".join(sorted(lost)),
                "gained_svids": ",".join(gained),
                "lost_durations": ",".join(f"{d:.1f}" for d in lost_durations),
                "min_loss_sec": min_loss_sec,
            })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label
    return pd.DataFrame(results)


def assess_interference(seg_metrics, sat_loss_df):
    """Per-antenna per-interference-type assessment against ETSI 1 dB criterion."""
    rows = []
    prev_baseline = None
    for _, seg in seg_metrics.iterrows():
        label = seg["label"]
        if is_interference(label) and prev_baseline is not None:
            deltas = []
            pre = prev_baseline["cno_by_sv"]
            interf = seg["cno_by_sv"]
            for svid, p in pre.items():
                if svid in interf and p["n"] >= 5 and interf[svid]["n"] >= 5:
                    deltas.append(interf[svid]["median"] - p["median"])
            delta_med = float(np.median(deltas)) if deltas else None
            delta_p25 = float(np.percentile(deltas, 25)) if deltas else None
            delta_p75 = float(np.percentile(deltas, 75)) if deltas else None
            loss_row = sat_loss_df[sat_loss_df["interf_seg"] == label]
            n_lost = int(loss_row["n_lost"].values[0]) if not loss_row.empty else 0
            pll_change = (seg["pll_ratio"] - prev_baseline["pll_ratio"]) * 100 if seg["pll_ratio"] is not None and prev_baseline["pll_ratio"] is not None else None
            etsi_pass = delta_med is not None and delta_med >= -1.0
            rows.append({
                "interf_seg": label,
                "delta_median": delta_med,
                "delta_p25": delta_p25,
                "delta_p75": delta_p75,
                "n_lost": n_lost,
                "pll_change_pct": pll_change,
                "etsi_pass": etsi_pass,
            })
        if label.startswith("无干扰"):
            prev_baseline = seg
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Correlation and significance
# ---------------------------------------------------------------------------

def pearson_r(x, y):
    """Pearson correlation coefficient."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    if len(x) < 3:
        return None
    mx, my = np.mean(x), np.mean(y)
    sx, sy = np.std(x, ddof=0), np.std(y, ddof=0)
    if sx == 0 or sy == 0:
        return None
    return float(np.mean((x - mx) * (y - my)) / (sx * sy))


def fisher_z_avg(rs):
    """Average correlation coefficients via Fisher z-transform."""
    rs = np.array(rs, dtype=float)
    rs = rs[(rs > -1.0) & (rs < 1.0)]
    if len(rs) == 0:
        return None
    zs = 0.5 * np.log((1.0 + rs) / (1.0 - rs))
    z_mean = np.mean(zs)
    r_mean = (np.exp(2.0 * z_mean) - 1.0) / (np.exp(2.0 * z_mean) + 1.0)
    return float(r_mean)


def compute_antenna_correlation(ch_df1, ch_df2):
    """Compute per-satellite and overall C/No correlation between two antennas."""
    svids = sorted(set(ch_df1["svid"].unique()) & set(ch_df2["svid"].unique()))
    rows = []
    all_x, all_y = [], []
    for svid in svids:
        d1 = ch_df1[ch_df1["svid"] == svid][["sow", "cno"]].rename(columns={"cno": "cno1"})
        d2 = ch_df2[ch_df2["svid"] == svid][["sow", "cno"]].rename(columns={"cno": "cno2"})
        merged = pd.merge(d1, d2, on="sow", how="inner")
        if len(merged) < 30:
            continue
        r = pearson_r(merged["cno1"].values, merged["cno2"].values)
        rows.append({
            "svid": svid,
            "sys": ch_df1[ch_df1["svid"] == svid]["sys"].iloc[0],
            "n": len(merged),
            "r": r,
        })
        all_x.extend(merged["cno1"].tolist())
        all_y.extend(merged["cno2"].tolist())
    df = pd.DataFrame(rows).sort_values(["sys", "svid"])
    overall_r = pearson_r(all_x, all_y) if len(all_x) >= 5 else None

    stats = {
        "overall_r": overall_r,
        "n_total": len(df),
    }
    if not df.empty:
        stats["fisher_z_avg_r"] = fisher_z_avg(df["r"].dropna())
        stats["r_median"] = float(df["r"].median())
        stats["r_mean"] = float(df["r"].mean())
        stats["r_p25"] = float(df["r"].quantile(0.25))
        stats["r_p75"] = float(df["r"].quantile(0.75))
        stats["n_strong"] = int((df["r"].abs() >= 0.7).sum())
        stats["n_moderate"] = int(((df["r"].abs() >= 0.4) & (df["r"].abs() < 0.7)).sum())
        stats["n_weak"] = int((df["r"].abs() < 0.4).sum())

        by_system = []
        for sys, g in df.groupby("sys"):
            by_system.append({
                "sys": sys,
                "n": len(g),
                "fisher_z_avg_r": fisher_z_avg(g["r"].dropna()),
                "r_median": float(g["r"].median()),
                "r_mean": float(g["r"].mean()),
                "n_strong": int((g["r"].abs() >= 0.7).sum()),
                "n_moderate": int(((g["r"].abs() >= 0.4) & (g["r"].abs() < 0.7)).sum()),
                "n_weak": int((g["r"].abs() < 0.4).sum()),
            })
        stats["by_system"] = pd.DataFrame(by_system)
    else:
        stats["fisher_z_avg_r"] = None
        stats["r_median"] = stats["r_mean"] = stats["r_p25"] = stats["r_p75"] = None
        stats["n_strong"] = stats["n_moderate"] = stats["n_weak"] = 0
        stats["by_system"] = pd.DataFrame()

    return df, overall_r, stats


def wilcoxon_signed_rank(diffs):
    """Wilcoxon signed-rank test, normal approximation with tie correction."""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    if n < 5:
        return None
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    tie_sum = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-12:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        t = j - i + 1
        if t > 1:
            tie_sum += t ** 3 - t
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_sum / 48.0
    if var <= 0:
        return None
    z = (w_plus - mean - math.copysign(0.5, w_plus - mean)) / math.sqrt(var)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return n, z, p


def compute_segment_wilcoxon(ant_data, first_ant, second_ant):
    """Per-segment Wilcoxon signed-rank test on paired first_ant vs second_ant C/No differences."""
    results = []
    seg_labels = [s["label"] for s in ant_data[first_ant]["segments"] if s["middle_duration"] > 0]
    for label in seg_labels:
        s1 = ant_data[first_ant]["seg_stats"][ant_data[first_ant]["seg_stats"]["segment"] == label]
        s2 = ant_data[second_ant]["seg_stats"][ant_data[second_ant]["seg_stats"]["segment"] == label]
        common = set(s1["svid"]) & set(s2["svid"])
        diffs = []
        for svid in common:
            n1 = int(s1[s1["svid"] == svid]["n"].values[0])
            n2 = int(s2[s2["svid"] == svid]["n"].values[0])
            if n1 < 5 or n2 < 5:
                continue
            m1 = s1[s1["svid"] == svid]["median"].values[0]
            m2 = s2[s2["svid"] == svid]["median"].values[0]
            diffs.append(m1 - m2)
        w = wilcoxon_signed_rank(diffs)
        results.append({
            "segment": label,
            "n_pairs": len(diffs),
            "median_diff": float(np.median(diffs)) if diffs else None,
            "wilcoxon_z": w[1] if w else None,
            "wilcoxon_p": w[2] if w else None,
            "significant": (w[2] < 0.05) if w else None,
        })
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# RANGECMP analysis
# ---------------------------------------------------------------------------

def rangecmp_segment_metrics(rangecmp_df, segments):
    """Compute RANGECMP metrics for each segment middle window."""
    rows = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        df = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
        if df.empty:
            rows.append({
                "label": seg["label"], "n": 0,
                "std_psr_median": None, "std_psr_mean": None,
                "std_psr_p25": None, "std_psr_p75": None,
                "std_adr_median": None, "std_adr_mean": None,
                "locktime_median": None, "locktime_p25": None,
                "doppler_std": None, "cno_median": None,
            })
            continue
        rows.append({
            "label": seg["label"],
            "n": len(df),
            "std_psr_median": float(df["std_psr"].median()),
            "std_psr_mean": float(df["std_psr"].mean()),
            "std_psr_p25": float(df["std_psr"].quantile(0.25)),
            "std_psr_p75": float(df["std_psr"].quantile(0.75)),
            "std_adr_median": float(df["std_adr"].median()),
            "std_adr_mean": float(df["std_adr"].mean()),
            "locktime_median": float(df["locktime"].median()),
            "locktime_p25": float(df["locktime"].quantile(0.25)),
            "doppler_std": float(df["doppler"].std()),
            "cno_median": float(df["cno"].median()),
        })
    return pd.DataFrame(rows)


def rangecmp_per_svid_stats(rangecmp_df, segments):
    """Per-satellite RANGECMP stats for each segment middle window."""
    rows = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        df = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
        for svid, g in df.groupby("svid"):
            if len(g) < 3:
                continue
            rows.append({
                "segment": seg["label"], "svid": svid, "sys": g["sys"].iloc[0],
                "n": len(g),
                "std_psr_median": float(g["std_psr"].median()),
                "std_psr_max": float(g["std_psr"].max()),
                "std_adr_median": float(g["std_adr"].median()),
                "locktime_median": float(g["locktime"].median()),
                "cno_median": float(g["cno"].median()),
            })
    return pd.DataFrame(rows)


def rangecmp_degradation(rangecmp_df, segments):
    """Compute per-satellite std_psr degradation for interference segments."""
    rows = []
    prev_baseline = None
    prev_label = None
    for seg in segments:
        label = seg["label"]
        ms, me = seg["middle_start"], seg["middle_end"]
        if is_interference(label) and prev_baseline is not None:
            bms, bme = prev_baseline["middle_start"], prev_baseline["middle_end"]
            bdf = rangecmp_df[(rangecmp_df["sow"] >= bms) & (rangecmp_df["sow"] < bme)]
            idf = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
            bstats = bdf.groupby("svid")["std_psr"].median()
            istats = idf.groupby("svid")["std_psr"].median()
            for svid in bstats.index:
                if svid in istats.index:
                    rows.append({
                        "baseline_seg": prev_label,
                        "interf_seg": label,
                        "svid": svid,
                        "sys": bdf[bdf["svid"] == svid]["sys"].iloc[0],
                        "baseline_std_psr": float(bstats[svid]),
                        "interf_std_psr": float(istats[svid]),
                        "delta": float(istats[svid] - bstats[svid]),
                    })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label
    return pd.DataFrame(rows)


def rangecmp_degradation_by_system(rangecmp_df, segments):
    """Per-system StdDev-PSR degradation for interference segments."""
    deg = rangecmp_degradation(rangecmp_df, segments)
    if deg.empty:
        return pd.DataFrame()
    rows = []
    for (baseline, interf, sys), g in deg.groupby(["baseline_seg", "interf_seg", "sys"]):
        rows.append({
            "baseline_seg": baseline,
            "interf_seg": interf,
            "sys": sys,
            "n": len(g),
            "delta_median": float(g["delta"].median()),
            "delta_mean": float(g["delta"].mean()),
            "delta_p25": float(g["delta"].quantile(0.25)),
            "delta_p75": float(g["delta"].quantile(0.75)),
            "n_increase": int((g["delta"] > 0).sum()),
            "n_decrease": int((g["delta"] < 0).sum()),
        })
    return pd.DataFrame(rows)


def rangecmp_adr_analysis(rangecmp_df, segments):
    """StdDev-ADR analysis per segment and per system."""
    rows = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        df = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
        for sys, g in df.groupby("sys"):
            if len(g) < 3:
                continue
            rows.append({
                "segment": seg["label"], "sys": sys,
                "n": len(g),
                "std_adr_median": float(g["std_adr"].median()),
                "std_adr_mean": float(g["std_adr"].mean()),
                "std_adr_p75": float(g["std_adr"].quantile(0.75)),
                "std_adr_max": float(g["std_adr"].max()),
            })
    return pd.DataFrame(rows)


def rangecmp_adr_degradation(rangecmp_df, segments):
    """Per-satellite StdDev-ADR degradation for interference segments."""
    rows = []
    prev_baseline = None
    prev_label = None
    for seg in segments:
        label = seg["label"]
        ms, me = seg["middle_start"], seg["middle_end"]
        if is_interference(label) and prev_baseline is not None:
            bms, bme = prev_baseline["middle_start"], prev_baseline["middle_end"]
            bdf = rangecmp_df[(rangecmp_df["sow"] >= bms) & (rangecmp_df["sow"] < bme)]
            idf = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
            bstats = bdf.groupby("svid")["std_adr"].median()
            istats = idf.groupby("svid")["std_adr"].median()
            for svid in bstats.index:
                if svid in istats.index:
                    rows.append({
                        "baseline_seg": prev_label,
                        "interf_seg": label,
                        "svid": svid,
                        "sys": bdf[bdf["svid"] == svid]["sys"].iloc[0],
                        "baseline_std_adr": float(bstats[svid]),
                        "interf_std_adr": float(istats[svid]),
                        "delta": float(istats[svid] - bstats[svid]),
                    })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label
    return pd.DataFrame(rows)


def joint_locktime_analysis(ch_df, rangecmp_df, segments, min_loss_sec=3.0):
    """Joint locktime loss analysis combining TRACKSTAT and RANGECMP."""
    rows = []
    if ch_df.empty or rangecmp_df.empty or not segments:
        return pd.DataFrame(rows)

    sows = sorted(ch_df["sow"].unique())
    if len(sows) < 2:
        return pd.DataFrame(rows)
    dt = float(np.median(np.diff(sows)))
    min_epochs = max(1, int(round(min_loss_sec / dt)))

    def _continuous_loss(df, ms, me, svid):
        epochs = sorted(df[(df["sow"] >= ms) & (df["sow"] < me) & (df["svid"] == svid)]["sow"].tolist())
        if not epochs:
            return True, me - ms
        gaps = []
        prev_ep = ms
        for ep in epochs:
            gaps.append(ep - prev_ep)
            prev_ep = ep
        gaps.append(me - prev_ep)
        max_gap = max(gaps)
        return max_gap >= min_loss_sec, max_gap

    prev_baseline = None
    prev_label = None
    for seg in segments:
        label = seg["label"]
        ms, me = seg["middle_start"], seg["middle_end"]
        if is_interference(label) and prev_baseline is not None:
            bms, bme = prev_baseline["middle_start"], prev_baseline["middle_end"]
            b_track = ch_df[(ch_df["sow"] >= bms) & (ch_df["sow"] < bme)]
            b_rc = rangecmp_df[(rangecmp_df["sow"] >= bms) & (rangecmp_df["sow"] < bme)]
            baseline_svs = set(b_track["svid"].unique()) | set(b_rc["svid"].unique())

            for svid in baseline_svs:
                track_lost, track_gap = _continuous_loss(ch_df, ms, me, svid)
                rc_lost, rc_gap = _continuous_loss(rangecmp_df, ms, me, svid)
                sys_name = "UNK"
                tsub = b_track[b_track["svid"] == svid]
                rsub = b_rc[b_rc["svid"] == svid]
                if not tsub.empty:
                    sys_name = tsub["sys"].iloc[0]
                elif not rsub.empty:
                    sys_name = rsub["sys"].iloc[0]
                rows.append({
                    "baseline_seg": prev_label,
                    "interf_seg": label,
                    "svid": svid,
                    "sys": sys_name,
                    "track_gap_sec": float(track_gap),
                    "rc_gap_sec": float(rc_gap),
                    "track_lost": track_lost,
                    "rc_lost": rc_lost,
                    "both_lost": track_lost and rc_lost,
                })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label
    return pd.DataFrame(rows)


def list_both_lost_satellites(joint_lock_df):
    """List satellites lost from both TRACKSTAT and RANGECMP."""
    if joint_lock_df.empty:
        return pd.DataFrame()
    rows = []
    for _, r in joint_lock_df[joint_lock_df["both_lost"]].iterrows():
        rows.append({
            "interf_seg": r["interf_seg"],
            "svid": r["svid"],
            "sys": r["sys"],
            "track_gap_sec": r["track_gap_sec"],
            "rc_gap_sec": r["rc_gap_sec"],
        })
    return pd.DataFrame(rows)


def rangecmp_band_analysis(rangecmp_df, segments):
    """Per-band (L1/L2/L5/E1/E5a/B1/B2 etc.) RANGECMP metrics per segment."""
    rows = []
    for seg in segments:
        ms, me = seg["middle_start"], seg["middle_end"]
        df = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
        for band, g in df.groupby("sig_band"):
            if len(g) < 3:
                continue
            rows.append({
                "segment": seg["label"], "band": band,
                "n": len(g),
                "std_psr_median": float(g["std_psr"].median()),
                "std_psr_mean": float(g["std_psr"].mean()),
                "std_adr_median": float(g["std_adr"].median()),
                "cno_median": float(g["cno"].median()),
                "locktime_median": float(g["locktime"].median()),
            })
    return pd.DataFrame(rows)


def rangecmp_band_degradation(rangecmp_df, segments):
    """Per-band StdDev-PSR degradation for interference segments."""
    rows = []
    prev_baseline = None
    prev_label = None
    for seg in segments:
        label = seg["label"]
        ms, me = seg["middle_start"], seg["middle_end"]
        if is_interference(label) and prev_baseline is not None:
            bms, bme = prev_baseline["middle_start"], prev_baseline["middle_end"]
            bdf = rangecmp_df[(rangecmp_df["sow"] >= bms) & (rangecmp_df["sow"] < bme)]
            idf = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
            for band in set(bdf["sig_band"].unique()) | set(idf["sig_band"].unique()):
                b_g = bdf[bdf["sig_band"] == band]
                i_g = idf[idf["sig_band"] == band]
                if len(b_g) < 3 or len(i_g) < 3:
                    continue
                rows.append({
                    "baseline_seg": prev_label,
                    "interf_seg": label,
                    "band": band,
                    "baseline_std_psr": float(b_g["std_psr"].median()),
                    "interf_std_psr": float(i_g["std_psr"].median()),
                    "delta": float(i_g["std_psr"].median() - b_g["std_psr"].median()),
                    "baseline_cno": float(b_g["cno"].median()),
                    "interf_cno": float(i_g["cno"].median()),
                    "delta_cno": float(i_g["cno"].median() - b_g["cno"].median()),
                })
        if label.startswith("无干扰"):
            prev_baseline = seg
            prev_label = label
    return pd.DataFrame(rows)


def adr_cno_scatter_data(rangecmp_df, segments):
    """Collect StdDev-ADR vs C/No scatter data per interference segment."""
    rows = []
    for seg in segments:
        label = seg["label"]
        if not is_interference(label):
            continue
        ms, me = seg["middle_start"], seg["middle_end"]
        df = rangecmp_df[(rangecmp_df["sow"] >= ms) & (rangecmp_df["sow"] < me)]
        for band, g in df.groupby("sig_band"):
            if len(g) < 5:
                continue
            rows.append({
                "segment": label,
                "band": band,
                "cno": g["cno"].tolist(),
                "std_adr": g["std_adr"].tolist(),
                "std_psr": g["std_psr"].tolist(),
            })
    return rows
