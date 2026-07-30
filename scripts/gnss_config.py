#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load and validate GNSS test configuration."""
import os
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "tests.yaml")


def load_config(path=None):
    """Load test configuration from YAML file."""
    if path is None:
        path = CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def get_test_groups(cfg):
    """Return list of test group dicts with resolved paths."""
    groups = []
    for g in cfg.get("test_groups", []):
        data_dir = os.path.join(BASE, g["data_dir"])
        antennas = []
        for a in g["antennas"]:
            antennas.append({
                "id": a["id"],
                "display_name": a["display_name"],
                "com3": os.path.join(data_dir, a["com3"]),
                "com4": os.path.join(data_dir, a["com4"]),
            })
        groups.append({
            "name": g["name"],
            "description": g.get("description", ""),
            "data_dir": data_dir,
            "antennas": antennas,
            "segments": g["segments"],
        })
    return groups


def build_segments_from_config(segment_defs, start_sow):
    """Build segment boundaries from config-defined durations.

    Returns list of dicts: {label, idx, start, end, middle_start, middle_end,
    middle_duration, truncated}.
    """
    segments = []
    cur = start_sow
    for idx, seg_def in enumerate(segment_defs):
        label = seg_def["label"]
        dur = float(seg_def["duration"])
        start = cur
        end = cur + dur
        if dur >= 10.0:
            mid_start = cur + (dur - 10.0) / 2.0
            mid_end = mid_start + 10.0
        else:
            mid_start = cur
            mid_end = end
        segments.append({
            "idx": idx + 1,
            "label": label,
            "start": start,
            "end": end,
            "middle_start": mid_start,
            "middle_end": mid_end,
            "duration": dur,
        })
        cur = end
    return segments


def clip_segments_to_file(segments, min_sow, max_sow):
    """Clip segment boundaries to actual file span; mark truncation."""
    out = []
    for seg in segments:
        s = max(seg["start"], min_sow)
        e = min(seg["end"], max_sow)
        ms = max(seg["middle_start"], min_sow)
        me = min(seg["middle_end"], max_sow)
        truncated = (s > seg["start"] + 0.001) or (e < seg["end"] - 0.001)
        out.append({
            **seg,
            "start": s, "end": e,
            "middle_start": ms, "middle_end": me,
            "clipped_duration": e - s,
            "middle_duration": max(0.0, me - ms),
            "truncated": truncated,
        })
    return out


def is_interference(label):
    """Return True only for actual interference segments (not 无干扰 baselines)."""
    return not label.startswith("无干扰")
