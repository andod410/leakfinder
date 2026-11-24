"""Postflop-läckor som fokuspunkter, följda vecka för vecka (riktlinje #1 och #2 från postflop-analysen).

De här är inte "folda"-regler utan frekvenser:

* #1 River, luft, ingen bet framför dig, heads-up: bluffa ca var tredje gång (mål: minst 35 % bet; omgång 2 2026-11-08).
  Luft = minst 60 % av slumpade händer slår dig.
(#2 "syna i stället för att 3-betta när din flop-bet höjs" fanns här i 2.57 men höll inte i nattanalysen
2026-11-08 – synerna mot all-in-höjningar, där 3-bet var omöjlig, hade jämförts med 3-bets – och är borttagen.)

Kostnad nu (bb/100) = hur långt du är från målet i dina senaste RECENT händer × hur ofta situationen
uppstår × vinsten per ändrat beslut. Vinsten per beslut är försiktigt satt (EFF) så att de 197k händerna i
analysen ger ~1,3 bb/100 som nattanalysen 2026-11-08 (där effekten räknades per pott: +4–4,7 bb per bluff;
försiktigt ca en tredjedel av det, eftersom poolen kan anpassa sig). Se projektdokumentet claude/nattanalys-2026-11-08.md.
"""
from __future__ import annotations

import numpy as np

SPECS = [
    {"id": "pf|river_bluff", "gid": "pf_river_bluff", "rank": 1, "dir": "min", "goal": 35.0, "target": 35.0, "eff": 1.9,
     "title": "River, luft, ingen bet framför dig (heads-up): bluffa ca var tredje gång, pottstort",
     "do": "River heads-up med luft, ingen bet framför dig: bluffa ca var tredje gång, pottstort",
     "what": "bluff", "unit": "bet",
     "why": ("Poolen foldar 59 % mot ½, 62–67 % mot ¾ och 68 % mot pott heads-up på river, och en ren bluff behöver 33–50 %. "
             "När du checkar med luft vinner du nästan aldrig. Mät: andel gånger du bettar när du har luft (minst 60 % "
             "av slumpade händer slår dig), heads-up, ingen bet framför dig. Mål minst 35 %. Storlek pott (¾ går också, aldrig "
             "under 40 %). Bäst i position, på skrämselkort och med blockers. +4–4,7 bb per bluff mot check (räknat per pott); "
             "kostnaden är en uppskattning från äldre händer (hypotes – prövas i det slumpade river-bluff-testet, inte bekräftad)."),
     "done_min": 60},
]


def _spots(ft, P, m):
    """(rad-index i pfd, 1 = avvikelse) för varje spec."""
    kv = ft.codes("kind")
    kind = P["kind"]
    st, fac, np_ = P["st"], P["facing"], P["np"]
    out = {}
    # #1: river, ingen bet framför, heads-up, luft – check är avvikelse, bet är rätt
    k_bet, k_chk = kv.get("bet", -9), kv.get("check", -9)
    a = m & (st == 3) & (fac == 0) & (np_ == 2) & (P["bf"] > 0.6) & ((kind == k_bet) | (kind == k_chk))
    ia = np.flatnonzero(a)
    out["pf|river_bluff"] = (ia, kind[ia] == k_chk)
    return out


def focus_items(st, recent: int, done_weeks: int) -> list:
    from .facts import dt_of
    ft = getattr(st, "ft", None)
    P = ft.t.get("pfd") if ft is not None else None
    if P is None or "bf" not in P or not len(P["hidx"]):
        return []
    rows = np.asarray(st.rows, dtype=np.int64)
    if not len(rows):
        return []
    mask = np.zeros(ft.n, bool)
    mask[rows] = True
    m = ft.subset_mask(mask, "pfd")
    rec_rows = rows[-recent:] if len(rows) > recent else rows
    n_rec = len(rec_rows)
    rmask = np.zeros(ft.n, bool)
    rmask[rec_rows] = True
    H = ft.H
    last_ts = int(H["ts"][rows].max())
    out = []
    sp = _spots(ft, P, m)
    for spec in SPECS:
        ix, dev = sp[spec["id"]]
        hid = P["hidx"][ix]
        ts = H["ts"][hid]
        inr = rmask[hid]
        o, d = int(inr.sum()), int((dev & inr).sum())
        if o == 0:
            continue
        dev_rate = d / o
        # frekvensen som visas: bet-andel (#1) eller 3-bet-andel (#2)
        shown = (1 - dev_rate) if spec["dir"] == "min" else dev_rate
        if spec["dir"] == "min":
            gap = max(0.0, spec["target"] / 100 - shown)
        else:
            gap = max(0.0, shown - spec["target"] / 100)
        per100 = gap * o / n_rec * 100.0 * spec["eff"] if n_rec else 0.0
        weeks = []
        for w in range(7, -1, -1):
            lo, hi = last_ts - (w + 1) * 7 * 86400, last_ts - w * 7 * 86400
            wm = (ts > lo) & (ts <= hi)
            wo, wd = int(wm.sum()), int((wm & dev).sum())
            r_ = None
            if wo:
                r_ = 100.0 * (wo - wd) / wo if spec["dir"] == "min" else 100.0 * wd / wo
            weeks.append({"label": dt_of(hi).strftime("%d/%m"), "opps": wo, "dev": wd, "rate": r_})
        lw = weeks[-done_weeks:]
        o2, d2 = sum(w["opps"] for w in lw), sum(w["dev"] for w in lw)
        if o2 >= spec["done_min"]:
            r2 = 100.0 * (o2 - d2) / o2 if spec["dir"] == "min" else 100.0 * d2 / o2
            done = r2 >= spec["goal"] if spec["dir"] == "min" else r2 <= spec["goal"]
        else:
            done = False
        out.append({"id": spec["id"], "gid": spec["gid"], "rank": spec["rank"], "title": spec["title"], "do": spec["do"],
                    "why": spec["why"], "level": "trolig", "estimate": True, "kind": "pf", "dir": spec["dir"], "goal": spec["goal"],
                    "what": spec["what"], "cost_hand": None, "per100": float(per100), "opps": o, "dev": d,
                    "rate": 100.0 * shown, "recent_hands": int(n_rec), "weeks": weeks, "done": bool(done),
                    "train": None, "except": [], "holdout": None,
                    "dev_rows": np.unique(hid[dev]).astype(np.int64)})
    return out


def good(x: dict, rate) -> bool:
    """Är veckans frekvens på rätt sida om målet?"""
    if rate is None:
        return False
    return rate >= x["goal"] if x.get("dir") == "min" else rate <= x.get("goal", 5.0)
