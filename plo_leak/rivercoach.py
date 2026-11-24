"""River-coach: bästa beslutet på river, hand för hand, mot poolens verkliga ranges.

Bygger på river-modellen (river.py) men med river-situationerna som sparas i faktatabellen, så att
den kan köras i programmet utan att läsa om händerna.

För varje river-beslut heads-up räknas:
* "slår dig" mot slumpade händer (styrkan på bordet, dina blockers inräknade),
* vinstchansen mot HANS LINJE (poolens visade händer i samma situation: roll, betstorlek, vem som
  var aggressor på turn, brädtyp och SPR, med grövre nivåer när det finns för få händer),
* EV för varje alternativ i bb, med rake: mot en bet syna/folda, i position efter check
  check/liten/medel/pottstor/överbet.

Modellen kontrolleras mot hur DINA händer faktiskt gick (på händer den inte lärt sig av). En del av
modellen som inte klarar kontrollen visas inte som råd, bara som "osäkert".
"""
from __future__ import annotations

import pickle

import numpy as np

from .river import (SIZE_BUCKETS, FeeModel, analyze_spots, component_ok, review_queue)

SIZE_SHORT = {name: short for (_, name), short in zip(SIZE_BUCKETS, ["liten", "medel", "pott", "överbet"])}


def _spots(ft, rows=None) -> list:
    R = ft.t.get("rsp")
    if R is None or "obj" not in R or not len(R["hidx"]):
        return []
    out = []
    allowed = None if rows is None else set(np.asarray(rows, dtype=int).tolist())
    for hi, o in zip(R["hidx"], R["obj"]):
        if allowed is not None and int(hi) not in allowed:
            continue
        try:
            out.append(pickle.loads(o))
        except Exception:
            continue
    return out


def _ev_call(det) -> float:
    """Syn mot fold i bb, med rake (vinstbeloppet efter rake ges av need = bet / (vinst + bet))."""
    bet, need, p = float(det["bet"]), float(det["need"]), float(det["p_win"])
    win_amt = bet / need - bet if need > 0 else 0.0
    return p * win_amt - (1 - p) * bet


def coach(st, hero: str) -> dict:
    """Kör river-modellen på alla sparade river-situationer. Returnerar en liten, sparbar struktur:
    beslut per hand-id, kontrollen och en sammanfattning."""
    ft = getattr(st, "ft", None)
    if ft is None:
        return {}
    rows = np.asarray(st.rows if st.rows is not None else np.arange(ft.n), dtype=int)
    spots = _spots(ft, rows)
    if len(spots) < 500:
        return {"too_few": len(spots)}
    H = ft.H
    fees = FeeModel().fit_arrays(H["pot"][rows], H["pot_fee"][rows], H["bb"][rows])
    total = int(len(st.rows)) if getattr(st, "rows", None) is not None else ft.n
    res = analyze_spots(spots, hero, fees, max(total, 1))
    calibrated = {"mot_bet": component_ok(res, "mot_bet"), "ip_efter_check": component_ok(res, "ip_efter_check")}
    ok = {k: False for k in calibrated}  # showdown selection is not counterfactual validation
    by_id = {}
    for d in res.decisions:
        det = d.detail
        e = {"kind": d.kind, "chosen": d.chosen, "best": d.best, "gain": round(float(d.gain), 2),
             "sure": False, "model_interval_positive": bool(d.gain_q05 > 0), "hb": round(float(det.get("hb", -1)), 3), "ok": ok[d.kind]}
        if d.kind == "mot_bet":
            e.update(p_win=round(float(det["p_win"]), 3), need=round(float(det["need"]), 3),
                     pot=round(float(det["pot"]), 1), bet=round(float(det["bet"]), 1),
                     ev_call=round(_ev_call(det), 2))
        else:
            e.update(ev={SIZE_SHORT.get(k, k): v for k, v in det["ev"].items()}, p_sd=round(float(det["p_sd"]), 3),
                     pot=round(float(det["pot"]), 1))
            e["chosen"] = SIZE_SHORT.get(d.chosen, d.chosen)
            e["best"] = SIZE_SHORT.get(d.best, d.best)
        by_id[d.id] = e
    cal = {k: {"n": v["n"], "pred": v["pred"], "actual": v["actual"], "ok": v["ok"]} for k, v in res.calibration.items()}
    finds = [{"kind": f["kind"], "sub": SIZE_SHORT.get(f["sub"], f["sub"]), "n": f["n"],
              "cost100": round(f["cost100"], 2), "cost100_cons": round(f["cost100_cons"], 2),
              "validated": False, "calibrated": f["validated"], "best": f["best_counts"]} for f in res.findings]
    queue = [{"id": d.id, "kind": d.kind, "chosen": SIZE_SHORT.get(d.chosen, d.chosen),
              "best": SIZE_SHORT.get(d.best, d.best), "gain": round(float(d.gain), 1)} for d in review_queue(res, 30)]
    return {"decisions": by_id, "ok": ok, "cal": cal, "findings": finds, "queue": queue,
            "n_spots": res.spots, "n_dec": len(res.decisions), "calibrated": calibrated,
            "validation": "hypotes – showdownurval, inte validerad på foldade händer", "bet_policy": BET_POLICY}


