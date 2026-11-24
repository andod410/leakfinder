"""Dela som bild: underlaget till delningsbilden (mobil och desktop).

Bilden ritas i webbläsaren (canvas) och laddas ner som PNG – programmet behöver inga extra paket.
Här räknas siffrorna fram från analysens händer:

* kurvan: resultat och all-in EV hand för hand (i dollar och i bb), glesad till högst MAX_POINTS punkter,
* rutorna överst: resultat, all-in EV och EV per 100 händer,
* nedre grafen:
  - utan startdatum: all-in EV per månad (per vecka om perioden är kortare än två månader),
  - med startdatum: före, efter och de senaste 7 dagarna – all-in EV, VPIP och regelföljning.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

MAX_POINTS = 1500
MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
LAST_DAYS = 7


def _d(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]}"


def _block(H, r) -> dict:
    n = int(len(r))
    if not n:
        return {"hands": 0}
    return {"hands": n, "ev100": 100.0 * float(H["ev"][r].sum()) / n, "vpip": 100.0 * float(H["vpip"][r].mean()),
            "money": float(H["money"][r].sum()), "ev_money": float(H["ev_m"][r].sum()),
            "net_bb": float(H["net"][r].sum()), "ev_bb": float(H["ev"][r].sum())}


def _follow(sessions: list, t0: int, t1: int):
    """Regelföljning (%) i sessionerna som startade mellan t0 och t1."""
    o = d = 0
    for s in sessions or []:
        if t0 <= s["t0"] <= t1:
            o += int(s.get("opps") or 0)
            d += int(s.get("dev") or 0)
    return (100.0 - 100.0 * d / o) if o else None


def share_data(C: dict, start: str | None = None) -> dict:
    from .facts import EPOCH, dt_of
    st = C.get("st")
    ft, rows = getattr(st, "ft", None), getattr(st, "rows", None)
    if ft is None or rows is None or not len(rows):
        return {"error": "Inga händer i urvalet."}
    H = ft.H
    r_all = np.asarray(rows, dtype=np.int64)
    r_all = r_all[np.argsort(H["ts"][r_all], kind="stable")]
    sd = None
    if start:
        try:
            sd = datetime.strptime(start, "%Y-%m-%d")
        except ValueError:
            sd = None
    t_start = int((sd - EPOCH).total_seconds()) if sd else None
    r = r_all[H["ts"][r_all] >= t_start] if t_start is not None else r_all
    if not len(r):
        return {"error": "Inga händer efter startdatumet."}
    n = len(r)
    idx = np.unique(np.r_[np.linspace(0, n - 1, min(n, MAX_POINTS)).astype(np.int64), n - 1])
    cm, ce = np.cumsum(H["money"][r]), np.cumsum(H["ev_m"][r])
    cb, ceb = np.cumsum(H["net"][r]), np.cumsum(H["ev"][r])
    ts = H["ts"][r]
    first, last = dt_of(int(ts[0])), dt_of(int(ts[-1]))
    games = (C.get("filters") or {}).get("games_sel") or [C.get("main_game") or "PLO"]
    out = {"game": " + ".join(games), "start": start if sd else "", "first": _d(first), "last": _d(last),
           "year": last.year, "total": _block(H, r),
           "series": {"i": (idx + 1).tolist(), "m": np.round(cm[idx], 2).tolist(), "e": np.round(ce[idx], 2).tolist(),
                      "b": np.round(cb[idx], 1).tolist(), "eb": np.round(ceb[idx], 1).tolist()}}
    # 2.89: samma linjer som vinstkurvan på Översikt – var och en kan väljas på bilden.
    # lines[k] = {"label", "color", "dash", "b": [...bb], "m": [...$]}; rakeback med procentsatserna från Översikt.
    from .report import CHART_SERIES
    sdm = H["sd"][r].astype(bool)
    try:
        from .rbcurve import current_cfg, rb_rows
        rb, rb_m = rb_rows(ft, r, current_cfg())
    except Exception:
        rb = rb_m = None
    raw = {"net": (H["net"][r], H["money"][r]), "ev": (H["ev"][r], H["ev_m"][r]),
           "sd": (np.where(sdm, H["net"][r], 0.0), np.where(sdm, H["money"][r], 0.0)),
           "nsd": (np.where(sdm, 0.0, H["net"][r]), np.where(sdm, 0.0, H["money"][r])),
           "rake": (H["rake"][r], H["rake_m"][r])}
    if rb is not None:
        raw["net_rb"] = (H["net"][r] + rb, H["money"][r] + rb_m)
        raw["ev_rb"] = (H["ev"][r] + rb, H["ev_m"][r] + rb_m)
    lines = {}
    for key, label, color, dash, _on in CHART_SERIES:
        if key not in raw:
            continue
        b_, m_ = raw[key]
        lines[key] = {"label": label, "color": color, "dash": bool(dash),
                      "b": np.round(np.cumsum(b_)[idx], 1).tolist(), "m": np.round(np.cumsum(m_)[idx], 2).tolist()}
    out["lines"] = lines
    if rb is not None:
        out["total"]["rb_bb"] = round(float(rb.sum()), 1)
        out["total"]["rb_money"] = round(float(rb_m.sum()), 2)
        out["total"]["ev_rb_bb"] = round(float(H["ev"][r].sum() + rb.sum()), 1)
        out["total"]["ev_rb_money"] = round(float(H["ev_m"][r].sum() + rb_m.sum()), 2)
        out["total"]["ev100_rb"] = round(100.0 * float(H["ev"][r].sum() + rb.sum()) / n, 1)
        out["total"]["rb100"] = round(100.0 * float(rb.sum()) / n, 1)
    # x-axelns markeringar: första handen varje månad (vid kort period: varje vecka)
    days = (last - first).days
    t64 = ts.astype("datetime64[s]")
    dD = t64.astype("datetime64[D]")
    wk = dD - ((dD.astype(np.int64) + 3) % 7).astype("timedelta64[D]")  # måndagen i veckan
    mo = t64.astype("datetime64[M]")
    key = mo if days > 45 else wk
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    def lab(j):
        dt = dt_of(int(ts[j]))
        return MONTHS[dt.month - 1] if days > 45 else _d(dt)
    out["marks"] = [{"i": int(j) + 1, "label": lab(j)} for j in starts]
    T = C.get("sessions") or {}
    sessions = T.get("sessions") or []
    if T.get("count", 0) > len(sessions):  # listan på sidan är kapad: räkna regelföljning på alla sessioner
        try:
            from .sessions import session_table
            sessions = session_table(st, {"rules": (C.get("fu") or {}).get("rules") or []}, limit=None).get("sessions") or []
        except Exception:
            pass
    if sd is None:
        # all-in EV per månad (per vecka vid kort period)
        monthly = days >= 60
        key = mo if monthly else wk
        st_ = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        en = np.r_[st_[1:], n]
        bars = []
        for a_, b_ in zip(st_, en):
            dt = dt_of(int(ts[a_]))
            if monthly:
                label = MONTHS[dt.month - 1]
            else:
                label = "v." + str(dt.isocalendar()[1])
            bars.append({"label": label, **_block(H, r[a_:b_])})
        out["mode"] = "months" if monthly else "weeks"
        out["bars"] = bars
    else:
        before = r_all[H["ts"][r_all] < t_start]
        t_last = int(ts[-1]) - LAST_DAYS * 86400
        mid = r[H["ts"][r] < t_last]
        recent = r[H["ts"][r] >= t_last]
        per = []
        if len(before):
            per.append({"label": "Före", "short": "Före", **_block(H, before),
                        "follow": _follow(sessions, int(H["ts"][before[0]]), t_start - 1)})
        if len(mid) >= 200 and len(recent):
            per.append({"label": f"{_d(sd)}–\n{_d(dt_of(int(ts[len(mid) - 1])))}", "short": "Efter\nstart", **_block(H, mid),
                        "follow": _follow(sessions, t_start, t_last - 1)})
            per.append({"label": f"Senaste\n{LAST_DAYS} dagarna", "short": f"Senaste\n{LAST_DAYS} d", **_block(H, recent),
                        "follow": _follow(sessions, t_last, int(ts[-1]))})
        else:
            per.append({"label": f"Sedan\n{_d(sd)}", "short": "Efter\nstart", **_block(H, r), "follow": _follow(sessions, t_start, int(ts[-1]))})
        out["mode"] = "periods"
        out["periods"] = per
    return out
