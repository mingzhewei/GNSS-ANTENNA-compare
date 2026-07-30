#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main entry point for GNSS multi-antenna interference analysis.

Reads config/tests.yaml and generates reports for all configured test groups.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gnss_config import load_config, get_test_groups, build_segments_from_config, clip_segments_to_file
from gnss_parser import load_antenna_data
from gnss_analyzer import (
    per_svid_stats, per_svid_stats_per_segment, segment_metrics,
    compute_interference_degradation, compute_satellite_loss, assess_interference,
    compute_antenna_correlation, compute_segment_wilcoxon,
    rangecmp_segment_metrics, rangecmp_per_svid_stats, rangecmp_degradation,
    rangecmp_degradation_by_system, rangecmp_adr_analysis, rangecmp_adr_degradation,
    joint_locktime_analysis, list_both_lost_satellites,
    rangecmp_band_analysis, rangecmp_band_degradation, adr_cno_scatter_data,
)
from gnss_reporter import (
    plot_per_svid_stats, plot_per_svid_time_series, plot_epoch_metrics,
    antenna_report, comparison_report,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def process_antenna(ant_cfg, segments):
    """Load and analyze one antenna's data."""
    data = load_antenna_data(ant_cfg)
    ch_df = data["ch_df"]
    bp_df = data["bp_df"]
    gst_df = data["gst_df"]
    gsv_df = data["gsv_df"]
    rangecmp_df = data["rangecmp"]

    # Per-sat stats
    stats = per_svid_stats(ch_df)
    seg_stats = per_svid_stats_per_segment(ch_df, segments)
    seg_metrics = segment_metrics(ch_df, bp_df, gst_df, gsv_df, segments)
    degradation_df, degradation_summary = compute_interference_degradation(seg_metrics)

    # Figures
    ant_name = ant_cfg["display_name"]
    fig_per_svid_stats = plot_per_svid_stats(stats, f"天线 {ant_name}：每颗卫星 C/N0 统计（全文件）")
    fig_per_svid_time = plot_per_svid_time_series(ch_df, f"天线 {ant_name}：每颗卫星 C/N0 时间序列")
    figures = plot_epoch_metrics(ch_df, bp_df, gst_df, gsv_df, segments, f"天线 {ant_name}")
    figures["per_svid_stats"] = fig_per_svid_stats
    figures["per_svid_time"] = fig_per_svid_time

    sat_loss = compute_satellite_loss(ch_df, segments)
    interf_assess = assess_interference(seg_metrics, sat_loss)

    # RANGECMP analyses
    rangecmp_seg = rangecmp_segment_metrics(rangecmp_df, segments)
    rangecmp_svid = rangecmp_per_svid_stats(rangecmp_df, segments)
    rangecmp_deg = rangecmp_degradation(rangecmp_df, segments)
    rangecmp_deg_sys = rangecmp_degradation_by_system(rangecmp_df, segments)
    rangecmp_adr = rangecmp_adr_analysis(rangecmp_df, segments)
    rangecmp_adr_deg = rangecmp_adr_degradation(rangecmp_df, segments)
    joint_lock = joint_locktime_analysis(ch_df, rangecmp_df, segments)
    both_lost = list_both_lost_satellites(joint_lock)
    rangecmp_band = rangecmp_band_analysis(rangecmp_df, segments)
    rangecmp_band_deg = rangecmp_band_degradation(rangecmp_df, segments)
    adr_cno_scatter = adr_cno_scatter_data(rangecmp_df, segments)

    return {
        "track": data["track"],
        "ch_df": ch_df,
        "bp_df": bp_df,
        "gst_df": gst_df,
        "gsv_df": gsv_df,
        "segments": segments,
        "stats": stats,
        "seg_stats": seg_stats,
        "seg_metrics": seg_metrics,
        "degradation": (degradation_df, degradation_summary),
        "sat_loss": sat_loss,
        "interf_assess": interf_assess,
        "figures": figures,
        "rangecmp": rangecmp_df,
        "rangecmp_seg": rangecmp_seg,
        "rangecmp_svid": rangecmp_svid,
        "rangecmp_deg": rangecmp_deg,
        "rangecmp_deg_sys": rangecmp_deg_sys,
        "rangecmp_adr": rangecmp_adr,
        "rangecmp_adr_deg": rangecmp_adr_deg,
        "joint_lock": joint_lock,
        "both_lost": both_lost,
        "rangecmp_band": rangecmp_band,
        "rangecmp_band_deg": rangecmp_band_deg,
        "adr_cno_scatter": adr_cno_scatter,
        "com4": data["com4"],
    }


def write_csv_outputs(report_dir, ant_data, ant_id, test_name):
    """Write all CSV companion files for one antenna."""
    d = ant_data
    d["sat_loss"].to_csv(os.path.join(report_dir, f"satellite_loss_{test_name}_{ant_id}.csv"),
                         index=False, encoding="utf-8-sig")
    d["interf_assess"].to_csv(os.path.join(report_dir, f"interference_assessment_{test_name}_{ant_id}.csv"),
                              index=False, encoding="utf-8-sig")
    d["rangecmp_seg"].to_csv(os.path.join(report_dir, f"rangecmp_segment_summary_{test_name}_{ant_id}.csv"),
                             index=False, encoding="utf-8-sig")
    d["rangecmp_svid"].to_csv(os.path.join(report_dir, f"rangecmp_per_segment_per_svid_{test_name}_{ant_id}.csv"),
                              index=False, encoding="utf-8-sig")
    if not d["rangecmp_deg"].empty:
        d["rangecmp_deg"].to_csv(os.path.join(report_dir, f"rangecmp_degradation_{test_name}_{ant_id}.csv"),
                                 index=False, encoding="utf-8-sig")
    if not d["rangecmp_deg_sys"].empty:
        d["rangecmp_deg_sys"].to_csv(os.path.join(report_dir, f"rangecmp_degradation_by_system_{test_name}_{ant_id}.csv"),
                                     index=False, encoding="utf-8-sig")
    if not d["rangecmp_adr"].empty:
        d["rangecmp_adr"].to_csv(os.path.join(report_dir, f"rangecmp_adr_analysis_{test_name}_{ant_id}.csv"),
                                 index=False, encoding="utf-8-sig")
    if not d["rangecmp_adr_deg"].empty:
        d["rangecmp_adr_deg"].to_csv(os.path.join(report_dir, f"rangecmp_adr_degradation_{test_name}_{ant_id}.csv"),
                                     index=False, encoding="utf-8-sig")
    if not d["joint_lock"].empty:
        d["joint_lock"].to_csv(os.path.join(report_dir, f"joint_locktime_analysis_{test_name}_{ant_id}.csv"),
                               index=False, encoding="utf-8-sig")
    if not d["both_lost"].empty:
        d["both_lost"].to_csv(os.path.join(report_dir, f"both_lost_satellites_{test_name}_{ant_id}.csv"),
                              index=False, encoding="utf-8-sig")
    if not d["rangecmp_band"].empty:
        d["rangecmp_band"].to_csv(os.path.join(report_dir, f"rangecmp_band_analysis_{test_name}_{ant_id}.csv"),
                                  index=False, encoding="utf-8-sig")
    if not d["rangecmp_band_deg"].empty:
        d["rangecmp_band_deg"].to_csv(os.path.join(report_dir, f"rangecmp_band_degradation_{test_name}_{ant_id}.csv"),
                                      index=False, encoding="utf-8-sig")
    d["stats"].to_csv(os.path.join(report_dir, f"per_svid_stats_{test_name}_{ant_id}.csv"),
                      index=False, encoding="utf-8-sig")
    d["seg_stats"].to_csv(os.path.join(report_dir, f"per_segment_per_svid_stats_{test_name}_{ant_id}.csv"),
                          index=False, encoding="utf-8-sig")
    d["seg_metrics"].to_csv(os.path.join(report_dir, f"segment_summary_{test_name}_{ant_id}.csv"),
                            index=False, encoding="utf-8-sig")
    if not d["degradation"][0].empty:
        d["degradation"][0].to_csv(os.path.join(report_dir, f"degradation_{test_name}_{ant_id}.csv"),
                                   index=False, encoding="utf-8-sig")


def run_test_group(group, base_dir):
    """Run analysis for one test group."""
    test_name = group["name"]
    print(f"\n=== Processing test group: {test_name} ===")
    print(f"Description: {group['description']}")

    report_dir = os.path.join(base_dir, "reports", test_name)
    os.makedirs(report_dir, exist_ok=True)

    antennas = group["antennas"]
    if len(antennas) < 2:
        print(f"  Skipping: need at least 2 antennas, got {len(antennas)}")
        return

    # Use first antenna to determine time range and build segments
    first_data = load_antenna_data(antennas[0])
    track = first_data["track"]
    start_sow = track[0]["sow"]
    end_sow = track[-1]["sow"]
    segments = build_segments_from_config(group["segments"], start_sow)
    segments = clip_segments_to_file(segments, start_sow, end_sow)

    # Process all antennas
    ant_data = {}
    for ant_cfg in antennas:
        ant_id = ant_cfg["id"]
        print(f"Processing antenna {ant_id} ({ant_cfg['display_name']})...")
        ant_data[ant_id] = process_antenna(ant_cfg, segments)

        # Write per-antenna HTML report
        html = antenna_report(ant_id, ant_cfg["display_name"], ant_data[ant_id], test_name)
        out_path = os.path.join(report_dir, f"antenna_{test_name}_{ant_cfg['display_name'].replace('北天', '')}_report.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Wrote {out_path}")

        # Write CSV outputs
        write_csv_outputs(report_dir, ant_data[ant_id], ant_id, test_name)

    # Pairwise comparison (currently supports exactly 2 antennas)
    if len(antennas) == 2:
        first_ant = antennas[0]["id"]
        second_ant = antennas[1]["id"]
        first_name = antennas[0]["display_name"]
        second_name = antennas[1]["display_name"]

        # Cross-antenna analyses
        corr_df, overall_r, corr_stats = compute_antenna_correlation(
            ant_data[first_ant]["ch_df"], ant_data[second_ant]["ch_df"])
        corr_df.to_csv(os.path.join(report_dir, f"antenna_correlation_{test_name}.csv"),
                       index=False, encoding="utf-8-sig")
        if not corr_stats["by_system"].empty:
            corr_stats["by_system"].to_csv(os.path.join(report_dir, f"antenna_correlation_by_system_{test_name}.csv"),
                                           index=False, encoding="utf-8-sig")

        wilcoxon_df = compute_segment_wilcoxon(ant_data, first_ant, second_ant)
        wilcoxon_df.to_csv(os.path.join(report_dir, f"segment_wilcoxon_{test_name}.csv"),
                           index=False, encoding="utf-8-sig")

        # Comparison report
        cmp_html = comparison_report(ant_data, corr_df, overall_r, corr_stats, wilcoxon_df,
                                     first_ant, second_ant, first_name, second_name, test_name)
        cmp_path = os.path.join(report_dir,
            f"antenna_{first_name.replace('北天', '')}_vs_{second_name.replace('北天', '')}_{test_name}_report.html")
        with open(cmp_path, "w", encoding="utf-8") as f:
            f.write(cmp_html)
        print(f"Wrote {cmp_path}")
    else:
        print(f"  Note: pairwise comparison skipped (requires exactly 2 antennas, got {len(antennas)})")


def main():
    cfg = load_config()
    groups = get_test_groups(cfg)
    for group in groups:
        run_test_group(group, BASE)


if __name__ == "__main__":
    main()
