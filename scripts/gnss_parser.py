#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified parser for GNSS COM3 ASCII and COM4 RANGECMP binary data."""
import os
import struct
from collections import defaultdict

import numpy as np
import pandas as pd

SYS_MAP = {0: "GPS", 1: "GLO", 2: "SBAS", 3: "GAL", 4: "BDS", 5: "QZS", 6: "NAVIC", 7: "OTH"}

POS_TYPE_MAP = {
    0: "NONE", 1: "FIXEDPOS", 2: "FIXEDHEIGHT", 4: "FLOATCONV", 5: "WIDELANE",
    6: "NARROWLANE", 8: "DOPPLER_VELOCITY", 16: "SINGLE", 17: "PSRDIFF",
    18: "WAAS", 19: "PROPAKDIFF", 32: "L1_FLOAT", 33: "IONOFREE_FLOAT",
    34: "NARROW_FLOAT", 48: "NARROW_FLOAT", 50: "NARROW_INT",
}

# Signal type mapping per Table 136 (bits 21-25), keyed by (sys_id, signal_code)
SIGNAL_MAP = {
    (0, 0): "L1", (0, 5): "L2", (0, 9): "L2", (0, 14): "L5", (0, 16): "L1", (0, 17): "L2",
    (1, 0): "L1", (1, 1): "L2", (1, 5): "L2", (1, 6): "L3",
    (2, 0): "L1", (2, 6): "L5",
    (3, 1): "E1", (3, 2): "E1", (3, 6): "E6", (3, 7): "E6", (3, 12): "E5a", (3, 17): "E5b", (3, 20): "E5",
    (4, 0): "B1", (4, 1): "B2", (4, 2): "B3", (4, 4): "B1", (4, 5): "B2", (4, 6): "B3", (4, 7): "B1", (4, 9): "B2",
    (5, 0): "L1", (5, 14): "L5", (5, 16): "L1", (5, 17): "L2", (5, 27): "L6",
    (6, 0): "L5",
    (7, 19): "L-Band",
}

STDDEV_PSR_TABLE = [
    0.050, 0.075, 0.113, 0.169, 0.253, 0.380, 0.570, 0.854,
    1.281, 2.375, 4.750, 9.500, 19.000, 38.000, 76.000, 152.000,
]


def sys_from_status(st):
    return SYS_MAP.get((st >> 16) & 0x7, "UNK")


def global_svid(sys, prn):
    """Return a globally-unique satellite identifier string, system+PRN."""
    if sys == "GLO":
        return f"GLO{prn + 37}" if prn else None
    if sys == "QZS":
        return f"QZS{191 + prn}"
    if sys == "SBAS":
        return f"SBAS{119 + prn}"
    if sys in ("GPS", "GAL", "BDS", "NAVIC", "OTH"):
        return f"{sys}{prn}"
    return None


# ---------------------------------------------------------------------------
# COM3 ASCII parsing
# ---------------------------------------------------------------------------

def parse_trackstat_line(line):
    """Parse one #TRACKSTATA line into an epoch dict."""
    head, data = line.split(";", 1)
    h = head.split(",")
    week = int(h[5])
    sow = float(h[6])
    flds = data.split(",")
    sol_status = flds[0]
    pos_type = flds[1]
    cutoff = float(flds[2])
    nchans = int(flds[3])
    chs = []
    i = 4
    for _ in range(nchans):
        if i + 10 > len(flds):
            break
        prn = int(flds[i])
        glofreq = int(flds[i + 1])
        ch_tr_status = int(flds[i + 2], 16)
        psr = float(flds[i + 3])
        doppler = float(flds[i + 4])
        cno = float(flds[i + 5])
        locktime = float(flds[i + 6])
        psrres = float(flds[i + 7])
        reject = flds[i + 8]
        psrresorb = float(flds[i + 9].split("*")[0])
        chs.append({
            "prn": prn, "glofreq": glofreq, "status": ch_tr_status,
            "psr": psr, "doppler": doppler, "cno": cno,
            "locktime": locktime, "psrres": psrres,
            "reject": reject, "psrresorb": psrresorb,
        })
        i += 10
    return {
        "week": week, "sow": sow, "sol_status": sol_status,
        "pos_type": pos_type, "cutoff": cutoff, "chs": chs,
    }


