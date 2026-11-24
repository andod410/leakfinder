"""Nya framåthypoteser (2.75), frysta 2026-11-15.

Tre hypoteser från analysen 2026-11-15 prövas BARA på händer spelade efter frysdatum. De är inte regler:
de räknas aldrig som regelbrott, ändrar inte facit i träningen och påverkar inte de frysta reglerna från
2026-11-13 (deras fingeravtryck är oförändrat). Definitionerna nedan är frysta – ändras något av dem ändras
fingeravtrycket (HYP_HASH), och resultat före och efter ändringen får inte läggas ihop.

* H1 BTN: öppna bara topp 30 %. Mäts: dina BTN-öppningar (foldat till dig) med handstyrka sämre än topp
  30 % jämfört med fold. Hypotesen håller om de förlorar mot fold.
* H2 SB/BB: folda 0 nöt-egenskaper mot en öppning i stället för att syna. Mäts: syn i SB/BB mot en öppning
  med 0 nöt-egenskaper jämfört med fold.
* H3 Rundown utan suited ess: syna i stället för att 3-betta. Mäts: 3-bets mot en öppning (alla positioner)
  med rundown och utan suited ess jämfört med fold. Synen med samma händer visas som jämförelse, men en
  jämförelse mellan två handlingar du själv valt kan inte bekräfta något (urval) – den är bara beskrivande.

Handstyrkan i H1 är fryst: vikterna i HAND_WEIGHTS och percentilen mot 20 000 slumpade händer (seed 7) –
samma poäng som träningens reglage använder utan sparade regler.

Kriterier (samma som framåttestet för reglerna): minst 100 händer och 20 spelpass, 95 %-intervall med
korrigering för tre hypoteser under noll och bootstrap. Läses tidigast vid 100 händer – innan dess "för få".
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime

import numpy as np

HYP_DATE = "2026-11-15"
HAND_WEIGHTS = [-0.296, 0.702, 0.708, 2.414, 0.012, 0.72, 0.658, -1.011, -1.212, 0.356, -0.45, 0.281]
BTN_TOP = 30.0
MIN_N = 100
MIN_CLU = 20

HYPOTHESES = [
    {"id": "H1", "title": "BTN: öppna bara topp 30 %",
     "measure": "BTN-öppningar sämre än topp 30 % jämfört med fold",
     "spots": ["rfi"], "pos": ["BTN"], "kind": "raise", "filter": f"pct>{BTN_TOP:g}"},
    {"id": "H2", "title": "SB/BB: folda 0 nöt-egenskaper mot en öppning i stället för att syna",
     "measure": "syn i SB/BB med 0 nöt-egenskaper jämfört med fold",
     "spots": ["sb_mot_hojning", "bb_mot_hojning"], "pos": ["SB", "BB"], "kind": "call", "filter": "nut=0"},
    {"id": "H3", "title": "Rundown utan suited ess: syna i stället för att 3-betta",
     "measure": "3-bet med rundown utan suited ess jämfört med fold",
     "spots": ["mot_hojning", "sb_mot_hojning", "bb_mot_hojning"], "pos": None, "kind": "raise",
     "filter": "rd=1,sa=0", "compare_kind": "call"},
]


def hyp_hash() -> str:
    spec = {"date": HYP_DATE, "w": HAND_WEIGHTS, "top": BTN_TOP, "h": HYPOTHESES, "min": [MIN_N, MIN_CLU]}
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


HYP_HASH = hyp_hash()


def hyp_ts() -> int:
    from .facts import ts_of
    return ts_of(datetime.strptime(HYP_DATE, "%Y-%m-%d"))


_DIST: dict = {}


def _random_scores(n_cards: int) -> np.ndarray:
    if n_cards not in _DIST:
        from .practice import DECK
        from .ranges import hand_features
        rnd = random.Random(7)
        w = np.array(HAND_WEIGHTS)
        _DIST[n_cards] = np.sort([float(hand_features(rnd.sample(DECK, n_cards)) @ w) for _ in range(20000)])
    return _DIST[n_cards]


def hand_pct(feats: np.ndarray, n_cards: int = 6) -> np.ndarray:
    """Percentil (0 = bäst) för faktatabellens egenskaper, mot slumpade händer."""
    X = feats.astype(np.float64)
    if len(X):
        X[:, 8] /= 5.0
    s = X @ np.array(HAND_WEIGHTS)
    arr = _random_scores(n_cards)
    return 100.0 * (1.0 - np.searchsorted(arr, s) / len(arr))


def _cell(x, c, families):
    from .fatigue import _cluster_mean_se
    from .holdout import _verdict
    n = len(x)
    mean, se = _cluster_mean_se(x, c) if n >= 2 else (float("nan"), float("nan"))
    nc = int(len(np.unique(c))) if n else 0
    v = "för få" if n < MIN_N or nc < MIN_CLU else _verdict(mean, se, n, True, families, nc)
    if v == "håller":
        from .statlib import bootstrap_t_p
        if bootstrap_t_p(x, c) > 0.05 / families:
            v = "osäkert"
    return {"n": n, "clusters": nc, "mean": float(mean) if np.isfinite(mean) else None,
            "se": float(se) if np.isfinite(se) else None, "verdict": v}


def hypotheses_test(st) -> dict:
    pre = getattr(getattr(st, "decisions", None), "pre", None)
    if pre is None or pre.ft is None or not len(pre):
        return {}
    from .practice import first_rows
    ft = pre.ft
    H = ft.H
    new = H["ts"][pre.hidx] >= hyp_ts()
    first = first_rows(pre) & ~np.isnan(pre.delta) & new
    hx = pre.hidx
    nut_lbl = np.array([ft.label("nut", int(c)) if c >= 0 else "" for c in range(int(H["nut"].max()) + 1)] or [""])
    nut = np.where(H["nut"][hx] >= 0, nut_lbl[np.clip(H["nut"][hx], 0, None)], "")
    sa = H["sa"][hx].astype(bool)
    rd = H["rd"][hx].astype(bool)
    n_cards = int((H["hole"][hx[0]] >= 0).sum()) if len(hx) else 6
    pos_lbl = np.array([ft.label("pos", int(c)) for c in range(int(pre.pos.max()) + 1)])
    pos = pos_lbl[pre.pos]
    out = []
    fam = len(HYPOTHESES)
    from .seqtest import cohorts, next_look, pass_order, sequential
    allr = np.flatnonzero(H["ts"] >= hyp_ts())
    coh = cohorts(H["ts"][allr], H["clu"][allr])
    n_pass = len(pass_order(H["ts"][allr], H["clu"][allr]))
    pct = None
    for h in HYPOTHESES:
        base = first & pre.is_spot(*h["spots"])
        if h["pos"]:
            base &= np.isin(pos, h["pos"])
        if h["filter"].startswith("pct>"):
            if pct is None:
                pct = np.full(len(pre), np.nan)
                idx = np.flatnonzero(first)
                pct[idx] = hand_pct(H["feats"][hx[idx]], n_cards)
            base &= pct > BTN_TOP
        elif h["filter"] == "nut=0":
            base &= nut == "0 nöt-egenskaper"
        elif h["filter"] == "rd=1,sa=0":
            base &= rd & ~sa
        m = base & (pre.kind == ft.code("kind", h["kind"]))
        # 2.81: fasta avläsningar (20/40/80 pass efter startdatum), se seqtest.py
        res = sequential(lambda cm, f, m=m: _cell(pre.delta[m & cm], pre.clu[m & cm], f), pre.clu, coh, fam)
        if not res.get("look"):
            res = {**_cell(pre.delta[m], pre.clu[m], fam), "look": 0}
            res["verdict"] = "för få"
        r = {"id": h["id"], "title": h["title"], "measure": h["measure"], **res}
        if h.get("compare_kind"):
            mc = base & (pre.kind == ft.code("kind", h["compare_kind"]))
            c = _cell(pre.delta[mc], pre.clu[mc], fam)
            r["compare"] = {"kind": h["compare_kind"], "n": c["n"], "mean": c["mean"], "se": c["se"],
                            "note": "beskrivande – en jämförelse mellan två handlingar du valt kan inte bekräfta något"}
        out.append(r)
    return {"date": HYP_DATE, "hash": HYP_HASH, "hands_after": int(len(np.unique(hx[new]))), "rules": out,
            "need": f"minst {MIN_N} händer och {MIN_CLU} spelpass per hypotes efter {HYP_DATE}",
            "note": "hypoteser – räknas inte som regelbrott och ändrar inte de frysta reglerna",
            "passes_after": n_pass, "next_look": next_look(n_pass), "looks": [20, 40, 80]}
