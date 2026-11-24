"""Fokus: en enda läcka att jobba med åt gången.

Kandidaterna är dina regler (bekräftade och troliga). Varje regel får en "kostnad nu": hur många
gånger du bröt mot den i dina senaste RECENT händer gånger vad ett sådant brott kostar i snitt
(från hela databasen), uttryckt i bb/100. Den dyraste blir fokus – det är där en ändring av ditt
spel just nu ger mest. Samma hand räknas bara på en regel (den mest specifika), så inget räknas två
gånger.

En läcka räknas som under kontroll när du de senaste DONE_WEEKS veckorna haft minst DONE_MIN
tillfällen och brutit mot regeln i högst DONE_RATE % av dem. Då föreslås nästa.
"""
from __future__ import annotations

import numpy as np

RECENT = 20000
DONE_WEEKS = 2
DONE_MIN = 100
DONE_RATE = 5.0


def _first_rows(pre):
    key = pre.hidx.astype(np.int64) * 64 + pre.spot
    _, first = np.unique(key, return_index=True)
    m = np.zeros(len(pre), bool)
    m[first] = True
    return m


def focus_list(st, rules_doc) -> list:
    """Reglerna sorterade efter vad de kostar dig nu (dyrast först)."""
    from .facts import dt_of
    from .practice import broke_mask, careful_costs, trainer_scenarios, violation_index
    if not rules_doc or not rules_doc.get("rules") or st is None:
        return []
    pre = st.decisions.pre
    if pre.ft is None or not len(pre):
        return []
    rules = rules_doc["rules"]
    H = pre.ft.H
    rows = np.asarray(st.rows)
    recent = rows[-RECENT:] if len(rows) > RECENT else rows
    n_recent = len(recent)
    in_recent = np.isin(pre.hidx, recent)
    vi = violation_index(rules, pre)
    careful = careful_costs(rules, pre, vi)
    first = _first_rows(pre)
    played = broke_mask(rules, pre, vi)
    # tillfällen = situationer där regeln säger folda; brott = du spelade ändå
    opp = first & (vi >= 0)
    dev = opp & played
    ts = H["ts"][pre.hidx]
    last_ts = int(H["ts"][rows[-1]]) if len(rows) else 0
    scen = {(s["spot"], s["pos"]): s["key"] for s in trainer_scenarios(rules_doc)}
    out = []
    for i, r in enumerate(rules):
        mi = vi == i
        n_opp, n_dev = int((opp & mi & in_recent).sum()), int((dev & mi & in_recent).sum())
        cost = float(careful[i])  # försiktig kostnad per brott (se careful_costs)
        per100 = -cost * n_dev / n_recent * 100.0 if n_recent else 0.0
        # vecka för vecka (de senaste 8 veckorna)
        weeks = []
        for w in range(7, -1, -1):
            lo, hi = last_ts - (w + 1) * 7 * 86400, last_ts - w * 7 * 86400
            wm = mi & (ts > lo) & (ts <= hi)
            o, d = int((opp & wm).sum()), int((dev & wm).sum())
            weeks.append({"label": dt_of(hi).strftime("%d/%m"), "opps": o, "dev": d,
                          "rate": 100.0 * d / o if o else None})
        lastw = [w for w in weeks[-DONE_WEEKS:]]
        o2, d2 = sum(w["opps"] for w in lastw), sum(w["dev"] for w in lastw)
        done = o2 >= DONE_MIN and 100.0 * d2 / o2 <= DONE_RATE
        # en situation i tränaren att öva på: där du bröt mot regeln oftast
        dpos = {}
        for j in np.flatnonzero(dev & mi & in_recent):
            k = (pre.label("spot", pre.spot[j]), pre.label("pos", pre.pos[j]))
            dpos[k] = dpos.get(k, 0) + 1
        train = None
        for k, _ in sorted(dpos.items(), key=lambda kv: -kv[1]):
            sk = scen.get(k) or scen.get(("rfi", k[1])) or scen.get(({"SB": "sb_mot_hojning", "BB": "bb_mot_hojning"}.get(k[1], "rfi"), k[1]))
            if sk:
                train = sk
                break
        if r.get("type") == "action":
            from .practice import THREEBET_POS
            tp = next((k[1] for k, _ in sorted(dpos.items(), key=lambda kv: -kv[1]) if k[1] in THREEBET_POS), "BB")
            train = f"3bet|{tp}"
        elif train is None and scen:
            train = next(iter(scen.values()))
        out.append({"id": r["id"], "title": r["title"], "do": short_do(r), "holdout": r.get("holdout"), "why": r.get("why", ""), "level": r.get("level", "bekräftad"),
                    "cost_hand": cost, "cost_rule": float(r.get("cost") or 0.0), "per100": per100, "opps": n_opp, "dev": n_dev,
                    "rate": 100.0 * n_dev / n_opp if n_opp else 0.0, "recent_hands": n_recent,
                    "weeks": weeks, "done": done, "train": train, "except": r.get("except") or [],
                    "dev_rows": np.unique(pre.hidx[dev & mi]).astype(np.int64)})
    out.sort(key=lambda x: (x["done"], -x["per100"]))
    return out


def short_do(r: dict) -> str:
    """En kort instruktion (några ord) för en regel – det du ska göra vid bordet."""
    t = r.get("type")
    if t == "rundown":
        return "Folda rena rundowns med lägsta kort " + ", ".join(r.get("groups") or [])
    if t == "nut" and r.get("spots"):
        return "Mot 3-bet: folda 0 nöt-egenskaper" + (" (utom " + ", ".join(r["except"]) + ")" if r.get("except") else "")
    if t == "nut":
        ps = "/".join(r.get("positions") or [r.get("pos", "")])
        return f"{ps}: folda {r.get('nut', '')}" + (" (utom " + ", ".join(r["except"]) + ")" if r.get("except") else "")
    if t == "action":
        return {"hp_sa": "3-betta högt par + suited ess – syna inte",
                "no_sa": "3-betta bara med suited ess"}.get(r.get("cond"), r.get("title", ""))
    if t == "cutoff":
        return f"{r.get('pos')}: spela bara topp {r.get('cut_pct', 0):.0f} %"
    if t == "combo":
        return r.get("title", "")
    return r.get("title", "")


def pick(flist: list, locked: str | None):
    """Fokusläckan: den du valt (om den finns kvar), annars den dyraste som inte är under kontroll."""
    if not flist:
        return None
    if locked:
        for f in flist:
            if f["id"] == locked:
                return f
    return flist[0]
