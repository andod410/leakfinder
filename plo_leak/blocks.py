"""Utveckling över tid: alla händer i urvalet delas i block om BLOCK händer (i tidsordning).

Per block mäts det som går att mäta säkert på 5 000 händer – ditt beteende:
* hur ofta du bryter mot varje regel (andel av tillfällena),
* väntad läckkostnad i bb/100 = dina regelbrott × vad ett brott kostar (försiktig kostnad, uppmätt på
  alla händer – den beror på handen och motståndarna, inte på dig, och blir säkrare ju fler händer),
* VPIP.
Resultatet (all-in EV) visas också, men på 5 000 händer är felmarginalen ±25–35 bb/100 – det är brus.
Därför visas även ett rullande resultat över de senaste ROLL blocken.

Nya läckor: dina senaste RECENT händer jämförs med alla tidigare. En varning ges när du
* bryter mot en regel klart oftare än förut, eller
* spelar klart fler händer från en position än förut (VPIP i samma läge: position, antal spelare, nivå,
  bordstyp), eller 3-bettar klart oftare/mer sällan mot en öppning från en position.
"Klart" = skillnaden är större än 3 felmarginaler (felmarginal per spelpass) (många jämförelser görs samtidigt, därför strängare än 95 %).
"""
from __future__ import annotations

import math

import numpy as np

BLOCK = 5000
MIN_LAST = 1000       # ett ofullständigt sista block visas om det har minst så många händer
ROLL = 5              # rullande resultat över 5 block = 25 000 händer
RECENT = 10000
MIN_OPPS = 20         # färre tillfällen i en ruta = grå (för lite att säga något)
Z = 3.0


def _blocks_of(n: int):
    """Start/slut-index för blocken (det sista ofullständiga tas med om det är stort nog)."""
    out = [(a, min(a + BLOCK, n)) for a in range(0, n, BLOCK)]
    if len(out) > 1 and out[-1][1] - out[-1][0] < MIN_LAST:
        a, _ = out.pop()
        out[-1] = (out[-1][0], n)
    return out


