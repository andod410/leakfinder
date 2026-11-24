"""Var går gränsen mellan lönsamma och förlorande starthänder?

1. Varje hand får en poäng för handstyrka från enkla egenskaper (nöt-egenskaper,
   färgstruktur, par, sammanhängning, låga kort). Vikterna lärs från dina egna
   beslut jämfört med fold – korsvaliderat: en hand i halva A får alltid sin poäng
   från vikter som lärts på halva B och tvärtom, så modellen kan inte belöna sig själv.
2. I varje situation (t.ex. öppna från HJ) rangordnas alla delade händer från
   topp 0 % (bäst) till 100 %.
3. Resultatet jämfört med fold för händerna du spelade anpassas till en fallande
   kurva över percentilen (isoton regression – bättre händer kan inte göra sämre).
4. Gränsen = där kurvan korsar noll. Felmarginalen tas fram genom att dra om hela
   spelpass (alla bord, nytt pass efter 30 minuters paus) 300 gånger.

Viktigt: gränsen gäller de händer du själv valt att spela. Inom ett percentilband
spelar du ofta bara en del av händerna, troligen de bättre, så kurvan säger inget
säkert om händer du foldat.
"""
from __future__ import annotations

import zlib
from collections import Counter, defaultdict

import numpy as np

from .cards import _connectivity, nut_qualities
from .statlib import bootstrap_t_p

FEATURE_NAMES = [
    "högt par (JJ+)", "suited ess", "rundown 5+", "AA", "antal par", "antal färger med 2–3 kort",
    "4+ i samma färg", "trips", "sammanhängning", "antal höga kort (T+)", "antal låga kort (2–4)",
    "suited kung utan ess i färgen",
]
SPOTS = {  # situation -> (namn, vad "spela" betyder)
    "rfi": ("Öppna när det är foldat till dig", "öppnar"),
    "bb_mot_hojning": ("BB mot en öppning", "försvarar"),
    "sb_mot_hojning": ("SB mot en öppning", "spelar"),
    "mot_hojning": ("Mot en öppning (cold call / 3-bet)", "spelar"),
    "mot_3bet_ip": ("Mot en 3-bet i position", "fortsätter"),
    "mot_3bet_oop": ("Mot en 3-bet ur position", "fortsätter"),
}
MIN_PLAYED = 300
BOOT = 300
N_BINS = 20


def hand_features(hole) -> np.ndarray:
    suits = Counter(c[1] for c in hole)
    rc = Counter(c[0] for c in hole)
    hp, sa, rd = nut_qualities(hole)
    suited_king = any(c[0] == 13 and 2 <= suits[c[1]] <= 3 and (14, c[1]) not in hole for c in hole)
    return np.array([
        hp, sa, rd, rc.get(14, 0) == 2,
        sum(1 for n in rc.values() if n == 2),
        sum(1 for n in suits.values() if 2 <= n <= 3),
        max(suits.values()) >= 4,
        max(rc.values()) >= 3,
        _connectivity([c[0] for c in hole]) / 5.0,
        sum(1 for c in hole if c[0] >= 10),
        sum(1 for c in hole if c[0] <= 4),
        suited_king,
    ], dtype=np.float64)


def _ridge(X, y, groups, lam=200.0):
    """Ridge-regression med egen intercept per situation+position (de straffas inte)."""
    gids = sorted(set(groups))
    gi = {g: i for i, g in enumerate(gids)}
    D = np.zeros((len(groups), len(gids)))
    D[np.arange(len(groups)), [gi[g] for g in groups]] = 1.0
    Z = np.hstack([X, D])
    pen = np.r_[np.full(X.shape[1], lam), np.zeros(len(gids))]
    w = np.linalg.solve(Z.T @ Z + np.diag(pen), Z.T @ y)
    return w[:X.shape[1]]


