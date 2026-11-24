"""3-bets mot en öppning: vilka händer du ska 3-betta och vilka du inte ska 3-betta.

Två regler prövas på dina egna händer (ditt första beslut mot en öppning: i position, i SB och i BB):

* "3-betta inte utan suited ess": dina 3-bets med händer utan suited ess jämförs med att folda
  (delta = exakt resultat mot fold). Regeln gäller när snittet är negativt även med felmarginalen
  (95 %, felmarginal per spelpass) och negativt i båda halvorna av spelpassen.
* "3-betta högt par + suited ess i stället för att syna": syn och 3-bet med samma händer jämförs.
  Regeln gäller när 3-bet är bättre än syn även med felmarginalen. Jämförelsen mellan två handlingar
  kan påverkas av urval (vilka av händerna du valde att 3-betta), därför räknas den som trolig och
  kostnaden per brott är den nedre gränsen för skillnaden, inte den uppmätta skillnaden.

Reglerna har typen "action": ett brott är en viss handling (bad_kind), inte att du spelade handen.
"""
from __future__ import annotations

import math

import numpy as np

SPOTS = ("mot_hojning", "bb_mot_hojning", "sb_mot_hojning")
MIN_N = 200


def _mean_se(x, c):
    from .fatigue import _cluster_mean_se
    return _cluster_mean_se(x, c)


def _base(pre):
    from .practice import first_rows
    H = pre.ft.H
    hx = pre.hidx
    first = first_rows(pre) & pre.is_spot(*SPOTS)
    raise_c, call_c = pre.ft.code("kind", "raise"), pre.ft.code("kind", "call")
    return H, hx, first, pre.kind == raise_c, pre.kind == call_c


def analyze(pre) -> dict:
    """Siffrorna bakom båda reglerna (visas även när reglerna inte är säkra)."""
    if pre is None or pre.ft is None or not len(pre):
        return {}
    H, hx, first, is_r, is_c = _base(pre)
    sa = H["sa"][hx].astype(bool)
    hp = H["hp"][hx].astype(bool)
    d = pre.delta
    clu = pre.clu
    out = {}
    m = first & is_r & ~sa & ~np.isnan(d)
    if m.sum() >= MIN_N:
        mean, se = _mean_se(d[m], clu[m])
        hv = (clu >> 7) & 1  # samma halvor av spelpassen som resten av programmet
        halves = [float(d[m & (hv == k)].mean()) if (m & (hv == k)).any() else float("nan") for k in (0, 1)]
        out["no_sa"] = {"n": int(m.sum()), "mean": mean, "se": se, "halves": halves,
                        "ok": bool(np.isfinite(se) and mean + 1.96 * se < 0 and all(h < 0 for h in halves))}
    g = first & hp & sa & ~np.isnan(d)
    mc, mr = g & is_c, g & is_r
    if mc.sum() >= MIN_N and mr.sum() >= MIN_N:
        c_mean, c_se = _mean_se(d[mc], clu[mc])
        r_mean, r_se = _mean_se(d[mr], clu[mr])
        raw_diff = r_mean - c_mean
        # jämför bara liknande händer: samma position, AA eller inte, och samma struktur (dubbelsuited …)
        diff, se, _ = strat_diff(pre, np.ones(len(pre), bool))
        hv = (clu >> 7) & 1
        hd = []
        for k in (0, 1):
            a_, b_ = mr & (hv == k), mc & (hv == k)
            hd.append(float(d[a_].mean() - d[b_].mean()) if a_.any() and b_.any() else float("nan"))
        out["hp_sa"] = {"n_call": int(mc.sum()), "n_raise": int(mr.sum()), "call": c_mean, "raise": r_mean,
                        "diff": diff, "raw_diff": raw_diff, "diff_lo": diff - 1.96 * se if np.isfinite(se) else float("nan"), "halves": hd,
                        "ok": bool(np.isfinite(se) and diff - 1.96 * se > 0 and all(h > 0 for h in hd))}
    out["flats"] = flat_table(pre)
    return out


