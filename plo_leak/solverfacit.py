"""2.77: solvern är facit preflop.

Bygger på solverref.decisions (första preflopbeslut i de 14 lägena med solverns frekvenser för handens grupp).

Nivåer (statistikergranskningen 2026-11-18: hela den mätbara förlusten mot fold ligger där solvern gör handlingen
under 1 %, −1,58 ± 0,30 bb; 1–10 % ≈ 0):
* "fel"       – solvern gör din handling < 1 %  (klart fel)
* "tveksamt"  – 1–10 %
* "ok"        – ≥ 10 %
Överspel mäts separat per läge och grupp: din spelfrekvens minus solverns (fångar blandade grupper).

Ingen solverdata sparas här – allt räknas från filen spelaren själv lagt in. Visas bara genom solvergrinden.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .solvergroups import ALL_NODES, EXTRA_PRIOR, NODE_DESC, NODE_LABEL, NODES, OPEN_NODES, classify, short

FEL = 1.0
TVEKSAMT = 10.0
MIN_BESLUT_LAGE = 150       # minst så många beslut i ett läge för att det ska kunna väljas till träningsrutan
MIN_GRUPP = 30              # minst så många beslut i en grupp för en tumregel
OVERCORR_PP = 3.0
COST_K = 100.0              # 2.83: krympning av kostnad per fel mot snittet (pseudo-antal fel)           # varning om öppningsfrekvensen är mer än så många procentenheter under solverns
ACT_TXT = {0: "foldade", 1: "synade", 2: "höjde"}


def verdict(s_act: float) -> str:
    if s_act < FEL:
        return "fel"
    if s_act < TVEKSAMT:
        return "tveksamt"
    return "ok"


def build(st, tab) -> dict | None:
    """Alla beslut med solverfrekvens + nivå + grupp på nivå 2 (för tumregler och överspel)."""
    from .solverref import decisions
    D = decisions(st, tab)
    if D is None or not len(D["hidx"]):
        return None
    act, sf = D["act"], D["sf"]
    s_act = sf[np.arange(len(act)), act]
    from .facts import decode_cards
    H = st.ft.H
    g2 = []
    for j in D["hidx"]:
        c = classify(decode_cards(H["hole"][j]))
        g2.append(short(c[0], c[1], None) if c else "")
    D["s_act"] = s_act
    D["fel"] = s_act < FEL
    D["tvek"] = (s_act >= FEL) & (s_act < TVEKSAMT)
    D["play_sol"] = 100.0 - sf[:, 0]
    D["g2"] = np.asarray(g2, dtype=object)
    return D


def _hands_in(st, t0: int, t1: int) -> int:
    ts = st.ft.H["ts"]
    m = (ts >= t0) & (ts < t1)
    if getattr(st, "mask", None) is not None:
        m &= st.mask
    return int(m.sum())


def _pace(st, t0: int, t1: int) -> tuple:
    """(händer per aktiv timme, snitt-bb i $) i fönstret – samma tidsregel som Timlön (luckor > 5 min = 5 min)."""
    from .hourly import _active_seconds
    H = st.ft.H
    m = (H["ts"] >= t0) & (H["ts"] < t1)
    if getattr(st, "mask", None) is not None:
        m &= st.mask
    idx = np.flatnonzero(m)
    if len(idx) < 2:
        return None, None
    o = idx[np.argsort(H["ts"][idx], kind="stable")]
    sec, _n, _t = _active_seconds(H["ts"][o].astype(np.int64), H["clu"][o])
    if sec <= 0:
        return None, None
    return len(idx) / (sec / 3600.0), float(H["bb"][idx].mean())


def _costs(D) -> dict:
    """Kostnad per spelat klart fel i bb (−resultat mot fold), per läge krympt mot snittet: (bb, antal fel)."""
    m = D["fel"] & (D["act"] > 0) & np.isfinite(D["delta"])
    c = -D["delta"][m]
    nd = D["node"][m]
    g = float(c.mean()) if len(c) else 0.0
    out = {"all": (g, int(len(c)))}
    for i in np.unique(nd).tolist():
        x = c[nd == i]
        out[int(i)] = ((float(x.sum()) + COST_K * g) / (len(x) + COST_K), int(len(x)))
    return out


_OPEN_COST = {"root", "F", "F-F"}  # SB-öppningen är inte en del av prio-raden "öppna tightare"


def _cat(node: str, act: int) -> str | None:
    """2.83: prio-kategori för ett spelat beslut: open (UTG/CO/BTN öppnar), raise (3-bet/squeeze/4-bet mot höjning),
    call (syn mot öppning utanför BB, även kallsyn av 3-bet). Övrigt: None."""
    if node in OPEN_NODES:
        return "open" if node in _OPEN_COST and act > 0 else None
    if act == 2:
        return "raise"
    if act == 1:
        lab = NODE_LABEL.get(node, "")
        if lab.startswith("BB") or "öppnade," in lab:
            return None
        return "call"
    return None


def prio_costs(st, D, now: datetime | None = None, days: int = 30) -> dict | None:
    """2.83: vad prio-raderna kostar nu i $/h (samma formel som träningsrutan, fönster `days` dagar)."""
    if D is None or not len(D["hidx"]):
        return None
    from .facts import dt_of
    now = now or dt_of(int(D["ts"].max()) + 1)
    t1, t0 = _ts(now), _ts(now - timedelta(days=days))
    N = _hands_in(st, t0, t1)
    hph, bb_usd = _pace(st, t0, t1)
    if not N or not hph:
        return None
    cost = _costs(D)
    w = (D["ts"] >= t0) & (D["ts"] < t1) & D["fel"] & (D["act"] > 0)
    out = {"open": 0.0, "raise": 0.0, "call": 0.0}
    for k in np.flatnonzero(w).tolist():
        i = int(D["node"][k])
        c = _cat(ALL_NODES[i], int(D["act"][k]))
        if c:
            out[c] += max(cost.get(i, cost["all"])[0], 0.0)
    f = hph * bb_usd / N
    return {**{k: v * f for k, v in out.items()}, "days": days, "hph": hph, "bb_usd": bb_usd,
            "from": (now - timedelta(days=days)).strftime("%Y-%m-%d")}


def _ts(dt: datetime) -> int:
    from .facts import ts_of
    return ts_of(dt)


# ------------------------------------------------------------------ tumregler per läge
def rules_for(D, k_idx, node_i: int, limit: int = 3) -> list:
    """Upp till `limit` testade tumregler för läget: grupper (nivå 0–1) där solvern spelar ≤ 10 % eller ≥ 80 %
    och du avviker minst 10 procentenheter, med minst MIN_GRUPP beslut. Sorterat efter hur många händer det gäller."""
    out = []
    ks = k_idx[D["node"][k_idx] == node_i]
    if not len(ks):
        return out
    by = {}
    for k in ks:
        by.setdefault(D["g2"][k], []).append(k)
    for g, kk in by.items():
        if not g or len(kk) < MIN_GRUPP:
            continue
        kk = np.asarray(kk)
        sol = float(D["play_sol"][kk].mean())
        du = float((D["act"][kk] > 0).mean() * 100)
        if sol <= 10 and du - sol >= 10:
            kind, text = "folda", f"{g}: folda (solvern spelar {sol:.0f} %, du {du:.0f} %)"
            weight = (du - sol) / 100 * len(kk)
        elif sol >= 80 and sol - du >= 10:
            kind, text = "spela", f"{g}: spela (solvern {sol:.0f} %, du {du:.0f} %)"
            weight = (sol - du) / 100 * len(kk)
        else:
            continue
        out.append({"group": g, "kind": kind, "sol": sol, "du": du, "n": len(kk), "text": text, "w": weight})
    out.sort(key=lambda r: -r["w"])
    return out[:limit]


def _examples(st, D, ks, limit: int = 4) -> list:
    from .facts import decode_cards, dt_of
    H = st.ft.H
    ks = [k for k in ks if D["fel"][k]]
    ks.sort(key=lambda k: -int(D["ts"][k]))
    out = []
    for k in ks[:limit]:
        j = int(D["hidx"][k])
        d = D["delta"][k]
        from .sessionfile import _cards
        hole = decode_cards(H["hole"][j])
        out.append({"hole": hole, "cards": _cards(hole), "act": ACT_TXT[int(D["act"][k])],
                    "sol": [float(x) for x in D["sf"][k]], "s_act": float(D["s_act"][k]),
                    "delta": None if np.isnan(d) else float(d), "date": dt_of(int(D["ts"][k])).strftime("%Y-%m-%d"),
                    "hand_id": str(H["id"][j])})
    return out


def training(st, tab, now: datetime | None = None, days: int = 7, top: int = 3, D=None) -> dict:
    """Träningsrutan: de `top` lägen som kostar mest i $/h de senaste `days` dagarna (2.83; tidigare flest klara fel
    per 100 händer, som fortfarande används om timtakten inte går att räkna).

    Mätning (förregistrerad, statistikern 2026-11-18): lägena väljs på urvalsveckan och mäts sedan på veckorna
    EFTER, mot de fyra veckorna före urvalsveckan – aldrig mot urvalsveckan själv (regression mot medel)."""
    D = D if D is not None else build(st, tab)
    if D is None:
        return {"empty": True}
    from .facts import dt_of
    now = now or dt_of(int(D["ts"].max()) + 1)
    t1 = _ts(now)
    t0 = _ts(now - timedelta(days=days))
    w = (D["ts"] >= t0) & (D["ts"] < t1)
    N = _hands_in(st, t0, t1)
    if not w.any() or not N:
        return {"empty": True}
    k_idx = np.flatnonzero(w)
    lagen = []
    for i, nd in enumerate(ALL_NODES):
        m = w & (D["node"] == i)
        n = int(m.sum())
        if n < MIN_BESLUT_LAGE:
            continue
        fel = int((m & D["fel"]).sum())
        felfold = int((m & D["fel"] & (D["act"] == 0)).sum())
        du_play = float((D["act"][m] > 0).mean() * 100)
        sol_play = float(D["play_sol"][m].mean())
        lagen.append({"node": nd, "label": NODE_LABEL[nd], "desc": NODE_DESC.get(nd, ""), "n": n, "fel": fel, "felfold": felfold,
                      "per100": 100.0 * fel / N, "share": 100.0 * fel / n, "du": du_play, "sol": sol_play,
                      "open": nd in OPEN_NODES, "i": i})
    # 2.83: kostnad i $/h = spelade klara fel per 100 händer (fönstret) × kostnad per fel i bb (hela urvalet,
    # krympt mot snittet över alla lägen) × händer per timme (fönstret) × bb i $ (fönstret). Felfoldar har okänd kostnad.
    hph, bb_usd = _pace(st, t0, t1)
    cost = _costs(D)
    for r in lagen:
        c = cost.get(r["i"], cost.get("all"))
        r["cost_bb"], r["cost_n"] = c
        r["fel_play"] = r["fel"] - r["felfold"]
        r["usd_h"] = (r["fel_play"] / N * hph * max(r["cost_bb"], 0.0) * bb_usd) if hph else None
    if hph:
        lagen.sort(key=lambda r: (-(r["usd_h"] or 0.0), -r["per100"]))
    else:
        lagen.sort(key=lambda r: -r["per100"])
    sel = lagen[:top]
    for r in sel:
        ks = [int(k) for k in k_idx if D["node"][k] == r["i"]]
        r["rules"] = rules_for(D, k_idx, r["i"])
        r["examples"] = _examples(st, D, ks)
        r["overcorr"] = bool(r["open"] and r["du"] < r["sol"] - OVERCORR_PP)
        r["weeks"] = weekly(st, D, r["i"], now)
    return {"empty": False, "days": days, "hands": N, "from": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to": now.strftime("%Y-%m-%d"), "lagen": sel, "all": lagen, "hph": hph, "bb_usd": bb_usd,
            "total_usd_h": (sum(r["usd_h"] or 0.0 for r in lagen) if hph else None),
            "total_fel": int((w & D["fel"]).sum()), "total_per100": 100.0 * int((w & D["fel"]).sum()) / N}


def weekly(st, D, node_i: int, now: datetime, weeks: int = 6) -> list:
    out = []
    for k in range(weeks, 0, -1):
        a = now - timedelta(days=7 * k)
        b = a + timedelta(days=7)
        t0, t1 = _ts(a), _ts(b)
        m = (D["ts"] >= t0) & (D["ts"] < t1) & (D["node"] == node_i)
        n = int(m.sum())
        out.append({"label": b.strftime("%d/%m"), "n": n,
                    "rate": float(100 * (m & D["fel"]).sum() / n) if n else None})
    return out


# ------------------------------------------------------------------ sessioner
def session_errors(st, D, t0: int, t1: int) -> dict:
    """Klara fel i ett pass: antal, per 100 händer och hand-id:n (för markering i sessionsfilen)."""
    if D is None:
        return {"n": 0, "fel": 0, "per100": None, "tvek": 0, "ids": {}}
    m = (D["ts"] >= t0) & (D["ts"] <= t1)
    N = _hands_in(st, t0, t1 + 1)
    H = st.ft.H
    ids = {}
    for k in np.flatnonzero(m):  # 2.78.1: per hand och läge (en hand kan ha både öppning och svar på 3-bet)
        nd = ALL_NODES[int(D["node"][k])]
        ids.setdefault(str(H["id"][int(D["hidx"][k])]), {})[nd] = {
            "v": "fel" if D["fel"][k] else ("tveksamt" if D["tvek"][k] else "ok"), "sol": [float(x) for x in D["sf"][k]],
            "s_act": float(D["s_act"][k]), "node": NODE_LABEL[nd], "act": int(D["act"][k])}
    fel = int((m & D["fel"]).sum())
    return {"n": int(m.sum()), "fel": fel, "tvek": int((m & D["tvek"]).sum()),
            "per100": 100.0 * fel / N if N else None, "hands": N, "ids": ids}


LONG_H = 4.0
EARLY_H = 2.0


def long_session_flag(st, D, t0: int, t1: int) -> dict | None:
    """4 h-flaggan (Andreas 2026-11-18): pass > 4 h varnas bara om passet ligger minus i all-in EV.
    Visar också om klara fel per 100 händer ökat efter 4 h jämfört med passets första 2 h (bättre tecken än EV)."""
    hrs = (t1 - t0) / 3600.0
    if hrs <= LONG_H:
        return None
    H = st.ft.H
    m = (H["ts"] >= t0) & (H["ts"] <= t1)
    if getattr(st, "mask", None) is not None:
        m &= st.mask
    ev = float(H["ev"][m].sum()) if "ev" in H else None
    out = {"hours": hrs, "ev_bb": ev, "warn": ev is not None and ev < 0}
    if D is not None:
        early = session_errors(st, D, t0, t0 + int(EARLY_H * 3600))
        late = session_errors(st, D, t0 + int(LONG_H * 3600), t1)
        out["early"] = early["per100"]
        out["late"] = late["per100"]
        out["worse"] = (early["per100"] is not None and late["per100"] is not None and late["hands"] >= 100
                        and late["per100"] > early["per100"])
    return out


# ------------------------------------------------------------------ träning med solvern som facit (punkt 11)
def trainer_scenarios(tab=None) -> list:
    nodes = [nd for nd in ALL_NODES if tab is None or nd in tab]
    return [{"key": f"sol|{nd}", "spot": "sol", "pos": nd, "label": f"🧮 {NODE_LABEL[nd]} – facit: solvern"} for nd in nodes]


_HARD = {}


def trainer_hand(tab, node: str, seed: int | None = None, focus: list | None = None) -> dict | None:
    """En slumpad 6-kortshand i solverläget. Facit: handling solvern gör ≥ 50 % = bäst, 10–50 % = blandat (räknas
    rätt), < 10 % = fel. Hälften av händerna dras ur grupper där solvern blandar eller där du ofta gör fel (focus)."""
    import random
    from .cards import card_str
    from .solverref import lookup
    if tab is None or node not in tab:
        return None
    rnd = random.Random(seed)
    deck = [(r, s) for r in range(2, 15) for s in "hdcs"]
    want_hard = rnd.random() < 0.5
    best = None
    for _ in range(3000):
        hole = rnd.sample(deck, 6)
        c = classify(hole)
        if not c:
            continue
        f, lvl, l2 = lookup(tab, node, c)
        if f is None:
            continue
        pr = EXTRA_PRIOR.get(node)  # 2.78: handen måste ha tagit sig hit (öppnat/3-bettat) – dra i proportion till det
        if pr and pr[0] in tab:
            fp = lookup(tab, pr[0], c)[0]
            if fp is None or rnd.random() * 100 > fp[pr[1]]:
                continue
        g = short(c[0], c[1], None)
        hard = (10 <= max(f) < 80) or (focus is not None and g in focus)
        best = (hole, f, c, l2, g)
        if hard == want_hard:
            break
    if best is None:
        return None
    hole, f, c, l2, g = best
    acts = ["fold", "call", "raise"]
    ok = [acts[i] for i in range(3) if f[i] >= TVEKSAMT]
    top = acts[int(np.argmax(f))]
    is_open = node in OPEN_NODES
    RAISE_WORD = {"F-F-RC5-RC16": "4-betta", "F-RC5-C-F": "squeeza", "F-F-RC5-C": "squeeza",
                  "RC5-F-C-F": "squeeza", "F-RC5-F-C": "squeeza", "F-RC5-C": "squeeza", "RC5-F-C": "squeeza",
                  "RC5-RC17": "4-betta", "RC5-RC17-F": "4-betta", "F-RC5-RC17": "4-betta", "RC5-C-C-F": "squeeza", "RC5-C-C": "squeeza",
                  "F-F-RC5-F-RC15-RC45": "all-in", "F-RC5-RC17-F-F-RC51": "all-in",
                  "RC5-RC17-RC58-F-F": "all-in", "RC5-C-RC24": "4-betta", "RC5-RC17-C-F": "4-betta", "RC5-F-C-C": "squeeza",
                  "RC5-C-C-C": "squeeza", "RC5-RC17-F-F": "4-betta", "RC5-C-RC24-F": "4-betta", "RC5-F-RC17-F": "4-betta",
                  "RC5-C-F-F": "squeeza"}
    word = {"fold": "folda", "call": "syna", "raise": "öppna" if is_open else RAISE_WORD.get(node, "4-betta" if node in EXTRA_PRIOR else "3-betta")}
    if node == "F-F-F-C":
        word = {"fold": "checka", "call": "–", "raise": "höja"}
    order = sorted(hole, key=lambda x: (-x[0], x[1]))
    return {"mode": "3bet", "spot": "sol", "pos": NODE_LABEL[node], "situation": NODE_DESC.get(node, "solverns facit"), "open_node": is_open or node == "F-F-F-C",
            "labels": {"fold": word["fold"].capitalize(), "call": word["call"].capitalize(), "raise": word["raise"].capitalize()},
            "cards": [[x[0], x[1]] for x in order], "text": " ".join(card_str(x) for x in order),
            "ok": ok, "best": f"solvern: {word['fold']} {f[0]:.0f} % · {word['call']} {f[1]:.0f} % · {word['raise']} {f[2]:.0f} %"
                              + ("" if is_open else ""),
            "note": f"Grupp: {short(c[0], c[1], l2)}. Bäst = {word[top]}. Under 10 % räknas som fel, 10–50 % som blandat (rätt).",
            "reasons": [], "nut": g}


_OPEN_CACHE = {}
OPEN_NODE = {"HJ": "root", "CO": "F", "BTN": "F-F", "SB": "F-F-F"}


def open_freq(tab, key: str = "", n: int = 6000) -> dict:
    """Solverns öppningsfrekvens per position (andel slumpade 6-kortshänder som spelas), för reglagets startvärde."""
    import random
    from .solverref import lookup
    if key and key in _OPEN_CACHE:
        return _OPEN_CACHE[key]
    rnd = random.Random(7)
    deck = [(r, s) for r in range(2, 15) for s in "hdcs"]
    acc = {p: [0.0, 0] for p in OPEN_NODE}
    for _ in range(n):
        c = classify(rnd.sample(deck, 6))
        if not c:
            continue
        for p, nd in OPEN_NODE.items():
            f, _l, _s = lookup(tab, nd, c)
            if f is not None:
                acc[p][0] += 100.0 - f[0]
                acc[p][1] += 1
    out = {p: round(a / k) for p, (a, k) in acc.items() if k}
    if key:
        _OPEN_CACHE[key] = out
    return out