def _pav_decreasing(x, y, w):
    """Isoton (fallande) regression av y på x. Returnerar anpassat värde per punkt i x-ordning."""
    order = np.argsort(x)
    yv, wv = list(-y[order]), list(w[order])  # ökande på -y
    vals, wts, sizes = [], [], []
    for v, ww in zip(yv, wv):
        vals.append(v); wts.append(ww); sizes.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2, s2 = vals.pop(), wts.pop(), sizes.pop()
            tot = wts[-1] + w2
            vals[-1] = (vals[-1] * wts[-1] + v2 * w2) / tot
            wts[-1] = tot
            sizes[-1] += s2
    fit = np.repeat(-np.array(vals), sizes)
    return x[order], fit


def _cutoff(pct, delta, w=None):
    """Percentilen där den fallande kurvan korsar noll (None = korsar aldrig inom det du spelat).
    Data samlas i N_BINS band först, så att enstaka extremvärden inte styr kurvan."""
    if len(pct) == 0:
        return None, None
    edges = np.linspace(0, 1, N_BINS + 1)
    idx = np.clip(np.digitize(pct, edges) - 1, 0, N_BINS - 1)
    cnt = np.bincount(idx, minlength=N_BINS).astype(float)
    sm = np.bincount(idx, weights=delta, minlength=N_BINS)
    ok = cnt > 0
    xs = ((edges[:-1] + edges[1:]) / 2)[ok]
    xs_sorted, fit = _pav_decreasing(xs, sm[ok] / cnt[ok], cnt[ok])
    neg = np.where(fit < 0)[0]
    if len(neg) == 0:
        return None, (xs_sorted, fit)
    k = neg[0]
    if k == 0:
        return 0.0, (xs_sorted, fit)
    # linjär interpolation mellan sista positiva och första negativa bandet
    x0, x1, f0, f1 = xs_sorted[k - 1], xs_sorted[k], fit[k - 1], fit[k]
    return float(x0 + (x1 - x0) * f0 / (f0 - f1)) if f0 != f1 else float(x1), (xs_sorted, fit)


def pre_features(dec, sel=None):
    """Handpoängens egenskaper för preflop-raderna (från faktatabellen, utan att läsa händer)."""
    pre = dec.pre
    hidx = pre.hidx if sel is None else pre.hidx[sel]
    X = pre.ft.H["feats"][hidx].astype(np.float64)
    if len(X):
        X[:, 8] /= 5.0
    return X


WR_BAND = 0.05      # 2.75: winrate-kurvan räknas i 5 %-band och fylls i per 1 %
WR_MIN_PLAYED = 30  # spelade händer i ett band för att det ska räknas
WR_MIN_RATE = 0.5   # bandet räknas som "osäkert" om du spelat under hälften av händerna i det


