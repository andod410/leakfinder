"""Trolig förbättring – det som troligast höjer din bb/100, även när det inte är bevisat.

"Bekräftat" kräver bevis som håller när hundratals saker prövas samtidigt. Det skyddar mot
falska läckor, men är för strängt för frågan "vad bör jag göra vid bordet?". Där räcker det att
väga sannolikheten att en fold är bättre mot vad det kostar om man har fel.

Här prövas bara starthandsbeslut, där jämförelsen med fold är exakt (en fold preflop kostar det
du redan lagt i potten). Kandidaterna är bestämda i förväg, inte utvalda efter hur de ser ut:

* antal nöt-egenskaper × position, och × "utanför blindarna" / "blindarna",
* rena rundowns efter lägsta kort,
* öppningsguidens rutor (position × kombination av nöt-egenskaper),
* range-gränser som inte bekräftats strikt (testet i den andra halvan av spelpassen).

Varje kandidat prövas utan att samma händer används två gånger: den väljs ut i ena halvan av dina
spelpass (förlorar den mot fold där?) och mäts i den andra halvan (och tvärtom). Bland alla
kandidater väljs sedan de som klarar Benjamini–Hochberg med en falskupptäcktsgrad på Q_FDR
(20 %): i snitt är högst var femte visad rad fel, och finns det inga verkliga förluster visas
oftast ingenting. "Säkerhet" = 1 − q-värdet. Väntad vinst räknas på den halva som inte användes
för att välja ut raden, så att den inte blir uppblåst av urvalet.
"""
from __future__ import annotations

import math

import numpy as np

from .rundowns import FIRST_SPOTS, GROUPS, group_of
from .statlib import BIG_WIN_BB, MIN_BIG_WINS, bootstrap_t_p, cluster_se

Q_FDR = 0.20   # högst så stor andel av de visade raderna väntas vara fel
N_MIN = 150
BLINDS = ("SB", "BB")
OUTSIDE = "utanför blindarna"


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


TESTED: list = []   # antal prövade kandidater som inte gick vidare (räknas med i falskupptäcktskontrollen)


def _cand(x, c, hands: int):
    """Välj i ena halvan av spelpassen, mät i den andra (båda hållen). Ingen förhandsgallring på hela
    urvalet – då hade mäthalvan redan varit "tittad på". p-värdet = 2 × det minsta av de två hållen
    (Bonferroni över hållen). Snittet = medel av mäthalvorna för de håll där kandidaten valdes ut, så att
    valet av det bästa hållet inte blåser upp det. Returnerar None om kandidaten inte valdes ut i något
    håll (räknas då ändå som prövad)."""
    x = np.asarray(x, dtype=float)
    c = np.asarray(c, dtype=np.int64)
    n = len(x)
    if n < N_MIN:
        return None
    half = (c >> 7) & 1
    picks = []
    for disc in (0, 1):
        md, mc = half == disc, half != disc
        if md.sum() < N_MIN // 2 or mc.sum() < N_MIN // 2 or float(x[md].mean()) >= 0:
            continue
        xc, cc = x[mc], c[mc]
        m_c = float(xc.mean())
        if m_c < 0 and int((xc > BIG_WIN_BB).sum()) < MIN_BIG_WINS:
            continue  # för få stora vinster för att en förlust ska gå att bedöma
        se = cluster_se(xc, cc)
        if not np.isfinite(se) or se <= 0:
            continue
        # ensidigt p-värde i mäthalvan med kluster-bootstrap-t (pokerresultat är sneda, så en
        # normalfördelning skulle ge för små p-värden)
        pv = _phi(m_c / se)
        if pv < 0.25:
            import zlib
            pv = float(bootstrap_t_p(xc, cc, reps=1500, seed=zlib.crc32(f"{n}|{m_c:.6f}".encode())))
        picks.append((pv, m_c, se, int(mc.sum())))
    if not picks:
        TESTED.append(1)
        return None
    pv = min(p[0] for p in picks)
    m_c = float(np.mean([p[1] for p in picks]))
    se = float(np.sqrt(np.mean([p[2] ** 2 for p in picks]) / len(picks)))
    n_c = sum(p[3] for p in picks)
    return {"n": int(n), "n_conf": n_c, "mean": m_c, "lo": m_c - 1.96 * se, "hi": m_c + 1.96 * se,
            "p_raw": min(1.0, 2 * pv), "gain100": -m_c * n / hands * 100.0, "total": float(np.sum(x))}


