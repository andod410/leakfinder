"""Betstorlek (2.72): hur poolen svarar per storlek – med GG:s rake – och hur dina egna storlekar fördelar sig.

Frågan från projektets start: är du för polariserad (antingen litet eller stort, sällan mitt emellan)?

* bet_events(): en rad per FÖRSTA bet på varje gata (flop, turn, river) i varje hand, av vem som helst. Storleken räknas på
  effektivt belopp (högst vad den största motståndaren kan syna) i andel av potten före betten.
  who: 0 = poolen bettar och du är inte med i handen (poolen mot poolen), 1 = du bettar, 2 = poolen bettar mot dig.
  out: 0 = alla foldade, 1 = minst en syn (ingen höjning), 2 = höjning.
* Break-even för en ren bluff med rake: fold ≥ b / (b + 1 − r), b = betten / potten, r = rake i andel av potten när du vinner
  den direkt (5 %, med nivåns tak uppskattat ur dina händer).
* Polariseringsmatris: dina bets per handgrupp × storlek, och hur stor andel som är extrema (< 45 % eller > 85 %) jämfört med
  poolens egen fördelning. Ingen solver – poolen är jämförelsen, inte GTO.
"""
from __future__ import annotations

import numpy as np

SIZES = [(0.0, 0.40, "⅓ (under 40 %)"), (0.40, 0.60, "½ (40–60 %)"), (0.60, 0.85, "⅔–¾ (60–85 %)"),
         (0.85, 1.10, "pott (85–110 %)"), (1.10, 99.0, "överbet (över 110 %)")]
STREETS = {1: "Flop", 2: "Turn", 3: "River"}
RAKE = 0.05
MIN_N = 30
SMALL, BIG = 0.45, 0.85   # polarisering: under 45 % eller över 85 % av potten räknas som extremt


def size_code(frac: float) -> int:
    for i, (lo, hi, _) in enumerate(SIZES):
        if lo <= frac < hi:
            return i
    return len(SIZES) - 1


def bet_events(h, hero: str) -> list:
    """[(gata 1–3, who, frac, spelare, ip, out, pott_bb)] – första bet per gata."""
    from .parser import POSTFLOP_ORDER
    bb = h.bb or 1.0
    order = {p: i for i, p in enumerate(POSTFLOP_ORDER)}
    put = {p: 0.0 for p in h.seats}
    folded = set()
    out = []
    acts = [a for a in h.actions if not a.inferred]
    sidx = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
    i = 0
    while i < len(acts):
        a = acts[i]
        st = sidx.get(a.street, 0)
        if st >= 1 and a.kind == "bet":
            active = [p for p in h.seats if p not in folded]
            pot = sum(put.values())
            if pot > 0 and len(active) >= 2:
                rem = {p: h.stacks.get(p, 0.0) - put[p] for p in active}
                opp = max((rem[p] for p in active if p != a.player), default=0.0)
                eff = min(a.added, max(opp, 0.0))
                can = [p for p in active if rem[p] > 1e-9]
                ip = bool(can) and max(can, key=lambda p: order.get(h.positions.get(p, ""), -1)) == a.player
                res = 0
                for b in acts[i + 1:]:
                    if b.street != a.street:
                        break
                    if b.kind == "raise":
                        res = 2
                        break
                    if b.kind == "call":
                        res = 1
                who = 1 if a.player == hero else (2 if hero in active else 0)
                out.append((st, who, eff / pot, len(active), int(ip), res, pot / bb))
            # resten av gatan: bara bokföring
            street = a.street
            while i < len(acts) and acts[i].street == street:
                b = acts[i]
                put[b.player] = put.get(b.player, 0.0) + b.added
                if b.kind == "fold":
                    folded.add(b.player)
                i += 1
            continue
        put[a.player] = put.get(a.player, 0.0) + a.added
        if a.kind == "fold":
            folded.add(a.player)
        i += 1
    return out


def _rake_caps(ft, rows) -> dict:
    """Rake-tak per nivå i bb: 99:e percentilen av pottens avgift i händer med flop (GG: 5 %, tak)."""
    H = ft.H
    caps = {}
    for code in np.unique(H["stake"][rows]):
        m = rows[(H["stake"][rows] == code) & (H["pot_fee"][rows] > 0)]
        caps[int(code)] = float(np.percentile(H["pot_fee"][m], 99)) if len(m) >= 50 else 3.0
    return caps


