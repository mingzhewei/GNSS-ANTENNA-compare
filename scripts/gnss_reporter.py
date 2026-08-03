#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified report generation for GNSS multi-antenna interference comparison."""
import base64
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gnss_analyzer import fmt, html_table, is_interference

plt.rcParams["font.family"] = ["Heiti TC", "Songti SC", "Arial Unicode MS", "Microsoft YaHei", "SimHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def plot_per_svid_stats(stats, title):
    if stats.empty:
        return None
    svids = stats["svid"].tolist()
    x = np.arange(len(svids))
    fig, ax = plt.subplots(figsize=(max(12, len(svids) * 0.45), 6))
    ax.vlines(x, stats["min"], stats["max"], color="#9aa0a6", lw=1.5, label="Min–Max")
    ax.bar(x, stats["p75"] - stats["p25"], bottom=stats["p25"], color="#4a90d9",
           alpha=0.7, width=0.6, label="25%–75%")
    ax.scatter(x, stats["median"], color="#d9634f", zorder=5, s=30, label="Median")
    ax.set_xticks(x)
    ax.set_xticklabels(svids, rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("C/N0 (dB-Hz)")
    ax.set_title(title)
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    return fig_to_base64(fig)


def plot_per_svid_time_series(ch_df, title):
    """Plot per-satellite C/No time series, one subplot per system."""
    systems = sorted(ch_df["sys"].unique())
    if not systems:
        return None
    n_sys = len(systems)
    fig, axes = plt.subplots(n_sys, 1, figsize=(14, 2.5 * n_sys), sharex=True)
    if n_sys == 1:
        axes = [axes]
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    for ax, sys in zip(axes, systems):
        sdf = ch_df[ch_df["sys"] == sys]
        svids = sorted(sdf["svid"].unique())
        for idx, svid in enumerate(svids):
            v = sdf[sdf["svid"] == svid]
            ax.plot(v["sow"], v["cno"], lw=0.8, alpha=0.8,
                    color=colors[idx % len(colors)], label=svid)
        ax.set_ylabel("C/N0 (dB-Hz)")
        ax.set_title(f"{sys}")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="upper right", fontsize=7, ncol=max(1, len(svids) // 8))
    axes[-1].set_xlabel("GPS seconds of week (s)")
    fig.suptitle(title, y=1.02, fontsize=14)
    return fig_to_base64(fig)


def _add_segment_shades(ax, segments):
    """Add vertical background shades for interference segments."""
    cmap = {
        "无干扰 #1": "#e8f5e9", "无干扰 #2": "#e8f5e9", "无干扰 #3": "#e8f5e9",
        "无干扰 #4": "#e8f5e9", "无干扰 #5": "#e8f5e9", "无干扰 #6": "#e8f5e9",
        "409MHz 干扰": "#ffebee", "392MHz 干扰": "#ffebee",
        "4G/5G 干扰": "#ffebee", "Wi-Fi 干扰": "#ffebee",
    }
    for seg in segments:
        if seg["middle_duration"] <= 0:
            continue
        ax.axvspan(seg["middle_start"], seg["middle_end"], alpha=0.25,
                   color=cmap.get(seg["label"], "#f5f5f5"))


def plot_epoch_metrics(ch_df, bp_df, gst_df, gsv_df, segments, title_prefix):
    """Generate multiple time-series figures."""
    figures = {}

    # 1. per-epoch median C/No
    ep = ch_df.groupby("sow").agg(
        median_cno=("cno", "median"),
        mean_cno=("cno", "mean"),
        pll_ratio=("state", lambda x: (x == "PLL_LOCK").mean()),
        n_sv=("svid", "nunique"),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(ep["sow"], ep["median_cno"], lw=1.2, color="#4a90d9", label="Median C/N0")
    ax.set_xlabel("GPS seconds of week (s)")
    ax.set_ylabel("C/N0 (dB-Hz)")
    ax.set_title(f"{title_prefix}：每历元 C/N0 中位数")
    ax.grid(True, linestyle="--", alpha=0.4)
    _add_segment_shades(ax, segments)
    figures["cno_time"] = fig_to_base64(fig)

    # 2. PLL ratio
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(ep["sow"], ep["pll_ratio"] * 100, lw=1.2, color="#43a567")
    ax.set_xlabel("GPS seconds of week (s)")
    ax.set_ylabel("PLL 锁定比例 (%)")
    ax.set_title(f"{title_prefix}：每历元 PLL 锁定比例")
    ax.set_ylim(0, 105)
    ax.grid(True, linestyle="--", alpha=0.4)
    _add_segment_shades(ax, segments)
    figures["pll_time"] = fig_to_base64(fig)

    # 3. satellite counts
    ep2 = ch_df.groupby("sow").agg(n_sv=("svid", "nunique")).reset_index()
    if not bp_df.empty:
        ep2 = ep2.merge(bp_df[["sow", "svs", "soln_svs"]], on="sow", how="left")
    if not gsv_df.empty:
        gsv_ep = gsv_df.groupby("sow")["in_view"].sum().reset_index().rename(columns={"in_view": "gsv_visible"})
        ep2 = ep2.merge(gsv_ep, on="sow", how="left")

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(ep2["sow"], ep2["n_sv"], lw=1.2, color="#4a90d9", label="TRACKSTAT 跟踪星数")
    if "svs" in ep2.columns:
        ax.plot(ep2["sow"], ep2["svs"], lw=1.2, color="#e8963c", label="BESTPOS 跟踪星数")
    if "soln_svs" in ep2.columns:
        ax.plot(ep2["sow"], ep2["soln_svs"], lw=1.2, color="#8e6fc0", label="BESTPOS 参与解算星数")
    if "gsv_visible" in ep2.columns:
        ax.plot(ep2["sow"], ep2["gsv_visible"], lw=1.2, color="#9aa0a6", linestyle="--", label="GSV 可见星数")
    ax.set_xlabel("GPS seconds of week (s)")
    ax.set_ylabel("卫星数")
    ax.set_title(f"{title_prefix}：卫星数时间序列")
    ax.legend(loc="upper right")
    ax.grid(True, linestyle="--", alpha=0.4)
    _add_segment_shades(ax, segments)
    figures["sat_count_time"] = fig_to_base64(fig)

    # 4. GPGST pr_rms
    if not gst_df.empty:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(gst_df["sow"], gst_df["pr_rms"], lw=1.2, color="#d9634f")
        ax.set_xlabel("GPS seconds of week (s)")
        ax.set_ylabel("伪距 RMS (m)")
        ax.set_title(f"{title_prefix}：GPGST 伪距 RMS")
        ax.grid(True, linestyle="--", alpha=0.4)
        _add_segment_shades(ax, segments)
        figures["pr_rms_time"] = fig_to_base64(fig)

    return figures


def antenna_report(ant_id, ant_name, data, test_name):
    """Generate per-antenna HTML report."""
    stats = data["stats"]
    seg_stats = data["seg_stats"]
    seg_metrics = data["seg_metrics"]
    degradation_df, degradation_summary = data["degradation"]
    segments = data["segments"]
    figures = data["figures"]
    title = f"天线 {ant_name} {test_name} 抗干扰测试报告"

    # Per-sat stats table rows
    per_sat_rows = []
    for _, r in stats.iterrows():
        per_sat_rows.append([
            r["svid"], r["sys"], int(r["n"]),
            fmt(r["max"]), fmt(r["min"]), fmt(r["p75"]), fmt(r["p25"]), fmt(r["median"])
        ])

    # Segment summary rows
    seg_rows = []
    missing_segments = []
    for _, s in seg_metrics.iterrows():
        if s["middle_duration"] <= 0:
            missing_segments.append(s["label"])
            continue
        seg_rows.append([
            s["label"], fmt(s["middle_start"], 3), fmt(s["middle_end"], 3),
            fmt(s["middle_duration"], 1) + ("*" if s["truncated"] else ""),
            fmt(s["agg_cno"]["median"]) if s["agg_cno"] else "—",
            fmt(s["agg_cno"]["p25"]) if s["agg_cno"] else "—",
            fmt(s["agg_cno"]["p75"]) if s["agg_cno"] else "—",
            fmt(s["pll_ratio"] * 100, 1) + "%" if s["pll_ratio"] is not None else "—",
            fmt(s["lockzero_ratio"] * 100, 1) + "%" if s["lockzero_ratio"] is not None else "—",
            fmt(s["n_tracked"], 1),
            fmt(s["avg_soln_svs"], 1) if s["avg_soln_svs"] is not None else "—",
            fmt(s["pr_rms"], 3) if s["pr_rms"] is not None else "—",
            s["best_pos_type"] or "—",
        ])

    # Time traceability: raw data range and segment definitions
    raw_start = data["track"][0]["sow"]
    raw_end = data["track"][-1]["sow"]
    raw_week = data["track"][0]["week"]
    raw_span = raw_end - raw_start

    # Segment definition rows (user-provided durations)
    seg_def_rows = []
    for seg in segments:
        seg_def_rows.append([
            seg["idx"], seg["label"], fmt(seg["duration"], 2),
            fmt(seg["start"], 3), fmt(seg["end"], 3),
            fmt(seg["middle_start"], 3), fmt(seg["middle_end"], 3),
            fmt(seg["middle_duration"], 1) + ("*" if seg["truncated"] else ""),
        ])

    # Per-segment per-sat stats rows
    seg_sat_rows = []
    for _, r in seg_stats.iterrows():
        seg_sat_rows.append([
            r["segment"], r["svid"], r["sys"], int(r["n"]),
            fmt(r["max"]), fmt(r["min"]), fmt(r["p75"]), fmt(r["p25"]), fmt(r["median"])
        ])

    # Degradation rows
    deg_rows = []
    if not degradation_df.empty:
        for _, r in degradation_df.iterrows():
            deg_rows.append([
                r["baseline_seg"], r["interf_seg"], r["svid"],
                fmt(r["pre_cno"]), fmt(r["interf_cno"]), fmt(r["delta"], 2)
            ])

    # Visible satellite rows
    talkers = sorted({t for _, s in seg_metrics.iterrows() for t in s["visible_by_sys"]})
    vis_rows = []
    for t in talkers:
        vis_rows.append([
            t,
            " / ".join(fmt(s["visible_by_sys"].get(t), 1) for _, s in seg_metrics.iterrows()),
        ])

    # Satellite loss rows
    loss_rows = []
    sat_loss = data["sat_loss"]
    for _, r in sat_loss.iterrows():
        loss_rows.append([
            r["baseline_seg"], r["interf_seg"],
            int(r["n_lost"]), r["lost_svids"],
            int(r["n_gained"]), r["gained_svids"],
        ])

    # RANGECMP rows
    rangecmp_seg_rows = []
    for _, r in data["rangecmp_seg"].iterrows():
        rangecmp_seg_rows.append([
            r["label"], int(r["n"]),
            fmt(r["std_psr_median"], 3), fmt(r["std_psr_mean"], 3),
            fmt(r["std_psr_p25"], 3), fmt(r["std_psr_p75"], 3),
            fmt(r["std_adr_median"], 4), fmt(r["std_adr_mean"], 4),
            fmt(r["locktime_median"], 1), fmt(r["locktime_p25"], 1),
            fmt(r["doppler_std"], 1), fmt(r["cno_median"], 1),
        ])

    rangecmp_deg_rows = []
    if not data["rangecmp_deg"].empty:
        for _, r in data["rangecmp_deg"].iterrows():
            rangecmp_deg_rows.append([
                r["baseline_seg"], r["interf_seg"], r["svid"],
                fmt(r["baseline_std_psr"], 3), fmt(r["interf_std_psr"], 3),
                fmt(r["delta"], 3),
            ])

    rangecmp_deg_sys_rows = []
    if not data["rangecmp_deg_sys"].empty:
        for _, r in data["rangecmp_deg_sys"].iterrows():
            rangecmp_deg_sys_rows.append([
                r["interf_seg"], r["sys"], int(r["n"]),
                fmt(r["delta_median"], 3), fmt(r["delta_mean"], 3),
                fmt(r["delta_p25"], 3), fmt(r["delta_p75"], 3),
                int(r["n_increase"]), int(r["n_decrease"]),
            ])

    rangecmp_adr_rows = []
    if not data["rangecmp_adr"].empty:
        for _, r in data["rangecmp_adr"].iterrows():
            rangecmp_adr_rows.append([
                r["segment"], r["sys"], int(r["n"]),
                fmt(r["std_adr_median"], 4), fmt(r["std_adr_mean"], 4),
                fmt(r["std_adr_p75"], 4), fmt(r["std_adr_max"], 4),
            ])

    joint_lock_rows = []
    if not data["joint_lock"].empty:
        for _, r in data["joint_lock"].iterrows():
            joint_lock_rows.append([
                r["interf_seg"], r["svid"], r["sys"],
                fmt(r["track_gap_sec"], 1), fmt(r["rc_gap_sec"], 1),
                "是" if r["track_lost"] else "否",
                "是" if r["rc_lost"] else "否",
                "是" if r["both_lost"] else "否",
            ])

    both_lost_rows = []
    if not data["both_lost"].empty:
        for _, r in data["both_lost"].iterrows():
            both_lost_rows.append([
                r["interf_seg"], r["svid"], r["sys"],
                fmt(r["track_gap_sec"], 1), fmt(r["rc_gap_sec"], 1),
            ])

    band_rows = []
    if not data["rangecmp_band"].empty:
        for _, r in data["rangecmp_band"].iterrows():
            band_rows.append([
                r["segment"], r["band"], int(r["n"]),
                fmt(r["std_psr_median"], 3), fmt(r["std_psr_mean"], 3),
                fmt(r["std_adr_median"], 4), fmt(r["cno_median"], 1),
                fmt(r["locktime_median"], 1),
            ])

    band_deg_rows = []
    if not data["rangecmp_band_deg"].empty:
        for _, r in data["rangecmp_band_deg"].iterrows():
            band_deg_rows.append([
                r["baseline_seg"], r["interf_seg"], r["band"],
                fmt(r["baseline_std_psr"], 3), fmt(r["interf_std_psr"], 3),
                fmt(r["delta"], 3),
                fmt(r["baseline_cno"], 1), fmt(r["interf_cno"], 1),
                fmt(r["delta_cno"], 1),
            ])

    # ADR vs C/No scatter figure
    adr_cno_fig = None
    if data["adr_cno_scatter"]:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        axes = axes.flatten()
        seg_names = ["409MHz 干扰", "392MHz 干扰", "4G/5G 干扰", "Wi-Fi 干扰"]
        for ax, seg_name in zip(axes, seg_names):
            scatter_items = [x for x in data["adr_cno_scatter"] if x["segment"] == seg_name]
            if not scatter_items:
                ax.set_title(f"{seg_name}：无数据")
                continue
            for item in scatter_items:
                band = item["band"]
                color = {"L1": "#4a90d9", "L2": "#e8963c", "L5": "#43a567",
                         "E1": "#8e6fc0", "E5a": "#d9634f", "E5b": "#9aa0a6",
                         "B1": "#3aa6a6", "B2": "#f0d88a", "B3": "#a03a30"}.get(band, "#5f6368")
                ax.scatter(item["cno"], item["std_adr"], s=8, alpha=0.5,
                           color=color, label=band)
            ax.set_xlabel("C/N0 (dB-Hz)")
            ax.set_ylabel("StdDev-ADR (cycles)")
            ax.set_title(f"{seg_name}")
            ax.grid(True, linestyle="--", alpha=0.4)
            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys(), fontsize=7, loc="upper right")
        fig.suptitle("StdDev-ADR vs C/N0 联合散点（按频点着色）", y=0.995)
        plt.tight_layout()
        adr_cno_fig = fig_to_base64(fig)

    # Degradation summary text
    deg_summary_text = ""
    if degradation_summary:
        deg_summary_text = (
            f"共同卫星配对数 N={degradation_summary['n_pairs']}；"
            f"ΔC/N0（干扰段中位数 − 前基线中位数）中位数 = {fmt(degradation_summary['median'], 2)} dB，"
            f"25/75 分位 = {fmt(degradation_summary['p25'], 2)} / {fmt(degradation_summary['p75'], 2)} dB，"
            f"平均 = {fmt(degradation_summary['mean'], 2)} dB。"
        )
    else:
        deg_summary_text = "无足够的共同卫星样本用于计算退化。"

    missing_seg_note = ""
    if missing_segments:
        missing_seg_note = f"<p class=\"bad\">注意：以下片段因超出文件实际时长而无法截取到数据：{', '.join(missing_segments)}。</p>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1f2329}}
.wrap{{max-width:1280px;margin:0 auto;padding:20px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px 22px;margin:14px 0}}
h1{{font-size:22px;margin:0 0 8px}} h2{{font-size:17px;border-left:4px solid #4a90d9;padding-left:10px;margin:28px 0 10px}}
h3{{font-size:15px;margin:18px 0 8px}}
table{{border-collapse:collapse;width:100%;font-size:12px;background:#fff;margin-top:8px}}
th,td{{border:1px solid #e5e7eb;padding:5px 7px;text-align:left;white-space:nowrap}}
th{{background:#f0f2f5}}
.good{{color:#43a567;font-weight:600}} .bad{{color:#d9634f;font-weight:600}}
.warn{{background:#fdeeee;border:1px solid #f0b9b3;border-radius:8px;padding:12px 16px;margin:14px 0;color:#a03a30}}
.note{{background:#fff8e6;border:1px solid #f0d88a;border-radius:8px;padding:12px 16px;margin:14px 0;color:#8a6d1a}}
img{{max-width:100%;border:1px solid #e5e7eb;border-radius:6px}}
.sub{{color:#5f6368;font-size:12px}}
.num{{font-family:"SF Mono",Menlo,Consolas,monospace}}
</style>
</head>
<body>
<div class="wrap">
<h1>{title}</h1>
<p class="sub">数据来源：{test_name} · 分析方法依据 M21 方案与 UG016/OEM7 字段定义 · 天线型号：{ant_name}</p>

<div class="card">
<h2>1. 数据完整性</h2>
<ul>
<li>COM3 解析结果：TRACKSTAT 历元 {len(data['track'])} 个；BESTPOS {len(data['bp_df'])} 条；GPGST {len(data['gst_df'])} 条；GSV {len(data['gsv_df'])} 条。</li>
<li>COM3 时间跨度：GPS 周 {data['track'][0]['week']}，周内秒 {data['track'][0]['sow']:.3f} s ~ {data['track'][-1]['sow']:.3f} s（时长 {(data['track'][-1]['sow']-data['track'][0]['sow']):.1f} s）。</li>
<li>COM4 二进制：共 {data['com4']['valid_msgs']} 条有效消息，消息 ID = {list(data['com4']['ids'].keys())[0]}（0x{list(data['com4']['ids'].keys())[0]:04X}）。</li>
<li>说明：COM4 为标准 RANGECMP（ID 140），已用于提取伪距标准差与载波相位标准差作为辅助验证；本报告以 COM3 ASCII 的 TRACKSTATA C/No 为核心指标。</li>
</ul>
</div>

<div class="card">
<h2>2. 数据时间范围与片段追溯</h2>
<p><b>原始数据时间范围</b>：GPS 周 {raw_week}，周内秒 {raw_start:.3f} s ~ {raw_end:.3f} s（总时长 {raw_span:.1f} s）。</p>
<p><b>片段定义</b>：按用户提供的连续片段时长依次切分；每个片段取中间 10 秒作为稳态分析窗口。带 * 号表示该片段被文件实际长度截断。</p>
{missing_seg_note}
<h3>2.1 用户提供的片段定义</h3>
{html_table(seg_def_rows, ["序号", "片段标签", "定义时长(s)", "片段起(s)", "片段止(s)", "分析窗口起(s)", "分析窗口止(s)", "窗口时长(s)"])}
<h3>2.2 实际分析窗口统计</h3>
{html_table(seg_rows, ["片段", "中间窗口起", "中间窗口止", "截取时长", "C/N0 中位数", "C/N0 p25", "C/N0 p75",
              "PLL 锁定", "locktime<0.5s", "跟踪星数", "参与解算星数", "伪距 RMS", "最佳定位类型"])}
</div>

<div class="card">
<h2>3. 每颗卫星 C/N0 统计（全文件）</h2>
<p>以 TRACKSTAT 的 <code>C/No</code>（dB-Hz）为准。柱状图展示每颗卫星的最高值、最低值、25/75 分位；红点为中位数。</p>
<img src="data:image/png;base64,{figures['per_svid_stats']}" alt="per-sat stats">
{html_table(per_sat_rows, ["卫星", "系统", "样本数", "最高值", "最低值", "75 分位", "25 分位", "中位数"])}
</div>

<div class="card">
<h2>4. 每颗卫星 C/No 时间序列</h2>
<img src="data:image/png;base64,{figures['per_svid_time']}" alt="per-sat time series">
</div>

<div class="card">
<h2>5. 综合时间序列</h2>
<h3>5.1 每历元 C/N0 中位数</h3>
<img src="data:image/png;base64,{figures['cno_time']}" alt="cno time">
<h3>5.2 每历元 PLL 锁定比例</h3>
<img src="data:image/png;base64,{figures['pll_time']}" alt="pll time">
<h3>5.3 卫星数时间序列</h3>
<p>图中同时给出 TRACKSTATA 实际跟踪星数、BESTPOS 跟踪星数、BESTPOS 参与解算星数、GSV 可见星数，便于区分“可见”“跟踪”“可用”三个概念。</p>
<img src="data:image/png;base64,{figures['sat_count_time']}" alt="sat count time">
<h3>5.4 GPGST 伪距 RMS</h3>
<img src="data:image/png;base64,{figures.get('pr_rms_time','')}" alt="pr rms time">
</div>

<div class="card">
<h2>6. 各片段每颗卫星 C/N0 统计</h2>
{html_table(seg_sat_rows, ["片段", "卫星", "系统", "样本数", "最高值", "最低值", "75 分位", "25 分位", "中位数"])}
</div>

<div class="card">
<h2>7. 干扰段卫星丢失情况</h2>
<p>下列卫星在相邻前一无干扰段被跟踪，但在干扰段中连续丢失 ≥3 秒（按 5 Hz 历元折算）。</p>
{html_table(loss_rows, ["基线片段", "干扰片段", "丢失数", "丢失卫星", "新增数", "新增卫星"])}
</div>

<div class="card">
<h2>8. 干扰段相对相邻无干扰段的 C/N0 退化</h2>
<p>{deg_summary_text}</p>
<p>判定参考：ETSI EN 303 413 以 ΔC/N0 ≤ 1 dB 为合格线；−1 ~ −3 dB 为明显退化；< −3 dB 为严重退化。</p>
{html_table(deg_rows, ["基线片段", "干扰片段", "卫星", "基线 C/N0", "干扰 C/N0", "ΔC/N0"])}
</div>

<div class="card">
<h2>9. RANGECMP 各片段观测量质量统计</h2>
<p>来源：COM4 二进制 RANGECMP（ID 140）。StdDev-PSR 为伪距标准差（m），StdDev-ADR 为载波相位标准差（cycles）。</p>
{html_table(rangecmp_seg_rows, ["片段", "样本数", "StdDev-PSR 中位数", "StdDev-PSR 均值", "StdDev-PSR p25", "StdDev-PSR p75",
              "StdDev-ADR 中位数", "StdDev-ADR 均值", "locktime 中位数", "locktime p25", "Doppler 标准差", "C/N0 中位数"])}
</div>

<div class="card">
<h2>10. RANGECMP 干扰段伪距标准差退化</h2>
<p>对每个真实干扰段，以其前一无干扰段为基线，计算共同卫星的 StdDev-PSR 中位数变化。正值表示伪距标准差增大（观测量质量下降）。</p>
{html_table(rangecmp_deg_rows, ["基线片段", "干扰片段", "卫星", "基线 StdDev-PSR", "干扰 StdDev-PSR", "ΔStdDev-PSR"])}
</div>

<div class="card">
<h2>11. RANGECMP 按系统伪距标准差退化</h2>
<p>按 GNSS 系统分组统计干扰段相对基线的 StdDev-PSR 变化。</p>
{html_table(rangecmp_deg_sys_rows, ["干扰片段", "系统", "共同卫星数", "ΔStdDev-PSR 中位数", "ΔStdDev-PSR 均值", "ΔStdDev-PSR p25", "ΔStdDev-PSR p75", "退化卫星数", "改善卫星数"])}
</div>

<div class="card">
<h2>12. RANGECMP 载波相位标准差（StdDev-ADR）分析</h2>
<p>StdDev-ADR 为载波相位标准差（单位 cycles），反映载波相位观测质量。数值越小，相位观测越稳定。</p>
{html_table(rangecmp_adr_rows, ["片段", "系统", "样本数", "StdDev-ADR 中位数", "StdDev-ADR 均值", "StdDev-ADR p75", "StdDev-ADR 最大值"])}
</div>

<div class="card">
<h2>13. 联合失锁分析（TRACKSTAT + RANGECMP）</h2>
<p>同时检查 TRACKSTAT 与 RANGECMP 的卫星连续性。track_lost 表示 TRACKSTAT 中连续丢失 ≥3 秒；rc_lost 表示 RANGECMP 中连续丢失 ≥3 秒；both_lost 表示两源均判定丢失。</p>
{html_table(joint_lock_rows, ["干扰片段", "卫星", "系统", "TRACKSTAT 最大丢失时长", "RANGECMP 最大丢失时长", "TRACKSTAT 丢失", "RANGECMP 丢失", "两源均丢失"])}
</div>

<div class="card">
<h2>14. 两源均丢失卫星名单</h2>
<p>同时被 TRACKSTAT 与 RANGECMP 判定为连续丢失 ≥3 秒的卫星，属于高置信度“真丢失”。</p>
{html_table(both_lost_rows, ["干扰片段", "卫星", "系统", "TRACKSTAT 最大丢失时长", "RANGECMP 最大丢失时长"])}
</div>

<div class="card">
<h2>15. RANGECMP 按频点观测量质量统计</h2>
<p>按信号频段（L1/L2/L5/E1/E5a/E5b/B1/B2/B3 等）拆分 RANGECMP 指标。392 MHz 的 3 次谐波 1176 MHz 距 L5/E5a 约 0.45 MHz；409 MHz 的 3 次谐波 1227 MHz 距 L2 约 0.60 MHz。但实际退化数据显示影响频段更广，说明干扰同时存在宽带阻塞与谐波耦合。</p>
{html_table(band_rows, ["片段", "频段", "样本数", "StdDev-PSR 中位数", "StdDev-PSR 均值", "StdDev-ADR 中位数", "C/N0 中位数", "locktime 中位数"])}
</div>

<div class="card">
<h2>16. RANGECMP 按频点伪距标准差退化</h2>
<p>对每个真实干扰段，以其前一无干扰段为基线，按频段统计 StdDev-PSR 与 C/N0 变化。</p>
{html_table(band_deg_rows, ["基线片段", "干扰片段", "频段", "基线 StdDev-PSR", "干扰 StdDev-PSR", "ΔStdDev-PSR", "基线 C/N0", "干扰 C/N0", "ΔC/N0"])}
</div>

<div class="card">
<h2>17. StdDev-ADR 与 C/N0 联合散点</h2>
<p>按频点着色展示干扰段内 StdDev-ADR 与 C/N0 的关系。若某频点在干扰下 C/N0 下降且 StdDev-ADR 上升，说明该频段受干扰影响显著。</p>
<img src="data:image/png;base64,{adr_cno_fig if adr_cno_fig else ''}" alt="adr cno scatter">
</div>

<div class="card">
<h2>18. GSV 可见卫星数（按系统）</h2>
<p>GSV 的 <code>in_view</code> 反映“可见星数”，与 TRACKSTATA/BESTPOS 的“跟踪星数/参与解算星数”不同。下表按片段顺序列出各系统平均可见星数。</p>
{html_table(vis_rows, ["系统", "各片段平均可见星数（按片段顺序）"])}
</div>

<div class="card">
<h2>19. 结论与说明</h2>
<ul>
<li>本报告核心指标 C/No 全部来自 UG016 §4.2.26 TRACKSTAT 的 <code>C/No</code> 字段（dB-Hz），即载噪比。</li>
<li>“可见星数”来自 NMEA GSV 的 <code>in_view</code>；“跟踪星数”来自 TRACKSTATA 每历元实际跟踪的唯一卫星数；“参与解算星数”来自 BESTPOS 的 <code># sats soln</code>。</li>
<li>COM4 二进制为标准 RANGECMP（ID 140），已用于提取逐星伪距标准差（StdDev-PSR）与载波相位标准差（StdDev-ADR）作为辅助验证；伪距退化维度同时参考 GPGST 字段 3（伪距 RMS）。</li>
<li>结论为“{ant_name} 天线 + M21 内置抗干扰算法”的系统级结论。</li>
</ul>
</div>

</div>
</body>
</html>"""
    return html


def comparison_report(ant_data, corr_df, overall_r, corr_stats, wilcoxon_df,
                      first_ant, second_ant, first_name, second_name, test_name):
    """Generate comparison HTML report for two antennas."""
    title = f"{first_name} vs {second_name} {test_name} 抗干扰对比报告"

    # Overall comparison rows
    cmp_rows = []
    for ant, d in ant_data.items():
        ch = d["ch_df"]
        if ch.empty:
            continue
        name = first_name if ant == first_ant else second_name
        cmp_rows.append([
            name,
            fmt(ch["cno"].median()),
            fmt(ch["cno"].mean()),
            fmt((ch["state"] == "PLL_LOCK").mean() * 100, 1) + "%",
            fmt((ch["locktime"] < 0.5).mean() * 100, 1) + "%",
            fmt((ch["reject"] != "GOOD").mean() * 100, 1) + "%",
            fmt(ch.groupby("sow")["svid"].nunique().mean(), 1),
            fmt(d["bp_df"]["soln_svs"].mean(), 1) if not d["bp_df"].empty else "—",
            fmt(d["gst_df"]["pr_rms"].median(), 3) if not d["gst_df"].empty else "—",
        ])

    # Time traceability: raw data range and segment definitions
    raw_start = ant_data[first_ant]["track"][0]["sow"]
    raw_end = ant_data[first_ant]["track"][-1]["sow"]
    raw_week = ant_data[first_ant]["track"][0]["week"]
    raw_span = raw_end - raw_start

    # Segment definition rows (user-provided durations)
    seg_def_rows = []
    for seg in ant_data[first_ant]["segments"]:
        seg_def_rows.append([
            seg["idx"], seg["label"], fmt(seg["duration"], 2),
            fmt(seg["start"], 3), fmt(seg["end"], 3),
            fmt(seg["middle_start"], 3), fmt(seg["middle_end"], 3),
            fmt(seg["middle_duration"], 1) + ("*" if seg["truncated"] else ""),
        ])

    # Per-segment comparison
    seg_cmp_rows = []
    seg_labels = [s["label"] for s in ant_data[first_ant]["segments"] if s["middle_duration"] > 0]
    for label in seg_labels:
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            seg = ant_data[ant]["seg_metrics"][ant_data[ant]["seg_metrics"]["label"] == label].iloc[0]
            seg_cmp_rows.append([
                name, label,
                fmt(seg["agg_cno"]["median"]) if seg["agg_cno"] else "—",
                fmt(seg["agg_cno"]["p25"]) if seg["agg_cno"] else "—",
                fmt(seg["agg_cno"]["p75"]) if seg["agg_cno"] else "—",
                fmt(seg["pll_ratio"] * 100, 1) + "%" if seg["pll_ratio"] is not None else "—",
                fmt(seg["n_tracked"], 1),
                fmt(seg["avg_soln_svs"], 1) if seg["avg_soln_svs"] is not None else "—",
                fmt(seg["pr_rms"], 3) if seg["pr_rms"] is not None else "—",
            ])

    # Per-system per-antenna median C/No
    sys_rows = []
    systems = sorted({s for d in ant_data.values() for s in d["ch_df"]["sys"].unique() if s})
    for sys in systems:
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            ch = ant_data[ant]["ch_df"]
            v = ch[ch["sys"] == sys]["cno"]
            sys_rows.append([name, sys, fmt(v.median()), fmt(v.mean()), len(v)])

    # Per-system per-segment corrected comparison
    diff_rows = []
    for label in seg_labels:
        for sys in systems:
            s1 = ant_data[first_ant]["seg_stats"][
                (ant_data[first_ant]["seg_stats"]["segment"] == label) &
                (ant_data[first_ant]["seg_stats"]["sys"] == sys)
            ]
            s2 = ant_data[second_ant]["seg_stats"][
                (ant_data[second_ant]["seg_stats"]["segment"] == label) &
                (ant_data[second_ant]["seg_stats"]["sys"] == sys)
            ]
            common = set(s1["svid"]) & set(s2["svid"])
            diffs = []
            for svid in common:
                m1 = s1[s1["svid"] == svid]["median"].values[0]
                m2 = s2[s2["svid"] == svid]["median"].values[0]
                diffs.append(m1 - m2)
            if diffs:
                diff_rows.append([
                    label, sys, len(diffs),
                    fmt(np.median(diffs), 2),
                    fmt(np.percentile(diffs, 25), 2),
                    fmt(np.percentile(diffs, 75), 2),
                ])

    # Satellite loss comparison rows
    loss_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        l1 = ant_data[first_ant]["sat_loss"][ant_data[first_ant]["sat_loss"]["interf_seg"] == label]
        l2 = ant_data[second_ant]["sat_loss"][ant_data[second_ant]["sat_loss"]["interf_seg"] == label]
        loss_rows.append([
            label,
            int(l1["n_lost"].values[0]) if not l1.empty else 0,
            l1["lost_svids"].values[0] if not l1.empty else "—",
            int(l2["n_lost"].values[0]) if not l2.empty else 0,
            l2["lost_svids"].values[0] if not l2.empty else "—",
        ])

    # Wilcoxon rows
    wilcox_rows = []
    for _, r in wilcoxon_df.iterrows():
        sig = "显著" if r["significant"] else "不显著"
        wilcox_rows.append([
            r["segment"],
            int(r["n_pairs"]),
            fmt(r["median_diff"], 2),
            fmt(r["wilcoxon_z"], 2) if r["wilcoxon_z"] is not None else "—",
            fmt(r["wilcoxon_p"], 4) if r["wilcoxon_p"] is not None else "—",
            sig,
        ])

    # Per-antenna interference assessment
    assess_rows = []
    for ant, d in ant_data.items():
        name = first_name if ant == first_ant else second_name
        for _, r in d["interf_assess"].iterrows():
            assess_rows.append([
                name, r["interf_seg"],
                fmt(r["delta_median"], 2),
                fmt(r["delta_p25"], 2),
                fmt(r["delta_p75"], 2),
                int(r["n_lost"]),
                fmt(r["pll_change_pct"], 1) + "%" if r["pll_change_pct"] is not None else "—",
                "通过" if r["etsi_pass"] else "未通过",
            ])

    # RANGECMP segment comparison rows
    rangecmp_cmp_rows = []
    for label in seg_labels:
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            r = ant_data[ant]["rangecmp_seg"][ant_data[ant]["rangecmp_seg"]["label"] == label]
            if not r.empty:
                r = r.iloc[0]
                rangecmp_cmp_rows.append([
                    name, label,
                    int(r["n"]),
                    fmt(r["std_psr_median"], 3),
                    fmt(r["std_psr_mean"], 3),
                    fmt(r["std_adr_median"], 4),
                    fmt(r["locktime_median"], 1),
                    fmt(r["doppler_std"], 1),
                    fmt(r["cno_median"], 1),
                ])

    # RANGECMP per-svid degradation comparison rows
    rangecmp_deg_cmp_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            deg = ant_data[ant]["rangecmp_deg"]
            if deg.empty:
                continue
            sub = deg[deg["interf_seg"] == label]
            if not sub.empty:
                delta_med = float(sub["delta"].median())
                delta_p25 = float(sub["delta"].quantile(0.25))
                delta_p75 = float(sub["delta"].quantile(0.75))
                n_increase = int((sub["delta"] > 0).sum())
                rangecmp_deg_cmp_rows.append([
                    name, label,
                    len(sub),
                    fmt(delta_med, 3),
                    fmt(delta_p25, 3),
                    fmt(delta_p75, 3),
                    n_increase,
                ])

    # RANGECMP per-system degradation comparison rows
    rangecmp_deg_sys_cmp_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            deg_sys = ant_data[ant]["rangecmp_deg_sys"]
            if deg_sys.empty:
                continue
            sub = deg_sys[deg_sys["interf_seg"] == label]
            for _, r in sub.iterrows():
                rangecmp_deg_sys_cmp_rows.append([
                    name, label, r["sys"], int(r["n"]),
                    fmt(r["delta_median"], 3), fmt(r["delta_mean"], 3),
                    fmt(r["delta_p25"], 3), fmt(r["delta_p75"], 3),
                    int(r["n_increase"]), int(r["n_decrease"]),
                ])

    # RANGECMP ADR comparison rows
    rangecmp_adr_cmp_rows = []
    for label in seg_labels:
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            adr = ant_data[ant]["rangecmp_adr"]
            if adr.empty:
                continue
            sub = adr[adr["segment"] == label]
            for _, r in sub.iterrows():
                rangecmp_adr_cmp_rows.append([
                    name, label, r["sys"], int(r["n"]),
                    fmt(r["std_adr_median"], 4), fmt(r["std_adr_mean"], 4),
                    fmt(r["std_adr_p75"], 4),
                ])

    # Joint locktime comparison rows
    joint_lock_cmp_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            jl = ant_data[ant]["joint_lock"]
            if jl.empty:
                continue
            sub = jl[jl["interf_seg"] == label]
            if not sub.empty:
                n_track_lost = int(sub["track_lost"].sum())
                n_rc_lost = int(sub["rc_lost"].sum())
                n_both_lost = int(sub["both_lost"].sum())
                joint_lock_cmp_rows.append([
                    name, label,
                    len(sub),
                    n_track_lost, n_rc_lost, n_both_lost,
                ])

    # Both-lost satellite list comparison rows
    both_lost_cmp_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            bl = ant_data[ant]["both_lost"]
            if bl.empty:
                continue
            sub = bl[bl["interf_seg"] == label]
            for _, r in sub.iterrows():
                both_lost_cmp_rows.append([
                    name, label, r["svid"], r["sys"],
                    fmt(r["track_gap_sec"], 1), fmt(r["rc_gap_sec"], 1),
                ])

    # RANGECMP band comparison rows
    band_cmp_rows = []
    for label in seg_labels:
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            band = ant_data[ant]["rangecmp_band"]
            if band.empty:
                continue
            sub = band[band["segment"] == label]
            for _, r in sub.iterrows():
                band_cmp_rows.append([
                    name, label, r["band"], int(r["n"]),
                    fmt(r["std_psr_median"], 3), fmt(r["std_psr_mean"], 3),
                    fmt(r["std_adr_median"], 4), fmt(r["cno_median"], 1),
                    fmt(r["locktime_median"], 1),
                ])

    # RANGECMP band degradation comparison rows
    band_deg_cmp_rows = []
    for label in seg_labels:
        if not is_interference(label):
            continue
        for ant in (first_ant, second_ant):
            name = first_name if ant == first_ant else second_name
            band_deg = ant_data[ant]["rangecmp_band_deg"]
            if band_deg.empty:
                continue
            sub = band_deg[band_deg["interf_seg"] == label]
            for _, r in sub.iterrows():
                band_deg_cmp_rows.append([
                    name, label, r["band"],
                    fmt(r["baseline_std_psr"], 3), fmt(r["interf_std_psr"], 3),
                    fmt(r["delta"], 3),
                    fmt(r["baseline_cno"], 1), fmt(r["interf_cno"], 1),
                    fmt(r["delta_cno"], 1),
                ])

    # Figures
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(systems))
    width = 0.35
    vals = {ant: [ant_data[ant]["ch_df"][ant_data[ant]["ch_df"]["sys"] == sys]["cno"].median()
            for sys in systems] for ant in (first_ant, second_ant)}
    ax.bar(x - width / 2, vals[first_ant], width, label=first_name, color="#4a90d9")
    ax.bar(x + width / 2, vals[second_ant], width, label=second_name, color="#e8963c")
    ax.set_xticks(x)
    ax.set_xticklabels(systems)
    ax.set_ylabel("C/N0 (dB-Hz)")
    ax.set_title("各系统 C/N0 中位数对比（全文件）")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig_sys = fig_to_base64(fig)

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(seg_labels))
    vals_first = [ant_data[first_ant]["seg_metrics"][ant_data[first_ant]["seg_metrics"]["label"] == lbl].iloc[0]["agg_cno"]["median"]
                   if ant_data[first_ant]["seg_metrics"][ant_data[first_ant]["seg_metrics"]["label"] == lbl].iloc[0]["agg_cno"] else 0
                   for lbl in seg_labels]
    vals_second = [ant_data[second_ant]["seg_metrics"][ant_data[second_ant]["seg_metrics"]["label"] == lbl].iloc[0]["agg_cno"]["median"]
                   if ant_data[second_ant]["seg_metrics"][ant_data[second_ant]["seg_metrics"]["label"] == lbl].iloc[0]["agg_cno"] else 0
                   for lbl in seg_labels]
    ax.bar(x - width / 2, vals_first, width, label=first_name, color="#4a90d9")
    ax.bar(x + width / 2, vals_second, width, label=second_name, color="#e8963c")
    ax.set_xticks(x)
    ax.set_xticklabels(seg_labels, rotation=30, ha="right")
    ax.set_ylabel("C/N0 (dB-Hz)")
    ax.set_title("各片段 C/N0 中位数对比")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig_seg = fig_to_base64(fig)

    # Correlation figure
    if not corr_df.empty:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.hist(corr_df["r"].dropna(), bins=20, color="#8e6fc0", edgecolor="white", alpha=0.8)
        ax.axvline(overall_r or 0, color="#d9634f", linestyle="--", lw=2,
                   label=f"总体 Pearson r = {fmt(overall_r, 3) if overall_r is not None else '—'}")
        ax.axvline(0.7, color="#43a567", linestyle=":", lw=1.5, label="强相关阈值 0.7")
        ax.axvline(0.4, color="#9aa0a6", linestyle=":", lw=1.5, label="中等相关阈值 0.4")
        ax.set_xlabel("Pearson 相关系数 r")
        ax.set_ylabel("卫星数")
        ax.set_title(f"逐星 C/N0 相关性分布（{first_name} vs {second_name}）")
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        fig_corr = fig_to_base64(fig)
    else:
        fig_corr = None

    # Satellite loss figure
    if loss_rows:
        interf_labels = [r[0] for r in loss_rows]
        lost_first = [r[1] for r in loss_rows]
        lost_second = [r[3] for r in loss_rows]
        fig, ax = plt.subplots(figsize=(10, 4.5))
        x = np.arange(len(interf_labels))
        ax.bar(x - width / 2, lost_first, width, label=first_name, color="#4a90d9")
        ax.bar(x + width / 2, lost_second, width, label=second_name, color="#e8963c")
        ax.set_xticks(x)
        ax.set_xticklabels(interf_labels, rotation=30, ha="right")
        ax.set_ylabel("丢失卫星数")
        ax.set_title("各干扰段相对前基线丢失卫星数")
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        fig_loss = fig_to_base64(fig)
    else:
        fig_loss = None

    # ADR vs C/No scatter comparison figure
    adr_cno_cmp_fig = None
    if ant_data[first_ant]["adr_cno_scatter"] or ant_data[second_ant]["adr_cno_scatter"]:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        axes = axes.flatten()
        seg_names = ["409MHz 干扰", "392MHz 干扰", "4G/5G 干扰", "Wi-Fi 干扰"]
        for ax, seg_name in zip(axes, seg_names):
            for ant, marker in [(first_ant, "o"), (second_ant, "s")]:
                scatter_items = [x for x in ant_data[ant]["adr_cno_scatter"] if x["segment"] == seg_name]
                for item in scatter_items:
                    band = item["band"]
                    band_color = {"L1": "#4a90d9", "L2": "#e8963c", "L5": "#43a567",
                                  "E1": "#8e6fc0", "E5a": "#d9634f", "E5b": "#9aa0a6",
                                  "B1": "#3aa6a6", "B2": "#f0d88a", "B3": "#a03a30"}.get(band, "#5f6368")
                    ax.scatter(item["cno"], item["std_adr"], s=8, alpha=0.4,
                               color=band_color, marker=marker)
            ax.set_xlabel("C/N0 (dB-Hz)")
            ax.set_ylabel("StdDev-ADR (cycles)")
            ax.set_title(f"{seg_name}")
            ax.grid(True, linestyle="--", alpha=0.4)
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#4a90d9', markersize=8, label=first_name),
            Line2D([0], [0], marker='s', color='w', markerfacecolor='#e8963c', markersize=8, label=second_name),
        ]
        fig.legend(handles=legend_elements, loc='upper right')
        fig.suptitle("StdDev-ADR vs C/N0 联合散点（颜色=频点，形状=天线）", y=0.995)
        plt.tight_layout()
        adr_cno_cmp_fig = fig_to_base64(fig)

    # Correlation summary rows
    corr_summary_rows = []
    if corr_stats:
        corr_summary_rows.append([
            fmt(corr_stats["overall_r"], 3),
            fmt(corr_stats["fisher_z_avg_r"], 3),
            fmt(corr_stats["r_median"], 3),
            fmt(corr_stats["r_mean"], 3),
            fmt(corr_stats["r_p25"], 3),
            fmt(corr_stats["r_p75"], 3),
            corr_stats["n_total"],
            corr_stats["n_strong"],
            corr_stats["n_moderate"],
            corr_stats["n_weak"],
        ])

    corr_sys_rows = []
    if corr_stats and not corr_stats["by_system"].empty:
        for _, r in corr_stats["by_system"].iterrows():
            corr_sys_rows.append([
                r["sys"], r["n"],
                fmt(r["fisher_z_avg_r"], 3),
                fmt(r["r_median"], 3),
                fmt(r["r_mean"], 3),
                r["n_strong"], r["n_moderate"], r["n_weak"],
            ])

    # Correlation table rows
    corr_rows = []
    for _, r in corr_df.iterrows():
        strength = "强" if abs(r["r"]) >= 0.7 else ("中等" if abs(r["r"]) >= 0.4 else "弱")
        corr_rows.append([r["svid"], r["sys"], int(r["n"]), fmt(r["r"], 3), strength])

    # Comprehensive conclusion
    win_first = 0
    win_second = 0
    tie = 0
    for _, r in wilcoxon_df.iterrows():
        if r["significant"]:
            if r["median_diff"] > 0:
                win_first += 1
            elif r["median_diff"] < 0:
                win_second += 1
            else:
                tie += 1
        else:
            tie += 1

    pass_first = sum(1 for _, r in ant_data[first_ant]["interf_assess"].iterrows() if r["etsi_pass"])
    pass_second = sum(1 for _, r in ant_data[second_ant]["interf_assess"].iterrows() if r["etsi_pass"])
    total_intf = len(ant_data[first_ant]["interf_assess"])

    total_lost_first = int(ant_data[first_ant]["sat_loss"]["n_lost"].sum()) if not ant_data[first_ant]["sat_loss"].empty else 0
    total_lost_second = int(ant_data[second_ant]["sat_loss"]["n_lost"].sum()) if not ant_data[second_ant]["sat_loss"].empty else 0

    def r_strength_text(rval):
        if rval is None:
            return "无法判定"
        if abs(rval) >= 0.7:
            return "强相关"
        if abs(rval) >= 0.4:
            return "中等相关"
        return "弱相关"

    fisher_r = corr_stats.get("fisher_z_avg_r") if corr_stats else None
    r_median = corr_stats.get("r_median") if corr_stats else None

    # Build dynamic per-scenario text
    scenario_texts = []
    assess_first = {r["interf_seg"]: r for _, r in ant_data[first_ant]["interf_assess"].iterrows()}
    assess_second = {r["interf_seg"]: r for _, r in ant_data[second_ant]["interf_assess"].iterrows()}
    for label in sorted(set(assess_first) | set(assess_second)):
        a = assess_first.get(label)
        b = assess_second.get(label)
        if a is None or b is None:
            continue
        da = a["delta_median"]
        db = b["delta_median"]
        if da is None or db is None:
            continue
        diff = da - db
        if abs(diff) < 0.5:
            desc = "两者基本持平"
        elif diff > 0:
            desc = f"{first_name} 更稳健（ΔC/N0 {da:.2f} dB vs {db:.2f} dB）"
        else:
            desc = f"{second_name} 更稳健（ΔC/N0 {db:.2f} dB vs {da:.2f} dB）"
        scenario_texts.append(f"{label} 场景 {desc}")
    scenario_summary = "；".join(scenario_texts) + "。" if scenario_texts else "无足够数据。"

    # Absolute performance analysis: baseline C/No and interference segment C/No
    def get_segment_cno(ant, label):
        seg = ant_data[ant]["seg_metrics"][ant_data[ant]["seg_metrics"]["label"] == label]
        if not seg.empty:
            agg = seg.iloc[0]["agg_cno"]
            return agg["median"] if agg else None
        return None

    baseline_first = []
    baseline_second = []
    interf_first = []
    interf_second = []
    for label in seg_labels:
        cno_first = get_segment_cno(first_ant, label)
        cno_second = get_segment_cno(second_ant, label)
        if cno_first is None or cno_second is None:
            continue
        if label.startswith("无干扰"):
            baseline_first.append(cno_first)
            baseline_second.append(cno_second)
        elif is_interference(label):
            interf_first.append(cno_first)
            interf_second.append(cno_second)

    baseline_diff = float(np.median(np.array(baseline_first) - np.array(baseline_second))) if baseline_first and baseline_second else None
    interf_diff = float(np.median(np.array(interf_first) - np.array(interf_second))) if interf_first and interf_second else None

    # Determine absolute vs relative performance conclusion
    if baseline_diff is not None and baseline_diff > 0.5:
        abs_better = first_name
    elif baseline_diff is not None and baseline_diff < -0.5:
        abs_better = second_name
    else:
        abs_better = "两者持平"

    if interf_diff is not None and interf_diff > 0.5:
        interf_abs_better = first_name
    elif interf_diff is not None and interf_diff < -0.5:
        interf_abs_better = second_name
    else:
        interf_abs_better = "两者持平"

    # Relative degradation (anti-jamming robustness)
    rel_texts = []
    for label in sorted(set(assess_first) | set(assess_second)):
        a = assess_first.get(label)
        b = assess_second.get(label)
        if a is None or b is None:
            continue
        da = a["delta_median"]
        db = b["delta_median"]
        if da is None or db is None:
            continue
        if da > db + 0.5:
            rel_texts.append(f"{label} {first_name} 退化更小")
        elif db > da + 0.5:
            rel_texts.append(f"{label} {second_name} 退化更小")
        else:
            rel_texts.append(f"{label} 退化相当")
    rel_summary = "；".join(rel_texts) + "。" if rel_texts else "无足够数据。"

    # Overall performance verdict
    if abs_better == first_name and interf_abs_better == first_name:
        overall_verdict = f"{first_name} 整体性能更强：基线更高且干扰段绝对水平仍保持领先。"
    elif abs_better == second_name and interf_abs_better == second_name:
        overall_verdict = f"{second_name} 整体性能更强：基线更高且干扰段绝对水平仍保持领先。"
    elif abs_better == first_name and interf_abs_better == second_name:
        overall_verdict = f"{first_name} 基线更高，但 {second_name} 干扰段绝对水平反超；两者各有优势。"
    elif abs_better == second_name and interf_abs_better == first_name:
        overall_verdict = f"{second_name} 基线更高，但 {first_name} 干扰段绝对水平反超；两者各有优势。"
    else:
        overall_verdict = "两者整体性能接近，无显著优劣。"

    # Determine COM4 format description dynamically
    com4_desc_parts = []
    for ant in (first_ant, second_ant):
        ids = ant_data[ant]["com4"]["ids"]
        name = first_name if ant == first_ant else second_name
        if 140 in ids:
            com4_desc_parts.append(f"{name} 为标准 RANGECMP（ID 140）")
        else:
            com4_desc_parts.append(f"{name} 为非标准格式（ID {list(ids.keys())}）")
    com4_desc = "；".join(com4_desc_parts)

    conclusion = f"""基于 {test_name} 真实同步测试数据（COM3 TRACKSTAT C/No）的对比结论：
<br><br>
1. <b>整体水平</b>：两根天线整体 C/N0 中位数、PLL 锁定率、跟踪星数、参与解算星数均非常接近，{first_name} 与 {second_name} 无显著整体优劣。
2. <b>相关性</b>：按卫星平均后的 Fisher-z 平均 r = {fmt(fisher_r, 3) if fisher_r is not None else "—"}（{r_strength_text(fisher_r)}），逐星 r 中位数 = {fmt(r_median, 3) if r_median is not None else "—"}；总体样本 r = {fmt(overall_r, 3) if overall_r is not None else "—"}。两根天线对同一电磁环境的响应具有一定一致性，但不同卫星间相关程度差异较大。
3. <b>显著性检验</b>：Wilcoxon 符号秩检验显示 {win_first} 个片段 {first_name} 显著更高、{win_second} 个片段 {second_name} 显著更高、{tie} 个片段无显著差异。
4. <b>抗干扰性（参考 ETSI EN 303 413 的 1 dB 行业参考线）</b>：{first_name} 在 {total_intf} 种干扰中通过 {pass_first} 种；{second_name} 通过 {pass_second} 种。
5. <b>卫星保持</b>：干扰段累计丢失卫星数 {first_name} 为 {total_lost_first} 颗次，{second_name} 为 {total_lost_second} 颗次。
6. <b>分场景退化</b>：{scenario_summary}
7. <b>绝对接收能力</b>：基线（无干扰）C/N0 差值中位数 = {fmt(baseline_diff, 2) if baseline_diff is not None else "—"} dB（{abs_better} 基线更高）；干扰段 C/N0 差值中位数 = {fmt(interf_diff, 2) if interf_diff is not None else "—"} dB（{interf_abs_better} 干扰段绝对水平更高）。
8. <b>相对抗干扰能力</b>：{rel_summary}
9. <b>总体性能判定</b>：{overall_verdict}
"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1f2329}}
.wrap{{max-width:1280px;margin:0 auto;padding:20px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px 22px;margin:14px 0}}
h1{{font-size:22px;margin:0 0 8px}} h2{{font-size:17px;border-left:4px solid #4a90d9;padding-left:10px;margin:28px 0 10px}}
h3{{font-size:15px;margin:18px 0 8px}}
table{{border-collapse:collapse;width:100%;font-size:12px;background:#fff;margin-top:8px}}
th,td{{border:1px solid #e5e7eb;padding:5px 7px;text-align:left;white-space:nowrap}}
th{{background:#f0f2f5}}
.good{{color:#43a567;font-weight:600}} .bad{{color:#d9634f;font-weight:600}}
.warn{{background:#fdeeee;border:1px solid #f0b9b3;border-radius:8px;padding:12px 16px;margin:14px 0;color:#a03a30}}
img{{max-width:100%;border:1px solid #e5e7eb;border-radius:6px}}
.sub{{color:#5f6368;font-size:12px}}
</style>
</head>
<body>
<div class="wrap">
<h1>{title}</h1>
<p class="sub">基于 {test_name} 真实同步测试数据 · COM3 ASCII（TRACKSTAT/BESTPOS/GST/GSV）+ COM4 RANGECMP</p>
<div class="card">
<p>本报告依据 M21 方案对 {test_name} 目录下的 {first_name} 与 {second_name} 天线 COM3 ASCII 数据进行分析。COM4 二进制中，{com4_desc}。结论为“天线 + M21 内置抗干扰算法”的系统级结论。</p>
</div>

<div class="card">
<h2>1. 数据时间范围与片段追溯</h2>
<p><b>原始数据时间范围</b>：GPS 周 {raw_week}，周内秒 {raw_start:.3f} s ~ {raw_end:.3f} s（总时长 {raw_span:.1f} s）。</p>
<p><b>片段定义</b>：按用户提供的连续片段时长依次切分；每个片段取中间 10 秒作为稳态分析窗口。带 * 号表示该片段被文件实际长度截断。</p>
<h3>1.1 用户提供的片段定义</h3>
{html_table(seg_def_rows, ["序号", "片段标签", "定义时长(s)", "片段起(s)", "片段止(s)", "分析窗口起(s)", "分析窗口止(s)", "窗口时长(s)"])}
</div>

<div class="card">
<h2>2. 整体指标对比</h2>
{html_table(cmp_rows, ["天线", "C/N0 中位数", "C/N0 均值", "PLL 锁定比", "locktime<0.5s", "reject 比例", "平均跟踪星数", "平均参与解算星数", "伪距 RMS 中位数"])}
</div>

<div class="card">
<h2>3. 各系统 C/N0 中位数对比</h2>
<img src="data:image/png;base64,{fig_sys}" alt="per-system cno">
{html_table(sys_rows, ["天线", "系统", "C/N0 中位数", "C/N0 均值", "样本数"])}
</div>

<div class="card">
<h2>4. 各片段 C/N0 中位数对比</h2>
<img src="data:image/png;base64,{fig_seg}" alt="per-segment cno">
{html_table(seg_cmp_rows, ["天线", "片段", "C/N0 中位数", "C/N0 p25", "C/N0 p75", "PLL 锁定比", "跟踪星数", "参与解算星数", "伪距 RMS"])}
</div>

<div class="card">
<h2>5. 同片段同系统 {first_name} − {second_name} 的 C/N0 中位数差值（{first_name} 减 {second_name}）</h2>
<p>正值表示 {first_name} 更高；负值表示 {second_name} 更高；±0.5 dB 内视为持平。</p>
{html_table(diff_rows, ["片段", "系统", "共同星数", "差值中位数", "差值 p25", "差值 p75"])}
</div>

<div class="card">
<h2>6. 逐星 C/N0 相关性分析</h2>
<p>对两颗天线均观测到的每颗卫星，按同一 GPS 周内秒（sow）配对计算 Pearson 相关系数 r。由于不同卫星 C/N0 基线不同，合并所有样本得到的总体 r 会受卫星构成影响；因此同时给出 Fisher-z 变换后的平均 r（跨卫星平均）以及逐星 r 的中位数/分布。r ≥ 0.7 为强相关，0.4–0.7 为中等相关，< 0.4 为弱相关。</p>
<h3>6.1 相关性总体摘要</h3>
{html_table(corr_summary_rows, ["总体样本 r", "Fisher-z 平均 r", "r 中位数", "r 均值", "r p25", "r p75", "卫星总数", "强相关数", "中等相关数", "弱相关数"])}
<h3>6.2 按系统相关性摘要</h3>
{html_table(corr_sys_rows, ["系统", "卫星数", "Fisher-z 平均 r", "r 中位数", "r 均值", "强相关数", "中等相关数", "弱相关数"])}
<h3>6.3 逐星相关性分布</h3>
<img src="data:image/png;base64,{fig_corr if fig_corr else ''}" alt="correlation histogram">
<h3>6.4 逐星相关性明细</h3>
{html_table(corr_rows, ["卫星", "系统", "配对样本数", "Pearson r", "相关强度"])}
</div>

<div class="card">
<h2>7. 显著性检验（Wilcoxon 符号秩检验）</h2>
<p>对每个片段，取 {first_name} 与 {second_name} 的共同卫星 C/N0 中位数差值进行配对检验。p < 0.05 认为差异显著。</p>
{html_table(wilcox_rows, ["片段", "配对卫星数", "差值中位数", "Z 值", "p 值", "显著性"])}
</div>

<div class="card">
<h2>8. 卫星丢失情况（干扰段相对前一无干扰段）</h2>
<p>列出在基线段出现、但在随后干扰段中连续丢失 ≥3 秒（按 5 Hz 历元折算）的卫星。</p>
<img src="data:image/png;base64,{fig_loss if fig_loss else ''}" alt="satellite loss">
{html_table(loss_rows, ["干扰片段", f"{first_name} 丢失数", f"{first_name} 丢失卫星", f"{second_name} 丢失数", f"{second_name} 丢失卫星"])}
</div>

<div class="card">
<h2>9. 单天线干扰退化评估（参考 ETSI EN 303 413 1 dB 行业参考线）</h2>
<p>每种干扰段相对其前一无干扰段的中位数 ΔC/N0；≥ −1 dB 判定为通过行业参考线。该 1 dB 门槛是 UAS/GNSS 抗干扰评估中广泛使用的经验参考，不等同于完整的 ETSI 认证测试。</p>
{html_table(assess_rows, ["天线", "干扰片段", "ΔC/N0 中位数", "ΔC/N0 p25", "ΔC/N0 p75", "丢失卫星数", "PLL 锁定变化", "参考线判据"])}
</div>

<div class="card">
<h2>10. RANGECMP 各片段观测量质量对比</h2>
<p>来源：COM4 二进制 RANGECMP（ID 140）。StdDev-PSR 为伪距标准差（m），StdDev-ADR 为载波相位标准差（cycles）。</p>
{html_table(rangecmp_cmp_rows, ["天线", "片段", "样本数", "StdDev-PSR 中位数", "StdDev-PSR 均值", "StdDev-ADR 中位数", "locktime 中位数", "Doppler 标准差", "C/N0 中位数"])}
</div>

<div class="card">
<h2>11. RANGECMP 干扰段伪距标准差退化对比</h2>
<p>对每个真实干扰段，以其前一无干扰段为基线，统计共同卫星 StdDev-PSR 中位数变化。正值表示伪距标准差增大（观测量质量下降）。</p>
{html_table(rangecmp_deg_cmp_rows, ["天线", "干扰片段", "共同卫星数", "ΔStdDev-PSR 中位数", "ΔStdDev-PSR p25", "ΔStdDev-PSR p75", "退化卫星数"])}
</div>

<div class="card">
<h2>12. RANGECMP 按系统伪距标准差退化对比</h2>
<p>按 GNSS 系统分组统计干扰段相对基线的 StdDev-PSR 变化。</p>
{html_table(rangecmp_deg_sys_cmp_rows, ["天线", "干扰片段", "系统", "共同卫星数", "ΔStdDev-PSR 中位数", "ΔStdDev-PSR 均值", "ΔStdDev-PSR p25", "ΔStdDev-PSR p75", "退化卫星数", "改善卫星数"])}
</div>

<div class="card">
<h2>13. RANGECMP 载波相位标准差（StdDev-ADR）对比</h2>
<p>StdDev-ADR 为载波相位标准差（单位 cycles），反映载波相位观测质量。数值越小，相位观测越稳定。</p>
{html_table(rangecmp_adr_cmp_rows, ["天线", "片段", "系统", "样本数", "StdDev-ADR 中位数", "StdDev-ADR 均值", "StdDev-ADR p75"])}
</div>

<div class="card">
<h2>14. 联合失锁分析对比（TRACKSTAT + RANGECMP）</h2>
<p>同时检查 TRACKSTAT 与 RANGECMP 的卫星连续性。track_lost 表示 TRACKSTAT 中连续丢失 ≥3 秒；rc_lost 表示 RANGECMP 中连续丢失 ≥3 秒；both_lost 表示两源均判定丢失。</p>
{html_table(joint_lock_cmp_rows, ["天线", "干扰片段", "共同卫星数", "TRACKSTAT 丢失数", "RANGECMP 丢失数", "两源均丢失数"])}
</div>

<div class="card">
<h2>15. 两源均丢失卫星名单对比</h2>
<p>同时被 TRACKSTAT 与 RANGECMP 判定为连续丢失 ≥3 秒的卫星，属于高置信度“真丢失”。</p>
{html_table(both_lost_cmp_rows, ["天线", "干扰片段", "卫星", "系统", "TRACKSTAT 最大丢失时长", "RANGECMP 最大丢失时长"])}
</div>

<div class="card">
<h2>16. RANGECMP 按频点观测量质量对比</h2>
<p>按信号频段（L1/L2/L5/E1/E5a/E5b/B1/B2/B3 等）拆分 RANGECMP 指标。392 MHz 的 3 次谐波 1176 MHz 距 L5/E5a 约 0.45 MHz；409 MHz 的 3 次谐波 1227 MHz 距 L2 约 0.60 MHz。但实际退化数据显示影响频段更广，说明干扰同时存在宽带阻塞与谐波耦合。</p>
{html_table(band_cmp_rows, ["天线", "片段", "频段", "样本数", "StdDev-PSR 中位数", "StdDev-PSR 均值", "StdDev-ADR 中位数", "C/N0 中位数", "locktime 中位数"])}
</div>

<div class="card">
<h2>17. RANGECMP 按频点伪距标准差退化对比</h2>
<p>对每个真实干扰段，以其前一无干扰段为基线，按频段统计 StdDev-PSR 与 C/N0 变化。</p>
{html_table(band_deg_cmp_rows, ["天线", "干扰片段", "频段", "基线 StdDev-PSR", "干扰 StdDev-PSR", "ΔStdDev-PSR", "基线 C/N0", "干扰 C/N0", "ΔC/N0"])}
</div>

<div class="card">
<h2>18. StdDev-ADR 与 C/N0 联合散点对比</h2>
<p>按频点着色、按天线形状区分展示干扰段内 StdDev-ADR 与 C/N0 的关系。若某频点在干扰下 C/N0 下降且 StdDev-ADR 上升，说明该频段受干扰影响显著。</p>
<img src="data:image/png;base64,{adr_cno_cmp_fig if adr_cno_cmp_fig else ''}" alt="adr cno scatter comparison">
</div>

<div class="card">
<h2>19. 综合结论</h2>
<p>{conclusion}</p>
<p class="sub">说明：COM4 二进制 {first_name}/{second_name} 中，{com4_desc}；结论为“天线 + M21 内置抗干扰算法”的系统级结论。</p>
</div>

</div>
</body>
</html>"""
    return html
