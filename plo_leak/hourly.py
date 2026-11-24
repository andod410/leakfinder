"""Timlön: händer per timme och vad du tjänar per timme – faktiskt och med all-in EV.

Speltiden räknas från tidsstämplarna i handhistoriken (när varje hand startade), för alla bord
tillsammans – spelar du flera bord samtidigt blir det alltså fler händer per timme:

* Händerna delas in i spelpass (ny session efter en paus på mer än 30 minuter).
* Inom ett pass räknas tiden mellan två händer i följd, men en lucka på mer än PAUSE_CAP
  (5 minuter) räknas bara som 5 minuter – längre luckor är pauser, inte spel.
* Den sista handen i varje pass får en typisk handlängd (medianen av luckorna).

Timlön = resultat / speltid. All-in EV-timlönen tar bort tur och otur i all-ins och är det
bästa måttet på vad du faktiskt tjänar per timme. Intervallet bygger på hur mycket resultaten
varierar mellan spelpassen. Rakeback ingår inte (se sidan Rakeback & leaderboard).
"""
from __future__ import annotations

import numpy as np

from .statlib import cluster_se

PAUSE_CAP = 300          # sekunder: längre luckor räknas som paus
DEFAULT_HAND_SEC = 60.0  # om det inte finns några luckor att mäta på
MIN_HOURS = 1.0          # veckor, nivåer och spelpass med kortare speltid får ingen timlön


def _active_seconds(ts: np.ndarray, clu: np.ndarray) -> tuple[float, int, float]:
    """(aktiv speltid i sekunder, antal spelpass, typisk tid per hand)."""
    n = len(ts)
    if not n:
        return 0.0, 0, DEFAULT_HAND_SEC
    gaps = np.diff(ts).astype(float)
    same = clu[1:] == clu[:-1]
    g = np.minimum(gaps[same], PAUSE_CAP)
    g = g[g > 0]
    tail = float(np.median(g)) if len(g) else DEFAULT_HAND_SEC
    sessions = int(1 + (~same).sum())
    return float(np.minimum(gaps[same], PAUSE_CAP).sum()) + sessions * tail, sessions, tail


def _ratio_se(money, ts, clu, total_sec) -> float:
    """Klustrat SE för (Σ dollar / Σ timmar) över spelpass: linjärisering av kvoten (pass = kluster)."""
    o = np.argsort(ts, kind="stable")
    money, ts, clu = np.asarray(money)[o], np.asarray(ts)[o], np.asarray(clu)[o]
    ids, inv = np.unique(clu, return_inverse=True)
    K = len(ids)
    if K < 2 or total_sec <= 0:
        return float("nan")
    m_k = np.bincount(inv, weights=money, minlength=K)
    s_k = np.zeros(K)
    for k in range(K):
        t = ts[inv == k]
        sec, _n, _tail = _active_seconds(t, np.zeros(len(t), int))
        s_k[k] = sec
    S = s_k.sum()
    if S <= 0:
        return float("nan")
    rate = m_k.sum() / S
    res = m_k - rate * s_k
    var = K / (K - 1) * (res ** 2).sum() / S ** 2
    return float(np.sqrt(var) * 3600.0)


def _block(H, r, hands_total=None) -> dict:
    ts, clu = H["ts"][r], H["clu"][r]
    sec, sessions, tail = _active_seconds(ts, clu)
    hours = sec / 3600.0
    n = len(r)
    money, ev_m, rake_m = H["money"][r], H["ev_m"][r], H["rake_m"][r]
    net, ev = H["net"][r], H["ev"][r]
    out = {"hands": n, "mixed_stakes": len(np.unique(H["bb"][r])) > 1, "hours": hours, "rate_ok": hours >= MIN_HOURS, "sessions": sessions, "hph": n / hours if hours > 0 else None,
           "money": float(money.sum()), "ev_money": float(ev_m.sum()), "rake_money": float(rake_m.sum()),
           "net_bb": float(net.sum()), "ev_bb": float(ev.sum()), "rake_bb": float(H["rake"][r].sum()),
           "bb_usd": float(np.median(H["bb"][r])) if n else 0.0,
           "start": int(ts.min()) if n else 0, "end": int(ts.max()) if n else 0}
    if n:
        out["rake100"] = 100.0 * out["rake_bb"] / n
        out["ev100"] = 100.0 * out["ev_bb"] / n
    if hours > 0:
        out.update(usd_h=out["money"] / hours, ev_usd_h=out["ev_money"] / hours,
                   pre_usd_h=(out["ev_money"] + out["rake_money"]) / hours, rake_usd_h=out["rake_money"] / hours,
                   bb_h=out["net_bb"] / hours, ev_bb_h=out["ev_bb"] / hours)
        if n >= 200 and sessions >= 5:
            # 2.81: kvotskattning per spelpass (passets EV i dollar och passets aktiva tid varierar båda) – osäkerheten
            # i speltakten ingår, inte bara i resultatet per hand
            se = _ratio_se(ev_m, ts, clu, sec)
            if np.isfinite(se):
                out["ev_lo"], out["ev_hi"] = out["ev_usd_h"] - 1.96 * se, out["ev_usd_h"] + 1.96 * se
    return out