def strat_diff(pre, rowmask) -> tuple:
    """3-bet minus syn med högt par + suited ess, jämfört inom grupper av liknande händer (position × AA eller
    inte × struktur), viktat efter gruppens storlek. Returnerar (skillnad, felmarginal, antal syner)."""
    from .subgroups import struct_codes
    H, hx, first, is_r, is_c = _base(pre)
    d = pre.delta
    g = first & H["hp"][hx].astype(bool) & H["sa"][hx].astype(bool) & ~np.isnan(d) & rowmask
    if g.sum() < 30:
        return float("nan"), float("nan"), int((g & is_c).sum())
    idx = np.flatnonzero(g)
    aa = (H["hole"][hx[idx]] >= 48).sum(axis=1) >= 2
    sc = struct_codes(H["feats"][hx[idx]])
    key = pre.pos[idx].astype(np.int64) * 100 + aa.astype(np.int64) * 10 + sc.astype(np.int64)
    W = D = V = 0.0
    for k in np.unique(key):
        mk = idx[key == k]
        c, r = mk[is_c[mk]], mk[is_r[mk]]
        if len(c) < 15 or len(r) < 15:
            continue
        mc, sc_ = _mean_se(d[c], pre.clu[c])
        mr, sr = _mean_se(d[r], pre.clu[r])
        if not (np.isfinite(sc_) and np.isfinite(sr)):
            continue
        w = min(len(c), len(r))
        W += w
        D += w * (mr - mc)
        V += w * w * (sc_ ** 2 + sr ** 2)
    if W == 0:
        return float("nan"), float("nan"), int((g & is_c).sum())
    return D / W, math.sqrt(V) / W, int((g & is_c).sum())


def flat_table(pre) -> list:
    """Syna eller 3-betta mot en öppning, per situation och position: vad har syn och 3-bet gett mot fold?
    Visar var "3-betta eller folda" troligen är bättre än att syna (syn nära noll efter rake)."""
    H, hx, first, is_r, is_c = _base(pre)
    d = pre.delta
    rows = []
    for sp in SPOTS:
        ms = first & pre.is_spot(sp) & ~np.isnan(d)
        for pc in np.unique(pre.pos[ms]):
            mp = ms & (pre.pos == pc)
            mc, mr = mp & is_c, mp & is_r
            if mc.sum() < MIN_N:
                continue
            c_mean, c_se = _mean_se(d[mc], pre.clu[mc])
            r_mean, r_se = _mean_se(d[mr], pre.clu[mr]) if mr.sum() >= 50 else (None, None)
            rows.append({"spot": sp, "pos": pre.label("pos", int(pc)), "n_call": int(mc.sum()), "n_raise": int(mr.sum()),
                         "flat_pct": 100.0 * mc.sum() / max(mp.sum(), 1), "call": c_mean, "call_se": c_se,
                         "raise": r_mean, "raise_se": r_se,
                         "flat_zero": bool(np.isfinite(c_se) and abs(c_mean) < 1.96 * c_se)})
    return rows


def threebet_rules(pre) -> list:
    A = analyze(pre)
    rules = []
    a = A.get("no_sa")
    if a and a["ok"]:
        rules.append({
            "id": "act|3bet_utan_sa", "type": "action", "spots": list(SPOTS), "cond": "no_sa", "bad_kind": "raise",
            "cmp": "fold", "cost": a["mean"], "level": "bekräftad",
            "title": "Mot en öppning: 3-betta inte utan suited ess (rundowns: syna i stället)",
            "why": (f"Dina 3-bets utan suited ess har gett {a['mean']:+.2f} bb per gång jämfört med att folda "
                    f"({a['n']} händer, minus även med felmarginalen och i båda halvorna av spelpassen). "
                    f"Syna eller folda i stället. Rundowns utan suited ess: syna hellre än folda (hypotes 2026-11-14: syn +0,76 ± 0,36 bb, "
                    f"3-bet −1,05 ± 1,19 bb mot fold).")})
    b = A.get("hp_sa")
    if b and b["ok"]:
        rules.append({
            "id": "act|3bet_hp_sa", "type": "action", "spots": list(SPOTS), "cond": "hp_sa", "bad_kind": "call",
            "cmp": "action", "cost": -max(b["diff_lo"], 0.0), "level": "trolig",
            "title": "Mot en öppning: 3-betta högt par + suited ess, syna inte",
            "why": (f"3-bet minus syn med samma sorts händer (samma position, AA eller inte, samma struktur): "
                    f"{b['diff']:+.2f} bb per hand. Kostnaden per syn räknas försiktigt som den nedre gränsen "
                    f"({b['diff_lo']:.2f} bb).")})
    return rules


def action_mask(r: dict, pre) -> np.ndarray:
    """Tillfällen för en action-regel: ditt första beslut i situationen när du spelade vidare (syn eller
    3-bet) med händer som regeln gäller."""
    H, hx, first, is_r, is_c = _base(pre)
    m = pre.is_spot(*(r.get("spots") or SPOTS)) & (is_r | is_c)
    if r.get("cond") == "no_sa":
        m &= ~H["sa"][hx].astype(bool)
    elif r.get("cond") == "hp_sa":
        m &= H["hp"][hx].astype(bool) & H["sa"][hx].astype(bool)
    else:
        return np.zeros(len(pre), bool)
    return m


