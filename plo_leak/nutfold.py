"""Starthänder efter antal nöt-egenskaper – jämfört med att folda direkt.

"Netto när spelad" (resultatet i händer du frivilligt spelade) räknar med blinden du redan
lagt i SB och BB. Därför säger det inte vad en fold hade gett. Här jämförs i stället ditt
första beslut preflop med att folda just då: en fold kostar exakt det du redan lagt i potten
(0 utanför blindarna, blinden i SB/BB). Allt räknas med all-in EV och efter rake.

* "Förlorar"/"lönsamt" kräver ett kluster-bootstrap-test (spelpass hålls ihop) som klarar
  Bonferroni över alla celler i samma tabell – annars "jämnt / osäkert".
* Totalt mot fold = summan över händerna: vad du hade vunnit (+) eller förlorat (−) på att
  spela dem i stället för att folda. Det är facit för urvalet, inte en prognos.
"""
from __future__ import annotations

import numpy as np

from .rundowns import FIRST_SPOTS
from .statlib import RULE_FAMILIES, RULE_MIN_N, ci_cell

POS_ORDER = ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
MIN_N = RULE_MIN_N


def nut_fold_table(st) -> dict:
    pre = st.decisions.pre
    if pre.ft is None or not len(pre):
        return {}
    ft = pre.ft
    H = ft.H
    m = np.flatnonzero(pre.is_spot(*FIRST_SPOTS))
    if not len(m):
        return {}
    _, first = np.unique(pre.hidx[m], return_index=True)
    r = m[np.sort(first)]
    hx = pre.hidx[r]
    nut = H["nut"][hx].astype(int)
    keep = nut >= 0
    r, hx, nut = r[keep], hx[keep], nut[keep]
    delta, clu, pos = pre.delta[r], pre.clu[r], pre.pos[r]
    played = ~np.isnan(delta)
    labels = sorted({int(x) for x in np.unique(nut)}, key=lambda c: ft.label("nut", c))
    present = [int(c) for c in np.unique(pos)]
    order = {p: i for i, p in enumerate(POS_ORDER)}
    pos_codes = sorted(present, key=lambda c: (order.get(ft.label("pos", c), 99), ft.label("pos", c)))

    def cell(mask, m_tests):
        pm = mask & played
        s = ci_cell(delta[pm], clu[pm], min_n=MIN_N, m_tests=m_tests * RULE_FAMILIES)
        dealt = int(mask.sum())
        return {**s, "dealt": dealt, "played": int(pm.sum()), "play_pct": 100.0 * pm.sum() / dealt if dealt else 0.0,
                "total": float(delta[pm].sum()) if pm.any() else 0.0}

    m_rows = max(1, sum(1 for c in labels if int(((nut == c) & played).sum()) >= MIN_N))
    rows = [{"name": ft.label("nut", c), **cell(nut == c, m_rows)} for c in labels]
    m_cells = max(1, sum(1 for c in labels for p in pos_codes if int(((nut == c) & (pos == p) & played).sum()) >= MIN_N))
    grid = []
    for c in labels:
        cells = []
        for p in pos_codes:
            mk = (nut == c) & (pos == p)
            cells.append({"pos": ft.label("pos", p), **cell(mk, m_cells)} if mk.any() else None)
        grid.append({"name": ft.label("nut", c), "cells": cells})
    return {"rows": rows, "positions": [ft.label("pos", p) for p in pos_codes], "grid": grid,
            "m_rows": m_rows, "m_cells": m_cells}


def confirmed_losses(tbl: dict) -> list:
    """Celler (nöt-egenskaper × position) med säkerställd förlust jämfört med fold."""
    out = []
    for g in (tbl or {}).get("grid", []):
        for c in g["cells"]:
            if c and c["verdict"] == "förlorar":
                out.append({"nut": g["name"], "pos": c["pos"], "mean": c["mean"], "n": c["n"], "total": c["total"]})
    return out
