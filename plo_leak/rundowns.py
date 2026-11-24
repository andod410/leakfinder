"""Från vilket lägsta kort börjar en rundown bli värd att spela?

För varje hand letas den högsta rundownen upp: fyra olika valörer inom fem steg i rad
(högst en lucka; ess räknas både högt och som 1). Handen grupperas efter rundownens
lägsta kort. För händer du spelade preflop visas:

* resultat jämfört med att folda direkt (all-in EV, efter rake) – exakt, eftersom fold
  preflop alltid kostar exakt det du redan lagt i potten,
* hur stor potten var när du vann med en stege,
* hur ofta din stege förlorade vid showdown (mot högre stege, färg eller kåk).

Huvudtabellen gäller "rena" rundowns – utan suited ess och utan högt par – så att det är
just rundownens värde som mäts. Alla rundown-händer visas också.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from .cards import nut_qualities
from .db import cached
from .statlib import RULE_FAMILIES, RULE_MIN_N, ci_cell

FIRST_SPOTS = {"rfi", "efter_limp", "bb_mot_hojning", "sb_mot_hojning", "mot_hojning", "kall_mot_3bet"}
GROUPS = ["A–3", "4", "5", "6", "7", "8", "9", "T eller högre"]
RANK_TXT = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}
STRAIGHT = 4


def rundown_low(hole) -> int | None:
    """Lägsta kortet i handens högsta rundown (None = ingen rundown)."""
    rs = set(c[0] for c in hole)
    if 14 in rs:
        rs.add(1)
    best = None
    for low in range(1, 11):
        inside = sorted(r for r in rs if low <= r <= low + 4)
        if len(inside) >= 4:
            # välj de fyra högsta i fönstret; lägsta av dem är rundownens lägsta kort
            best = inside[-4]
    return best


def group_of(low: int) -> str:
    if low <= 3:
        return "A–3"
    if low >= 10:
        return "T eller högre"
    return str(low)


def _final_category(h, hero):
    from .ev import CATEGORY, _pairs, _triples, fast_best
    hole = h.hole.get(hero)
    if not hole or len(h.board) < 5:
        return None
    return CATEGORY[fast_best(_pairs(hole), _triples(h.board[:5]))]


def _stat(x, c, m: int = 1):
    return ci_cell(x, c, empty="–", min_n=RULE_MIN_N, m_tests=m * RULE_FAMILIES)


def rundown_table(st) -> dict:
    """Bygger tabellerna ur faktatabellen (inga händer behöver läsas in)."""
    pre = st.decisions.pre
    out = {}
    if pre.ft is None or not len(pre):
        return {"pure": {"rows": [], "cum": [], "answer": _answer([])},
                "all": {"rows": [], "cum": [], "answer": _answer([])}}
    H = pre.ft.H
    m = np.flatnonzero(pre.is_spot(*FIRST_SPOTS))
    # första beslutet per hand
    _, first = np.unique(pre.hidx[m], return_index=True)
    r = m[np.sort(first)]
    hx = pre.hidx[r]
    low = H["rdlow"][hx].astype(int)
    keep = low >= 0
    r, hx, low = r[keep], hx[keep], low[keep]
    pure = ~(H["hp"][hx] | H["sa"][hx])
    delta, clu = pre.delta[r], pre.clu[r]
    played = ~np.isnan(delta)
    straight = (H["cat"][hx] == STRAIGHT) & (H["fold_st"][hx] < 0)
    won, sd, pot = H["won"][hx], H["sd"][hx], H["pot"][hx]
    grp = np.array([group_of(int(x)) for x in low], dtype=object) if len(low) else np.zeros(0, dtype=object)
    for kind_, km in (("pure", pure), ("all", np.ones(len(r), bool))):
        rows = []
        cells = {}
        # Bonferroni över grupperna i tabellen (rader) respektive i "från X och uppåt" (kumulativt)
        m_rows = max(1, sum(1 for g in GROUPS if int((km & (grp == g) & played).sum()) >= RULE_MIN_N))
        for g in GROUPS:
            gm = km & (grp == g)
            if not gm.any():
                continue
            pm = gm & played
            d, c = delta[pm], clu[pm]
            cells[g] = (d, c)
            s = _stat(d, c, m_rows)
            wp = pot[pm & straight & won]
            sds = int((pm & straight & sd).sum())
            lost = int((pm & straight & sd & ~won).sum())
            rows.append({"group": g, "dealt": int(gm.sum()), "played": s["n"],
                         "play_pct": 100.0 * s["n"] / int(gm.sum()), **s,
                         "straight_wins": int(len(wp)),
                         "avg_win_pot": float(np.mean(wp)) if len(wp) else None,
                         "median_win_pot": float(np.median(wp)) if len(wp) else None,
                         "sd_straights": sds,
                         "straight_lost_pct": (100.0 * lost / sds if sds >= 20 else None)})
        # "från X och uppåt": kumulativt
        cum = []
        m_cum = max(1, 2 * len(cells))
        for i, g in enumerate(GROUPS):
            above = [cells[x] for x in GROUPS[i:] if x in cells]
            below = [cells[x] for x in GROUPS[:i] if x in cells]
            d = np.concatenate([a[0] for a in above]) if above else np.zeros(0)
            c = np.concatenate([a[1] for a in above]) if above else np.zeros(0, np.int64)
            db = np.concatenate([a[0] for a in below]) if below else np.zeros(0)
            cb = np.concatenate([a[1] for a in below]) if below else np.zeros(0, np.int64)
            if not len(d):
                continue
            cum.append({"from": g, "above": _stat(d, c, m_cum), "below": _stat(db, cb, m_cum) if len(db) else None})
        out[kind_] = {"rows": rows, "cum": cum, "answer": _answer(rows)}
    return out


def _answer(rows) -> dict:
    """Lägsta kort från vilket rundowns inte längre förlorar mot fold.
    Kräver att varje grupp därifrån och uppåt inte är klart förlorande, och att gruppen
    precis under är klart förlorande – annars sägs att det inte går att avgöra."""
    r = {x["group"]: x for x in rows if x["n"] >= 30}
    order = [g for g in GROUPS if g in r]
    if not order:
        return {"kind": "unknown", "text": "För få spelade rundowns för att säga något."}
    losing = [g for g in order if r[g]["verdict"] == "förlorar"]
    if not losing:
        return {"kind": "none", "text": "Ingen grupp av rundowns har förlorat klart mot fold – det går inte att peka ut "
                                       "någon gräns i din data."}
    top_losing = max(order.index(g) for g in losing)
    if top_losing == len(order) - 1:
        return {"kind": "all", "text": "Även de högsta rundownsen har förlorat mot fold i din data."}
    nxt = order[top_losing + 1]
    above = order[top_losing + 1:]
    good = [g for g in above if r[g]["verdict"] == "lönsamt"]
    tail = (f" Grupp{'en' if len(good) == 1 else 'erna'} {', '.join(good)} har varit klart lönsam{'' if len(good) == 1 else 'ma'}."
            if good else " De är dock inte heller klart lönsamma – de ligger runt noll.")
    return {"kind": "cut", "from": nxt,
            "text": (f"Rundowns med lägsta kort {order[top_losing]} eller lägre har förlorat klart mot fold. "
                     f"Från lägsta kort {nxt} och uppåt förlorar ingen grupp klart." + tail)}