def _winrate_curve(pct, played, delta, total_hands: int) -> dict | None:
    """Förväntat resultat mot fold om du öppnar exakt topp X % (X = 0–100), i bb per 100 händer i
    situationen. Varje 5 %-band får medelvärdet av händerna du spelade i bandet, gånger bandets andel av
    alla delade händer (= som om du spelat alla händer i bandet). Kurvan är summan av banden upp till X,
    linjär inom ett band. Över din spelade range finns ingen data – där slutar kurvan.
    Handpoängen är korsvaliderad (lärd på andra halvan av spelpassen) men bandens medel är mätta på samma
    händer, så toppen är något optimistisk – intervallet visar hur säker den är."""
    n = len(pct)
    if n < 500:
        return None
    nb = int(round(1 / WR_BAND))
    mean, var, share, rate, ok = [], [], [], [], []
    for b in range(nb):
        m = (pct >= b * WR_BAND) & (pct < (b + 1) * WR_BAND)
        mp = m & played
        d = delta[mp]
        share.append(m.sum() / n)
        rate.append(mp.sum() / m.sum() if m.sum() else 0.0)
        if len(d) >= WR_MIN_PLAYED:
            mean.append(float(d.mean()))
            var.append(float(d.var(ddof=1) / len(d)))
            ok.append(True)
        else:
            mean.append(None); var.append(None); ok.append(False)
    last = 0
    while last < nb and ok[last]:
        last += 1  # första bandet utan data avslutar kurvan
    pts = []
    cum, cvar = 0.0, 0.0
    for x in range(0, 101):
        b = min(int(x / 100 / WR_BAND), nb - 1)
        if x > 0 and b >= last and x / 100 > last * WR_BAND + 1e-9:
            break
        # summan av hela banden före b plus en del av band b
        cum_b = sum(mean[k] * share[k] for k in range(b)) * 100
        var_b = sum(var[k] * share[k] ** 2 for k in range(b)) * 100 ** 2
        frac = (x / 100 - b * WR_BAND) / WR_BAND
        if b < last:
            cum = cum_b + frac * mean[b] * share[b] * 100
            cvar = var_b + (frac * share[b] * 100) ** 2 * var[b]
        pts.append([x, round(float(cum), 2), round(float(1.96 * cvar ** 0.5), 2), bool(rate[b] >= WR_MIN_RATE)])
    if len(pts) < 2:
        return None
    # Toppen söks bara där du spelat minst hälften av bandets händer. I band där du bara spelat ett urval
    # (de du valde att öppna) är medlet för högt – de valda händerna är bättre än bandet i stort.
    solid = []
    for p in pts:  # sammanhängande från topp 0 %: efter första osäkra bandet räknas inget som säkert
        if not p[3]:
            break
        solid.append(p)
    for p in pts[len(solid):]:
        p[3] = False
    solid = solid or pts[:1]
    peak = max(solid, key=lambda p: p[1])
    plateau = [p[0] for p in solid if p[1] >= peak[1] - 2.0]
    now = float(delta[played].sum()) / n * 100
    return {"points": pts, "peak_pct": peak[0], "peak_bb100": peak[1], "peak_ci": peak[2],
            "max_pct": pts[-1][0], "solid_max_pct": solid[-1][0],
            "plateau": [min(plateau), max(plateau)] if plateau else None, "now_bb100": round(now, 2), "now_pct": round(100 * float(played.mean()), 1),
            "share_of_hands": round(n / max(total_hands, n), 4), "dealt": int(n)}