def _bh_q(pvals: list, extra: int = 0) -> list:
    """Benjamini–Hochberg-justerade p-värden (q-värden). extra = prövade kandidater som inte gick vidare
    (räknas med i antalet tester, med p = 1)."""
    k = len(pvals)
    pvals = list(pvals) + [1.0] * extra
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [1.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        q[i] = prev
    return q[:k]


def _first(pre):
    m = np.flatnonzero(pre.is_spot(*FIRST_SPOTS))
    if not len(m):
        return m
    _, first = np.unique(pre.hidx[m], return_index=True)
    return m[np.sort(first)]


def likely_improvements(st, ranges=None, confirmed_ids=()) -> list:
    pre = st.decisions.pre
    if pre.ft is None or not len(pre) or not st.hands:
        return []
    ft, H, hands = pre.ft, pre.ft.H, st.hands
    TESTED.clear()
    out = []
    r = _first(pre)
    if len(r):
        hx = pre.hidx[r]
        delta, clu, pos = pre.delta[r], pre.clu[r], pre.pos[r]
        played = ~np.isnan(delta)
        nut = H["nut"][hx].astype(int)
        blind_codes = [ft.codes("pos")[b] for b in BLINDS if b in ft.codes("pos")]
        is_blind = np.isin(pos, blind_codes)
        # nöt-egenskaper × position och × grupp av positioner
        for code in sorted({int(x) for x in np.unique(nut) if x >= 0}):
            lab = ft.label("nut", code)
            groups = [(ft.label("pos", int(p)), [ft.label("pos", int(p))], pos == p) for p in np.unique(pos)]
            groups += [(OUTSIDE, None, ~is_blind), ("blindarna", list(BLINDS), is_blind)]
            for gname, plist, gm in groups:
                mk = (nut == code) & gm & played
                c = _cand(delta[mk], clu[mk], hands)
                if c:
                    plist = plist or sorted({ft.label("pos", int(p)) for p in np.unique(pos[(nut == code) & gm])})
                    rule = {"id": f"nut|{gname}|{lab}", "type": "nut", "positions": plist, "nut": lab,
                            "pos": gname, "cost": c["mean"]}
                    out.append({**c, "kind": "nut", "group": gname, "members": plist,
                                "title": f"{gname[0].upper() + gname[1:]}: folda händer med {lab}",
                                "rule": rule})
        # rena rundowns
        low = H["rdlow"][hx].astype(int)
        pure = (low >= 0) & ~(H["hp"][hx] | H["sa"][hx])
        grp = np.array([group_of(int(x)) if x >= 0 else "" for x in low], dtype=object)
        for g in GROUPS:
            mk = pure & (grp == g) & played
            c = _cand(delta[mk], clu[mk], hands)
            if c:
                out.append({**c, "kind": "rundown", "title": f"Folda rena rundowns med lägsta kort {g}",
                            "rule": {"id": f"rundown|{g}", "type": "rundown", "groups": [g], "cost": c["mean"]}})
    # öppningsguidens rutor (öppningar när det foldats till dig)
    from .cards import nut_combo_label
    m = np.flatnonzero(pre.is_spot("rfi") & (pre.kind == ft.code("kind", "raise")) & ~np.isnan(pre.delta))
    if len(m):
        hx = pre.hidx[m]
        bits = H["hp"][hx].astype(np.int64) * 4 + H["sa"][hx] * 2 + H["rd"][hx]
        for p in np.unique(pre.pos[m]):
            pl = ft.label("pos", int(p))
            if pl in BLINDS:
                continue
            for b in range(8):
                mk = (pre.pos[m] == p) & (bits == b)
                c = _cand(pre.delta[m][mk], pre.clu[m][mk], hands)
                if c:
                    combo = nut_combo_label((bool(b & 4), bool(b & 2), bool(b & 1)))
                    # 2.87 (R3-06): "bara" – regeln gäller händer där kombinationen är enda styrkan, inte t.ex. suited ess
                    # tillsammans med högt par eller rundown
                    what = "händer utan nöt-egenskaper" if combo == "ingen" else f"händer där {combo} är enda styrkan"
                    out.append({**c, "kind": "combo", "title": f"{pl}: öppna inte {what}", "pos": pl, "combo": combo,
                                "rule": {"id": f"combo|rfi|{pl}|{combo}", "type": "combo", "spot": "rfi", "pos": pl,
                                         "combo": combo, "cost": c["mean"]}})
    # range-gränser som inte klarade det strikta kravet
    for rg in ranges or []:
        t = rg.get("test") or {}
        if rg["verdict"]["kind"] != "unclear" or t.get("p") is None or t.get("mean") is None or t["mean"] >= 0:
            continue
        if t["n"] < N_MIN or rg.get("score_thr") is None:
            continue
        if t.get("marg_mean") is not None and t["marg_mean"] >= 0:
            continue  # händerna närmast gränsen har inte förlorat – gränsen sitter för snävt
        out.append({"n": t["n"], "mean": t["mean"], "lo": None, "hi": None, "p_raw": float(t["p"]),
                    "gain100": -t["mean"] * t["n"] / hands * 100.0, "total": t["mean"] * t["n"], "kind": "cutoff",
                    "title": f"{rg['pos']}: spela bara topp {rg['cutoff_pct']:.0f} % ({rg['name'][0].lower() + rg['name'][1:] if rg['name'][1:2].islower() else rg['name']})"
                             + (" – utom höga rundowns" if rg["spot"] in ("mot_3bet_oop", "mot_3bet_ip") else ""),
                    "rule": {"id": f"cut|{rg['spot']}|{rg['pos']}", "type": "cutoff", "spot": rg["spot"], "pos": rg["pos"],
                             "thr": rg["score_thr"], "weights": list(rg["weights"].values()), "cut_pct": rg["cutoff_pct"],
                             "num_cards": rg.get("num_cards", 6), "cost": t["mean"]}})
    # falskupptäcktskontroll över alla kandidater som prövats
    qs = _bh_q([o["p_raw"] for o in out], extra=len(TESTED))
    for o, q in zip(out, qs):
        o["q"] = q
        o["p"] = 1.0 - q
    out = [o for o in out if o["q"] <= Q_FDR and o["rule"]["id"] not in set(confirmed_ids)]
    # samma händer ska inte stå flera gånger: en grupp av positioner ersätter sina egna positioner,
    # och "0 nöt-egenskaper" för en position ersätter öppningsguidens "ingen" för samma position
    pooled = {(o["rule"]["nut"], p) for o in out if o["kind"] == "nut" and o["group"] in (OUTSIDE, "blindarna")
              for p in o["members"]}
    zero = {p for o in out if o["kind"] == "nut" and o["rule"]["nut"].startswith("0 ") for p in o["members"]}
    keep = []
    for o in out:
        if o["kind"] == "nut" and o["group"] not in (OUTSIDE, "blindarna") and (o["rule"]["nut"], o["group"]) in pooled:
            continue
        if o["kind"] == "combo" and o["combo"] == "ingen" and o["pos"] in zero:
            continue
        keep.append(o)
    keep.sort(key=lambda o: -o["gain100"])
    for o in keep:
        o["rule"].update(level="trolig", title=o["title"],
                         why=(f"Har gett {o['mean']:+.2f} bb per hand jämfört med fold i den halva av spelpassen som inte "
                              f"användes för att välja ut den ({o['n']} händer totalt). Säkerhet ca {100 * o['p']:.0f} % – inte bevisat."))
    return keep[:12]


def covered(o: dict, confirmed: list) -> bool:
    """Täcks förbättringen redan av en bekräftad regel (samma händer)?"""
    r = o["rule"]
    for c in confirmed:
        if c["id"] == r["id"]:
            return True
        if r["type"] == "rundown" and c["type"] == "rundown" and set(r["groups"]) <= set(c["groups"]):
            return True
    if r["type"] == "nut":
        same_spots = lambda c: (tuple(c.get("spots") or ()) == tuple(r.get("spots") or ()))
        conf_pos = {p for c in confirmed if c["type"] == "nut" and c["nut"] == r["nut"] and same_spots(c)
                    for p in (c.get("positions") or [c["pos"]])}
        if set(r["positions"]) <= conf_pos:
            return True
    if r["type"] == "combo":
        if any(c["type"] == "combo" and c["pos"] == r["pos"] and c["combo"] == r["combo"] for c in confirmed):
            return True
        if r["combo"] == "ingen" and any(c["type"] == "nut" and c["nut"].startswith("0 ") and not c.get("spots")
                                         and r["pos"] in (c.get("positions") or [c["pos"]]) for c in confirmed):
            return True
    return False
