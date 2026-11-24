"""Sessioner: följde du dina regler i det här spelpasset?

En session är en följd av händer utan en paus på mer än 30 minuter (GAP). En session kan alltså vara
10 minuter eller 4 timmar. För varje session räknas, med dina sparade regler (bekräftade och troliga):

* tillfällen: situationer där en regel säger folda,
* brott: tillfällen där du spelade handen ändå,
* regelföljning: andel tillfällen du följde regeln,
* väntad kostnad: brotten × vad ett brott kostar i snitt (från hela databasen), i bb och bb/100.

Det jämförs med ditt snitt i alla tidigare sessioner. Regelföljningen är det du styr över – den
säger mycket redan efter en kort session. Resultatet (bb, EV) svänger för mycket för att säga
något om en enskild session och visas bara som information.
"""
from __future__ import annotations

import math

import numpy as np

GAP = 30 * 60   # sekunder: längre paus = ny session
REST_H = 8.0    # 2.72: minst så många timmar sedan förra passet = utvilad (hypotes, inte bevisad effekt)
MORNING = (6, 12)  # 2.72: morgonpass = start 06–12 (hypotes)
MAX_LIST = 1000  # så många sessioner listas (sorterbar lista)
DEV_SHOW = 60   # så många regelbrott visas i en session (de dyraste)


def session_bounds(ts: np.ndarray) -> np.ndarray:
    """Index där en ny session börjar (ts i tidsordning)."""
    if not len(ts):
        return np.zeros(0, np.int64)
    return np.flatnonzero(np.r_[True, np.diff(ts) > GAP])


def _z(dev, opps, p0):
    """Hur säkert sessionens brottsandel skiljer sig från snittet (binomial z)."""
    if opps <= 0 or p0 is None or not 0 < p0 < 1:
        return None
    return (dev / opps - p0) / math.sqrt(p0 * (1 - p0) / opps)


