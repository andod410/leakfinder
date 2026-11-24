"""Tid i sessionen: spelar du sämre ju längre du spelar?

För varje hand räknas hur länge sessionen pågått (ny session efter mer än 30 minuters paus). Händerna
delas i timmar (0–1 h, 1–2 h …) och för varje timme mäts:

* VPIP-avvikelse: hur mycket oftare du spelar en hand än du brukar i samma läge (samma position, antal
  spelare, nivå och bordstyp). Det tar bort effekten av att borden ser olika ut.
* regelbrott per 100 händer och deras väntade kostnad (brott × vad ett brott kostar i snitt).
* all-in EV per 100 händer (svänger mycket – bara som information).

Osäkerheten räknas per spelpass (kluster), eftersom händer i samma pass hänger ihop. En timme räknas
som tydligt sämre än den första när VPIP-avvikelsen är högre än i första timmen även med
felmarginalen (95 %). Rekommenderad paus = den första sådana timmen.

Väntad vinst av en gräns: om händerna efter gränsen hade spelats som under den första timmen (en paus
på mer än 30 minuter startar en ny session, och nya sessioner börjar tight igen), skulle regelbrotten
ha kostat lika lite som då. Skillnaden räknas om till bb/100 över alla händer.
"""
from __future__ import annotations

import math

import numpy as np

from .sessions import session_bounds

EDGES_H = [0, 1, 2, 3, 4]          # timmar; sista gruppen = 4 h eller mer
MIN_HANDS = 500                    # färre händer i en timgrupp = ingen bedömning
LIMITS_H = (1.0, 1.5, 2.0, 2.5, 3.0)


def _cluster_mean_se(x, c):
    """Medel och kluster-medelfel (c = spelpass)."""
    x = np.asarray(x, float)
    if len(x) < 2:
        return (float(x.mean()) if len(x) else 0.0), float("nan")
    m = float(x.mean())
    _, inv = np.unique(c, return_inverse=True)
    k = inv.max() + 1
    if k < 2:
        return m, float("nan")
    s = np.bincount(inv, weights=x - m, minlength=k)
    return m, float(math.sqrt(k / (k - 1) * (s ** 2).sum()) / len(x))


def hand_session_info(st):
    """(rader i tidsordning, sessionsnummer per rad, timmar in i sessionen per rad)."""
    H = st.ft.H
    r = np.asarray(st.rows, dtype=np.int64)
    r = r[np.argsort(H["ts"][r], kind="stable")]
    ts = H["ts"][r].astype(np.int64)
    starts = session_bounds(ts)
    lens = np.diff(np.r_[starts, len(r)])
    sess = np.repeat(np.arange(len(starts)), lens)
    t_in = (ts - ts[starts][sess]) / 3600.0
    return r, sess, t_in


def _vpip_dev(H, r):
    """VPIP minus ditt snitt i samma läge (position, antal spelare, nivå, bordstyp)."""
    key = (H["pos"][r].astype(np.int64) * 16 + H["nplay"][r].astype(np.int64)) * 4096 \
        + H["stake"][r].astype(np.int64) * 2 + H["ttype"][r].astype(np.int64)
    _, inv = np.unique(key, return_inverse=True)
    v = H["vpip"][r].astype(float)
    mean = np.bincount(inv, weights=v) / np.bincount(inv)
    return v - mean[inv]


def _breaks(st, rules_doc, r):
    """Väntad kostnad (bb, negativ) och 1/0 för regelbrott per rad i r."""
    from .practice import broke_mask, careful_costs, first_rows, violation_index
    H = st.ft.H
    cost = np.zeros(len(r))
    brk = np.zeros(len(r))
    rules = (rules_doc or {}).get("rules") or []
    pre = st.decisions.pre if getattr(st, "decisions", None) else None
    if not rules or pre is None or pre.ft is None or not len(pre):
        return cost, brk
    vi = violation_index(rules, pre)
    m = first_rows(pre) & (vi >= 0) & broke_mask(rules, pre, vi)
    idx = np.flatnonzero(m)
    _, firsts = np.unique(pre.hidx[idx], return_index=True)
    idx = idx[firsts]
    pos = np.full(st.ft.n, -1, np.int64)
    pos[r] = np.arange(len(r))
    k = pos[pre.hidx[idx]]
    ok = k >= 0
    rc = careful_costs(rules, pre, vi)
    cost[k[ok]] = rc[vi[idx][ok]]
    brk[k[ok]] = 1.0
    return cost, brk