def hourly_table(st, all_sessions: bool = False) -> dict:
    ft, rows = getattr(st, "ft", None), getattr(st, "rows", None)
    if ft is None or rows is None or not len(rows):
        return {}
    from .facts import dt_of
    H = ft.H
    r = np.asarray(rows)
    total = _block(H, r)
    if not total["hours"]:
        return {}
    # per nivå (speltid medan du spelade just den nivån)
    stakes = []
    for code in np.unique(H["stake"][r]):
        m = r[H["stake"][r] == code]
        if len(m) >= 100:
            b = _block(H, m)
            if b["hours"] >= MIN_HOURS:
                stakes.append({"stake": ft.label("stake", int(code)), **b})
    stakes.sort(key=lambda x: -x["hands"])
    # per vecka
    weeks = []
    days = H["ts"][r] // 86400
    wk = np.array([dt_of(int(d) * 86400).isocalendar()[:2] for d in np.unique(days)])
    day_to_wk = {int(d): f"{a}-v{b:02d}" for d, (a, b) in zip(np.unique(days), wk)}
    labels = np.array([day_to_wk[int(d)] for d in days])
    for w in sorted(set(labels.tolist())):
        m = r[labels == w]
        b = _block(H, m)
        if b["hours"] >= MIN_HOURS:  # en timlön på några minuters spel säger ingenting
            weeks.append({"week": w, **b})
    # de senaste spelpassen
    clu = H["clu"][r]
    sess = []
    starts = np.flatnonzero(np.r_[True, clu[1:] != clu[:-1]])
    ends = np.r_[starts[1:], len(r)]
    for a, b_ in (list(zip(starts, ends)) if all_sessions else list(zip(starts, ends))[-15:])[::-1]:
        m = r[a:b_]
        blk = _block(H, m)
        sess.append({"start": dt_of(int(H["ts"][m[0]])).strftime("%Y-%m-%d %H:%M"),
                     "end": dt_of(int(H["ts"][m[-1]])).strftime("%H:%M"), **blk})
    mx = max([abs(w.get("ev_usd_h") or 0) for w in weeks] + [abs(w.get("usd_h") or 0) for w in weeks] + [1e-9])
    return {"total": total, "stakes": stakes, "weeks": weeks, "weeks_max": mx, "sessions": sess,
            "pause_min": PAUSE_CAP // 60}


HOURLY_HEADER = ["level", "label", "hands", "sessions", "start", "end", "active_hours", "hands_per_hour",
                 "net_usd", "ev_usd", "rake_usd", "net_usd_per_h", "ev_usd_per_h", "ev_usd_per_h_lo95", "ev_usd_per_h_hi95",
                 "rake_usd_per_h", "ev_bb100", "rake_bb100", "mixed_stakes", "rakeback", "note"]


def hourly_summary_rows(st) -> list:
    """2.71: timlönen exakt som appen räknar den, för total, nivå, vecka och session (för djupexporten).
    Nivåernas timmar räknas medan just den nivån spelades och ÖVERLAPPAR i pass med flera nivåer –
    de kan inte summeras. Rakeback ingår inte."""
    from .facts import dt_of
    T = hourly_table(st, all_sessions=True)
    if not T:
        return []
    def d(ts):
        return dt_of(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""
    def row(level, label, b, note=""):
        f = lambda x, k=2: "" if x is None else round(float(x), k)
        return [level, label, b["hands"], b["sessions"], d(b.get("start")), d(b.get("end")), f(b["hours"], 3),
                f(b.get("hph"), 1), f(b["money"]), f(b["ev_money"]), f(b["rake_money"]), f(b.get("usd_h")),
                f(b.get("ev_usd_h")), f(b.get("ev_lo")), f(b.get("ev_hi")), f(b.get("rake_usd_h")),
                f(b.get("ev100")), f(b.get("rake100")), int(bool(b["mixed_stakes"])), "exkluderad", note]
    tot = T["total"]
    out = [row("total", "alla", tot, "aktiv tid: luckor > 5 min räknas som 5 min, ny session efter 30 min")]
    sh = sum(b["hours"] for b in T["stakes"])
    for b in T["stakes"]:
        out.append(row("stake", b["stake"], b, "timmar överlappar i pass med flera nivåer – summera inte"
                       if sh > tot["hours"] + 0.01 else ""))
    if sh > tot["hours"] + 0.01:
        out.append(["overlap", "nivåtimmar minus total", "", "", "", "", round(sh - tot["hours"], 3)] + [""] * 12
                   + ["nivåernas timmar är inte disjunkta"])
    for b in T["weeks"]:
        out.append(row("week", b["week"], b))
    for b in T["sessions"]:
        out.append(row("session", b["start"], b))
    return out