def session_table(st, rules_doc, focus_id: str | None = None, limit: int | None = MAX_LIST) -> dict:
    from .facts import dt_of
    from .practice import broke_mask, first_rows, violation_index
    ft, rows = getattr(st, "ft", None), getattr(st, "rows", None)
    if ft is None or rows is None or not len(rows):
        return {}
    H = ft.H
    r = np.asarray(rows, dtype=np.int64)
    r = r[np.argsort(H["ts"][r], kind="stable")]
    ts = H["ts"][r]
    starts = session_bounds(ts)
    ends = np.r_[starts[1:], len(r)]
    ns = len(starts)
    sess_of_row = np.repeat(np.arange(ns), ends - starts)
    sid = np.full(ft.n, -1, np.int64)
    sid[r] = sess_of_row
    hands = (ends - starts).astype(np.int64)
    net = np.bincount(sess_of_row, weights=H["net"][r], minlength=ns)
    ev = np.bincount(sess_of_row, weights=H["ev"][r], minlength=ns)
    money = np.bincount(sess_of_row, weights=H["money"][r], minlength=ns)
    ev_m = np.bincount(sess_of_row, weights=H["ev_m"][r], minlength=ns)
    rules = (rules_doc or {}).get("rules") or []
    nr = len(rules)
    opp = np.zeros((ns, max(nr, 1)), np.int64)
    dev = np.zeros((ns, max(nr, 1)), np.int64)
    dev_rows: list = [[] for _ in range(ns)]
    pre = st.decisions.pre if getattr(st, "decisions", None) else None
    if nr and pre is not None and pre.ft is not None and len(pre):
        vi = violation_index(rules, pre)
        s_pre = sid[pre.hidx]
        m = first_rows(pre) & (vi >= 0) & (s_pre >= 0)
        # en hand räknas en gång (första beslutet som en regel gäller), även om flera beslut i
        # samma hand träffas av en regel
        idx = np.flatnonzero(m)
        _, firsts = np.unique(pre.hidx[idx], return_index=True)
        m = np.zeros(len(pre), bool)
        m[idx[firsts]] = True
        played = broke_mask(rules, pre, vi)
        np.add.at(opp, (s_pre[m], vi[m]), 1)
        md = m & played
        np.add.at(dev, (s_pre[md], vi[md]), 1)
        for j in np.flatnonzero(md):
            dev_rows[int(s_pre[j])].append((int(pre.hidx[j]), rules[int(vi[j])]["title"]))
    cost = np.array([float(x.get("cost") or 0.0) for x in rules] or [0.0])
    exp_cost = (dev * cost[None, :]).sum(1)  # bb (negativt = förlust)
    o_tot, d_tot = opp.sum(1), dev.sum(1)
    out = []
    cum_o = cum_d = 0
    cum_ro = np.zeros(max(nr, 1), np.int64)
    cum_rd = np.zeros(max(nr, 1), np.int64)
    for i in range(ns):
        p0 = cum_d / cum_o if cum_o else None  # snittet i alla tidigare sessioner
        a, b = int(starts[i]), int(ends[i])
        t0, t1 = int(ts[a]), int(ts[b - 1])
        rate = 100.0 * d_tot[i] / o_tot[i] if o_tot[i] else None
        z = _z(d_tot[i], o_tot[i], p0)
        gap_h = (t0 - int(ts[int(ends[i - 1]) - 1])) / 3600.0 if i > 0 else None
        per_rule = []
        for k, ru in enumerate(rules):
            if not opp[i, k]:
                continue
            pr0 = cum_rd[k] / cum_ro[k] if cum_ro[k] else None
            per_rule.append({"id": ru["id"], "title": ru["title"], "level": ru.get("level", "bekräftad"),
                             "opps": int(opp[i, k]), "dev": int(dev[i, k]),
                             "rate": 100.0 * dev[i, k] / opp[i, k], "base": 100.0 * pr0 if pr0 is not None else None,
                             "cost": float(dev[i, k] * cost[k]), "focus": ru["id"] == focus_id})
        per_rule.sort(key=lambda x: (not x["focus"], x["cost"]))
        out.append({
            "i": i, "key": f"{t0}", "start": dt_of(t0).strftime("%Y-%m-%d %H:%M"), "end": dt_of(t1).strftime("%H:%M"),
            "day": dt_of(t0).strftime("%Y-%m-%d"), "t0": t0, "t1": t1,
            "minutes": max(1, round((t1 - t0) / 60)), "hands": int(hands[i]),
            "net": float(net[i]), "ev": float(ev[i]), "money": float(money[i]), "ev_money": float(ev_m[i]),
            "bb100": 100.0 * net[i] / hands[i], "ev100": 100.0 * ev[i] / hands[i],
            "opps": int(o_tot[i]), "dev": int(d_tot[i]), "rate": rate,
            "follow": 100.0 - rate if rate is not None else None,
            "base": 100.0 * p0 if p0 is not None else None,
            "base_follow": 100.0 - 100.0 * p0 if p0 is not None else None,
            "z": z, "verdict": _verdict(rate, p0, z, int(o_tot[i])),
            "exp_cost": float(exp_cost[i]), "exp100": 100.0 * float(exp_cost[i]) / hands[i],
            "per_rule": per_rule, "dev_rows": dev_rows[i], **rest_info(t0, gap_h)})
        cum_o += int(o_tot[i])
        cum_d += int(d_tot[i])
        cum_ro += opp[i]
        cum_rd += dev[i]
    total_o, total_d = int(o_tot.sum()), int(d_tot.sum())
    # trend: regelföljning de senaste sessionerna (med minst 5 tillfällen), äldst först
    trend = [{"key": s["key"], "label": s["start"][5:], "follow": s["follow"], "opps": s["opps"]}
             for s in out if s["opps"] >= 5][-30:]
    return {"sessions": out[::-1][:limit] if limit else out[::-1], "count": ns, "has_rules": bool(nr),
            "rate": 100.0 * total_d / total_o if total_o else None,
            "follow": 100.0 - 100.0 * total_d / total_o if total_o else None,
            "trend": trend, "gap_min": GAP // 60}


def rest_info(t0: int, gap_h) -> dict:
    """2.72: utvilad (≥ REST_H h sedan förra passet), morgonpass (start 06–12) och tid sedan förra passet.
    Märkningen är en hypotes att följa upp – morgon, vila och kortare pass går inte att skilja åt i datan."""
    from .facts import dt_of
    hr = dt_of(t0).hour
    morning = MORNING[0] <= hr < MORNING[1]
    rested = None if gap_h is None else gap_h >= REST_H
    if gap_h is None:
        gap_txt = "första passet i urvalet"
    elif gap_h < 1:
        gap_txt = f"{gap_h * 60:.0f} min sedan förra passet"
    elif gap_h < 48:
        gap_txt = f"{gap_h:.1f} h sedan förra passet".replace(".", ",")
    else:
        gap_txt = f"{gap_h / 24:.1f} dygn sedan förra passet".replace(".", ",")
    tags = (["🌅 morgonpass"] if morning else []) + (["😴 utvilad"] if rested else (["⚠ kort vila"] if rested is False else []))
    return {"gap_h": gap_h, "rested": rested, "morning": morning, "gap_txt": gap_txt, "rest_tags": tags}


def _verdict(rate, p0, z, opps) -> dict:
    if rate is None:
        return {"tone": "", "text": "Inga tillfällen där en regel säger folda"}
    if p0 is None:
        return {"tone": "", "text": "Första sessionen – inget snitt att jämföra med"}
    if opps < 5:
        return {"tone": "", "text": "För få tillfällen för att jämföra"}
    if z is not None and z <= -2:
        return {"tone": "good", "text": "Tydligt bättre än ditt snitt"}
    if z is not None and z >= 2:
        return {"tone": "bad", "text": "Tydligt sämre än ditt snitt"}
    if rate < 100.0 * p0:
        return {"tone": "good-soft", "text": "Bättre än ditt snitt (kan vara slump)"}
    if rate > 100.0 * p0:
        return {"tone": "bad-soft", "text": "Sämre än ditt snitt (kan vara slump)"}
    return {"tone": "", "text": "Som ditt snitt"}


def session_detail(table: dict, key: str, st, hero: str) -> dict | None:
    """En session med regelbrotten som går att spela upp."""
    from .facts import decode_cards, dt_of
    s = next((x for x in (table or {}).get("sessions", []) if x["key"] == key), None)
    if s is None:
        return None
    H = st.ft.H
    devs = []
    for hx, title in s["dev_rows"]:
        devs.append({"id": str(H["id"][hx]), "time": dt_of(int(H["ts"][hx])).strftime("%H:%M"),
                     "pos": st.ft.label("pos", int(H["pos"][hx])), "net": float(H["net"][hx]),
                     "ev": float(H["ev"][hx]), "rule": title,
                     "hole": sorted(decode_cards(H["hole"][hx]), key=lambda c: (-c[0], c[1]))})
    n_all = len(devs)
    if n_all > DEV_SHOW:  # långa sessioner: de dyraste brotten (i tidsordning)
        keep = sorted(range(n_all), key=lambda i: devs[i]["net"])[:DEV_SHOW]
        devs = [devs[i] for i in sorted(keep)]
    return {**s, "devs": devs, "devs_all": n_all}


def export_sessions(T: dict, n: int = 60) -> dict:
    """Sessionerna för analysfilen till Claude (utan radnummer)."""
    if not T:
        return {}
    keep = ("start", "end", "minutes", "hands", "net", "ev", "money", "ev_money", "bb100", "ev100", "opps", "dev",
            "follow", "base_follow", "z", "verdict", "exp_cost", "exp100", "gap_h", "rested", "morning")
    return {"count": T["count"], "follow_all": T.get("follow"), "gap_min": T.get("gap_min"),
            "latest": [{**{k: s[k] for k in keep},
                        "per_rule": [{k: r[k] for k in ("title", "level", "opps", "dev", "rate", "base", "cost")}
                                     for r in s["per_rule"]]} for s in T["sessions"][:n]]}