def fatigue_table(st, rules_doc, limit_h: float | None = None) -> dict:
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None or len(st.rows) < 2 * MIN_HANDS:
        return {}
    H = ft.H
    r, sess, t_in = hand_session_info(st)
    dv = _vpip_dev(H, r)
    cost, brk = _breaks(st, rules_doc, r)
    ev = H["ev"][r].astype(float)
    n = len(r)
    grp = np.searchsorted(np.array(EDGES_H[1:], float), t_in, side="right")
    rows = []
    for g in range(len(EDGES_H)):
        m = grp == g
        k = int(m.sum())
        label = f"{EDGES_H[g]}–{EDGES_H[g + 1]} h" if g + 1 < len(EDGES_H) else f"{EDGES_H[g]} h eller mer"
        if not k:
            rows.append({"label": label, "hands": 0})
            continue
        vm, vse = _cluster_mean_se(dv[m], sess[m])
        bm, bse = _cluster_mean_se(brk[m], sess[m])
        cm, cse = _cluster_mean_se(cost[m], sess[m])
        em, ese = _cluster_mean_se(ev[m], sess[m])
        rows.append({"label": label, "hands": k, "share": 100.0 * k / n, "ok": k >= MIN_HANDS,
                     "vpip": 100.0 * float(H["vpip"][r][m].mean()), "vdev": 100.0 * vm, "vdev_se": 100.0 * vse,
                     "brk100": 100.0 * bm, "cost100": 100.0 * cm, "cost_se": 100.0 * cse,
                     "ev100": 100.0 * em, "ev_se": 100.0 * ese, "sessions": int(len(np.unique(sess[m])))})
    base = rows[0]
    worse_from = None
    for g, x in enumerate(rows[1:], 1):
        if not x.get("ok") or not base.get("ok"):
            continue
        d = x["vdev"] - base["vdev"]
        se = math.sqrt((x["vdev_se"] or 0) ** 2 + (base["vdev_se"] or 0) ** 2)
        x["vdiff"] = d
        x["worse"] = bool(np.isfinite(se) and d - 1.96 * se > 0)
        if x["worse"] and worse_from is None:
            worse_from = g
    # väntad vinst av olika gränser: händer efter gränsen kostar som i första timmen
    c0 = base.get("cost100", 0.0) / 100.0 if base.get("hands") else 0.0
    options = []
    for L in LIMITS_H:
        late = t_in >= L
        save = float((c0 - cost[late]).sum()) / n * 100.0 if late.any() else 0.0
        options.append({"h": L, "late_share": 100.0 * float(late.mean()), "save100": save})
    rec = float(EDGES_H[worse_from]) if worse_from is not None else None
    limit = limit_h or rec
    # sessioner som gått över gränsen, vecka för vecka (andel händer efter gränsen)
    return {"rows": rows, "recommended_h": rec, "limit_h": limit, "options": options,
            "significant": worse_from is not None, "hands": n,
            "late_share": 100.0 * float((t_in >= limit).mean()) if limit else None,
            "save100": next((o["save100"] for o in options if limit and abs(o["h"] - limit) < 1e-9),
                            float((c0 - cost[t_in >= limit]).sum()) / n * 100.0 if limit else None)}


def hours_text(h: float) -> str:
    """1 -> "1 timme", 1.5 -> "1,5 timmar"."""
    return f"{h:g}".replace(".", ",") + (" timme" if abs(h - 1) < 1e-9 else " timmar")


def session_hours(st, rules_doc, t0: int, t1: int) -> list:
    """Timme för timme i en session: händer, VPIP-avvikelse och regelbrott."""
    ft = st.ft
    H = ft.H
    r, sess, t_in = hand_session_info(st)
    ts = H["ts"][r]
    m = (ts >= t0) & (ts <= t1)
    if not m.any():
        return []
    dv = _vpip_dev(H, r)
    cost, brk = _breaks(st, rules_doc, r)
    out = []
    hrs = np.floor(t_in[m]).astype(int)
    for hh in np.unique(hrs):
        k = hrs == hh
        out.append({"label": f"{hh}–{hh + 1} h", "hands": int(k.sum()),
                    "vpip": 100.0 * float(H["vpip"][r][m][k].mean()), "vdev": 100.0 * float(dv[m][k].mean()),
                    "brk": int(brk[m][k].sum()), "cost": float(cost[m][k].sum())})
    return out