KIND_TEXT = {
    "river_fold": "Foldar mot river-bets där syn hade gett mer",
    "river_call": "Synar river-bets där fold hade gett mer",
    "ip_missad_bet": "Checkar bakom river där bet hade gett mer",
    "ip_onodig_bet": "Bettar river där check hade gett mer",
    "ip_fel_storlek": "Fel storlek på river-bet",
}
ACT = {"call": "syna", "fold": "folda", "check": "checka", "liten": "betta litet (~1/3)", "medel": "betta medel (~2/3)",
       "pott": "betta pott", "överbet": "överbetta"}
BET_POLICY = "bet/fold"   # 2.73: bets värderas som om du alltid foldar mot en check-raise (ingen syn/återhöjning räknas)


def line_text(e: dict) -> str:
    """En rad till sessionsfilen och uppspelningen."""
    if not e:
        return ""
    if not e.get("ok"):  # 2.77 (punkt 16): ingen rad när modellen inte klarar kontrollen – v3-skuggmodellen prövar ersättaren
        return ""
    sure = ""
    if e["kind"] == "mot_bet":
        verdict = "syna" if e["p_win"] > e["need"] else "folda"
        return (f"River-coach: slår dig {100 * e['hb']:.0f} % slumpat · vinstchans mot hans linje ≈{100 * e['p_win']:.0f} % · "
                f"behövs {100 * e['need']:.0f} % → **{verdict}** (syn mot fold {e['ev_call']:+.1f} bb){sure}")
    evs = " · ".join(f"{ACT.get(k, k).split(' (')[0]} {v:+.1f}" for k, v in sorted(e["ev"].items(), key=lambda kv: -kv[1]))
    return (f"River-coach: slår dig {100 * e['hb']:.0f} % slumpat · bäst: **{ACT.get(e['best'], e['best'])}** · "
            f"EV i bb: {evs}{sure}")


# ---------------------------------------------------------------- 2.79: i en egen process
def light_state(st):
    """Bara det coach() läser: radurvalet, pott/avgift/bb per hand och river-situationerna."""
    from types import SimpleNamespace
    ft = st.ft
    H = {k: ft.H[k] for k in ("pot", "pot_fee", "bb")}
    rsp = ft.t.get("rsp")
    t = {"rsp": {"hidx": rsp["hidx"], "obj": rsp["obj"]}} if rsp is not None and "obj" in rsp else {}
    return SimpleNamespace(ft=SimpleNamespace(n=ft.n, H=H, t=t), rows=st.rows)


def coach_worker(args):
    """Arbetsprocess: en ny process börjar alltid med samma slumpfrö i river.py (12345), som en ny körning av programmet."""
    import os
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(k, "1")
    light, hero = args
    try:
        return coach(light, hero)
    except Exception as e:
        return {"error": str(e)}