def analyze_ranges(dec, seed: int = 11) -> list[dict]:
    pre = dec.pre
    if pre.ft is None or not len(pre):
        return []
    sel_rows = np.flatnonzero(pre.is_spot(*SPOTS))
    if not len(sel_rows):
        return []
    X = pre_features(dec, sel_rows)
    clu_r = pre.clu[sel_rows]
    half = (clu_r >> 7) & 1
    d_raw = pre.delta[sel_rows]
    played = ~np.isnan(d_raw)
    delta = np.where(played, d_raw, 0.0)
    gcode = pre.spot[sel_rows].astype(np.int64) * 1000 + pre.pos[sel_rows]
    grp = gcode
    score = np.zeros(len(sel_rows))
    weights = {}
    for hf in (0, 1):
        tr = played & (half != hf)
        if tr.sum() < 200:
            return []
        w = _ridge(X[tr], delta[tr], grp[tr].tolist())
        weights[hf] = w
        score[half == hf] = X[half == hf] @ w  # korsvaliderad poäng
    wavg = (weights[0] + weights[1]) / 2
    rng = np.random.default_rng(seed)
    out = []
    by = defaultdict(list)
    for i, g in enumerate(grp.tolist()):
        by[g].append(i)
    num_cards = int((pre.ft.H["hole"][pre.hidx[sel_rows[0]]] >= 0).sum())
    for g, ids in sorted(by.items(), key=lambda kv: kv[1][0]):
        spot, pos = pre.label("spot", g // 1000), pre.label("pos", g % 1000)
        ids = np.array(ids)
        if played[ids].sum() < MIN_PLAYED:
            continue
        # percentil bland ALLA delade händer i situationen (0 = bäst)
        s = score[ids]
        pct = (np.argsort(np.argsort(-s, kind="stable"), kind="stable") + 0.5) / len(s)
        pl = played[ids]
        cut, curve = _cutoff(pct[pl], delta[ids][pl])
        play_rate = float(pl.mean())
        # bootstrap över spelpass
        clus = clu_r[ids]
        uc, inv = np.unique(clus, return_inverse=True)
        o_ = np.argsort(inv, kind="stable")
        members = np.split(o_, np.cumsum(np.bincount(inv, minlength=len(uc)))[:-1])
        boots = []
        for _ in range(BOOT):
            pick = rng.integers(0, len(uc), len(uc))
            sel = np.concatenate([members[k] for k in pick])
            selp = sel[pl[sel]]
            c, _ = _cutoff(pct[selp], delta[ids][selp])
            boots.append(1.0 if c is None else c)  # None = lönsamt genom hela spelade rangen
        lo, hi = (float(np.quantile(boots, 0.1)), float(np.quantile(boots, 0.9)))
        # resultat per tiondel (beskrivande)
        bands = []
        for b in range(10):
            m = (pct >= b / 10) & (pct < (b + 1) / 10)
            mp = m & pl
            d = delta[ids][mp]
            mi = np.where(m)[0]
            mi = mi[np.argsort(pct[mi])]
            ex = [_example(pre.hole(sel_rows[ids[j]]), pct[j], pl[j]) for j in
                  (mi[np.linspace(0, len(mi) - 1, min(4, len(mi))).astype(int)] if len(mi) else [])]
            bands.append({"band": f"{b * 10}–{(b + 1) * 10} %", "dealt": int(m.sum()), "played": int(mp.sum()), "examples": ex,
                          "play_pct": 100.0 * mp.sum() / m.sum() if m.sum() else 0.0,
                          "mean": float(d.mean()) if len(d) else None,
                          "se": float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else None})
        border = {"inside": [], "outside": []}
        if cut is not None:
            for side, lo_, hi_ in (("inside", cut - 0.03, cut), ("outside", cut, cut + 0.03)):
                bi = np.where((pct >= lo_) & (pct < hi_))[0]
                bi = bi[np.argsort(pct[bi])]
                pick = bi[np.linspace(0, len(bi) - 1, min(6, len(bi))).astype(int)] if len(bi) else []
                border[side] = [_example(pre.hole(sel_rows[ids[j]]), pct[j], pl[j]) for j in pick]
        # Bekräftelse utanför urvalet: gränsen hittas i ena halvan av spelpassen, och händerna du
        # spelat bortom den gränsen testas i den andra halvan (och tvärtom).
        # Ingen information från testhalvan får påverka vilka händer som testas: handpoängen räknas
        # med vikter som bara lärts på anpassningshalvan, percentilerna räknas inom varje halva, och
        # gränsen hittas på anpassningshalvan.
        hv = ((clus >> 7) & 1).astype(int)
        beyond = []
        dist = []
        Xg = X[ids]
        for hf in (0, 1):
            w_fit = weights[1 - hf]  # weights[x] är lärda på halvan != x, alltså på halva hf
            sf = Xg @ w_fit
            pct_h = np.zeros(len(ids))
            for half_v in (0, 1):
                hm = np.flatnonzero(hv == half_v)
                if len(hm):
                    r_ = np.argsort(np.argsort(-sf[hm], kind="stable"), kind="stable")
                    pct_h[hm] = (r_ + 0.5) / len(hm)
            fit_m = pl & (hv == hf)
            c_h, _ = _cutoff(pct_h[fit_m], delta[ids][fit_m])
            if c_h is None:
                continue
            bi_ = np.where(pl & (hv != hf) & (pct_h > c_h))[0]
            beyond.append(bi_)
            dist.append(pct_h[bi_] - c_h)
        beyond = np.concatenate(beyond) if beyond else np.array([], dtype=int)
        dist = np.concatenate(dist) if dist else np.array([])
        test = {"n": int(len(beyond)), "mean": None, "p": None, "marg_n": 0, "marg_mean": None, "marg_se": None}
        if len(beyond) >= 100:
            xb = delta[ids][beyond]
            test["mean"] = float(xb.mean())
            # gränsens läge: även händerna närmast gränsen (den närmaste halvan av händerna bortom den)
            # ska ha förlorat mot fold – annars sitter gränsen för snävt och bannar lönsamma händer
            near = dist <= np.median(dist)
            if near.sum() >= 50:
                from .fatigue import _cluster_mean_se
                mm, ms = _cluster_mean_se(xb[near], clus[beyond][near])
                test.update(marg_n=int(near.sum()), marg_mean=mm, marg_se=ms)
            test["p"] = float(bootstrap_t_p(xb, clus[beyond], reps=2000,
                                            seed=zlib.crc32(f"{spot}|{pos}".encode())))
        wr_curve = _winrate_curve(pct, pl, delta[ids], len(np.unique(pre.hidx))) if spot == "rfi" else None
        verdict = None  # sätts när alla grupper är klara (Bonferroni)
        # Gränsen uttryckt som poäng (med medelvikterna), så att den kan användas på nya händer
        s_avg = X[ids] @ wavg
        score_thr = None if cut is None else float(np.quantile(s_avg, 1 - cut))
        out.append({"spot": spot, "pos": pos, "name": SPOTS[spot][0], "verb": SPOTS[spot][1],
                    "dealt": int(len(ids)), "played": int(pl.sum()), "play_pct": 100 * play_rate,
                    "cutoff_pct": None if cut is None else 100 * cut, "lo_pct": 100 * lo, "hi_pct": 100 * hi,
                    "verdict": verdict, "test": test, "bands": bands, "border": border,
                    "score_thr": score_thr, "num_cards": num_cards, "wr_curve": wr_curve,
                    "curve": [[round(100 * float(x), 1), round(float(f), 3)] for x, f in zip(*curve)] if curve else []})
    order = {"rfi": 0, "bb_mot_hojning": 1, "sb_mot_hojning": 2, "mot_hojning": 3, "mot_3bet_ip": 4, "mot_3bet_oop": 5}
    pos_order = {"UTG": 0, "UTG+1": 1, "MP": 2, "LJ": 3, "HJ": 4, "CO": 5, "BTN": 6, "SB": 7, "BB": 8}
    out.sort(key=lambda r: (order.get(r["spot"], 9), pos_order.get(r["pos"], 9)))
    k = max(len(out), 1)
    for r in out:
        r["verdict"] = _verdict(r, k)
    for r in out:
        r["weights"] = {n: round(float(v), 3) for n, v in zip(FEATURE_NAMES, wavg)}
    return out


def _example(hole, p, played) -> dict:
    from .cards import card_str, nut_combo_label
    order = sorted(hole, key=lambda c: (-c[0], c[1]))
    return {"cards": [list(c) for c in order], "text": " ".join(card_str(c) for c in order),
            "pct": round(100 * float(p), 1), "played": bool(played),
            "nut": nut_combo_label(nut_qualities(hole))}


def _verdict(r: dict, k: int) -> dict:
    """"För brett" kräver att händerna bortom gränsen förlorar mot fold även i den halva av
    spelpassen som inte användes för att hitta gränsen (Bonferroni över alla situationer)."""
    t = r["test"]
    alpha = 0.05 / k
    if t["p"] is not None and t["mean"] < 0 and t["p"] <= alpha and t.get("marg_mean") is not None \
            and t["marg_mean"] >= 0:
        return {"kind": "unclear",
                "text": (f"Händerna långt bortom gränsen förlorar ({t['mean']:+.2f} bb per gång mot fold), men de närmast "
                         f"gränsen har gått {t['marg_mean']:+.2f} bb – gränsen sitter för snävt. Folda de sämsta, men "
                         f"spela inte efter just den här procentsatsen.")}
    if t["p"] is not None and t["mean"] < 0 and t["p"] <= alpha:
        return {"kind": "wide",
                "text": (f"Du spelar bredare än det som lönar sig. Händerna bortom gränsen har gett {t['mean']:+.2f} bb "
                         f"per gång jämfört med fold ({t['n']} st), bekräftat i den halva av dina spelpass som inte "
                         f"användes för att hitta gränsen.")}
    if r["cutoff_pct"] is None or r["lo_pct"] >= r["play_pct"] - 0.5:
        return {"kind": "ok", "text": "Inget tyder på att du spelar för brett här. Om du borde spela fler händer går inte "
                                      "att avgöra – vi vet inte hur händerna du foldat hade gått."}
    return {"kind": "unclear", "text": "Kurvan antyder en gräns, men det bekräftas inte i den andra halvan av dina "
                                       "spelpass – det går inte att säga att du spelar för brett."}


def model_note() -> str:
    return __doc__


# ---------------------------------------------------------------- öppningsguide
COMBO_ORDER = ["högt par + suited ess + rundown", "högt par + suited ess", "suited ess + rundown", "högt par + rundown",
               "suited ess", "rundown", "högt par", "ingen"]


def opening_guide(dec, z: float = 1.96) -> list[dict]:
    """Per position: hur dina öppningar (när det foldats till dig) gått jämfört med fold, uppdelat på
    vilka nöt-egenskaper handen har. "Folda"/"Öppna" bara när förlusten/vinsten är säkerställd: ett
    kluster-bootstrap-t-test som klarar Bonferroni över alla celler i guiden – annars "Osäkert"."""
    from .cards import nut_combo_label
    from .statlib import cluster_se
    cells = defaultdict(lambda: {"dealt": 0, "vals": [], "clus": []})
    pre = dec.pre
    if pre.ft is not None and len(pre):
        H = pre.ft.H
        m = pre.is_spot("rfi")
        hx = pre.hidx[m]
        bits = H["hp"][hx].astype(np.int64) * 4 + H["sa"][hx] * 2 + H["rd"][hx]
        poss, kinds, deltas, clus = pre.pos[m], pre.kind[m], pre.delta[m], pre.clu[m]
        raise_code = pre.ft.code("kind", "raise")
        key = poss.astype(np.int64) * 10 + bits
        for k in np.unique(key):
            km = key == k
            pos_l = pre.label("pos", k // 10)
            b_ = int(k % 10)
            combo_l = nut_combo_label((bool(b_ & 4), bool(b_ & 2), bool(b_ & 1)))
            c = cells[(pos_l, combo_l)]
            c["dealt"] += int(km.sum())
            om = km & (kinds == raise_code) & ~np.isnan(deltas)
            c["vals"].extend(deltas[om].tolist())
            c["clus"].extend(clus[om].tolist())
    pos_order = ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB"]
    from .statlib import ci_cell
    # alla celler i guiden bedöms tillsammans: Bonferroni över dem som har minst 30 öppningar
    from .statlib import RULE_FAMILIES, RULE_MIN_N
    m_guide = RULE_FAMILIES * max(1, sum(1 for k, v in cells.items() if k[0] in pos_order and len(v["vals"]) >= RULE_MIN_N))
    out = []
    for pos in [p for p in pos_order if any(k[0] == p for k in cells)]:
        rows = []
        tot_d = sum(v["dealt"] for k, v in cells.items() if k[0] == pos)
        for combo in COMBO_ORDER:
            c = cells.get((pos, combo))
            if not c or not c["dealt"]:
                continue
            n = len(c["vals"])
            cc = ci_cell(c["vals"], c["clus"], min_n=RULE_MIN_N, z=z, m_tests=m_guide)
            verdict = {"förlorar": "Folda", "lönsamt": "Öppna", "jämnt / osäkert": "Osäkert", "osäkert (svansvakt)": "Osäkert"}.get(cc["verdict"], "För få")
            if cc["lo"] is not None and not np.isfinite(cc["lo"]):
                verdict = "För få"
            rows.append({"combo": combo, "n_qual": 0 if combo == "ingen" else combo.count("+") + 1,
                         "dealt": c["dealt"], "share": 100.0 * c["dealt"] / tot_d, "opens": n,
                         "open_pct": 100.0 * n / c["dealt"], "mean": cc["mean"],
                         "lo": cc["lo"], "hi": cc["hi"], "verdict": verdict})
        opened = sum(r["opens"] for r in rows)
        out.append({"pos": pos, "dealt": tot_d, "open_pct": 100.0 * opened / tot_d if tot_d else 0.0, "rows": rows})
    return out