def betsize_report(st) -> dict:
    ft = getattr(st, "ft", None)
    B = ft.t.get("bsz") if ft is not None else None
    if B is None or not len(B["hidx"]):
        return {}
    rows = np.asarray(st.rows, dtype=np.int64)
    mask = np.zeros(ft.n, bool)
    mask[rows] = True
    m = ft.subset_mask(mask, "bsz")
    if m.sum() < 200:
        return {}
    caps = _rake_caps(ft, rows)
    H = ft.H
    stake = H["stake"][B["hidx"]]
    cap = np.array([caps.get(int(s), 3.0) for s in stake])
    pot = np.maximum(B["pot"], 1e-9)
    r = np.minimum(RAKE, cap / pot)
    frac = B["frac"]
    be = frac / (frac + 1.0 - r)
    sc = np.array([size_code(f) for f in frac], np.int8)
    hu = B["np"] == 2
    table = []
    for s in (1, 2, 3):
        for k, (_lo, _hi, name) in enumerate(SIZES):
            base = m & hu & (B["st"] == s) & (sc == k)
            pool = base & (B["who"] == 0)
            mine = base & (B["who"] == 1)
            row = {"street": STREETS[s], "size": name, "n_pool": int(pool.sum()), "n_hero": int(mine.sum())}
            if pool.sum():
                row.update(fold_pool=100.0 * float((B["out"][pool] == 0).mean()),
                           call_pool=100.0 * float((B["out"][pool] == 1).mean()),
                           raise_pool=100.0 * float((B["out"][pool] == 2).mean()),
                           be=100.0 * float(be[pool].mean()))
            if mine.sum():
                row.update(fold_hero=100.0 * float((B["out"][mine] == 0).mean()),
                           raise_hero=100.0 * float((B["out"][mine] == 2).mean()),
                           be_hero=100.0 * float(be[mine].mean()))
            fp = row.get("fold_pool") if row["n_pool"] >= MIN_N else None
            row["edge"] = None if fp is None else fp - row["be"]
            row["ok"] = row["n_pool"] >= MIN_N
            table.append(row)
    # storleksfördelning: du mot poolen (första bet på gatan, alla bordstorlekar)
    dist = []
    for s in (1, 2, 3):
        d = {"street": STREETS[s]}
        for who, key in ((1, "hero"), (0, "pool")):
            mm = m & (B["st"] == s) & (B["who"] == who)
            n = int(mm.sum())
            d[f"n_{key}"] = n
            d[key] = [100.0 * float((sc[mm] == k).mean()) if n else 0.0 for k in range(len(SIZES))]
            f = frac[mm]
            d[f"ext_{key}"] = 100.0 * float(((f < SMALL) | (f > BIG)).mean()) if n else None
            d[f"mid_{key}"] = 100.0 * float(((f >= SMALL) & (f <= BIG)).mean()) if n else None
        dist.append(d)
    tot_h = m & (B["who"] == 1)
    tot_p = m & (B["who"] == 0)
    ext_h = 100.0 * float(((frac[tot_h] < SMALL) | (frac[tot_h] > BIG)).mean()) if tot_h.any() else None
    ext_p = 100.0 * float(((frac[tot_p] < SMALL) | (frac[tot_p] > BIG)).mean()) if tot_p.any() else None
    return {"sizes": [x[2] for x in SIZES], "table": table, "dist": dist, "matrix": _matrix(st, ft, mask),
            "ext_hero": ext_h, "ext_pool": ext_p, "small": int(SMALL * 100), "big": int(BIG * 100),
            "caps": {ft.label("stake", k): round(v, 2) for k, v in caps.items()}}


def _matrix(st, ft, mask) -> list:
    """Dina bets (bet och höjning när ingen bettat före dig på gatan) per handgrupp × storlek, med resultat i andel av potten."""
    P = ft.t.get("pfd")
    if P is None or not len(P["hidx"]):
        return []
    m = ft.subset_mask(mask, "pfd")
    k_bet = ft.codes("kind").get("bet", -9)
    bet = m & (P["kind"] == k_bet) & np.isfinite(P["size"])
    groups = []
    for s in (1, 2):
        for g, name in ((0, "Svag utan drag"), (1, "Drag"), (2, "Två par eller bättre")):
            groups.append((STREETS[s], name, bet & (P["st"] == s) & (P["grp"] == g)))
    bf = P["bf"]
    for lo, hi, name in ((0, 0.10, "Nöten/nästan (≤ 10 % slår dig)"), (0.10, 0.35, "Stark (10–35 %)"),
                         (0.35, 0.60, "Medel (35–60 %)"), (0.60, 1.01, "Luft (över 60 %)")):
        groups.append(("River", name, bet & (P["st"] == 3) & (bf >= lo) & (bf < hi)))
    out = []
    sizes = P["size"] / 100.0
    sc = np.array([size_code(x) if np.isfinite(x) else -1 for x in sizes], np.int8)
    y = P["fh"] / np.maximum(P["pot"], 1e-9)
    for street, name, gm in groups:
        n = int(gm.sum())
        cells = []
        for k in range(len(SIZES)):
            cm = gm & (sc == k)
            c = int(cm.sum()) if n else 0
            yy = y[cm] if c else np.zeros(0)
            yy = yy[np.isfinite(yy)]
            cells.append({"n": c, "pct": 100.0 * c / n if n else 0.0,
                          "res": float(yy.mean()) if len(yy) >= MIN_N else None})
        ext = 100.0 * float(((sizes[gm] < SMALL) | (sizes[gm] > BIG)).mean()) if n else None
        out.append({"street": street, "group": name, "n": n, "cells": cells, "ext": ext})
    return out