VS3BET = ("mot_3bet_oop", "mot_3bet_ip")
MIN_EXEMPT = 100  # så många spelade händer krävs för att en undergrupp ska undantas
NUT0 = "0 nöt-egenskaper"


def vs3bet_nut_rule(pre) -> list:
    """Mot 3-bet efter din öppning: folda händer med 0 nöt-egenskaper (inget högt par, inget suited ess,
    ingen rundown).

    Korsvaliderat, så att regeln inte blir "bekräftad" på slump: spelpassen delas i två halvor. I den ena
    halvan väljs undantagen (undergrupper som gått plus mot fold, minst MIN_EXEMPT/2 händer); i den andra
    mäts resten mot fold. Båda riktningarna görs. Bekräftad = minus i båda halvorna med ca 90 % säkerhet
    var för sig (z < −1,28 i båda); trolig = ca 80 % i båda. Undantagen som
    visas och används väljs på alla händer (minst MIN_EXEMPT och plus)."""
    if pre is None or pre.ft is None or not len(pre):
        return []
    from .practice import first_rows
    from .subgroups import STRUCT, struct_codes
    H, hx = pre.ft.H, pre.hidx
    code = pre.ft.codes("nut").get(NUT0)
    if code is None:
        return []
    d = pre.delta
    base = first_rows(pre) & pre.is_spot(*VS3BET) & (H["nut"][hx] == code)
    played = base & ~np.isnan(d)
    if played.sum() < MIN_N:
        return []
    sc = struct_codes(H["feats"][hx])
    clu = np.asarray(pre.clu, dtype=np.int64)
    half = ((clu * 2654435761) >> 7) & 1  # spelpass → halva (stabil, oberoende av ordning)

    def exempt_in(mask, min_n):
        out = []
        for k in range(len(STRUCT)):
            mk = mask & (sc == k)
            if mk.sum() >= max(min_n, 30) and _mean_se(d[mk], clu[mk])[0] >= 0:
                out.append(k)
        return out

    est = []
    for sel_h in (0, 1):
        ex = exempt_in(played & (half == sel_h), MIN_EXEMPT // 2)
        test = played & (half != sel_h) & ~np.isin(sc, ex)
        if test.sum() < 50:
            return []
        est.append(_mean_se(d[test], clu[test]) + (int(test.sum()),))
    (m1, s1, n1), (m2, s2, n2) = est
    if not all(np.isfinite(x) for x in (m1, s1, m2, s2)):
        return []
    mean = (n1 * m1 + n2 * m2) / (n1 + n2)
    se = math.sqrt((n1 * s1) ** 2 + (n2 * s2) ** 2) / (n1 + n2)
    if mean >= 0:
        return []
    # de två mätningarna är korrelerade (undantagen i den ena halvan beror på samma data som mätningen i
    # den andra), så de vägs inte ihop till ett z-värde. I stället måste båda halvorna klara gränsen var för
    # sig. Simulerat på slumpdata (ingen verklig skillnad): bekräftad ca 2,5 %, trolig ca 6 %.
    z1, z2 = m1 / s1 if s1 > 0 else 0.0, m2 / s2 if s2 > 0 else 0.0
    level = "bekräftad" if max(z1, z2) < -1.2816 else ("trolig" if max(z1, z2) < -0.8416 else None)
    if level is None:
        return []
    subs, exempt = [], []
    for k, name in enumerate(STRUCT):
        mk = played & (sc == k)
        if mk.sum() < 30:
            continue
        m_ = _mean_se(d[mk], clu[mk])[0]
        subs.append({"name": name, "n": int(mk.sum()), "mean": float(m_)})
        if m_ >= 0 and mk.sum() >= MIN_EXEMPT:
            exempt.append(name)
    pos = sorted({pre.label("pos", int(p)) for p in np.unique(pre.pos[base])})
    ex = (" – utom " + ", ".join(exempt)) if exempt else ""
    return [{
        "id": "nut3b|mot 3-bet|0 nöt-egenskaper", "type": "nut", "spots": list(VS3BET), "positions": pos,
        "pos": "mot 3-bet", "nut": NUT0, "cost": float(mean), "level": level, "except": exempt or None,
        "sub": subs, "title": "Mot 3-bet efter din öppning: folda händer med 0 nöt-egenskaper" + ex,
        "why": (f"Korsvaliderat (undantag valda i ena halvan av spelpassen, mätt i den andra): syn eller 4-bet med "
                f"de här händerna har gett {mean:+.2f} ± {1.96 * se:.2f} bb per gång jämfört med att folda "
                f"({n1 + n2} händer). Händer med minst en nöt-egenskap (högt par, suited ess, rundown) går plus "
                f"mot 3-bet.")}]