def focus_item(st, rules_doc, F: dict, recent: int, done_weeks: int, done_min: int):
    """Sessionslängden som en läcka i fokuskön: "ta paus efter X h". Kostnaden nu = vad regelbrotten
    efter gränsen kostat utöver första timmens nivå, i dina senaste händer."""
    from .facts import dt_of
    if not F or not F.get("limit_h") or not F.get("significant"):
        return None
    L = F["limit_h"]
    H = st.ft.H
    r, sess, t_in = hand_session_info(st)
    cost, _ = _breaks(st, rules_doc, r)
    c0 = F["rows"][0]["cost100"] / 100.0
    late = t_in >= L
    rec = slice(max(0, len(r) - recent), len(r))
    n_rec = len(r[rec])
    per100 = float((c0 - cost[rec][late[rec]]).sum()) / n_rec * 100.0 if n_rec else 0.0
    ts = H["ts"][r]
    last = int(ts[-1])
    weeks = []
    for w in range(7, -1, -1):
        lo, hi = last - (w + 1) * 7 * 86400, last - w * 7 * 86400
        wm = (ts > lo) & (ts <= hi)
        o, d = int(wm.sum()), int((wm & late).sum())
        weeks.append({"label": dt_of(hi).strftime("%d/%m"), "opps": o, "dev": d, "rate": 100.0 * d / o if o else None})
    lw = weeks[-done_weeks:]
    o2, d2 = sum(w["opps"] for w in lw), sum(w["dev"] for w in lw)
    hstr = hours_text(L)
    return {"id": "session|langd", "title": f"Ta minst 30 minuters paus efter {hstr}",
            "why": (f"Efter {hstr} i samma session spelar du lösare och bryter oftare mot dina regler än under "
                    f"första timmen – oavsett när på dygnet du börjar. En paus på mer än 30 minuter startar en ny "
                    f"session, och nya sessioner börjar tight igen. Pausen är ett sätt att följa dina regler – kostnaden här är "
                    f"samma pengar som regelbrotten efter gränsen, så lägg inte ihop den med reglernas kostnad. "
                    f"Se Sessioner → Tid i sessionen."),
            "overlap": True,
            "level": "bekräftad", "cost_hand": None, "per100": max(per100, 0.0),
            "opps": int(n_rec), "dev": int(late[rec].sum()),
            "rate": 100.0 * float(late[rec].mean()) if n_rec else 0.0, "recent_hands": n_rec,
            "weeks": weeks, "done": o2 >= done_min and 100.0 * d2 / o2 <= 5.0, "train": None, "except": [],
            "kind": "session", "dev_rows": np.zeros(0, np.int64)}


# ---------------------------------------------------------------- 2.68: stoppregel och "när det går dåligt"
STOP_BB = 500.0   # 2.72 (Andreas 2026-11-14): bankrulleskydd, inte ett winrate-löfte …
STOP_H = 2.0      # … eller efter så här många timmar (det som kommer först) – beteenderegel, EV-effekten är inte visad
BIG_LOSS_BB = 175.0  # 2.72: förlorad pott större än så → paus
PAUSE_SEC = 900      # pausens längd (2.86: 15 min, tidigare 2 min – beslut 2026-11-21)
HAND_SEC = 60        # ungefärlig handlängd (bara starttid finns i handhistoriken)
DOWN_BB = 150.0   # "back" / "plus" i analysen nedan


def _before_net(H, r, sess):
    """Resultat i bb i passet FÖRE varje hand (rader i tidsordning, sess = sessionsnummer per rad)."""
    net = H["net"][r].astype(float)
    cs = np.cumsum(net) - net
    starts = np.r_[0, np.flatnonzero(np.diff(sess)) + 1]
    return cs - cs[starts][sess]


