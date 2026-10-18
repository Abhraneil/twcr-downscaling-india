#!/usr/bin/env python3
"""LaTeX tables for the white paper, written straight from the scoring output so no number
is typed by hand:

    python docs/whitepaper/make_tables.py      (run by `make` in docs/whitepaper)

Reads  results/scores.csv (full precision; SCORECARD.md, rounded to 3 decimals, if it is
       missing) and results/HYPOTHESES.md, all written by scripts/scoring/score_all.py
Writes docs/whitepaper/tables/scores_<event>.tex and hypotheses.tex
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "tables"

COLS = [("bias_pct", "{:+.0f}"), ("corr_total", "{:.2f}"), ("peak_ratio", "{:.2f}"),
        ("maxloc_err_km", "{:.0f}"), ("SAL_S", "{:+.2f}"), ("SAL_A", "{:+.2f}"), ("SAL_L", "{:.2f}"),
        ("FSS_115.6mm_5pt", "{:.2f}"), ("FSS_204.5mm_5pt", "{:.2f}")]
NAMES = {"DRIVER": "driver alone", "WRF_12km": "WRF 12\\,km", "WRF_3km": "WRF 3\\,km",
         "RegCM_12km": "RegCM5 12\\,km", "RegCM_3km": "RegCM5 3\\,km"}
ORDER = ["DRIVER", "WRF_12km", "WRF_3km", "RegCM_12km", "RegCM_3km"]


def md_tables(text: str) -> dict[str, list[dict[str, str]]]:
    """Markdown pipe tables under '## <name>' headings -> {name: [row dicts]}."""
    out, name, head = {}, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            name, head = line[3:].strip(), None
            out[name] = []
        elif line.startswith("|") and name is not None:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if head is None:
                head = cells
            elif not re.fullmatch(r"[:\- ]+", "".join(cells)):
                out[name].append(dict(zip(head, cells)))
    return out


def split_run(run: str) -> tuple[str, str]:
    """'WRF_12km_ERA5' -> ('WRF_12km', 'ERA5'); 'DRIVER_20CRv3' -> ('DRIVER', '20CRv3')."""
    parts = run.split("_")
    return "_".join(parts[:-1]), parts[-1]


def score_table(event: str, rows: list[dict[str, str]]) -> str:
    runs = {split_run(r["run"]): r for r in rows if r["run"] != "IMD"}
    drivers = [d for d in ("20CRv3", "ERA5") if any(k[1] == d for k in runs)]
    lines = []
    for i, d in enumerate(drivers):
        if i:
            lines.append("\\midrule")
        for kind in ORDER:
            r = runs.get((kind, d))
            if r is None:
                continue
            cells = [fmt.format(float(r[c])) if r.get(c, "nan") not in ("nan", "") else "--" for c, fmt in COLS]
            cells = [c.replace("-", "$-$") if c.startswith("-") else c for c in cells]
            lines.append(f"{NAMES[kind]} & {d} & " + " & ".join(cells) + " \\\\")
    return "\n".join(lines) + "\n"


def from_csv(f: Path) -> dict[str, list[dict[str, str]]]:
    """results/scores.csv (event, run, metric, value) -> the same form as md_tables()."""
    tab: dict[str, dict[str, dict[str, str]]] = {}
    with open(f) as fh:
        for r in csv.DictReader(fh):
            tab.setdefault(r["event"], {}).setdefault(r["run"], {"run": r["run"]})[r["metric"]] = r["value"]
    return {ev: list(runs.values()) for ev, runs in tab.items()}


def hypotheses_table(text: str) -> str:
    rows = md_tables("## H\n" + text.split("\n", 1)[1])["H"]
    lines = []
    prev = None
    for r in rows:
        if prev and r["ID"] != prev:
            lines.append("\\midrule")
        prev = r["ID"]
        case = r["Case"].replace("_", "\\_")
        val = re.sub(r"-(\d)", r"$-$\1", r["Value(s)"].replace("%", "\\%").replace("->", "$\\to$"))
        res = "\\textbf{pass}" if r["Result"] == "PASS" else "fail"
        lines.append(f"{r['ID']} & {case} & {val} & {res} \\\\")
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    f = ROOT / "results" / "scores.csv"
    sc = from_csv(f) if f.exists() else md_tables((ROOT / "results" / "SCORECARD.md").read_text())
    print(f"scores from {f.name if f.exists() else 'SCORECARD.md'}")
    for ev, rows in sc.items():
        (OUT / f"scores_{ev}.tex").write_text(score_table(ev, rows))
        print(f"tables/scores_{ev}.tex: {len(rows) - 1} runs")
    (OUT / "hypotheses.tex").write_text(hypotheses_table((ROOT / "results" / "HYPOTHESES.md").read_text()))
    print("tables/hypotheses.tex")


if __name__ == "__main__":
    main()
