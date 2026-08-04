# -*- coding: utf-8 -*-
"""汇总 4 组双天线抗干扰对比测试，生成精简的中文综合 HTML 报告。

数据来源：reports/<test>/ 下已生成的分析 CSV（utf-8-sig）。
输出：reports/consolidated_report.html

口径约定（全报告统一）：
- segment_wilcoxon 的 median_diff = 076 - 竞品（共同卫星 C/N0 中位数之差的中位数，
  由 gnss_analyzer.compute_segment_wilcoxon(ant_data, first_ant=076, second_ant=竞品) 产生，
  first_ant 为 config/tests.yaml 中排在第一位的 076）。正值 = 076 更高。
- delta_median / delta_cno 为负值 = 衰减多少 dB。
- "衰减差" = 076衰减 - 竞品衰减（即 |竞品衰减| - |076衰减|），正值 = 竞品多衰减 = 076 占优。
"""

import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "reports")
OUT_HTML = os.path.join(REPORTS, "consolidated_report.html")

TESTS = [
    ("0728-076-560", "560", "北天BT-T560"),
    ("0728-076-617", "617", "北天BT-T617"),
    ("0731-076-by403", "by403", "by403"),
    ("0731-076-speed", "speed", "speed"),
]
BASELINE_NAME = "北天BT-T076"
SCENARIOS = ["409MHz 干扰", "392MHz 干扰", "4G/5G 干扰", "Wi-Fi 干扰"]
BASELINE_SEGS = ["无干扰 #1", "无干扰 #2", "无干扰 #3", "无干扰 #4", "无干扰 #5"]
BAND_ORDER = ["L1", "L2", "L5", "E1", "E5a", "E5b", "B1", "B2I", "B2a", "B3"]


def read_csv(test, pattern):
    path = os.path.join(REPORTS, test, pattern.format(test=test))
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def seg_mean_cno(stats_df, segment):
    """片段内全星加权平均 C/N0（按每颗星的样本数 n 加权 median）。"""
    df = stats_df[stats_df["segment"] == segment]
    if df.empty or df["n"].sum() == 0:
        return None
    return float((df["median"] * df["n"]).sum() / df["n"].sum())