def session_stop(st, rules_doc, t0: int, t1: int, stop_bb: float = STOP_BB, stop_h: float = STOP_H) -> dict | None:
    """Stoppregeln i efterhand (programmet visar den aldrig under spel – GG förbjuder realtidshjälp):
    nådde passet −stop_bb eller stop_h timmar, när, och vad kostade händerna efter gränsen?"""
    ft = st.ft
    H = ft.H
    r, sess, t_in = hand_session_info(st)
    ts = H["ts"][r]
    m = (ts >= t0) & (ts <= t1)
    if m.sum() < 2:
        return None
    rr = r[m]
    sid = np.asarray(sess)[m]
    # 2.87 (R5-02/R6-01): tiden och förlusten räknas per pass, inte från urvalets första hand – annars blev flera pass
    # i en sessionsfil ett enda "pass" (t.ex. "gränsen nåddes efter 7 h 58 min").
    tin = np.zeros(len(rr)); before = np.zeros(len(rr))
    net = H["net"][rr].astype(float)
    for s_ in np.unique(sid):
        k = sid == s_
        tin[k] = (ts[m][k] - ts[m][k].min()) / 3600.0
        before[k] = np.cumsum(net[k]) - net[k]
    over = (before <= -stop_bb) | (tin >= stop_h)
    hit = np.flatnonzero(over)
    dv = _vpip_dev(H, r)[m]
    cost, brk = _breaks(st, rules_doc, r)
    cost, brk = cost[m], brk[m]
    ev = H["ev"][rr].astype(float)
    vp = H["vpip"][rr].astype(float)
    out = {"stop_bb": stop_bb, "stop_h": stop_h, "hands": int(len(rr)), "kept": not len(hit),
           "big_loss_bb": BIG_LOSS_BB, **_pause_check(H, rr, ts[m])}
    if not len(hit):
        return out
    i = int(hit[0])
    why = "−%g bb" % stop_bb if before[i] <= -stop_bb else "%g timmar" % stop_h
    # efter gränsen = alla händer efter att gränsen nåtts i sitt eget pass
    after_mask = np.zeros(len(rr), bool)
    for s_ in np.unique(sid):
        k = np.flatnonzero(sid == s_)
        h_ = k[over[k]]
        if len(h_):
            after_mask[h_[0]:k[-1] + 1] = True
    a, b = ~after_mask, after_mask
    def part(s):
        n = len(ev[s])
        return {"hands": n, "ev": float(ev[s].sum()), "ev100": (100.0 * float(ev[s].mean()) if n else None),
                "vpip": (100.0 * float(vp[s].mean()) if n else None), "vdev": (100.0 * float(dv[s].mean()) if n else None),
                "brk": int(brk[s].sum()), "brk100": (100.0 * float(brk[s].mean()) if n else None), "cost": float(cost[s].sum())}
    out.update({"why": why, "at_min": int(round(tin[i] * 60)), "at_net": float(before[i]),
                "before": part(a), "after": part(b),
                "n_sessions": int(len(np.unique(sid))), "sessions_over": int(len(np.unique(sid[over])))})
    return out


def _pause_check(H, rr, ts) -> dict:
    """2.72: efter en förlorad pott på mer än BIG_LOSS_BB bb ska du pausa 15 minuter (2.86; tidigare 2). Handhistoriken har bara starttider,
    så pausen räknas ungefärligt: nästa hand (alla bord) startade minst PAUSE_SEC + HAND_SEC sekunder efter förlusthanden."""
    net = H["net"][rr].astype(float)
    big = np.flatnonzero(net <= -BIG_LOSS_BB)
    taken = 0
    ts = np.asarray(ts)
    for i in big:
        # 2.87 (R5-01): räknas från förlusthandens slut (+HAND_SEC), och händer som redan pågick på andra bord får
        # spelas klart (ytterligare HAND_SEC). Pausen är bruten om en ny hand startar innan pausen är slut.
        lo, hi = ts[i] + 2 * HAND_SEC, ts[i] + HAND_SEC + PAUSE_SEC
        if not np.any((ts > lo) & (ts < hi)):
            taken += 1
    return {"big_losses": int(len(big)), "pauses_taken": int(taken)}


