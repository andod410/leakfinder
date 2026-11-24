"""Rakeback-mätning per dygn (2.77.4, Andreas 2026-11-18: från och med idag, en gång per dygn).

Per dygn för du in vad GG faktiskt gav för det dygnets spel:
* GEMs intjänade under dygnet (inte saldot – saldot ändras när du löser in),
* GEM-värde i $ (om du vet det; annars räknas det med kursen nedan),
* leaderboard-utbetalning i $ för dygnets leaderboard (datumet leaderboarden gällde, inte utbetalningsdagen),
* övrigt i $ (agentbonus, kampanjer m.m.).
Programmet räknar din rake samma GG-dygn (från 08:00 UTC, se day_start) och visar rakeback i procent per dygn, per vecka och totalt.

2.77.5: GEMs blir mer värda ju längre du sparar (dyrare föremål ger bättre kurs), så kursen bestäms när du LÖSER IN:
du för in inlösen (datum, GEMs, värde i $). Kursen = summa $ / summa GEMs över alla inlösen. Före första inlösen används
en planerad kurs som du anger. Rakeback visas både kontant (leaderboard + övrigt) och med GEMs till kursen.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

START = "2026-11-18"
RESET_UTC_HOUR = 8   # GG nollställer leaderboards 09:00 svensk vintertid / 10:00 sommartid = 08:00 UTC (Andreas 2026-11-18)


def _last_sunday(y: int, m: int) -> datetime:
    d = datetime(y, m + 1, 1) - timedelta(days=1) if m < 12 else datetime(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _swedish_offset(utc: datetime) -> int:
    """+2 h sommartid (sista söndagen i mars 01:00 UTC – sista söndagen i oktober 01:00 UTC), annars +1 h.
    Räknas utan tidszonsdatabas (finns inte alltid på Windows)."""
    a = _last_sunday(utc.year, 3).replace(hour=1)
    b = _last_sunday(utc.year, 10).replace(hour=1)
    return 2 if a <= utc < b else 1


def day_start(d: datetime) -> datetime:
    """GG-dygnets start i handtid (svensk lokal tid) för dygnet d: 08:00 UTC den dagen."""
    u = datetime(d.year, d.month, d.day, RESET_UTC_HOUR)
    return u + timedelta(hours=_swedish_offset(u))
GEM_USD_DEFAULT = 0.0   # $ per GEM; sätts när du vet kursen


def _num(x) -> float:
    try:
        return max(0.0, float(str(x).replace(",", ".").replace(" ", "")))
    except ValueError:
        return 0.0


def _settings(db) -> dict:
    from . import watch
    try:
        return watch.load_settings(db) or {}
    except Exception:
        return {}


def entries(db) -> list:
    S = _settings(db)
    out = list(S.get("rb_days") or [])
    for e in S.get("rb_weeks") or []:  # 2.77–2.77.3 sparade per vecka – visas kvar som en rad
        if not any(x.get("day") == e.get("week") for x in out):
            out.append({"day": e.get("week"), "gems": e.get("gems", 0), "gem_usd": e.get("gem_usd", 0),
                        "lb_usd": e.get("lb_usd", 0), "other_usd": e.get("other_usd", 0), "week_entry": True})
    return sorted(out, key=lambda e: e["day"])


def redemptions(db) -> list:
    return sorted(_settings(db).get("rb_redeem") or [], key=lambda e: e["day"])


def gem_rate(db) -> float:
    """Realiserad kurs från inlösen om sådana finns, annars den planerade kursen."""
    R = redemptions(db)
    g = sum(e["gems"] for e in R)
    if g > 0:
        return sum(e["usd"] for e in R) / g
    return float(_settings(db).get("rb_gem_usd", GEM_USD_DEFAULT) or 0.0)


def add(db, form) -> list:
    from . import watch
    S = _settings(db)
    cur = list(S.get("rb_days") or [])
    if form.get("redeem"):
        R = [e for e in (S.get("rb_redeem") or []) if e.get("day") != form.get("rday")]
        if not form.get("ta_bort"):
            try:
                d = datetime.strptime(str(form.get("rday", ""))[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                R.append({"day": d, "gems": _num(form.get("rgems")), "usd": _num(form.get("rusd"))})
            except ValueError:
                pass
        watch.save_settings(db, rb_redeem=R)
        return entries(db)
    if "gem_rate" in form and not form.get("day"):
        watch.save_settings(db, rb_gem_usd=_num(form.get("gem_rate")))
        return entries(db)
    try:
        d = datetime.strptime(str(form.get("day") or form.get("week") or "")[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return entries(db)
    cur = [e for e in cur if e.get("day") != d]
    if form.get("ta_bort"):
        weeks = [e for e in (S.get("rb_weeks") or []) if e.get("week") != d]
        watch.save_settings(db, rb_days=cur, rb_weeks=weeks)
        return entries(db)
    cur.append({"day": d, "gems": _num(form.get("gems")), "gem_usd": _num(form.get("gem_usd")),
                "lb_usd": _num(form.get("lb_usd")), "other_usd": _num(form.get("other_usd"))})
    cur.sort(key=lambda e: e["day"])
    watch.save_settings(db, rb_days=cur)
    return entries(db)


def table(st, db) -> dict:
    from .facts import ts_of
    H = st.ft.H
    # 2.80: kontobonusen gäller ALLA dina händer det dygnet – rake räknas därför på hela faktatabellen (alla varianter
    # och bord), inte på det urval som råkar vara valt. Annars blir täljare och nämnare olika populationer.
    rows = np.arange(st.ft.n, dtype=np.int64)
    rate = gem_rate(db)
    no_rake_value = 0.0
    out = []
    tot_r = tot_v = 0.0
    weeks = {}
    for e in entries(db):
        a = datetime.strptime(e["day"], "%Y-%m-%d")
        span = 7 if e.get("week_entry") else 1
        t0, t1 = ts_of(day_start(a)), ts_of(day_start(a + timedelta(days=span)))
        r = rows[(H["ts"][rows] >= t0) & (H["ts"][rows] < t1)]
        rake = float(H["rake_m"][r].sum()) if len(r) else 0.0
        gem_val = e["gem_usd"] if e["gem_usd"] else e["gems"] * rate
        cash = e["lb_usd"] + e["other_usd"]
        val = gem_val + cash
        row = {**e, "hands": int(len(r)), "rake": rake, "gem_val": gem_val, "value": val,
               "pct": 100.0 * val / rake if rake else None, "cash_pct": 100.0 * cash / rake if rake else None, "lb_pct": 100.0 * e["lb_usd"] / rake if rake else None,
               "gem_pct": 100.0 * gem_val / rake if rake else None}
        out.append(row)
        wk = (a - timedelta(days=a.weekday())).strftime("%Y-%m-%d")
        w = weeks.setdefault(wk, {"week": wk, "rake": 0.0, "value": 0.0, "days": 0, "no_rake_value": 0.0})
        w["days"] += 1
        if rake:   # samma täckning i vecka och total: bara dygn med inläst rake räknas i procenten
            w["rake"] += rake
            w["value"] += val
            tot_r += rake
            tot_v += val
        else:
            w["no_rake_value"] += val
            no_rake_value += val
    for w in weeks.values():
        w["pct"] = 100.0 * w["value"] / w["rake"] if w["rake"] else None
    R = redemptions(db)
    gems_earned = sum(e["gems"] for e in entries(db))
    gems_redeemed = sum(e["gems"] for e in R)
    return {"rows": out, "weeks": sorted(weeks.values(), key=lambda w: w["week"]), "start": START, "gem_rate": rate,
            "redeem": R, "rate_realized": bool(R), "gems_left": max(0.0, gems_earned - gems_redeemed),
            "planned_rate": float(_settings(db).get("rb_gem_usd", GEM_USD_DEFAULT) or 0.0),
            "pct": 100.0 * tot_v / tot_r if tot_r else None, "rake": tot_r, "value": tot_v,
            "no_rake_value": no_rake_value, "scope": "alla dina händer (oberoende av urvalet)"}
