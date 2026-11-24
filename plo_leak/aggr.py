"""Aggression: hur ofta du bettar och höjer, och när det lönar sig.

Mått (dina postflop-beslut):
* AF = (bet + höjning) / syn, och AFq = (bet + höjning) / (bet + höjning + syn + fold), per gata.
* C-bet: flop heads-up när du var sist att höja preflop, i och ur position.
* Check-raise: heads-up ur position, när du checkat och mött en bet.
* Stab-andel: heads-up i position när det checkats till dig (alla gator) – hur ofta du bettar.
* Bet mot check när det checkats till dig i position, per handgrupp: vad fick du tillbaka i andel av potten?
  (Jämförelsen påverkas av att du själv väljer när du bettar – se den som riktning.)
* Per spelpass: stab-andel och resultat utan showdown – vinner du mer när du är aggressiv?
"""
from __future__ import annotations

import numpy as np

BLOCK = 5000
GRP = ["Svag (par eller sämre, inget drag)", "Drag", "Två par eller bättre"]
STREET = {1: "Flop", 2: "Turn", 3: "River"}
PASSIVE_PP = 6.0     # en session är "passiv" när stab-andelen är minst så många procentenheter under din normala
MIN_OPPS = 30


def _sel(ft, rows):
    P = ft.t.get("pfd") if ft is not None else None
    if P is None or not len(P["hidx"]):
        return None, None
    mask = np.zeros(ft.n, bool)
    mask[np.asarray(rows, dtype=np.int64)] = True
    return P, ft.subset_mask(mask, "pfd")


