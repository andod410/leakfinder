"""Nivåer: går du tydligt sämre på en nivå än på en annan?

För varje nivå med tillräckligt många händer räknas all-in EV per 100 händer (efter rake) med
felmarginal per spelpass, VPIP och rake. Den nivå där du gått bäst (bland nivåer med minst
BEST_MIN händer) jämförs med de andra. En nivå är "tydligt sämre" när skillnaden är större än noll även
med felmarginalen (95 %). Skillnaden räknas försiktigt: den nedre gränsen för skillnaden används som
kostnad, inte den uppmätta skillnaden.
"""
from __future__ import annotations

import math

import numpy as np

MIN_HANDS = 3000
BEST_MIN = 10000


def _mean_se(x, c):
    from .fatigue import _cluster_mean_se
    return _cluster_mean_se(x, c)


def stake_check(st, rules_doc=None) -> dict:
    """rules_doc ges: jämförelsen görs på resultatet med dina regelbrott borträknade (brott × försiktig
    kostnad läggs tillbaka). Annars kan en nivå se sämre ut bara för att du bröt mot reglerna oftare där –
    och då är det reglerna som är läckan, inte nivån."""
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None or not len(st.rows):
        return {}
    from .fatigue import hand_session_info
    H = ft.H
    r, sess, _ = hand_session_info(st)
    codes = H["stake"][r]
    ev_all = H["ev"][r].astype(float)
    adj = False
    if rules_doc and (rules_doc.get("rules") or []) and getattr(st, "decisions", None) is not None:
        from .fatigue import _breaks
        cost, _ = _breaks(st, rules_doc, r)
        if cost.any():
            ev_all = ev_all - cost
            adj = True
    rows = []
    for c in np.unique(codes):
        m = codes == c
        n = int(m.sum())
        if n < MIN_HANDS:
            continue
        ev, se = _mean_se(ev_all[m], sess[m])
        raw, _ = _mean_se(H["ev"][r][m].astype(float), sess[m])
        # 2.80: jämförelsen görs i dollar per aktiv timme (samma tidsmått som Timlön) – högst bb/100 är inte
        # samma sak som högst timlön när nivåerna har olika storlek på big blind
        from .hourly import _active_seconds
        rr = r[m]
        o = np.argsort(H["ts"][rr], kind="stable")
        sec, _ns, _t = _active_seconds(H["ts"][rr][o], np.asarray(sess[m])[o])
        hph = n / (sec / 3600.0) if sec > 0 else None
        if "bb" in H:
            bb_usd = float(np.median(H["bb"][rr])) if n else 0.0
        else:
            try:
                bb_usd = float(ft.label("stake", int(c)).split("/")[1])
            except (IndexError, ValueError):
                bb_usd = 0.0
        usd_h = ev * bb_usd * hph if hph else None
        se_h = se * bb_usd * hph if hph else None
        rows.append({"stake": ft.label("stake", int(c)), "code": int(c), "hands": n, "ev100": 100 * ev, "se100": 100 * se,
                     "raw100": 100 * raw, "hph": hph, "usd_h": usd_h, "se_usd_h": se_h,
                     "vpip": 100 * float(H["vpip"][r][m].mean()), "rake100": 100 * float(H["rake"][r][m].mean()),
                     "share": 100.0 * n / len(r)})
    big = [x for x in rows if x["hands"] >= BEST_MIN]
    if len(rows) < 2 or not big:
        return {"rows": rows, "best": None, "worse": [], "adjusted": adj}
    if any(x["usd_h"] is None for x in rows):
        return {"rows": rows, "best": None, "worse": [], "adjusted": adj, "unit": "USD/h"}
    best = max(big, key=lambda x: x["usd_h"])
    worse = []
    # den bästa nivån väljs efter resultaten och jämförs med alla andra: Bonferroni-korrigera (en-sidigt, 5 % totalt)
    z = _z_bonf(len(rows) - 1)
    for x in rows:
        if x is best:
            x["verdict"] = "bäst"
            continue
        d = best["ev100"] - x["ev100"]
        se = math.sqrt(best["se100"] ** 2 + x["se100"] ** 2)
        x["diff"], x["diff_lo"] = d, d - z * se
        du = best["usd_h"] - x["usd_h"]
        seu = math.sqrt(best["se_usd_h"] ** 2 + x["se_usd_h"] ** 2)
        x["diff_usd_h"], x["diff_usd_h_lo"] = du, du - z * seu
        # tydligt sämre = lägre timlön i dollar även med felmarginalen; kostnaden i bb/100 visas bara när bb-skillnaden
        # också är säker, annars 0 (rådet gäller då timlönen, inte en uppmätt läcka i bb)
        x["verdict"] = "tydligt sämre" if np.isfinite(seu) and du - z * seu > 0 else "osäkert"
        if x["diff_lo"] < 0:
            x["diff_lo"] = 0.0
        if x["verdict"] == "tydligt sämre":
            worse.append(x)
    rows.sort(key=lambda x: -x["hands"])
    return {"rows": rows, "best": best, "worse": worse, "adjusted": adj, "unit": "USD/h"}


