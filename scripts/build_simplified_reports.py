# Temporary script: strip selected chapters from the 4 pairwise comparison
# reports to produce simplified versions. Chapters are <div class="card">
# blocks whose <h2> starts with "N. ". Chapter numbers are kept as-is
# (with gaps) so they stay traceable to the full reports and the guide.
import glob
import os
import re

from bs4 import BeautifulSoup

KEEP = {1, 2, 3, 4, 8, 9, 10, 13, 14, 18}

for path in sorted(glob.glob("reports/*/antenna_*_vs_*_report.html")):
    if path.endswith("_simplified_report.html"):
        continue
    html = open(path, encoding="utf-8").read()
    soup = BeautifulSoup(html, "html.parser")
    removed = []
    for card in soup.select("div.card"):
        h2 = card.find("h2")
        if not h2:
            continue
        m = re.match(r"\s*(\d+)\.", h2.get_text())
        if m and int(m.group(1)) not in KEEP:
            removed.append(int(m.group(1)))
            card.decompose()
    out = path.replace("_report.html", "_simplified_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(str(soup))
    kept = [int(re.match(r"\s*(\d+)\.", h.get_text()).group(1))
            for h in soup.select("div.card h2") if re.match(r"\s*(\d+)\.", h.get_text())]
    print(f"{os.path.basename(out)}: kept {kept}, removed {removed}")