def fmt(v, nd=1, na="—"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return na
    return f"{v:.{nd}f}"


def fmt_signed(v, nd=1, na="—"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return na
    return f"{v:+.{nd}f}"


def html_table(headers, rows):
    out = ["<table><thead><tr>"]
    out += [f"<th>{h}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def collect():
    """读取全部数据，返回 {test: {...}}。"""
    data = {}
    for test, comp_id, comp_name in TESTS:
        d = {"comp_id": comp_id, "comp_name": comp_name}
        d["assess_076"] = read_csv(test, "interference_assessment_{test}_076.csv")
        d["assess_comp"] = read_csv(test, f"interference_assessment_{{test}}_{comp_id}.csv")
        d["wilcoxon"] = read_csv(test, "segment_wilcoxon_{test}.csv")
        d["svid_076"] = read_csv(test, "per_segment_per_svid_stats_{test}_076.csv")
        d["svid_comp"] = read_csv(test, f"per_segment_per_svid_stats_{{test}}_{comp_id}.csv")
        d["band_076"] = read_csv(test, "rangecmp_band_degradation_{test}_076.csv")
        d["band_comp"] = read_csv(test, f"rangecmp_band_degradation_{{test}}_{comp_id}.csv")

        # 基线绝对水平：5 个无干扰段的全星加权平均 C/N0 再取平均
        for ant in ("076", "comp"):
            vals = [seg_mean_cno(d[f"svid_{ant}"], s) for s in BASELINE_SEGS]
            vals = [v for v in vals if v is not None]
            d[f"baseline_{ant}"] = sum(vals) / len(vals) if vals else None

        # 干扰段绝对水平
        for scen in SCENARIOS:
            d[f"abs_076_{scen}"] = seg_mean_cno(d["svid_076"], scen)
            d[f"abs_comp_{scen}"] = seg_mean_cno(d["svid_comp"], scen)

        # 衰减（delta_median）
        for ant in ("076", "comp"):
            a = d[f"assess_{ant}"].set_index("interf_seg")
            for scen in SCENARIOS:
                row = a.loc[scen] if scen in a.index else None
                d[f"att_{ant}_{scen}"] = float(row["delta_median"]) if row is not None else None
                d[f"lost_{ant}_{scen}"] = int(row["n_lost"]) if row is not None else None

        # wilcoxon
        w = d["wilcoxon"].set_index("segment")
        for seg in BASELINE_SEGS + SCENARIOS:
            if seg in w.index:
                row = w.loc[seg]
                d[f"wx_diff_{seg}"] = float(row["median_diff"])
                d[f"wx_p_{seg}"] = float(row["wilcoxon_p"]) if pd.notna(row["wilcoxon_p"]) else None
                d[f"wx_sig_{seg}"] = bool(row["significant"]) if pd.notna(row["significant"]) else False
                d[f"wx_n_{seg}"] = int(row["n_pairs"])
            else:
                d[f"wx_diff_{seg}"] = d[f"wx_p_{seg}"] = d[f"wx_n_{seg}"] = None
                d[f"wx_sig_{seg}"] = False

        # 频点退化：(interf_seg, band) -> delta_cno
        for ant in ("076", "comp"):
            b = d[f"band_{ant}"]
            m = {}
            if b is not None:
                for _, r in b.iterrows():
                    m[(r["interf_seg"], r["band"])] = float(r["delta_cno"])
            d[f"bandmap_{ant}"] = m
        data[test] = d
    return data


def judge(d, scen):
    """场景胜出判定。score = 衰减差 + wilcoxon 差（均为正值=076 占优）。
    衰减差 = att_076 - att_comp（负值相减，正=竞品衰减更多）。
    >0.5 → 076 胜；<-0.5 → 竞品胜；否则持平。wilcoxon 缺失时仅按衰减判定。"""
    a076, ac = d[f"att_076_{scen}"], d[f"att_comp_{scen}"]
    if a076 is None or ac is None:
        return None, None, "数据缺失"
    att_gap = a076 - ac
    wx = d[f"wx_diff_{scen}"]
    wx_note = ""
    if wx is None or (d[f"wx_n_{scen}"] or 0) < 5:
        wx = 0.0
        wx_note = "（wilcoxon 样本不足，仅按衰减判定）"
    score = att_gap + wx
    if score > 0.5:
        return score, att_gap, BASELINE_NAME + wx_note
    if score < -0.5:
        return score, att_gap, d["comp_name"] + wx_note
    return score, att_gap, "基本持平" + wx_note


def build_html(data):
    css = """
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1f2329}
.wrap{max-width:1280px;margin:0 auto;padding:20px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px 22px;margin:14px 0}
h1{font-size:22px;margin:0 0 8px} h2{font-size:17px;border-left:4px solid #4a90d9;padding-left:10px;margin:28px 0 10px}
h3{font-size:15px;margin:18px 0 8px}
table{border-collapse:collapse;width:100%;font-size:12px;background:#fff;margin-top:8px}
th,td{border:1px solid #e5e7eb;padding:5px 7px;text-align:left;white-space:nowrap}
th{background:#f0f2f5}
.good{color:#43a567;font-weight:600} .bad{color:#d9634f;font-weight:600}
.warn{background:#fdeeee;border:1px solid #f0b9b3;border-radius:8px;padding:12px 16px;margin:14px 0;color:#a03a30}
.note{background:#fff8e6;border:1px solid #f0d88a;border-radius:8px;padding:12px 16px;margin:14px 0;color:#8a6d1a}
.sub{color:#5f6368;font-size:12px}
.num{font-family:"SF Mono",Menlo,Consolas,monospace}
"""

    # ---------- 计算场景判定与综合分 ----------
    scen_judge = {}   # (test, scen) -> (winner, att_gap, score)
    composite = {}    # test -> 相对 076 综合优势分（正=076 占优）
    detail = {}
    for test, comp_id, comp_name in TESTS:
        d = data[test]
        baseline_gap = (d["baseline_076"] or 0) - (d["baseline_comp"] or 0)
        att_gaps, abs_gaps = [], []
        for scen in SCENARIOS:
            score, att_gap, winner = judge(d, scen)
            scen_judge[(test, scen)] = (winner, att_gap, score)
            att_gaps.append(att_gap)
            wx = d[f"wx_diff_{scen}"]
            if wx is not None and (d[f"wx_n_{scen}"] or 0) >= 5:
                abs_gaps.append(wx)
        mean_att = sum(att_gaps) / len(att_gaps)
        mean_abs = sum(abs_gaps) / len(abs_gaps) if abs_gaps else 0.0
        composite[test] = baseline_gap + mean_att + mean_abs
        detail[test] = (baseline_gap, mean_att, mean_abs)

    # 排名：076 为 0 分基准；竞品按 composite 升序（分越低竞品相对越强）
    ranking = sorted(TESTS, key=lambda t: composite[t[0]])
    rank_list = [("076", BASELINE_NAME, 0.0)]
    for test, comp_id, comp_name in ranking:
        rank_list.append((comp_id, comp_name, composite[test]))
    rank_list.sort(key=lambda x: x[2])  # 分数越低 = 076 占优越少 = 该天线相对越强

    best_name = rank_list[0][1]
    best_test = next((t for t in TESTS if t[2] == best_name), None)

    parts = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>GNSS 双天线抗干扰对比综合报告</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<h1>GNSS 双天线抗干扰对比综合报告</h1>
<p class="sub">4 组对比测试（0728-076-560 / 0728-076-617 / 0731-076-by403 / 0731-076-speed）· 共同基准：北天BT-T076（id=076）·
每组 9 个连续片段（无干扰×5 + 409MHz / 392MHz / 4G/5G / Wi-Fi 干扰各 1 段），干扰源距天线 15 cm，双天线相距 30 cm 同步采集 ·
接收机：北云 M21</p>
<div class="note"><b>判定口径</b>：
① 衰减量 delta_median 为干扰段 C/N0 相对前一无干扰基线的变化中位数，<b>负值 = 衰减多少 dB</b>；
② wilcoxon median_diff = <b>076 − 竞品</b>（共同卫星配对，正值 = 076 段内绝对水平更高，p&lt;0.05 为显著）；
③ 衰减差 = 076衰减 − 竞品衰减，<b>正值 = 竞品多衰减 = 076 占优</b>；
④ 场景胜出 = 衰减差 + wilcoxon 差 &gt; 0.5 dB 判 076 胜，&lt; -0.5 dB 判竞品胜，其间为持平；
⑤ 综合优势分 = 基线差 + 平均衰减差 + 平均 wilcoxon 差（dB，正值 = 076 占优）。</div>
"""]

    # ---------- 1. 最终结论 ----------
    rows = []
    for i, (aid, name, score) in enumerate(rank_list, 1):
        cls = ' class="good"' if i == 1 else ""
        rows.append([f"<b{cls}>{i}</b>", f"<b{cls}>{name}</b>", aid,
                     f'<span class="num">{fmt_signed(score, 1)}</span>'])
    parts.append(f"""<div class="card">
<h2>最终结论</h2>
<p><b class="good">总体最好：{best_name}</b>。
理由：{conclusion_reason(best_test, data, scen_judge) if best_test else "基准天线 076 自身综合表现最佳。"}</p>
{html_table(["总排名", "天线", "id", "相对 076 综合优势分(dB)"], rows)}
<p class="sub">综合优势分为相对 076 的折算值（076 计 0），仅用于排序参考；逐维度明细见下。</p>
<ul>{''.join(f'<li>{pair_verdict(t, data, scen_judge, composite)}</li>' for t in TESTS)}</ul>
</div>""")

    # ---------- 2. 基准绝对能力 ----------
    rows = []
    for test, comp_id, comp_name in TESTS:
        d = data[test]
        gap = d["baseline_comp"] - d["baseline_076"]
        gap_cls = "bad" if gap < -0.3 else ("good" if gap > 0.3 else "")
        wx = d["wx_diff_无干扰 #1"]
        rows.append([
            test, comp_name,
            f'<span class="num">{fmt(d["baseline_076"])}</span>',
            f'<span class="num">{fmt(d["baseline_comp"])}</span>',
            f'<span class="num {gap_cls}">{fmt_signed(gap)}</span>',
            f'<span class="num">{fmt_signed(wx)}</span>' + ("（显著）" if d["wx_sig_无干扰 #1"] else "（不显著）"),
        ])
    parts.append(f"""<div class="card">
<h2>基准绝对能力对比（无干扰段平均 C/N0，dB-Hz）</h2>
<p>5 个无干扰段的全星加权平均 C/N0 之均值。差值 = 竞品 − 076，正值 = 竞品基线收星更强。末列为「无干扰 #1」段共同卫星配对 wilcoxon 中位差（076 − 竞品）作交叉验证。</p>
{html_table(["测试组", "竞品", "076 基线", "竞品基线", "差值(竞品−076)", "wilcoxon 差(076−竞品)"], rows)}
</div>""")

    # ---------- 3. 四个干扰场景 ----------
    for idx, scen in enumerate(SCENARIOS, 1):
        rows = []
        for test, comp_id, comp_name in TESTS:
            d = data[test]
            winner, att_gap, score = scen_judge[(test, scen)]
            wx, p = d[f"wx_diff_{scen}"], d[f"wx_p_{scen}"]
            if wx is None or (d[f"wx_n_{scen}"] or 0) < 5:
                wx_txt = f'<span class="bad">样本不足(n={d[f"wx_n_{scen}"]})</span>'
            else:
                sig = "，显著" if d[f"wx_sig_{scen}"] else "，不显著"
                wx_txt = f'<span class="num">{fmt_signed(wx)}</span>（p={fmt(p, 3)}{sig}）'
            wcls = "good" if winner.startswith(BASELINE_NAME) else ("bad" if winner.startswith(comp_name) else "")
            rows.append([
                comp_name,
                f'<span class="num">{fmt(d[f"att_076_{scen}"])}</span>',
                f'<span class="num">{fmt(d[f"att_comp_{scen}"])}</span>（丢星 {d[f"lost_comp_{scen}"]}）',
                f'<span class="num">{fmt_signed(att_gap)}</span>',
                f'<span class="num">{fmt(d[f"abs_076_{scen}"])}</span> / <span class="num">{fmt(d[f"abs_comp_{scen}"])}</span>',
                wx_txt,
                f'<b class="{wcls}">{winner}</b>' if wcls else winner,
            ])
        parts.append(f"""<div class="card">
<h2>干扰场景 {idx}：{scen}</h2>
{html_table(["对比组", "076 衰减(dB)", "竞品衰减(dB)", "衰减差(正=076占优)", "段内绝对C/N0 076/竞品", "wilcoxon差(076−竞品)", "胜出方"], rows)}
</div>""")

    # ---------- 4. 频点对比 ----------
    band_parts = []
    for test, comp_id, comp_name in TESTS:
        d = data[test]
        m076, mc = d["bandmap_076"], d["bandmap_comp"]
        bands = [b for b in BAND_ORDER if any((s, b) in m076 or (s, b) in mc for s in SCENARIOS)]
        rows = []
        for band in bands:
            row = [f"<b>{band}</b>"]
            for scen in SCENARIOS:
                v076, vc = m076.get((scen, band)), mc.get((scen, band))
                if v076 is None and vc is None:
                    row.append("—")
                elif v076 is None or vc is None:
                    row.append('<span class="bad">缺失</span>')
                else:
                    gap = v076 - vc  # 正=076 退化更少=076 优
                    cls = "good" if gap >= 3 else ("bad" if gap <= -3 else "")
                    row.append(f'<span class="num {cls}">{fmt_signed(gap, 0)}</span>')
            rows.append(row)
        # 缺失频点统计
        missing = []
        for scen in SCENARIOS:
            b076 = {b for (s, b) in m076 if s == scen}
            bc = {b for (s, b) in mc if s == scen}
            lack = b076 - bc
            if lack:
                missing.append(f"{scen}：{comp_name} 缺 {', '.join(sorted(lack, key=BAND_ORDER.index))}")
        miss_txt = f'<p class="bad">数据缺失：{"；".join(missing)}（该竞品在此场景下未跟踪到这些频点的信号，本身就是抗干扰弱的表现）。</p>' if missing else ""
        band_parts.append(f"""<h3>076 vs {comp_name}（{test}）</h3>
{html_table(["频点"] + [s.replace(" 干扰", "") for s in SCENARIOS], rows)}
{miss_txt}""")

    parts.append(f"""<div class="card">
<h2>按频点的退化对比（RANGECMP delta_cno）</h2>
<p>单元格 = 076退化 − 竞品退化（dB，<b class="good">绿色 ≥ +3 = 076 在该频点明显占优</b>，<b class="bad">红色 ≤ -3 = 竞品明显占优</b>）。退化值为负（衰减），差值为两者之差。
「—」表示两天线均无该频点数据（392MHz 干扰段所有天线都缺 L5/E5a 的 RANGECMP 记录，属数据本身特征）。</p>
{''.join(band_parts)}
</div>""")

    # ---------- 5. 判定方法与局限 ----------
    parts.append("""<div class="card">
<h2>判定方法与局限</h2>
<ul>
<li>接收机为北云 M21，其内置抗干扰算法无法关闭，测得的是「天线 + 接收机算法」的整体表现，不能单独归因于天线。</li>
<li>干扰源距天线 15 cm 近场放置、双天线相距 30 cm，两天线处干扰场强可能不完全一致，绝对差值含几何误差；结论以双天线同步配对差分为主。</li>
<li>每组仅单轮测试、每干扰场景仅 1 个片段（中间 10 s 稳态窗口），样本量有限；0728-076-560 组 392MHz 段因 560 大量丢星，共同卫星配对仅 4 对，wilcoxon 检验不可用，该场景仅按衰减量判定。</li>
<li>076 的基线绝对水平在不同测试日之间存在漂移，跨组比较绝对值需谨慎，组内对比不受影响。</li>
</ul>
</div>
</div>
</body>
</html>""")
    return "".join(parts), rank_list, composite, detail, scen_judge


def conclusion_reason(best_test, data, scen_judge):
    if best_test is None:
        return ""
    test, comp_id, comp_name = best_test
    d = data[test]
    wins = [s for s in SCENARIOS if scen_judge[(test, s)][0].startswith(comp_name)]
    ties = [s for s in SCENARIOS if scen_judge[(test, s)][0].startswith("基本持平")]
    losses = [s for s in SCENARIOS if scen_judge[(test, s)][0].startswith(BASELINE_NAME)]
    base_gap = d["baseline_comp"] - d["baseline_076"]
    # 竞品相对 076 衰减优势最大的场景（衰减差 = 076 - 竞品，最负 = 竞品优势最大）
    adv_scen = min(SCENARIOS, key=lambda s: scen_judge[(test, s)][1])
    return (f"无干扰基线绝对水平较 076 {fmt_signed(base_gap)} dB；"
            f"4 个干扰场景中胜出 {len(wins)} 个（{'、'.join(wins) if wins else '无'}），"
            f"持平 {len(ties)} 个，076 胜出 {len(losses)} 个（{'、'.join(losses) if losses else '无'}）；"
            f"优势最大的 {adv_scen} 下衰减仅 "
            f"{fmt(d[f'att_comp_{adv_scen}'])} dB（076 为 {fmt(d[f'att_076_{adv_scen}'])} dB）。")


def pair_verdict(t, data, scen_judge, composite):
    test, comp_id, comp_name = t
    d = data[test]
    w076 = sum(1 for s in SCENARIOS if scen_judge[(test, s)][0].startswith(BASELINE_NAME))
    wc = sum(1 for s in SCENARIOS if scen_judge[(test, s)][0].startswith(comp_name))
    base_gap = d["baseline_comp"] - d["baseline_076"]
    verdict = "076 总体更好" if composite[test] > 0.5 else (f"{comp_name} 总体更好" if composite[test] < -0.5 else "两者接近")
    return (f"<b>076 vs {comp_name}</b>（{test}）：基线差 {fmt_signed(base_gap)} dB，"
            f"干扰场景 076 胜 {w076} / {comp_name} 胜 {wc} / 平 {4 - w076 - wc}，"
            f"综合优势分 {fmt_signed(composite[test], 1)} → <b>{verdict}</b>")


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    data = collect()
    html, rank_list, composite, detail, scen_judge = build_html(data)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT_HTML}")

    # ---- 控制台摘要，便于核对 ----
    print("\n===== 摘要 =====")
    for test, comp_id, comp_name in TESTS:
        d = data[test]
        print(f"\n[{test}] 076 vs {comp_name}")
        print(f"  基线 C/N0: 076={fmt(d['baseline_076'], 2)}  {comp_name}={fmt(d['baseline_comp'], 2)}  "
              f"差(竞品-076)={fmt_signed(d['baseline_comp'] - d['baseline_076'], 2)}")
        for scen in SCENARIOS:
            winner, att_gap, score = scen_judge[(test, scen)]
            print(f"  {scen}: 076 {fmt(d[f'att_076_{scen}'], 2)} / {comp_name} {fmt(d[f'att_comp_{scen}'], 2)}"
                  f"  衰减差={fmt_signed(att_gap, 2)}  wx={fmt_signed(d[f'wx_diff_{scen}'], 2)}"
                  f"  绝对 076={fmt(d[f'abs_076_{scen}'], 2)}/{fmt(d[f'abs_comp_{scen}'], 2)}"
                  f"  -> {winner} (score={fmt_signed(score, 2)})")
        bg, ma, mb = detail[test]
        print(f"  综合: 基线差={fmt_signed(bg, 2)} 平均衰减差={fmt_signed(ma, 2)} 平均wx差={fmt_signed(mb, 2)}"
              f"  综合优势分={fmt_signed(composite[test], 2)}")
    print("\n排名: " + " > ".join(n for _, n, _ in rank_list))


if __name__ == "__main__":
    main()
