"""Resultat efter pottens storlek – var tjänar och förlorar du pengarna?

Händerna delas in efter hela pottens storlek när handen är slut (bb): 0–10, 10–20 … 190–200
och över 200. För varje grupp visas faktiskt resultat och all-in EV (tur i all-ins bortrensad),
totalt, per hand och som bidrag till din bb/100.

Pottens storlek beror delvis på hur handen slutar (pottar du vinner blir ofta stora), så stora
pottar ser alltid ut som stora vinster eller förluster. Därför visas också *vägen in i potten*:
vem som satsade sist och om du själv synade dig in. Det är det som säger något om hur lös du är.
"""
from __future__ import annotations

import numpy as np

from .statlib import cluster_se

EDGES = list(range(0, 201, 10))                     # 0, 10, … 200
LABELS = [f"{a}–{a + 10}" for a in EDGES[:-1]] + ["200+"]
BANDS = [(0, 50, "0–50 bb"), (50, 100, "50–100 bb"), (100, 150, "100–150 bb"), (150, 200, "150–200 bb"),
         (200, 1e12, "200+ bb")]
PATHS = [("bet", "Du satsade sist", "Du bettade eller höjde sist i handen"),
         ("call", "Du synade sist", "En motståndare satsade sist och du synade"),
         ("fold", "Du foldade", "Du foldade någon gång i handen"),
         ("none", "Ingen satsning", "Ingen bettade eller höjde efter blindarna")]


def _bucket(pot: np.ndarray) -> np.ndarray:
    return np.minimum((np.maximum(pot, 0) // 10).astype(int), len(LABELS) - 1)


def _path(H, r) -> np.ndarray:
    """0 = du satsade sist, 1 = du synade sist, 2 = du foldade, 3 = ingen satsning."""
    la = H["la"][r] if "la" in H else np.zeros(len(r), int)
    folded = H["fold_st"][r] >= 0
    out = np.full(len(r), 3, dtype=int)
    out[la == 1] = 0
    out[(la == 2) & ~folded] = 1
    out[folded] = 2
    return out


def pot_table(st) -> dict:
    ft, rows = getattr(st, "ft", None), getattr(st, "rows", None)
    if ft is None or rows is None or not len(rows):
        return {}
    H = ft.H
    r = np.asarray(rows)
    hands = len(r)
    pot = H["pot"][r]
    b = _bucket(pot)
    net, ev, money, ev_m, clu = H["net"][r], H["ev"][r], H["money"][r], H["ev_m"][r], H["clu"][r]
    rows_out = []
    for k, lab in enumerate(LABELS):
        m = b == k
        n = int(m.sum())
        if not n:
            rows_out.append({"label": lab, "n": 0})
            continue
        se = cluster_se(ev[m], clu[m]) if n >= 30 else float("nan")
        rows_out.append({
            "label": lab, "n": n, "share": 100.0 * n / hands,
            "net": float(net[m].sum()), "ev": float(ev[m].sum()),
            "money": float(money[m].sum()), "ev_money": float(ev_m[m].sum()),
            "net_hand": float(net[m].mean()), "ev_hand": float(ev[m].mean()),
            "ev_lo": float(ev[m].mean() - 1.96 * se) if np.isfinite(se) else None,
            "ev_hi": float(ev[m].mean() + 1.96 * se) if np.isfinite(se) else None,
            "net100": 100.0 * float(net[m].sum()) / hands, "ev100": 100.0 * float(ev[m].sum()) / hands,
            "sd_pct": 100.0 * float(H["sd"][r][m].mean()),
            "won_sd_pct": (100.0 * float((H["won"][r][m] & H["sd"][r][m]).sum()) / int(H["sd"][r][m].sum())
                           if int(H["sd"][r][m].sum()) else None),
        })
    # vägen in i potten, i grova band
    path = _path(H, r)
    ic = H["ic"][r] if "ic" in H else np.zeros(hands)
    ia = H["ia"][r] if "ia" in H else np.zeros(hands)
    bands = []
    for lo, hi, lab in BANDS:
        bm = (pot >= lo) & (pot < hi)
        cells = []
        for pi, (key, name, _) in enumerate(PATHS):
            m = bm & (path == pi)
            n = int(m.sum())
            cells.append({"key": key, "n": n, "share": 100.0 * n / int(bm.sum()) if bm.any() else 0.0,
                          "ev": float(ev[m].sum()) if n else 0.0, "ev_hand": float(ev[m].mean()) if n else None,
                          "net": float(net[m].sum()) if n else 0.0})
        tot_in = float(ic[bm].sum() + ia[bm].sum())
        bands.append({"label": lab, "n": int(bm.sum()), "ev": float(ev[bm].sum()), "cells": cells,
                      "call_share": 100.0 * float(ic[bm].sum()) / tot_in if tot_in > 0 else None})
    big = pot >= 150
    return {"rows": rows_out, "bands": bands, "paths": [{"key": k, "name": n, "help": h_} for k, n, h_ in PATHS],
            "hands": hands, "has_path": "la" in H,
            "big": {"n": int(big.sum()), "ev": float(ev[big].sum()), "net": float(net[big].sum()),
                    "ev100": 100.0 * float(ev[big].sum()) / hands, "share": 100.0 * float(big.mean())}}
