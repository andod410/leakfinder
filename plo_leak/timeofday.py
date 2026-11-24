"""När du vinner: resultat per tid på dygnet och nivå.

Dygnet delas i fyra block (00–06, 06–12, 12–18, 18–24, tiden enligt handhistoriken). För varje block och
nivå räknas all-in EV per 100 händer med felmarginal per spelpass. Det bästa blocket jämförs med resten;
eftersom fyra block jämförs krävs z > 2,5 (Bonferroni) för "tydligt". Skillnaden är hittad i efterhand och
bör bekräftas på nya händer – värdet i läckkartan räknas därför försiktigt.
"""
from __future__ import annotations

import math

import numpy as np

BLOCKS = [(0, 6, "00–06"), (6, 12, "06–12"), (12, 18, "12–18"), (18, 24, "18–24")]
Z = 2.5
MIN_HANDS = 3000


def when_table(st) -> dict:
    from .fatigue import _cluster_mean_se, hand_session_info
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None or len(st.rows) < 4 * MIN_HANDS:
        return {}
    H = ft.H
    r, sess, _ = hand_session_info(st)
    n = len(r)
    ev = H["ev"][r].astype(float)
    hour = (H["ts"][r].astype(np.int64) // 3600) % 24
    blk = np.searchsorted([6, 12, 18], hour, side="right")
    stake = H["stake"][r]
    stakes = [int(c) for c, k in sorted(zip(*np.unique(stake, return_counts=True)), key=lambda t: -t[1]) if k >= MIN_HANDS]
    cols = [{"code": None, "label": "Alla nivåer"}] + [{"code": c, "label": "$" + ft.label("stake", c).replace("/", "/$")} for c in stakes]
    grid = []
    for b, (_, _, lab) in enumerate(BLOCKS):
        row = {"label": lab, "cells": []}
        for c in cols:
            m = (blk == b) & ((stake == c["code"]) if c["code"] is not None else True)
            k = int(m.sum())
            if k < 500:
                row["cells"].append(None)
                continue
            mean, se = _cluster_mean_se(ev[m], sess[m])
            row["cells"].append({"hands": k, "ev100": 100 * mean, "pm": 196 * se, "share": 100.0 * k / n,
                                 "contrib": 100.0 * float(ev[m].sum()) / n})
        grid.append(row)
    totals = []
    for c in cols:
        m = (stake == c["code"]) if c["code"] is not None else np.ones(n, bool)
        mean, se = _cluster_mean_se(ev[m], sess[m])
        totals.append({"ev100": 100 * mean, "pm": 196 * se, "contrib": 100.0 * float(ev[m].sum()) / n, "hands": int(m.sum())})
    # bästa blocket mot resten (alla nivåer)
    best = max(range(len(BLOCKS)), key=lambda b: (grid[b]["cells"][0] or {"ev100": -1e9})["ev100"])
    mb, sb = _cluster_mean_se(ev[blk == best], sess[blk == best])
    mo, so = _cluster_mean_se(ev[blk != best], sess[blk != best])
    d, se = mb - mo, math.sqrt(sb ** 2 + so ** 2)
    sig = bool(np.isfinite(se) and d / se > Z)
    outside = float((blk != best).mean())
    value100 = max(0.0, 100 * (d - Z * se)) * outside * 0.5 if sig else 0.0
    # bästa rutan (nivå × block) och sämsta
    cells = [(grid[b]["cells"][j], BLOCKS[b][2], cols[j]["label"]) for b in range(len(BLOCKS)) for j in range(1, len(cols))
             if grid[b]["cells"][j]]
    best_cell = max(cells, key=lambda t: t[0]["ev100"]) if cells else None
    worst_cell = min(cells, key=lambda t: t[0]["contrib"]) if cells else None
    return {"cols": cols, "grid": grid, "totals": totals, "best": BLOCKS[best][2], "diff100": 100 * d, "pm": 196 * se,
            "z": d / se if se else None, "significant": sig, "value100": value100, "hands": n,
            "best_cell": {"block": best_cell[1], "stake": best_cell[2], **best_cell[0]} if best_cell else None,
            "worst_cell": {"block": worst_cell[1], "stake": worst_cell[2], **worst_cell[0]} if worst_cell else None}


def ev_color(v) -> str:
    if v is None:
        return "var(--chip)"
    x = max(-1.0, min(1.0, v / 20.0))
    return (f"color-mix(in srgb, var(--good) {round(35 + 65 * x)}%, var(--chip))" if x >= 0 else
            f"color-mix(in srgb, var(--bad) {round(35 - 65 * x)}%, var(--chip))")
