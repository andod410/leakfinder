"""Positionsläckor (2.75): var kostar ditt första beslut preflop mest, position för position?

För varje position delas ditt första beslut preflop (öppna, syna, 3-betta, limpa …) upp i grupper:
situation × handling × nöt-egenskaper. Varje grupp jämförs med att folda just då (delta = exakt
resultat mot fold, all-in EV, efter rake; i SB/BB räknas blinden du redan lagt som förlorad vid fold).

* "Totalt mot fold" = summan över gruppens händer. Negativt = du hade tjänat på att folda dem.
* bb/100 (totalt) = gruppens summa delat med alla händer i urvalet × 100 – hur mycket gruppen drar
  ner din totala vinst. bb/100 (i positionen) = samma summa delat med händerna i positionen.
* "säkert minus" = hela 95 %-intervallet (felmarginal per spelpass) ligger under noll.
  "bekräftad förlust" kräver dessutom att det klarar korrigering för alla grupper som prövas
  (samma test som resten av programmet, inklusive svansvakten). Säkert minus utan bekräftelse är
  en stark kandidat, inte ett bevis – många grupper prövas samtidigt.
* Bara grupper med minst MIN_N spelade händer bedöms. Folds visas inte som grupper (de är facit).
"""
from __future__ import annotations

import numpy as np

from .rundowns import FIRST_SPOTS
from .statlib import ci_cell, cluster_se

POS_ORDER = ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
MIN_N = 30
TOP = 6


def position_leaks(st) -> dict:
    pre = st.decisions.pre
    if pre.ft is None or not len(pre):
        return {}
    from .decisions import ACTION_VERB, SPOT_NAMES
    ft = pre.ft
    H = ft.H
    m = np.flatnonzero(pre.is_spot(*FIRST_SPOTS))
    if not len(m):
        return {}
    _, first = np.unique(pre.hidx[m], return_index=True)   # första beslutet per hand
    r = m[np.sort(first)]
    hx = pre.hidx[r]
    nut = H["nut"][hx].astype(int)
    delta, clu, pos, spot, kind = pre.delta[r], pre.clu[r], pre.pos[r], pre.spot[r], pre.kind[r]
    played = ~np.isnan(delta)
    total_hands = max(int(getattr(st, "hands", 0) or 0), len(r))

    # alla grupper med minst MIN_N spelade – Bonferroni över dem
    keys = {}
    for i in np.flatnonzero(played):
        keys.setdefault((int(pos[i]), int(spot[i]), int(kind[i]), int(nut[i])), []).append(i)
    big = {k: np.array(v) for k, v in keys.items() if len(v) >= MIN_N}
    m_tests = max(1, len(big))

    order = {p: i for i, p in enumerate(POS_ORDER)}
    pos_codes = sorted({int(p) for p in np.unique(pos)}, key=lambda c: (order.get(ft.label("pos", c), 99), ft.label("pos", c)))
    out = []
    for p in pos_codes:
        pm = pos == p
        dealt = int(pm.sum())
        tot = float(np.nansum(delta[pm & played]))
        groups = []
        for (pp, sp, kd, nu), idx in big.items():
            if pp != p:
                continue
            x, c = delta[idx], clu[idx]
            cell = ci_cell(x, c, min_n=MIN_N, m_tests=m_tests)
            se = cluster_se(x, c)
            mean = float(x.mean())
            s_name, k_name = ft.label("spot", sp), ft.label("kind", kd)
            gsum = float(x.sum())
            groups.append({
                "label": f"{ACTION_VERB.get((s_name, k_name), k_name).capitalize()} {SPOT_NAMES.get(s_name, s_name)}",
                "spot": s_name, "action": k_name, "nut": ft.label("nut", nu) if nu >= 0 else "okänt",
                "n": int(len(idx)), "mean": mean, "lo": mean - 1.96 * se, "hi": mean + 1.96 * se,
                "total": gsum, "bb100_total": 100.0 * gsum / total_hands, "bb100_pos": 100.0 * gsum / dealt if dealt else 0.0,
                "sure_minus": bool(np.isfinite(se) and mean + 1.96 * se < 0),
                "confirmed": cell.get("verdict") == "förlorar", "verdict": cell.get("verdict")})
        losing = sorted((g for g in groups if g["total"] < 0), key=lambda g: g["total"])
        out.append({"pos": ft.label("pos", p), "dealt": dealt, "played": int((pm & played).sum()),
                    "total": tot, "bb100_total": 100.0 * tot / total_hands, "bb100_pos": 100.0 * tot / dealt if dealt else 0.0,
                    "sure": [g for g in losing if g["sure_minus"]], "largest": losing[:TOP],
                    "sure_cost_bb100": 100.0 * sum(g["total"] for g in losing if g["sure_minus"]) / total_hands})
    worst = sorted(out, key=lambda x: x["sure_cost_bb100"])
    return {"positions": out, "hands": total_hands, "m_tests": m_tests, "min_n": MIN_N,
            "biggest": worst[0]["pos"] if worst and worst[0]["sure_cost_bb100"] < 0 else None}
