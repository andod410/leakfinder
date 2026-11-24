"""2.76: rakeback i vinstkurvan (på/av på Översikt).

Rakeback per hand = handens rake × (Ocean Rewards % + leaderboard % för spelformen + agentbonus %).
Procentsatserna kommer från mätningen 11 sep – 14 nov 2026 (GEM-värde och leaderboard-utbetalningar mot
programmets rake) och kan ändras på Översikt. Agentbonusen är 0 tills den faktiskt betalats.
Räknas i efterhand på händerna – ingen ny faktatabell.
"""
from __future__ import annotations

import numpy as np

# 2.86: standardvärden efter mätningarna 19 nov och 20–21 nov (GEMs 17,5–17,9 % av raken; leaderboard + freeroll
# 8,8 % på 0.5/1, 9,5 % på 1/2; totalt 26–27 %). Sparade värden på Översikt gäller före standardvärdena.
DEFAULT = {"on": False, "ocean": 17.7, "agent": 0.0,
           "lb": {"PLO6 0.5/1": 8.8, "PLO6 1/2": 9.5, "PLO4 Rush & Cash": 34.7, "Övrigt": 0.0}}


def settings(db) -> dict:
    from . import watch
    try:
        d = (watch.load_settings(db) or {}).get("rakeback_curve") or {}
    except Exception:
        d = {}
    out = {**DEFAULT, **{k: v for k, v in d.items() if k in DEFAULT}}
    out["lb"] = {**DEFAULT["lb"], **(d.get("lb") or {})}
    return out


def save(db, form) -> dict:
    from . import watch
    cur = settings(db)

    def num(k, old):
        try:
            v = float(str(form.get(k, "")).replace(",", "."))
            return max(0.0, min(100.0, v))
        except ValueError:
            return old
    if "toggle" in form:
        cur["on"] = not cur["on"]
    else:
        cur["ocean"] = num("ocean", cur["ocean"])
        cur["agent"] = num("agent", cur["agent"])
        cur["lb"] = {k: num("lb_" + k, v) for k, v in cur["lb"].items()}
    watch.save_settings(db, rakeback_curve=cur)
    return cur


def _form_of(game: str, stake: str, rc: bool) -> str:
    g = game.replace("-", "")
    if g == "PLO4" and rc:
        return "PLO4 Rush & Cash"
    if g == "PLO6" and stake in ("0.5/1", "0.5/1.0"):
        return "PLO6 0.5/1"
    if g == "PLO6" and stake in ("1/2", "1.0/2.0"):
        return "PLO6 1/2"
    return "Övrigt"


def pct_rows(ft, rows, cfg) -> np.ndarray:
    """Rakeback i procent av raken för raderna `rows` i hands-tabellen (i den ordningen)."""
    H = ft.H
    rows = np.asarray(rows)
    game, stake, rc = H["game"][rows], H["stake"][rows], H["ttype"][rows]
    out = np.zeros(len(rows))
    base = float(cfg.get("ocean", 0)) + float(cfg.get("agent", 0))
    for g in np.unique(game):
        for s in np.unique(stake[game == g]):
            for r in (0, 1):
                m = (game == g) & (stake == s) & (rc == r)
                if m.any():
                    form = _form_of(ft.label("game", int(g)), ft.label("stake", int(s)), bool(r))
                    out[m] = base + float(cfg["lb"].get(form, 0.0))
    return out


def pct_per_row(st, cfg) -> np.ndarray:
    """Rakeback i procent av raken för varje hand i urvalet (i urvalets ordning)."""
    return pct_rows(st.ft, st.rows, cfg)


def rb_rows(ft, rows, cfg):
    """2.86: rakeback per hand för raderna `rows`: (bb, $)."""
    p = pct_rows(ft, rows, cfg) / 100.0
    return ft.H["rake"][rows] * p, ft.H["rake_m"][rows] * p


def current_cfg() -> dict:
    """2.86: procentsatserna från Översikt (eller standardvärdena om databasen inte nås)."""
    try:
        from .web import get_db
        return settings(get_db())
    except Exception:
        return {**DEFAULT, "lb": dict(DEFAULT["lb"])}


def summary(st, cfg) -> dict:
    """Serier och nyckeltal med rakeback. Tomt om urvalet saknar faktatabell."""
    if getattr(st, "ft", None) is None or getattr(st, "rows", None) is None or not len(st.rows):
        return {}
    H = st.ft.H
    rows = st.rows
    pct = pct_per_row(st, cfg) / 100.0
    rb = H["rake"][rows] * pct
    rb_m = H["rake_m"][rows] * pct
    n = len(rows)
    ev, ev_m = H["ev"][rows], H["ev_m"][rows]
    net, net_m = H["net"][rows], H["money"][rows]
    out = {"cum_ev_rb": np.cumsum(ev + rb), "cum_ev_rb_m": np.cumsum(ev_m + rb_m),
           "cum_net_rb": np.cumsum(net + rb), "cum_net_rb_m": np.cumsum(net_m + rb_m),   # 2.88
           "rb_bb": float(rb.sum()), "rb_money": float(rb_m.sum()),
           "ev100": float(100 * ev.sum() / n), "ev100_rb": float(100 * (ev.sum() + rb.sum()) / n),
           "pct": float(100 * rb.sum() / H["rake"][rows].sum()) if H["rake"][rows].sum() > 0 else 0.0}
    out.update(winrate_stats(st.ft, rows, ev, rb, net))
    out["luck_m"] = float(net_m.sum() - ev_m.sum())
    return out


def _ci100(x) -> float:
    """95 %-intervall (±) för medelvärdet per 100 händer."""
    n = len(x)
    return float(1.96 * 100 * np.std(x, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")


def winrate_stats(ft, rows, ev, rb, net) -> dict:
    """2.88: verklig winrate = all-in EV inkl. rakeback i bb/100, med 95 %-intervall, totalt och per nivå."""
    n = len(rows)
    out = {"n": int(n), "rb100": float(100 * rb.sum() / n) if n else 0.0,
           "ev100_rb_ci": _ci100(ev + rb), "luck_bb": float(net.sum() - ev.sum()), "per_stake": []}
    stake = ft.H["stake"][rows]
    for s in np.unique(stake):
        m = stake == s
        k = int(m.sum())
        if k < 200:
            continue
        out["per_stake"].append({"stake": ft.label("stake", int(s)), "n": k,
                                 "ev100_rb": float(100 * (ev[m].sum() + rb[m].sum()) / k),
                                 "ci": _ci100(ev[m] + rb[m]), "rb100": float(100 * rb[m].sum() / k)})
    out["per_stake"].sort(key=lambda x: -x["n"])
    return out