def parse_bestpos_line(line):
    """Parse one #BESTPOSA line."""
    head, data = line.split(";", 1)
    h = head.split(",")
    week = int(h[5])
    sow = float(h[6])
    flds = data.split(",")
    return {
        "week": week, "sow": sow,
        "sol_stat": flds[0], "pos_type": flds[1],
        "lat": float(flds[2]), "lon": float(flds[3]), "hgt": float(flds[4]),
        "undulation": float(flds[5]), "datum": flds[6],
        "lat_sigma": float(flds[7]), "lon_sigma": float(flds[8]), "hgt_sigma": float(flds[9]),
        "stn_id": flds[10], "diff_age": float(flds[11]), "sol_age": float(flds[12]),
        "svs": int(flds[13]), "soln_svs": int(flds[14]),
        "ggl1": int(flds[15]), "ggl1l2": int(flds[16]),
        "ext_sol_stat": flds[17], "galileo_sig": flds[18],
    }


def parse_gst_line(line):
    """Parse one $GPGST line."""
    flds = line.strip().split(",")
    # $GPGST,time,rrms,semi_major,semi_minor,orient,lat_std,lon_std,alt_std*cs
    return {
        "time": flds[1],
        "pr_rms": float(flds[2]) if flds[2] else np.nan,
        "semi_major": float(flds[3]) if flds[3] else np.nan,
        "semi_minor": float(flds[4]) if flds[4] else np.nan,
        "orient": float(flds[5]) if flds[5] else np.nan,
        "lat_std": float(flds[6]) if flds[6] else np.nan,
        "lon_std": float(flds[7]) if flds[7] else np.nan,
        "alt_std": float(flds[8].split("*")[0]) if flds[8] else np.nan,
    }


def parse_gsv_line(line):
    """Parse one NMEA GSV line."""
    flds = line.strip().split(",")
    talker = flds[0][1:3]
    total = int(flds[3])
    sats = []
    i = 4
    while i + 4 <= len(flds):
        prn = int(flds[i]) if flds[i] else 0
        elev = int(flds[i + 1]) if flds[i + 1] else 0
        azim = int(flds[i + 2]) if flds[i + 2] else 0
        snr = int(flds[i + 3].split("*")[0]) if flds[i + 3] else 0
        sats.append({"prn": prn, "elev": elev, "azim": azim, "snr": snr})
        i += 4
    return {"talker": talker, "in_view": total, "sats": sats}


def parse_com3(path):
    """Parse one COM3 ASCII file into dict of lists."""
    track = []
    bestpos = []
    gst = []
    gsv = []
    last_sow = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                if line.startswith("#TRACKSTATA"):
                    ep = parse_trackstat_line(line)
                    last_sow = ep["sow"]
                    for ch in ep["chs"]:
                        sys = sys_from_status(ch["status"])
                        ch["sys"] = sys
                        ch["svid"] = global_svid(sys, ch["prn"])
                        if ch["svid"] is None:
                            ch["svid"] = f"UNK{ch['prn']}"
                    track.append(ep)
                elif line.startswith("#BESTPOSA"):
                    bp = parse_bestpos_line(line)
                    last_sow = bp["sow"]
                    bestpos.append(bp)
                elif line.startswith("$GPGST"):
                    g = parse_gst_line(line)
                    g["sow"] = last_sow
                    gst.append(g)
                elif line.startswith("$") and "GSV" in line[:6]:
                    g = parse_gsv_line(line)
                    g["sow"] = last_sow
                    gsv.append(g)
            except Exception:
                continue
    return {"track": track, "bestpos": bestpos, "gst": gst, "gsv": gsv}


