"""Lättlästa sammanställningar: river-syner per betstorlek och "Det viktigaste" överst i rapporten."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .decisions import RIVER_BUCKETS, SIZE_BUCKETS
from .statlib import ci_cell

MIN_CELL = 30

STRENGTH_SHORT = {
    RIVER_BUCKETS[0][1]: "Nöten eller nästan",
    RIVER_BUCKETS[1][1]: "Nära nöten",
    RIVER_BUCKETS[2][1]: "Medelstark",
    RIVER_BUCKETS[3][1]: "Svag",
    RIVER_BUCKETS[4][1]: "Mycket svag",
}
STRENGTH_HELP = {
    "Nöten eller nästan": "under 10 % av motståndarens möjliga händer slår dig",
    "Nära nöten": "10–25 % slår dig",
    "Medelstark": "25–50 % slår dig",
    "Svag": "50–75 % slår dig",
    "Mycket svag": "över 75 % slår dig",
}


def _cell(vals, clus, m: int = 1):
    """Cell med bedömning; m = antal celler i samma tabell som bedöms (Bonferroni)."""
    return ci_cell(vals, clus, min_n=MIN_CELL, m_tests=m)


def _m(*lists) -> int:
    return max(1, sum(1 for v in lists if len(v) >= MIN_CELL))


def river_call_table(dec) -> dict:
    """River mot en bet: per betstorlek hur ofta du foldat och hur dina syner gått jämfört med fold,
    samt en tabell betstorlek × handstyrka. Synernas resultat är exakt (sista beslutet i handen)."""
    rows = dec.river
    if not rows:
        return {}
    sizes = [n for _, n in SIZE_BUCKETS]
    strengths = [STRENGTH_SHORT[n] for _, n in RIVER_BUCKETS]
    by_size = defaultdict(lambda: {"faced": 0, "fold": 0, "call": 0, "raise": 0, "vals": [], "clus": []})
    grid = defaultdict(lambda: {"faced": 0, "fold": 0, "vals": [], "clus": []})
    for size, strength, kind, delta, clu, hid in rows:
        s_ = STRENGTH_SHORT.get(strength, strength)
        b = by_size[size]
        g = grid[(size, s_)]
        b["faced"] += 1
        g["faced"] += 1
        if kind == "fold":
            b["fold"] += 1
            g["fold"] += 1
        elif kind in ("call", "raise"):
            b[kind] += 1
            if kind == "call":
                b["vals"].append(delta)
                b["clus"].append(clu)
                g["vals"].append(delta)
                g["clus"].append(clu)
    all_vals = [b["vals"] for b in by_size.values()] + [g["vals"] for g in grid.values()] + \
               [sum((b["vals"] for b in by_size.values()), [])]
    m_r = _m(*all_vals)
    out_sizes = []
    tot = {"faced": 0, "fold": 0, "vals": [], "clus": []}
    for sz in sizes:
        b = by_size.get(sz)
        if not b or not b["faced"]:
            continue
        c = _cell(b["vals"], b["clus"], m_r)
        out_sizes.append({"size": sz, "faced": b["faced"], "fold_pct": 100.0 * b["fold"] / b["faced"],
                          "calls": len(b["vals"]), "total": float(np.sum(b["vals"])) if b["vals"] else 0.0, **c})
        tot["faced"] += b["faced"]
        tot["fold"] += b["fold"]
        tot["vals"] += b["vals"]
        tot["clus"] += b["clus"]
    ct = _cell(tot["vals"], tot["clus"], m_r)
    total_row = {"size": "Alla storlekar", "faced": tot["faced"],
                 "fold_pct": 100.0 * tot["fold"] / tot["faced"] if tot["faced"] else 0.0,
                 "calls": len(tot["vals"]), "total": float(np.sum(tot["vals"])) if tot["vals"] else 0.0, **ct}
    grid_rows = []
    for st_ in strengths:
        cells = []
        for sz in sizes:
            g = grid.get((sz, st_))
            if not g or not g["faced"]:
                cells.append(None)
                continue
            c = _cell(g["vals"], g["clus"], m_r)
            c["faced"] = g["faced"]
            c["fold_pct"] = 100.0 * g["fold"] / g["faced"]
            # möjlig överfoldning: synerna i rutan har gått klart bättre än fold (även med felmarginalen)
            # och du foldar ändå ofta. Foldade händer är de svagaste i rutan, så det är en signal, inte ett bevis.
            c["overfold"] = bool(c.get("lo") is not None and c["lo"] > 0 and c["fold_pct"] >= 20 and c["n"] >= 30)
            c["folds"] = g["fold"]
            cells.append(c)
        grid_rows.append({"strength": st_, "help": STRENGTH_HELP[st_], "cells": cells})
    overfold = [{"strength": g["strength"], "size": sizes[i].split(" (")[0], "fold_pct": c["fold_pct"], "folds": c["folds"],
                 "mean": c["mean"], "lo": c["lo"], "n": c["n"]}
                for g in grid_rows for i, c in enumerate(g["cells"]) if c and c.get("overfold")]
    return {"overfold": overfold, "sizes": out_sizes, "total": total_row, "grid": grid_rows,
            "size_names": [s.split(" (")[0].capitalize() for s in sizes],
            "size_help": [s.split(" (")[1].rstrip(")") if " (" in s else "" for s in sizes]}


def key_points(st, money, stake_rows, nut_rows, guide, river_tbl, leaks, turn_tbl=None, nut_fold=None, confirmed=None, likely=None, pots=None, hourly=None) -> list[dict]:
    """De viktigaste slutsatserna i klartext. tone: good / bad / info."""
    pts = []
    n = st.hands or 1
    rake100 = 100 * st.rake_paid_bb / n
    ev100 = st.ev_bb100
    pre_ev100 = 100 * (st.ev_net_bb + st.ev_rake_bb) / n
    luck = st.net_money - st.ev_net_money
    pts.append({"tone": "good" if st.net_money >= 0 else "bad", "title": "Resultat",
                "text": (f"Du har {'vunnit' if st.net_money >= 0 else 'förlorat'} {abs(st.net_money):,.0f} $ på "
                         f"{st.hands:,} händer ({st.bb100:+.1f} bb/100). Utan tur och otur i all-ins (all-in EV) hade det "
                         f"varit {st.ev_net_money:+,.0f} $ ({ev100:+.1f} bb/100) – du har haft "
                         f"{'tur' if luck > 0 else 'otur'} för {abs(luck):,.0f} $.").replace(",", " ")})
    pts.append({"tone": "bad" if rake100 > abs(pre_ev100) else "info", "title": "Rake",
                "text": (f"Rake och avgifter kostar dig {rake100:.1f} bb/100 ({st.rake_paid_money:,.0f} $). Före rake och "
                         f"utan all-in-tur ligger du på {pre_ev100:+.1f} bb/100"
                         + (" – raken äter upp mer än hela din edge." if pre_ev100 > 0 and rake100 > pre_ev100 else ".")
                         ).replace(",", " ")})
    if nut_fold and nut_fold.get("rows"):
        from .nutfold import confirmed_losses
        d = {r["name"]: r for r in nut_fold["rows"]}
        z = d.get("0 nöt-egenskaper")
        bad = confirmed_losses(nut_fold)
        if bad:
            txt = ", ".join(f"{c['nut']} från {c['pos']} ({c['mean']:+.2f} bb per hand, {c['n']} st)" for c in bad[:4])
            pts.append({"tone": "bad", "title": "Starthänder",
                        "text": f"Säkerställd förlust jämfört med att folda direkt: {txt}. Folda dem. "
                                f"Se Nöt-egenskaper under Preflop."})
        elif z and z["played"] >= MIN_CELL and z["mean"] is not None:
            worse = z["verdict"] == "förlorar"
            pts.append({"tone": "bad" if worse else "info", "title": "Starthänder",
                        "text": (f"Händer med 0 nöt-egenskaper har gett {z['mean']:+.2f} bb per spelad hand jämfört med "
                                 f"att folda direkt ({z['played']} st, totalt {z['total']:+.0f} bb, blindar medräknade). "
                                 + ("Förlusten är säkerställd totalt, men ingen enskild position klarar kravet – "
                                    "se per position under Preflop." if worse else
                                    "Inte säkerställt – kan vara slump. Se per position under Preflop."))})
    if guide:
        folds = [(g["pos"], r["combo"]) for g in guide for r in g["rows"] if r["verdict"] == "Folda"]
        if folds:
            txt = ", ".join(f"{c} från {p}" for p, c in folds[:5])
            pts.append({"tone": "bad", "title": "Öppningar",
                        "text": f"Öppningar med säkerställd förlust jämfört med fold: {txt}. "
                                f"Se Öppningsguiden under Preflop."})
    if river_tbl and river_tbl.get("total") and river_tbl["total"]["calls"] >= MIN_CELL:
        t = river_tbl["total"]
        best = [r for r in river_tbl["sizes"] if r["verdict"] == "lönsamt"]
        pts.append({"tone": "good" if t["mean"] > 0 else "bad", "title": "River",
                    "text": (f"Mot river-bets foldar du {t['fold_pct']:.0f} %. Dina syner har gett {t['mean']:+.1f} bb per syn "
                             f"jämfört med fold ({t['calls']} syner, totalt {t['total']:+.0f} bb)."
                             + (" Klart lönsamt mot: " + ", ".join(r["size"].split(" (")[0] for r in best) + " bets."
                                if best else ""))})
    if turn_tbl and turn_tbl.get("total") and turn_tbl["total"]["n"] >= MIN_CELL:
        t = turn_tbl["total"]
        cc = next((r for r in turn_tbl["paths"] if r["path"] == "synade river-bet"), None)
        pts.append({"tone": "good" if t["verdict"] == "lönsamt" else ("bad" if t["verdict"] == "förlorar" else "info"),
                    "title": "Turn",
                    "text": (f"Dina syner mot turn-bets har gett {t['mean']:+.1f} bb per syn jämfört med att folda turn "
                             f"({t['n']} syner, {t['verdict']})."
                             + (f" När du sedan också synade river blev det {cc['mean']:+.1f} bb per gång ({cc['n']} st)." if cc else ""))})
    if likely:
        top = likely[:3]
        pts.append({"tone": "bad", "title": "Trolig förbättring",
                    "text": "Inte bevisat, men troligast bättre för din bb/100: " + "; ".join(
                        f"{o['title']} (ca {o['gain100']:+.1f} bb/100, säkerhet {100 * o['p']:.0f} %)" for o in top)
                            + ". Se Läckor."})
    ht = (hourly or {}).get("total") or {}
    if ht.get("hph") and ht.get("hours", 0) >= 1:
        rng = (f" (95 %: {ht['ev_lo']:+,.2f} till {ht['ev_hi']:+,.2f} $)" if "ev_lo" in ht else "")
        pts.append({"tone": "good" if ht.get("ev_lo", -1) > 0 else ("bad" if ht.get("ev_hi", 1) < 0 else "info"),
                    "title": "Timlön",
                    "text": (f"Du spelar ca {ht['hph']:.0f} händer i timmen ({ht['hours']:.0f} timmar). Timlön: "
                             f"{ht['usd_h']:+,.2f} $ faktiskt och {ht['ev_usd_h']:+,.2f} $ med all-in EV{rng}. "
                             f"Se Timlön under Resultat & graf.").replace(",", " ")})
    prow = [r for r in ((pots or {}).get("rows") or []) if r.get("n", 0) >= MIN_CELL]
    if prow:
        worst = min(prow, key=lambda r: r["ev"])
        best = max(prow, key=lambda r: r["ev"])
        big = pots["big"]
        pts.append({"tone": "bad" if big["n"] and big["ev"] < 0 else "info", "title": "Pottstorlek",
                    "text": (f"Mest förlorar du i pottar på {worst['label']} bb ({worst['ev']:+.0f} bb med all-in EV), "
                             f"mest vinner du i {best['label']} bb ({best['ev']:+.0f} bb)."
                             + (f" Pottar på 150 bb och mer: {big['ev']:+.0f} bb ({big['ev100']:+.1f} bb/100)." if big["n"] else "")
                             + " Se Pottstorlek under Resultat & graf.")})
    conf = confirmed or []
    if leaks or conf:
        parts = []
        if leaks:
            parts.append((f"{len(leaks)} läcka" if len(leaks) == 1 else f"{len(leaks)} läckor") + " från bevismotorn")
        if conf:
            parts.append(f"{len(conf)} starthandsregel{'' if len(conf) == 1 else 'er'}: " + "; ".join(r["title"] for r in conf[:4]))
        pts.append({"tone": "bad", "title": "Bekräftade läckor",
                    "text": "Säkerställt: " + " · ".join(parts) + ". Se Läckor."})
    else:
        pts.append({"tone": "info", "title": "Bekräftade läckor",
                    "text": "Ingen läcka klarar de stränga kraven (hittad i ena halvan av händerna och bekräftad i den andra, "
                            "eller säkerställd i tabellerna med korrigering för många tester). Tabellerna under Preflop och "
                            "Turn & river visar riktningar, med felmarginal."})
    return pts


PATH_ORDER = ["synade river-bet", "foldade mot river-bet", "höjde river-bet", "check-check river",
              "bettade själv river", "ingen river (all-in eller handen slut)", "övrigt"]
TURN_STRENGTH_ORDER = ["stark hand + stort drag", "stark hand", "medelstark hand + stort drag", "medelstark hand",
                       "svag hand + stort drag", "svag hand"]


def turn_call_table(dec) -> dict:
    """När du synat en bet på turn: hur slutade handen jämfört med att folda på turn, uppdelat på vad som
    hände på river. Varje rad är exakt (allt som hände efter turn-synen räknas in)."""
    rows = dec.turn_calls
    if not rows:
        return {}
    by_path = defaultdict(lambda: {"vals": [], "clus": []})
    grid = defaultdict(lambda: {"vals": [], "clus": []})
    allv, allc = [], []
    for strength, delta, clu, path in rows:
        by_path[path]["vals"].append(delta)
        by_path[path]["clus"].append(clu)
        allv.append(delta)
        allc.append(clu)
        key = "synade river-bet" if path == "synade river-bet" else "övriga vägar"
        grid[(strength, key)]["vals"].append(delta)
        grid[(strength, key)]["clus"].append(clu)
        grid[(strength, "alla")]["vals"].append(delta)
        grid[(strength, "alla")]["clus"].append(clu)
    n_all = len(allv)
    m_t = _m(allv, *[b["vals"] for b in by_path.values()], *[g["vals"] for g in grid.values()])
    paths = []
    for p in PATH_ORDER:
        b = by_path.get(p)
        if not b or not b["vals"]:
            continue
        c = _cell(b["vals"], b["clus"], m_t)
        paths.append({"path": p, "share": 100.0 * len(b["vals"]) / n_all, "total": float(np.sum(b["vals"])), **c})
    total = {"path": "Alla turn-syner", "share": 100.0, "total": float(np.sum(allv)), **_cell(allv, allc, m_t)}
    strengths = []
    for s_ in TURN_STRENGTH_ORDER + sorted({k[0] for k in grid} - set(TURN_STRENGTH_ORDER)):
        if (s_, "alla") not in grid:
            continue
        strengths.append({"strength": s_,
                          "all": _cell(grid[(s_, "alla")]["vals"], grid[(s_, "alla")]["clus"], m_t),
                          "callcall": _cell(grid[(s_, "synade river-bet")]["vals"], grid[(s_, "synade river-bet")]["clus"], m_t)
                          if (s_, "synade river-bet") in grid else None,
                          "other": _cell(grid[(s_, "övriga vägar")]["vals"], grid[(s_, "övriga vägar")]["clus"], m_t)
                          if (s_, "övriga vägar") in grid else None})
    return {"paths": paths, "total": total, "strengths": strengths}


BLUFF_SIZES = [(0.40, "Liten (under 40 %)"), (0.60, "Medel (40–60 %)"), (0.85, "Stor (60–85 %)"), (9e9, "Pott eller mer")]
BLUFF_STR = [(0.10, "Nöten eller nästan"), (0.25, "Nära nöten"), (0.50, "Medelstark"), (0.75, "Svag"), (1.01, "Mycket svag")]


def river_bluff_table(ft, rows) -> dict:
    """Dina egna river-bets heads-up: hur ofta motståndaren foldat per storlek mot vad en ren bluff behöver
    (bet / (pott + bet)), och hur ofta du bettar i position när det checkats till dig, per handstyrka.
    Motståndarens fold syns alltid, så foldandelen är ett opartiskt mått (det är ditt urval av händer som
    bettar som kan skilja sig, inte hur poolen svarar på storleken). Felmarginal per spelpass."""
    from .fatigue import _cluster_mean_se
    V = ft.t.get("rvb") if ft is not None else None
    if V is None or not len(V["hidx"]):
        return {}
    mask = np.zeros(ft.n, bool)
    mask[np.asarray(rows, dtype=np.int64)] = True
    m = ft.subset_mask(mask, "rvb")
    role, frac, resp, bf = V["role"][m], V["frac"][m], V["resp"][m], V["bf"][m]
    clu = ft.H["clu"][V["hidx"][m]]
    bet = (role <= 1) & (resp >= 0)
    sizes = []
    lo_ = 0.0
    for hi_, name in BLUFF_SIZES:
        mk = bet & (frac >= lo_) & (frac < hi_)
        lo_ = hi_
        n = int(mk.sum())
        if n < 50:
            continue
        p, se = _cluster_mean_se((resp[mk] == 0).astype(float), clu[mk])
        need = float(np.median(frac[mk]) / (1 + np.median(frac[mk])))
        sizes.append({"size": name, "n": n, "fold_pct": 100 * p, "fold_lo": 100 * (p - 1.96 * se), "fold_hi": 100 * (p + 1.96 * se),
                      "need_pct": 100 * need, "frac_pct": 100 * float(np.median(frac[mk])),
                      "edge": bool(np.isfinite(se) and p - 1.96 * se > need)})
    ip = []
    for k, (lim, name) in enumerate(BLUFF_STR):
        lo = BLUFF_STR[k - 1][0] if k else -0.5
        mk = (bf >= lo) & (bf < lim) & ((role == 1) | (role == 2)) & (bf >= 0)
        b, c = int((mk & (role == 1)).sum()), int((mk & (role == 2)).sum())
        if b + c:
            ip.append({"strength": name, "bet": b, "check": c, "n": b + c, "bet_pct": 100.0 * b / (b + c)})
    nb = int(bet.sum())
    weak = int((bet & (bf >= 0.50)).sum())
    # försiktigt värde: hälften av dina check-igenom i position med luft (minst 75 % slår dig) blir bluffar
    # med den storlek som har störst marginal, räknat på den nedre gränsen för foldandelen
    est100 = 0.0
    edge = [s for s in sizes if s["edge"]]
    if edge:
        best = max(edge, key=lambda s: s["fold_lo"] / 100 - (1 - s["fold_lo"] / 100) * s["frac_pct"] / 100)
        ev_pot = best["fold_lo"] / 100 - (1 - best["fold_lo"] / 100) * best["frac_pct"] / 100
        air = (role == 2) & (bf >= 0.75)
        pots = ft.H["pot"][V["hidx"][m][air]]
        if air.any() and ev_pot > 0:
            est100 = 100.0 * 0.5 * air.sum() * ev_pot * float(np.median(pots)) / len(rows)
    return {"sizes": sizes, "ip": ip, "bets": nb, "weak_share": 100.0 * weak / nb if nb else None,
            "any_edge": bool(edge), "est100": est100}


CALL_BINS = [0.0, 0.05, 0.10, 0.175, 0.25, 0.35, 0.50, 0.65, 0.80, 1.01]  # andel motståndarhänder som slår dig
SIZE_SHORT = ["Liten bet (under 40 %)", "Medel (40–60 %)", "Stor (60–85 %)", "Pottstor eller mer"]


def _pct_label(x: float) -> str:
    return (f"{100 * min(x, 1.0):.1f}".rstrip("0").rstrip(".") + " %").replace(".", ",")


def river_call_guide(ft, rows, recent: int = 20000) -> dict:
    """River mot en bet heads-up: upp till vilken handstyrka har dina syner gått plus mot fold, per betstorlek?
    Handstyrka = andel av motståndarens möjliga händer (lika många kort) som slår dig på bordet (0 = nöten).
    Gränsen = svagaste styrkan där synerna fortfarande gått plus, räknat från nöten och nedåt (minst 20 syner
    per steg). En fold med en starkare hand än gränsen räknas som en möjlig miss. Folds kan inte värderas,
    så värdet räknas försiktigt: missar × den nedre gränsen (95 %) för synernas resultat i samma steg."""
    from .cards import CATEGORY_NAMES
    from .decisions import SIZE_BUCKETS as SB
    from .fatigue import _cluster_mean_se
    R = ft.t.get("riv") if ft is not None else None
    if R is None or "bf" not in R or not len(R["hidx"]):
        return {}
    rows = np.asarray(rows, dtype=np.int64)
    mask = np.zeros(ft.n, bool)
    mask[rows] = True
    m = ft.subset_mask(mask, "riv") & (R["bf"] >= 0)
    if m.sum() < 200:
        return {}
    hx, bf, kind, d = R["hidx"][m], R["bf"][m], R["kind"][m], R["delta"][m]
    cat = R["cat"][m] if "cat" in R else np.full(m.sum(), -1)
    size = R["size"][m]
    clu = ft.H["clu"][hx]
    fold_c, call_c = ft.code("kind", "fold"), ft.code("kind", "call")
    rec_set = set(rows[-recent:].tolist())
    recent_m = np.array([int(x) in rec_set for x in hx])
    n_hands = len(rows)
    out = []
    missed_rows = []
    total_val = 0.0
    for si, (_, sname) in enumerate(SB):
        sc = ft.code("size", sname)
        ms = size == sc
        if ms.sum() < 50:
            continue
        cells = []
        thr = None
        ok_run = True
        for k in range(len(CALL_BINS) - 1):
            lo, hi = CALL_BINS[k], CALL_BINS[k + 1]
            mb = ms & (bf >= lo) & (bf < hi)
            n = int(mb.sum())
            mc = mb & (kind == call_c)
            nf = int((mb & (kind == fold_c)).sum())
            mean = se = None
            if mc.sum() >= 20:
                mean, se = _cluster_mean_se(d[mc], clu[mc])
            cats = [CATEGORY_NAMES.get(int(c), "") for c, _ in sorted(
                ((c, int((mb & (cat == c)).sum())) for c in np.unique(cat[mb]) if c >= 0), key=lambda t: -t[1])[:2]]
            good = mean is not None and mean > 0
            if ok_run and good:
                thr = hi
            elif mean is not None:
                ok_run = False
            cells.append({"lo": lo, "hi": hi, "n": n, "fold_pct": 100.0 * nf / n if n else None, "folds": nf,
                          "calls": int(mc.sum()), "mean": mean, "se": se, "cats": [c for c in cats if c],
                          "state": "good" if good else ("bad" if mean is not None else "few")})
        if thr is None:
            continue
        inside = ms & (bf < thr)
        folds_in = inside & (kind == fold_c)
        val = 0.0
        for c in cells:
            if c["hi"] <= thr and c["mean"] is not None and c["se"] is not None:
                val += c["folds"] * max(0.0, c["mean"] - 1.96 * c["se"])
        total_val += val
        for j in np.flatnonzero(folds_in & recent_m):
            missed_rows.append(int(hx[j]))
        out.append({"size": SIZE_SHORT[si], "thr": thr, "thr_label": _pct_label(thr), "cells": cells,
                    "spots": int(inside.sum()), "folds": int(folds_in.sum()),
                    "fold_pct": 100.0 * folds_in.sum() / max(inside.sum(), 1),
                    "recent_folds": int((folds_in & recent_m).sum()), "recent_spots": int((inside & recent_m).sum()),
                    "val100": 100.0 * val / n_hands})
    if not out:
        return {}
    missed_rows = sorted(set(missed_rows), key=lambda x: -int(ft.H["ts"][x]))[:12]
    return {"sizes": out, "bins": CALL_BINS, "val100": 100.0 * total_val / n_hands,
            "missed": [{"id": str(ft.H["id"][x]), "row": x} for x in missed_rows]}