def _z_bonf(k: int) -> float:
    """z för en-sidig test med 5 % fel totalt över k jämförelser (k = 1 ger 1,645; ett extra urval av
    bästa nivån gör att vi använder 2,5 % per sida som tidigare: k = 1 ger 1,96)."""
    from statistics import NormalDist
    k = max(int(k), 1)
    return NormalDist().inv_cdf(1 - 0.025 / k)


def focus_item(st, S: dict, recent: int, done_weeks: int, done_min: int):
    """"Spela på $X" som en läcka i fokuskön, om en nivå är tydligt sämre och du fortfarande spelar den."""
    from .facts import dt_of
    if not S or not S.get("worse") or not S.get("best"):
        return None
    from .fatigue import hand_session_info
    H = st.ft.H
    r, _, _ = hand_session_info(st)
    codes = H["stake"][r]
    worse_codes = {x["code"]: x for x in S["worse"]}
    rec = r[-recent:] if len(r) > recent else r
    rc = H["stake"][rec]
    cost = sum(max(x["diff_lo"], 0.0) / 100.0 * int((rc == c).sum()) for c, x in worse_codes.items())
    per100 = 100.0 * cost / len(rec) if len(rec) else 0.0
    bad = np.isin(codes, list(worse_codes))
    ts = H["ts"][r]
    last = int(ts[-1])
    weeks = []
    for w in range(7, -1, -1):
        lo, hi = last - (w + 1) * 7 * 86400, last - w * 7 * 86400
        wm = (ts > lo) & (ts <= hi)
        o, d = int(wm.sum()), int((wm & bad).sum())
        weeks.append({"label": dt_of(hi).strftime("%d/%m"), "opps": o, "dev": d, "rate": 100.0 * d / o if o else None})
    lw = weeks[-done_weeks:]
    o2, d2 = sum(w["opps"] for w in lw), sum(w["dev"] for w in lw)
    b = S["best"]
    names = ", ".join("$" + x["stake"].replace("/", "/$") for x in S["worse"])
    return {"id": "niva|" + b["stake"], "title": f"Spela på ${b['stake'].replace('/', '/$')} – inte på {names}",
            "why": (f"På {names} har du tjänat tydligt mindre per timme än på ${b['stake'].replace('/', '/$')} "
                    f"(${S['worse'][0]['usd_h']:+.0f}/h mot ${b['usd_h']:+.0f}/h, {S['worse'][0]['ev100']:+.1f} mot {b['ev100']:+.1f} bb/100 i all-in EV"
                    f"{' med dina regelbrott borträknade' if S.get('adjusted') else ''}, skillnaden är säker även "
                    f"med felmarginalen). Obs: nivå och tidsperiod hänger ihop om du bytt nivå vid ett visst datum. Gå upp igen först när du ligger stabilt plus på den lägre nivån. Se Resultat & graf → Per nivå."),
            "level": "bekräftad", "cost_hand": None, "per100": per100, "opps": int(len(rec)), "dev": int(np.isin(rc, list(worse_codes)).sum()),
            "rate": 100.0 * float(np.isin(rc, list(worse_codes)).mean()) if len(rec) else 0.0, "recent_hands": int(len(rec)),
            "weeks": weeks, "done": o2 >= done_min and 100.0 * d2 / o2 <= 5.0, "train": None, "except": [],
            "kind": "stake", "dev_rows": np.zeros(0, np.int64)}