def block_table(st, rules_doc) -> dict:
    from .facts import dt_of
    from .fatigue import _cluster_mean_se, _vpip_dev, hand_session_info
    from .practice import broke_mask, careful_costs, first_rows, violation_index
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None or len(st.rows) < 2 * BLOCK:
        return {}
    H = ft.H
    r, sess, _ = hand_session_info(st)
    n = len(r)
    pos_of = np.full(ft.n, -1, np.int64)
    pos_of[r] = np.arange(n)
    B = _blocks_of(n)
    blk = np.zeros(n, np.int64)
    for i, (a, b) in enumerate(B):
        blk[a:b] = i
    nb = len(B)
    ev = H["ev"][r].astype(float)
    vp = H["vpip"][r].astype(float)
    blocks = []
    for i, (a, b) in enumerate(B):
        m = blk == i
        e, se = _cluster_mean_se(ev[m], sess[m])
        lo = max(0, i - ROLL + 1)
        mr = (blk >= lo) & (blk <= i)
        re_, rse = _cluster_mean_se(ev[mr], sess[mr])
        blocks.append({"i": i, "label": f"{i + 1}", "hands": int(b - a), "full": b - a >= BLOCK,
                       "from": dt_of(int(H["ts"][r[a]])).strftime("%Y-%m-%d"),
                       "to": dt_of(int(H["ts"][r[b - 1]])).strftime("%Y-%m-%d"),
                       "vpip": 100.0 * float(vp[m].mean()), "ev100": 100.0 * e, "ev_se": 100.0 * se,
                       "roll100": 100.0 * re_, "roll_se": 100.0 * rse, "roll_hands": int(mr.sum()),
                       "cost100": 0.0, "breaks": 0})
    rules = (rules_doc or {}).get("rules") or []
    pre = st.decisions.pre if getattr(st, "decisions", None) else None
    rule_rows = []
    warnings = []
    have_pre = pre is not None and pre.ft is not None and len(pre)
    if rules and have_pre:
        vi = violation_index(rules, pre)
        k = pos_of[pre.hidx]
        m = first_rows(pre) & (vi >= 0) & (k >= 0)
        brk = broke_mask(rules, pre, vi) & m
        cc = careful_costs(rules, pre, vi)
        bi = np.where(k >= 0, blk[np.maximum(k, 0)], -1)
        opp = np.zeros((len(rules), nb), np.int64)
        dev = np.zeros((len(rules), nb), np.int64)
        np.add.at(opp, (vi[m], bi[m]), 1)
        np.add.at(dev, (vi[brk], bi[brk]), 1)
        cost_b = (dev * cc[:, None]).sum(0)
        for i in range(nb):
            blocks[i]["cost100"] = -100.0 * float(cost_b[i]) / blocks[i]["hands"]
            blocks[i]["breaks"] = int(dev[:, i].sum())
        recent = k >= n - RECENT
        for ri, ru in enumerate(rules):
            if not opp[ri].sum():
                continue
            cells = [{"opps": int(opp[ri, i]), "dev": int(dev[ri, i]),
                      "rate": 100.0 * dev[ri, i] / opp[ri, i] if opp[ri, i] >= MIN_OPPS else None} for i in range(nb)]
            per100 = [-100.0 * dev[ri, i] * cc[ri] / blocks[i]["hands"] for i in range(nb)]
            row = {"id": ru["id"], "title": ru["title"], "level": ru.get("level", "bekräftad"), "cells": cells,
                   "per100": per100, "cost_hand": float(cc[ri])}
            fv = [c["rate"] for c in cells if c["rate"] is not None]
            row["first"], row["last"] = (fv[0], fv[-1]) if fv else (None, None)
            rule_rows.append(row)
            # ny läcka: bryter du oftare mot regeln nu än förut?
            mi = m & (vi == ri)
            o1, o0 = int((mi & recent).sum()), int((mi & ~recent).sum())
            if o1 >= 50 and o0 >= 50 and n - RECENT >= RECENT:
                # andel brott med felmarginal per spelpass (brott i samma pass hänger ihop)
                x = brk[mi].astype(float)
                cs = sess[np.maximum(k[mi], 0)]
                rr = recent[mi]
                p1, s1 = _cluster_mean_se(x[rr], cs[rr])
                p0, s0 = _cluster_mean_se(x[~rr], cs[~rr])
                se = math.sqrt(s1 ** 2 + s0 ** 2) if np.isfinite(s1) and np.isfinite(s0) else float("nan")
                if np.isfinite(se) and se > 0 and (p1 - p0) / se > Z and p1 - p0 >= 0.05:
                    warnings.append({"kind": "regel", "title": ru["title"],
                                     "text": f"Du bryter mot regeln i {100 * p1:.0f} % av tillfällena de senaste "
                                             f"{RECENT:,} händerna, mot {100 * p0:.0f} % tidigare.".replace(",", " "),
                                     "cost100": -100.0 * (p1 - p0) * o1 * cc[ri] / RECENT})
    # nya läckor i VPIP och 3-bet per position
    if n - RECENT >= RECENT:
        dv = _vpip_dev(H, r)
        late = np.arange(n) >= n - RECENT
        for pc in np.unique(H["pos"][r]):
            mp = H["pos"][r] == pc
            a_, b_ = mp & late, mp & ~late
            if a_.sum() < 500 or b_.sum() < 500:
                continue
            m1, s1 = _cluster_mean_se(dv[a_], sess[a_])
            m0, s0 = _cluster_mean_se(dv[b_], sess[b_])
            se = math.sqrt(s1 ** 2 + s0 ** 2) if np.isfinite(s1) and np.isfinite(s0) else float("nan")
            d = m1 - m0
            if np.isfinite(se) and abs(d) > Z * se and abs(d) >= 0.03:
                p = ft.label("pos", int(pc))
                warnings.append({"kind": "vpip", "title": f"{p}: {'fler' if d > 0 else 'färre'} spelade händer",
                                 "text": f"Du spelar {abs(100 * d):.1f} procentenheter {'fler' if d > 0 else 'färre'} "
                                         f"händer från {p} de senaste {RECENT:,} händerna än tidigare (i samma läge). "
                                         f"{'Kolla att det inte är händer dina regler säger folda.' if d > 0 else 'Det kan vara bra – eller för tight. Kolla Läckor.'}".replace(",", " "),
                                 "cost100": None})
        if have_pre:
            from .threebet import SPOTS
            k = pos_of[pre.hidx]
            fm = first_rows(pre) & pre.is_spot(*SPOTS) & (k >= 0)
            played = fm & ~np.isnan(pre.delta)
            is_r = pre.kind == pre.ft.code("kind", "raise")
            lt = np.zeros(len(pre), bool)
            lt[k >= 0] = k[k >= 0] >= n - RECENT
            for pc in np.unique(pre.pos[played]):
                mp = played & (pre.pos == pc)
                o1, o0 = int((mp & lt).sum()), int((mp & ~lt).sum())
                if o1 < 100 or o0 < 100:
                    continue
                cs = sess[np.maximum(k, 0)]
                x = is_r.astype(float)
                p1, s1 = _cluster_mean_se(x[mp & lt], cs[mp & lt])
                p0, s0 = _cluster_mean_se(x[mp & ~lt], cs[mp & ~lt])
                se = math.sqrt(s1 ** 2 + s0 ** 2) if np.isfinite(s1) and np.isfinite(s0) else float("nan")
                if np.isfinite(se) and se > 0 and abs(p1 - p0) / se > Z and abs(p1 - p0) >= 0.05:
                    pl = pre.label("pos", int(pc))
                    warnings.append({"kind": "3bet", "title": f"{pl}: 3-bettar {'oftare' if p1 > p0 else 'mer sällan'} mot öppning",
                                     "text": f"Av händerna du spelar mot en öppning från {pl} 3-bettar du {100 * p1:.0f} % "
                                             f"de senaste {RECENT:,} händerna, mot {100 * p0:.0f} % tidigare.".replace(",", " "),
                                     "cost100": None})
    warnings.sort(key=lambda w: -(w["cost100"] or 0.0))
    c = [b["cost100"] for b in blocks]
    trend = None
    if len(c) >= 2 and rules:
        trend = {"first": c[0], "last": c[-1], "best": min(c), "change": c[-1] - c[0]}
    return {"blocks": blocks, "rules": rule_rows, "warnings": warnings, "trend": trend, "block": BLOCK,
            "roll": ROLL, "recent": RECENT, "hands": n, "min_opps": MIN_OPPS}


def rate_color(rate) -> str:
    """0 % = grön, 5 % (målet) = gulgrön, 30 % eller mer = röd."""
    if rate is None:
        return "var(--chip)"
    x = max(0.0, min(1.0, (rate - 2.0) / 28.0))
    return f"color-mix(in srgb, var(--bad) {round(100 * x)}%, var(--good))"


def export_blocks(T: dict) -> dict:
    if not T:
        return {}
    return {"block": T["block"], "blocks": T["blocks"], "warnings": T["warnings"], "trend": T["trend"],
            "rules": [{k: v for k, v in r.items()} for r in T["rules"]]}