def _fe_coef(y, X, c):
    """Linjär regression inom pass (fixed effects: varje pass jämförs med sig självt) med kluster-medelfel."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    _, inv = np.unique(c, return_inverse=True)
    k = inv.max() + 1
    cnt = np.bincount(inv, minlength=k).astype(float)
    def dm(v):
        return v - (np.bincount(inv, weights=v, minlength=k) / cnt)[inv]
    yd = dm(y)
    Xd = np.column_stack([dm(X[:, j]) for j in range(X.shape[1])])
    p = X.shape[1]
    active = np.flatnonzero(np.linalg.norm(Xd, axis=0) > 1e-10)
    beta, se = np.full(p, np.nan), np.full(p, np.nan)
    if not len(active) or k < 2:
        return beta.tolist(), se.tolist()
    A = Xd[:, active]
    # A coefficient is identified only if every null-space vector is zero there.
    # Never attribute a time effect to "back" by arbitrarily dropping a collinear control.
    _, singular, vh = np.linalg.svd(A, full_matrices=A.shape[0] < A.shape[1])
    tol = max(A.shape) * np.finfo(float).eps * singular[0]
    rank = int((singular > tol).sum())
    null = vh[rank:]
    identifiable = np.ones(len(active), bool) if not len(null) else np.linalg.norm(null, axis=0) < 1e-8
    inv_x = np.linalg.pinv(A.T @ A)
    b = np.linalg.lstsq(A, yd, rcond=None)[0]
    e = yd - A @ b
    S = np.column_stack([np.bincount(inv, weights=A[:, j] * e, minlength=k) for j in range(A.shape[1])])
    V = inv_x @ (S.T @ S) @ inv_x * (k / (k - 1))
    beta[active[identifiable]] = b[identifiable]
    se[active[identifiable]] = np.sqrt(np.maximum(np.diag(V), 0))[identifiable]
    return beta.tolist(), se.tolist()


def down_table(st, rules_doc, down_bb: float = DOWN_BB) -> dict:
    """Spelar du sämre när du ligger back i passet? Jämför varje pass med sig självt (fixed effects) och tar bort
    effekten av tiden, så att "back" inte bara betyder "sent i passet"."""
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None or len(st.rows) < 2 * MIN_HANDS:
        return {}
    H = ft.H
    r, sess, t_in = hand_session_info(st)
    if sess.max() + 1 < 10:
        return {}  # för få pass för att jämföra varje pass med sig självt
    before = _before_net(H, r, sess)
    dv = _vpip_dev(H, r)
    cost, brk = _breaks(st, rules_doc, r)
    ev = H["ev"][r].astype(float)
    back = before <= -down_bb
    plus = before >= down_bb
    rows = []
    for name, m in (("Back mer än %g bb" % down_bb, back), ("Mellan", ~back & ~plus), ("Plus mer än %g bb" % down_bb, plus)):
        k = int(m.sum())
        if not k:
            rows.append({"label": name, "hands": 0})
            continue
        vm, vse = _cluster_mean_se(dv[m], sess[m])
        em, ese = _cluster_mean_se(ev[m], sess[m])
        rows.append({"label": name, "hands": k, "share": 100.0 * k / len(r), "vdev": 100.0 * vm,
                     "brk100": 100.0 * float(brk[m].mean()), "cost100": 100.0 * float(cost[m].mean()),
                     "ev100": 100.0 * em, "ev_se": 100.0 * ese, "hours": float(t_in[m].mean())})
    # tiden räknas bort med halvtimmesblock (inte en rak linje – annars får "back" äran för tidseffekten)
    blk = np.minimum((t_in * 2).astype(int), 8)
    D = np.column_stack([(blk == k).astype(float) for k in range(1, 9)])
    X = np.column_stack([back.astype(float), plus.astype(float), D])
    bv, sv = _fe_coef(dv * 100.0, X, sess)
    bb_, sb_ = _fe_coef(brk * 100.0, X, sess)
    hv, hsv = _fe_coef(dv * 100.0, t_in[:, None], sess)
    hb, hsb = _fe_coef(brk * 100.0, t_in[:, None], sess)
    # 50 händer efter en förlorad pott på mer än 100 bb (samma pass)
    net = H["net"][r].astype(float)
    big = np.flatnonzero(net <= -100.0)
    win = np.zeros(len(r), bool)
    for i in big:
        j = slice(i + 1, i + 51)
        win[j] = sess[j] == sess[i]
    tb, tsb = _fe_coef(brk * 100.0, np.column_stack([win.astype(float), D]), sess)
    eff = {"vpip_back": bv[0], "vpip_back_se": sv[0], "vpip_plus": bv[1], "vpip_hour": hv[0], "vpip_hour_se": hsv[0],
           "brk_back": bb_[0], "brk_back_se": sb_[0], "brk_plus": bb_[1], "brk_hour": hb[0], "brk_hour_se": hsb[0],
           "brk_after_loss": tb[0], "brk_after_loss_se": tsb[0], "after_loss_hands": int(win.sum())}
    hours_eq = (bv[0] / hv[0]) if hv[0] and hv[0] > 0 and np.isfinite(bv[0]) and bv[0] > 0 else None
    sig = bool(np.isfinite(sv[0]) and bv[0] - 1.96 * sv[0] > 0)
    hour_sig = bool(np.isfinite(hsv[0]) and hv[0] - 1.96 * hsv[0] > 0)
    loss_sig = bool(np.isfinite(tsb[0]) and tb[0] - 1.96 * tsb[0] > 0)
    return {"rows": rows, "eff": eff, "hours_eq": hours_eq, "significant": sig, "hour_sig": hour_sig, "loss_sig": loss_sig,
            "estimable": bool(np.isfinite(bv[0]) and np.isfinite(sv[0])), "down_bb": down_bb,
            "hands": int(len(r)), "sessions": int(sess.max() + 1)}