# ---------------------------------------------------------------------------
# COM4 binary parsing
# ---------------------------------------------------------------------------

def inspect_com4(path):
    """Return summary of valid ByNav standard-binary messages in a COM4 file."""
    data = open(path, "rb").read()
    ids = defaultdict(int)
    lens = defaultdict(int)
    times = []
    i = 0
    while i < len(data) - 12:
        if data[i] == 0xAA and data[i + 1] == 0x44 and data[i + 2] == 0x12:
            hdr_len = data[i + 3]
            msg_id = struct.unpack("<H", data[i + 4:i + 6])[0]
            msg_len = struct.unpack("<H", data[i + 8:i + 10])[0]
            total_len = hdr_len + msg_len + 4
            if i + total_len <= len(data):
                ids[msg_id] += 1
                lens[msg_id] = msg_len
                week = struct.unpack("<H", data[i + 14:i + 16])[0]
                ms = struct.unpack("<I", data[i + 16:i + 20])[0]
                times.append((week, ms))
                i += total_len
                continue
        i += 1
    return {
        "valid_msgs": sum(ids.values()),
        "ids": dict(ids), "lengths": dict(lens),
        "time_range": (times[0], times[-1]) if times else None,
    }


def parse_rangecmp_file(path):
    """Parse a COM4 binary file and return a DataFrame of RANGECMP observations."""
    data = open(path, "rb").read()
    records = []
    i = 0
    while i < len(data) - 12:
        if data[i] == 0xAA and data[i + 1] == 0x44 and data[i + 2] == 0x12:
            hdr_len = data[i + 3]
            msg_id = struct.unpack("<H", data[i + 4:i + 6])[0]
            msg_len = struct.unpack("<H", data[i + 8:i + 10])[0]
            if msg_id == 140:
                week = struct.unpack("<H", data[i + 14:i + 16])[0]
                ms = struct.unpack("<I", data[i + 16:i + 20])[0]
                sow = ms / 1000.0
                payload = data[i + hdr_len:i + hdr_len + msg_len]
                nobs = struct.unpack("<I", payload[0:4])[0]
                for j in range(nobs):
                    rec = payload[4 + j * 24:4 + (j + 1) * 24]
                    if len(rec) < 24:
                        break
                    val = int.from_bytes(rec, byteorder="little", signed=False)

                    def get_bits(start, length):
                        return (val >> start) & ((1 << length) - 1)

                    ch_status = get_bits(0, 32)
                    doppler_raw = get_bits(32, 28)
                    psr_raw = get_bits(60, 36)
                    adr_raw = get_bits(96, 32)
                    stddev_psr_code = get_bits(128, 4)
                    stddev_adr_code = get_bits(132, 4)
                    prn = get_bits(136, 8)
                    locktime_raw = get_bits(144, 21)
                    cno_raw = get_bits(165, 5)
                    glofreq = get_bits(170, 6)

                    sys_id = (ch_status >> 16) & 0x7
                    state = ch_status & 0x1F
                    pll_lock = bool((ch_status >> 10) & 1)
                    code_lock = bool((ch_status >> 12) & 1)
                    parity = bool((ch_status >> 15) & 1)
                    sig_code = (ch_status >> 21) & 0x1F
                    sig_band = SIGNAL_MAP.get((sys_id, sig_code), "UNK")

                    doppler = doppler_raw / 256.0
                    if doppler_raw >= (1 << 27):
                        doppler = (doppler_raw - (1 << 28)) / 256.0
                    adr = adr_raw / 256.0
                    if adr_raw >= (1 << 31):
                        adr = (adr_raw - (1 << 32)) / 256.0

                    psr = psr_raw / 128.0
                    std_psr = STDDEV_PSR_TABLE[stddev_psr_code] if stddev_psr_code < len(STDDEV_PSR_TABLE) else np.nan
                    std_adr = (stddev_adr_code + 1) / 512.0
                    locktime = locktime_raw / 32.0
                    cno = 20 + cno_raw
                    sys_name = SYS_MAP.get(sys_id, "UNK")
                    svid = f"{sys_name}{prn}" if sys_name != "GLO" else f"GLO{prn + 37}"

                    records.append({
                        "sow": sow, "week": week,
                        "sys": sys_name, "prn": prn, "svid": svid,
                        "ch_status": ch_status,
                        "state": state,
                        "pll_lock": pll_lock,
                        "code_lock": code_lock,
                        "parity": parity,
                        "sig_code": sig_code,
                        "sig_band": sig_band,
                        "doppler": doppler,
                        "psr": psr,
                        "adr": adr,
                        "std_psr": std_psr,
                        "std_adr": std_adr,
                        "locktime": locktime,
                        "cno": cno,
                        "glofreq": glofreq,
                    })
            i += hdr_len + msg_len + 4
        else:
            i += 1
    if not records:
        return pd.DataFrame(columns=[
            "sow", "week", "sys", "prn", "svid", "ch_status", "state",
            "pll_lock", "code_lock", "parity", "sig_code", "sig_band",
            "doppler", "psr", "adr", "std_psr", "std_adr", "locktime",
            "cno", "glofreq",
        ])
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# DataFrame builders
# ---------------------------------------------------------------------------