def aggression(st) -> dict:
    from .fatigue import _cluster_mean_se, hand_session_info
    ft = getattr(st, "ft", None)
    P, m = _sel(ft, st.rows) if ft is not None else (None, None)
    if P is None or m.sum() < 500:
        return {}
    H = ft.H
    kc = {k: ft.code("kind", k) for k in ("bet", "raise", "call", "fold", "check")}
    kind = P["kind"]
    agg = np.isin(kind, [kc["bet"], kc["raise"]])
    call, fold, bet, chk = kind == kc["call"], kind == kc["fold"], kind == kc["bet"], kind == kc["check"]
    hu = P["np"] == 2
    streets = []
    for s in (1, 2, 3):
        ms = m & (P["st"] == s)
        a, c, f = int((agg & ms).sum()), int((call & ms).sum()), int((fold & ms).sum())
        streets.append({"street": STREET[s], "af": a / c if c else None, "afq": 100.0 * a / (a + c + f) if a + c + f else None})
    cb = m & hu & (P["st"] == 1) & P["pfa"] & (P["facing"] == 0) & (P["ord"] == 1)
    cbet = {"ip": 100.0 * (bet & cb & P["ip"]).sum() / max((cb & P["ip"]).sum(), 1),
            "oop": 100.0 * (bet & cb & ~P["ip"]).sum() / max((cb & ~P["ip"]).sum(), 1)}
    crm = m & hu & ~P["ip"] & (P["facing"] == 1) & (P["ord"] == 2)
    cr = [{"street": STREET[s], "pct": 100.0 * (kind[crm & (P["st"] == s)] == kc["raise"]).mean() if (crm & (P["st"] == s)).any() else None}
          for s in (1, 2, 3)]
    stab_m = m & hu & P["ip"] & (P["facing"] == 0) & (P["ord"] == 1)
    stab_all = 100.0 * (bet & stab_m).sum() / max(stab_m.sum(), 1)
    # bet mot check i position när det checkats till dig
    spots = [("Flop – du var höjare (c-bet)", (P["st"] == 1) & P["pfa"]),
             ("Flop – checkat till dig", (P["st"] == 1) & ~P["pfa"]),
             ("Turn – efter check–check på flop", (P["st"] == 2) & (P["prev"] == 0)),
             ("River – checkat till dig", P["st"] == 3)]
    x = P["fh"] / np.maximum(P["pot"], 1e-9)
    table = []
    for name, sm in spots:
        base = stab_m & sm & ~np.isnan(x)
        rows = []
        for g in range(3):
            mb, mc = base & (P["grp"] == g) & bet, base & (P["grp"] == g) & chk
            if mb.sum() < 30 or mc.sum() < 30:
                continue
            rows.append({"grp": GRP[g], "bet": float(x[mb].mean()), "check": float(x[mc].mean()),
                         "bet_pct": 100.0 * mb.sum() / (mb.sum() + mc.sum()), "n": int(mb.sum() + mc.sum()),
                         "checks": int(mc.sum())})
        if rows:
            table.append({"spot": name, "rows": rows})
    # per spelpass och per block: stab-andel och resultat utan showdown
    r, sess, _ = hand_session_info(st)
    pos = np.full(ft.n, -1, np.int64)
    pos[r] = np.arange(len(r))
    k = pos[P["hidx"]]
    ok = stab_m & (k >= 0)
    s_of = np.full(len(P["hidx"]), -1, np.int64)
    s_of[ok] = sess[k[ok]]
    ns = int(sess.max()) + 1 if len(sess) else 0
    opp_s = np.bincount(s_of[ok], minlength=ns)
    bet_s = np.bincount(s_of[ok & bet], minlength=ns)
    ev = H["ev"][r].astype(float)
    nsd = np.where(H["sd"][r].astype(bool), 0.0, ev)
    hands_s = np.bincount(sess, minlength=ns)
    ev_s = np.bincount(sess, weights=ev, minlength=ns)
    nsd_s = np.bincount(sess, weights=nsd, minlength=ns)
    big = (hands_s >= 300) & (opp_s >= MIN_OPPS)
    quart = []
    if big.sum() >= 12:
        rate = np.where(opp_s > 0, bet_s / np.maximum(opp_s, 1), np.nan)
        qs = np.quantile(rate[big], [0.25, 0.5, 0.75])
        lab = ["Mest passiva fjärdedelen", "Under mitten", "Över mitten", "Mest aggressiva fjärdedelen"]
        q = np.searchsorted(qs, rate, side="right")
        for j in range(4):
            mm = big & (q == j)
            if not mm.any():
                continue
            quart.append({"label": lab[j], "sessions": int(mm.sum()), "hands": int(hands_s[mm].sum()),
                          "stab": 100.0 * bet_s[mm].sum() / opp_s[mm].sum(),
                          "nsd100": 100.0 * nsd_s[mm].sum() / hands_s[mm].sum(),
                          "ev100": 100.0 * ev_s[mm].sum() / hands_s[mm].sum()})
    blocks = []
    nb = max(1, len(r) // BLOCK)
    bk = np.minimum(np.arange(len(r)) // BLOCK, nb - 1)
    kb = np.full(len(P["hidx"]), -1, np.int64)
    kb[ok] = bk[k[ok]]
    for b in range(nb):
        mo = ok & (kb == b)
        mh = bk == b
        nsd_m, nsd_se = _cluster_mean_se(nsd[mh], sess[mh])
        blocks.append({"label": str(b + 1), "stab": 100.0 * (bet & mo).sum() / max(mo.sum(), 1),
                       "nsd100": 100.0 * nsd_m, "hands": int(mh.sum())})
    return {"streets": streets, "cbet": cbet, "cr": cr, "stab": stab_all, "table": table, "quart": quart,
            "blocks": blocks, "passive_pp": PASSIVE_PP}


def session_stab(st, t0: int, t1: int, normal: float | None) -> dict | None:
    """Stab-andelen i en session jämfört med din normala."""
    ft = st.ft
    rows = np.asarray(st.rows, dtype=np.int64)
    ts = ft.H["ts"][rows]
    P, m = _sel(ft, rows[(ts >= t0) & (ts <= t1)])
    if P is None:
        return None
    bet = P["kind"] == ft.code("kind", "bet")
    sm = m & (P["np"] == 2) & P["ip"] & (P["facing"] == 0) & (P["ord"] == 1)
    n = int(sm.sum())
    if n < 10:
        return None
    rate = 100.0 * (bet & sm).sum() / n
    return {"opps": n, "stab": rate, "normal": normal,
            "passive": bool(normal is not None and n >= MIN_OPPS and rate <= normal - PASSIVE_PP)}