def build_channel_df(track):
    rows = []
    for ep in track:
        sow = ep["sow"]
        for ch in ep["chs"]:
            rows.append({
                "sow": sow, "week": ep["week"], "svid": ch["svid"], "sys": ch["sys"],
                "prn": ch["prn"], "cno": ch["cno"], "locktime": ch["locktime"],
                "state": ch["status"], "status": ch["status"],
                "reject": ch["reject"], "psrres": ch["psrres"],
                "doppler": ch["doppler"],
            })
    return pd.DataFrame(rows)


def build_channel_df_fixed(track):
    rows = []
    for ep in track:
        sow = ep["sow"]
        for ch in ep["chs"]:
            rows.append({
                "sow": sow, "week": ep["week"], "svid": ch["svid"], "sys": ch["sys"],
                "prn": ch["prn"], "cno": ch["cno"], "locktime": ch["locktime"],
                "status": ch["status"],
                "reject": ch["reject"], "psrres": ch["psrres"],
                "doppler": ch["doppler"],
            })
    return pd.DataFrame(rows)


def tracking_state_desc(status):
    state = status & 0x1F
    pll = bool((status >> 10) & 1)
    code = bool((status >> 12) & 1)
    if state == 4 and pll and code:
        return "PLL_LOCK"
    if state == 7:
        return "FLL"
    if state == 1:
        return "SEARCH"
    if state == 0:
        return "IDLE"
    return "OTHER"


def load_antenna_data(antenna_cfg):
    """Load COM3 and COM4 data for one antenna.

    Returns dict with ch_df, bp_df, gst_df, gsv_df, rangecmp_df, com4_summary.
    """
    com3 = parse_com3(antenna_cfg["com3"])
    com4 = inspect_com4(antenna_cfg["com4"])
    rangecmp_df = parse_rangecmp_file(antenna_cfg["com4"])

    track = com3["track"]
    ch_df = build_channel_df_fixed(track)
    ch_df["state"] = ch_df["status"].apply(tracking_state_desc)
    bp_df = pd.DataFrame(com3["bestpos"])
    gst_df = pd.DataFrame(com3["gst"])
    gsv_df = pd.DataFrame(com3["gsv"])

    return {
        "track": track,
        "ch_df": ch_df,
        "bp_df": bp_df,
        "gst_df": gst_df,
        "gsv_df": gsv_df,
        "rangecmp": rangecmp_df,
        "com4": com4,
    }
