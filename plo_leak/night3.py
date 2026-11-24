"""🌙 Skuggmodell v3 (2.77.6): motståndarens range efter hans linje, kalibrerad mot visade händer.

Varför: v2 (night2) överskattar din vinstchans på river med 17–25 procentenheter (showdown-test 2026-11-18), eftersom
den antar att en check alltid betyder den svagare delen av rangen. v3 lär sig i stället hur poolen faktiskt agerar
med olika händer.

Modell (utvecklad och testad 2026-11-18 på 19 okt–12 nov, se projektdokumentet v3-utveckling-2026-11-18.md):
* Kandidater: K slumpade 6-kortshänder ur leken minus bord och dina kort.
* Egenskaper per kandidat och gata: percentil bland kandidaterna (0 = bäst), percentil², chans att bli topp 15 % på
  nästa kort (flop/turn), nöt (percentil < 3 %).
* Varje postflopbeslut motståndaren tar är ett val mellan tre handlingar (check / liten bet / stor bet, eller
  fold / syn / höj), en logistisk modell per gata × bet framför × position × föregående aggressor × storlek han möter.
* Preflop: solverns frekvens för motståndarens första preflophandling (i de 14 lägena) som vikt w^β, där β skattas –
  β < 1 = poolen spelar bredare än solvern.
* Anpassning: betingad likelihood för de visade händerna givet hela linjen. Urvalet (visade händer) beror bara på
  observerade handlingar, så skattningen är giltig trots att bara showdown-händer syns.
* Kalibrering: Platt-skalning av P(du vinner) på dina egna river-beslut, korsanpassad i två halvor (inget läckage).

Förregistrerat (2026-11-18, ändras inte): parametrarna anpassas en gång på händer FÖRE V3_FREEZE och fryses
(fingeravtryck). Testet gäller bara dina heads-up river-beslut som går till showdown (check bakom i position, syn mot
bet) EFTER V3_FREEZE. Avläsning vid 20, 40 och 80 spelpass, z = 2,13 (som v2):
  A. Brier v3 lägre än v2 på samma beslut (parat, klustrat per pass): diff + z·se < 0.
  B. Kalibrering: |medel(prognos − utfall)| + z·se < 0,05.
  C. Brier v3 lägre än slumpade händer (samma krav som A).
Godkänd = A och B och C. Underkänd = A:s intervall helt över 0 eller B:s bias visad > 0,05. Annars "inte avgjord" efter
80 pass. Före 20 pass visas inga siffror. Ger inga råd förrän godkänd.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import zlib
from datetime import datetime, timedelta

import numpy as np

VERSION = 1
V3_FREEZE = "2026-11-19"
TRAIN_DAYS = 40
K = 200
NEXT = 10
L2 = 0.05
LOOKS = (20, 40, 80)
Z = 2.13
STREETS = ("flop", "turn", "river")
NB = {"flop": 3, "turn": 4, "river": 5}
ST = {"flop": 0, "turn": 1, "river": 2}
NF = 5
NG = 3 * 2 * 2 * 2 * 2
SUIT = "cdhs"
MIN_TRAIN, MIN_CAL = 500, 100
PRED_POOL_MIN = 1500   # 2.79: färre nya händer än så räknas i huvudprocessen (att starta processer kostar några sekunder)
PLAN = ("v3/2026-11-18: frys före 2026-11-19; test heads-up river (check bakom, syn) efter frysdatum; "
        "avläsning 20/40/80 pass; A Brier < v2, B |bias| < 0,05, C Brier < slump; z 2,13")


# ------------------------------------------------------------------ egenskaper
def feats(cands, board, street, rng):
    """2.79: samma värden och samma slumpdragningar som tidigare, men bordets trippler och kandidaternas par räknas en
    gång och alla NEXT nästa-kort-bord utvärderas i ett anrop (fastev_delat)."""
    nb = NB[street]
    b = np.asarray(board[:nb], dtype=np.int64)
    from .fastev_delat import pairs_of, vs_boards
    pid, ps = pairs_of(cands)
    v = vs_boards(pid, ps, b[None, :])[0]
    sv = np.sort(v)[::-1]
    rank = np.searchsorted(-sv, -v, side="left") / len(v)
    if street == "river":
        imp = np.zeros(len(v))
    else:
        bset = set(b.tolist())
        pool = np.array([c for c in range(52) if c not in bset])
        nxt = rng.choice(pool, size=NEXT, replace=False)
        ok = ~(cands[None, :, :] == nxt[:, None, None]).any(2)                        # (NEXT, N)
        v2 = vs_boards(pid, ps, np.concatenate([np.repeat(b[None, :], len(nxt), 0), nxt[:, None]], 1))
        # plats bland de kandidater som kan ha handen = antal möjliga kandidater med strikt högre värde (som searchsorted)
        nok = ok.sum(1)
        off = (np.arange(len(nxt), dtype=np.int64) << 32)[:, None]
        srt = np.sort((np.where(ok, v2, -1) + off).ravel())                             # raderna efter varandra
        N = v2.shape[1]
        gt = (N - (np.searchsorted(srt, (v2 + off).ravel(), side="right").reshape(v2.shape) - off // (1 << 32) * N))
        r2 = gt / np.maximum(nok, 1)[:, None]
        hit = np.zeros(len(v))
        cnt = np.zeros(len(v))
        for i in range(len(nxt)):   # samma summeringsordning som tidigare (heltal – exakt ändå)
            hit += ok[i] * (r2[i] < 0.15)
            cnt += ok[i]
        imp = hit / np.maximum(cnt, 1)
    return np.stack([rank, rank ** 2, imp, (rank < 0.03).astype(float)], 1).astype(np.float32)


def line_of(h, player):
    """(gata, bet framför 0/1, ip 0/1, handling 0/1/2, föregående aggressor 0/1, storlek han möter 0/1)."""
    out = []
    pot = sum(a.added for a in h.actions if a.street == "preflop")
    prev_aggr = 0
    for st in STREETS:
        acts = [a for a in h.actions if a.street == st and not a.kind.startswith("post")]
        if not acts:
            continue
        order = []
        for a in acts:
            if a.player not in order:
                order.append(a.player)
        bet, face, aggr_now = False, 0.0, 0
        for a in acts:
            if a.player == player:
                ip = int(order[-1] == player)
                if not bet:
                    if a.kind == "check":
                        out.append((st, 0, ip, 0, prev_aggr, 0))
                    elif a.kind == "bet":
                        out.append((st, 0, ip, 1 if a.added < 0.55 * max(pot, 1e-9) else 2, prev_aggr, 0))
                else:
                    act = {"fold": 0, "call": 1, "raise": 2}.get(a.kind)
                    if act is not None:
                        out.append((st, 1, ip, act, prev_aggr, int(face >= 0.55)))
                if a.kind in ("bet", "raise"):
                    aggr_now = 1
            if a.kind in ("bet", "raise"):
                face = a.added / max(pot, 1e-9)
                bet = True
            pot += a.added
        prev_aggr = aggr_now
    return out


_PFC: dict = {"tab": None, "memo": {}, "groups": {}}


def _class_keys(cands):
    """Nyckel som bestämmer solvergroups.classify helt (kontrolleras i testerna mot classify på slumpade händer):
    trips/quads -> -1; utan par: valörerna; med par: antal par, högsta parets valör, minst två klädda kort utanför paren,
    ess finns. Dessutom färgantalen (sorterade) och antal ess i en färg med minst två kort (högst 2 räknas)."""
    c = np.asarray(cands, dtype=np.int64)
    r, s = c // 4, c % 4
    rc = (r[:, :, None] == np.arange(13)).sum(1)                                  # (N, 13)
    trips = rc.max(1) >= 3
    npair = (rc == 2).sum(1)
    top = np.where(rc == 2, np.arange(13), -1).max(1)
    bw = ((rc == 1) & (np.arange(13) >= 8)).sum(1) >= 2
    has_a = rc[:, 12] > 0
    rs = np.sort(r, axis=1)
    rk = np.zeros(len(c), np.int64)
    for i in range(c.shape[1]):
        rk = rk * 13 + rs[:, i]
    base = np.where(npair == 0, rk, 5_000_000 + ((npair * 13 + top) * 2 + bw) * 2 + has_a)
    sc = (s[:, :, None] == np.arange(4)).sum(1)                                   # (N, 4)
    scs = np.sort(sc, axis=1)
    sk = ((scs[:, 0] * 7 + scs[:, 1]) * 7 + scs[:, 2]) * 7 + scs[:, 3]
    nut = np.minimum(((r == 12) & (np.take_along_axis(sc, s, 1) >= 2)).sum(1), 2)
    return np.where(trips, -1, (base * 2401 + sk) * 3 + nut)


def pf_logw(tab, h, player, cands):
    """2.79: samma vikt som tidigare – men classify + lookup räknas en gång per handklass (nyckel ovan) och läge."""
    from .solvergroups import NODES, classify, node_of
    from .solverref import lookup
    if tab is None:
        return None
    nd = node_of(h, player)
    if nd is None or nd[1] == 0:
        return None
    ni, act = nd
    if _PFC["tab"] is not tab:
        _PFC["tab"], _PFC["memo"] = tab, {}
    memo, groups = _PFC["memo"], _PFC["groups"]
    out = np.empty(len(cands), np.float32)
    for k, key in enumerate(_class_keys(cands).tolist()):
        val = memo.get((ni, act, key))
        if val is None:
            g = groups.get(key, False)
            if g is False:
                c = cands[k]
                g = groups[key] = classify([(int(x) // 4 + 2, SUIT[int(x) % 4]) for x in c])
            f = lookup(tab, NODES[ni], g)[0] if g else None
            val = memo[(ni, act, key)] = np.log(max((f[act] if f is not None else 0.0) / 100.0, 0.005))
        out[k] = val
    return out


def _codes(cards):
    from .fastev import codes
    return codes(cards)


def _deck_minus(dead):
    d = set(dead)
    return np.array([c for c in range(52) if c not in d])


def train_item(h, hero, player, tab, rng):
    shown = (h.shown or {}).get(player)
    if not shown or len(shown) != 6 or not h.hole.get(hero):
        return None
    L = line_of(h, player)
    if not L:
        return None
    b = _codes(h.board)
    true = np.array(_codes(shown))
    pool = _deck_minus(b + _codes(h.hole[hero]) + true.tolist())
    cands = np.stack([true] + [rng.choice(pool, 6, replace=False) for _ in range(K - 1)])
    return {"id": h.id, "line": L, "F": {s: feats(cands, b, s, rng) for s in {x[0] for x in L}}, "pf": pf_logw(tab, h, player, cands)}


def hero_item(h, hero, tab, rng):
    """Heros heads-up river-beslut som går till showdown: check bakom i position eller syn mot bet."""
    from .fastev import best_values
    if len(h.board) != 5 or len(h.remaining()) != 2 or hero not in h.remaining() or not h.hole.get(hero):
        return None
    v = [p for p in h.remaining() if p != hero][0]
    shown = (h.shown or {}).get(v)
    if not shown or len(shown) != 6:
        return None
    ra = [a for a in h.actions if a.street == "river" and not a.kind.startswith("post")]
    hr = [a for a in ra if a.player == hero]
    if not hr:
        return None
    last = hr[-1]
    if last.kind == "check" and ra[-1] is last and ra[0].player == v and ra[0].kind == "check":
        kind = "check_bakom"
    elif last.kind == "call":
        kind = "syn"
    else:
        return None
    L = line_of(h, v)
    idx = ra.index(last)
    nv = sum(1 for a in ra[:idx] if a.player == v and a.kind in ("check", "bet", "call", "raise"))
    L = [x for x in L if x[0] != "river"] + [x for x in L if x[0] == "river"][:nv]
    b = _codes(h.board)
    hc = _codes(h.hole[hero])
    pool = _deck_minus(b + hc)
    cands = np.stack([rng.choice(pool, 6, replace=False) for _ in range(K)])
    hv = best_values(np.array([hc]), np.array([b]))[0]
    from .fastev_delat import vs_board
    cv = vs_board(cands, b)
    tv = best_values(np.array([_codes(shown)]), np.array([b]))[0]
    return {"id": h.id, "kind": kind, "line": L, "F": {s: feats(cands, b, s, rng) for s in {x[0] for x in L} | {"river"}},
            "pf": pf_logw(tab, h, v, cands), "win_c": ((hv > cv) + 0.5 * (hv == cv)).astype(np.float32),
            "won": 1.0 if hv > tv else (0.5 if hv == tv else 0.0)}


# ------------------------------------------------------------------ modell
def group(st, fac, ip, pa, sz):
    return (((ST[st] * 2 + fac) * 2 + ip) * 2 + pa) * 2 + sz


def _logp(W, X, G):
    from scipy.special import logsumexp
    lg = np.einsum("dkf,daf->dka", X, W[G])
    lg = np.concatenate([np.zeros(lg.shape[:2] + (1,)), lg], 2)
    return lg - logsumexp(lg, axis=2, keepdims=True)


def design(items):
    """Anpassningens indata: X (D, K, 1+4) float32, grupp G, handling A, item-index I (stigande), preflopvikt PF (NI, K)."""
    D = sum(len(it["line"]) for it in items)
    Kc = len(next(iter(items[0]["F"].values()))) if items else K
    X = np.empty((D, Kc, NF), np.float32)
    X[:, :, 0] = 1.0
    G = np.empty(D, np.int64)
    A = np.empty(D, np.int64)
    I = np.empty(D, np.int64)
    d = 0
    for i, it in enumerate(items):
        for (st, fac, ip, a, pa, sz) in it["line"]:
            X[d, :, 1:] = it["F"][st]
            G[d], A[d], I[d] = group(st, fac, ip, pa, sz), a, i
            d += 1
    PF = np.zeros((len(items), Kc), np.float32)
    for i, it in enumerate(items):
        if it.get("pf") is not None:
            PF[i] = it["pf"]
    return X, G, A, I, PF


def _lse3(l1, l2):
    """logsumexp över [0, l1, l2] (sista axeln) med exakt samma räkneordning som scipy.special.logsumexp (≥ 1.15):
    max, antal maxima m, summan av de övriga exp(a − max)/m, log1p(s) + log(m) + max. Utan mellanarrayer (D, K, 3)."""
    mx = np.maximum(np.maximum(0.0, l1), l2)
    m0, m1, m2 = mx == 0.0, l1 == mx, l2 == mx
    m = m0.astype(np.float64)
    m += m1
    m += m2
    e = np.where(m0, 0.0, np.exp(0.0 - mx))
    e += np.where(m1, 0.0, np.exp(l1 - mx))
    e += np.where(m2, 0.0, np.exp(l2 - mx))
    s = np.where(e == 0, e, e / m)
    out = np.log1p(s) + np.log(m) + mx
    return out


_LSE3_OK: dict = {}


def _lse3_ok() -> bool:
    """Ger _lse3 bit för bit samma svar som den installerade scipy? (Annars används scipy direkt – samma resultat som
    före 2.79, bara långsammare.)"""
    if "ok" not in _LSE3_OK:
        from scipy.special import logsumexp
        r = np.random.default_rng(0)
        l1 = np.concatenate([r.normal(0, 3, 20000), np.zeros(50), r.normal(0, 40, 2000)])
        l2 = np.concatenate([r.normal(0, 3, 20000), np.zeros(50), r.normal(0, 40, 2000)])
        l2[:500] = l1[:500]
        a = np.stack([np.zeros_like(l1), l1, l2], 1)
        try:
            ref = logsumexp(a, axis=1)
            _LSE3_OK["ok"] = bool(np.array_equal(ref, _lse3(l1, l2)))
        except Exception:
            _LSE3_OK["ok"] = False
    return _LSE3_OK["ok"]


def fit(items, maxiter: int = 300):
    return fit_design(*design(items), maxiter=maxiter)


def fit_design(X, G, A, I, PF, maxiter: int = 300):
    """2.79: samma likelihood, gradient och L-BFGS som tidigare (samma einsum-anrop, samma summeringsordning), men
    softmax över tre handlingar räknas kolumnvis utan (D, K, 3)-mellanarrayer, Σ per hand med reduceat i stället för
    np.add.at och gradienten per grupp med bincount (samma ordning som add.at)."""
    from scipy.optimize import minimize
    from scipy.special import logsumexp
    D, Kc, _ = X.shape
    NI = len(PF)
    starts = np.flatnonzero(np.r_[True, I[1:] != I[:-1]]) if D else np.zeros(0, np.int64)
    if len(starts) != NI or (D and not np.array_equal(I[starts], np.arange(NI))):  # varje hand måste ha minst en rad
        starts = None
    steps = []
    if starts is not None:
        ln = np.diff(np.r_[starts, D])
        steps = [(j, np.flatnonzero(ln > j)) for j in range(1, int(ln.max()) if NI else 1)]
    fast = _lse3_ok()
    A1, A2 = (A == 1)[:, None], (A == 2)[:, None]
    Ar = np.arange(D)

    def loss(wb):
        w, beta = wb[:-1], wb[-1]
        W = w.reshape(NG, 2, NF)
        if fast:
            lg = np.einsum("dkf,daf->dak", X, W[G])   # samma produkter och summor som "…->dka", bara kolumnvis lagrat
            l1, l2 = lg[:, 0], lg[:, 1]
            lse = _lse3(l1, l2)
            lp1 = l1 - lse
            lp2 = l2 - lse
            del lg
            la = np.where(A1, lp1, np.where(A2, lp2, 0.0 - lse))
            del lse
            pi1 = np.exp(lp1)
            del lp1
            pi2 = np.exp(lp2)
            del lp2
        else:
            lp = _logp(W, X, G)
            la = lp[Ar, :, A]
            pi1, pi2 = np.exp(lp[:, :, 1]), np.exp(lp[:, :, 2])
            del lp
        if starts is not None:
            S = 0.0 + la[starts]                       # samma ordning som add.at: 0 + första + andra + …
            for j, ix in steps:
                S[ix] += la[starts[ix] + j]
        else:
            S = np.zeros((NI, Kc))
            np.add.at(S, I, la)
        del la
        S = S + beta * PF
        lse2 = logsumexp(S, 1, keepdims=True)
        post = np.exp(S - lse2)
        ll = (S[:, 0] - lse2[:, 0]).sum()
        r = -post
        r[:, 0] += 1.0
        rd = r[I]
        grad = np.zeros_like(W)
        for a, Aa, pa in ((1, A1, pi1), (2, A2, pi2)):
            gw = np.einsum("dk,dkf->df", np.nan_to_num(rd * (Aa - pa)), X)
            for f in range(NF):
                grad[:, a - 1, f] = np.bincount(G, weights=gw[:, f], minlength=NG)
        gb = (PF[:, 0] - (post * PF).sum(1)).sum()
        return -ll + L2 * (w ** 2).sum(), np.append(-grad.ravel() + 2 * L2 * w, -gb)

    res = minimize(loss, np.zeros(NG * 2 * NF + 1), jac=True, method="L-BFGS-B", options={"maxiter": maxiter})
    return {"W": res.x[:-1].reshape(NG, 2, NF), "beta": float(res.x[-1]), "ll": float(-res.fun / max(NI, 1)), "n": NI}


def predict(model, it) -> float:
    from scipy.special import expit, logit, logsumexp
    W, beta = model["W"], model["beta"]
    S = np.zeros(len(it["win_c"]))
    for (st, fac, ip, a, pa, sz) in it["line"]:
        f = it["F"][st]
        x = np.concatenate([np.ones((len(f), 1), np.float32), f], 1)[None]
        S += _logp(W, x, np.array([group(st, fac, ip, pa, sz)]))[0][:, a]
    if it.get("pf") is not None:
        S = S + beta * it["pf"]
    p = float((np.exp(S - logsumexp(S)) * it["win_c"]).sum())
    a, b = model.get("platt", (1.0, 0.0))
    return float(expit(a * logit(min(max(p, 1e-3), 1 - 1e-3)) + b))


def _platt(p, y):
    from scipy.optimize import minimize
    from scipy.special import expit, logit
    z = logit(np.clip(np.asarray(p), 1e-3, 1 - 1e-3))
    y = np.asarray(y)

    def f(ab):
        q = np.clip(expit(ab[0] * z + ab[1]), 1e-6, 1 - 1e-6)
        return -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))
    return tuple(float(x) for x in minimize(f, [1.0, 0.0], method="Nelder-Mead").x)


def model_hash(model) -> str:
    h = hashlib.sha256()
    h.update(np.round(model["W"], 6).tobytes())
    h.update(json.dumps([round(model["beta"], 6), [round(x, 6) for x in model.get("platt", (1, 0))], VERSION, PLAN]).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ lagring
def store_path(db):
    from .nightly import cache_dir
    return cache_dir(db) / (db.path.stem + "_night3.pkl")


def load(db) -> dict:
    try:
        return pickle.load(open(store_path(db), "rb"))
    except Exception:
        return {}


def save(db, S: dict) -> None:
    p = store_path(db)
    tmp = p.with_suffix(".tmp")
    pickle.dump(S, open(tmp, "wb"))
    tmp.replace(p)


def _freeze_ts():
    from .facts import ts_of
    return ts_of(datetime.strptime(V3_FREEZE, "%Y-%m-%d"))


# ------------------------------------------------------------------ parallellt (2.78.2)
_WK: dict = {}


def _init_worker(db_path, hero):
    import os
    from types import SimpleNamespace
    from .db import HandDB
    _low()
    _WK["low"] = True
    _WK["db"] = HandDB(db_path)
    _WK["hero"] = hero
    _WK["tab"] = solver_tab(SimpleNamespace(path=__import__("pathlib").Path(db_path)))


def _low():
    try:
        import os
        import sys
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(10)
    except Exception:
        pass


def _feat_chunk(args):
    ids, seed = args
    rng = np.random.default_rng(seed)
    db, hero, tab = _WK["db"], _WK["hero"], _WK["tab"]
    train, cal = [], []
    for hid in ids:
        h = db.get_hand(hid)
        if h is None or len(h.board) != 5:
            continue
        for p in h.remaining():
            if p != hero:
                it = train_item(h, hero, p, tab, rng)
                if it:
                    train.append(it)
        it = hero_item(h, hero, tab, rng)
        if it:
            cal.append(it)
    return train, cal


def _fit_job(items):
    _low()
    return fit(items)


def _fit_arrays(args):
    """2.79: anpassning från färdiga indata (design) – körs i samma förvärmda processer som egenskaperna."""
    if not _WK.get("low"):
        _low()
        _WK["low"] = True
    return fit_design(*args)


def _pred_chunk(args):
    """Prognoser för en del av de nya händerna (samma frö per hand som i huvudprocessen: crc32(hand-id))."""
    hids, model = args
    db, hero, tab = _WK["db"], _WK["hero"], _WK["tab"]
    out = []
    for hid in hids:
        h = db.get_hand(hid)
        it = hero_item(h, hero, tab, np.random.default_rng(zlib.crc32(hid.encode()))) if h is not None else None
        out.append(None if it is None else {"kind": it["kind"], "p": predict(model, it), "won": it["won"],
                                            "rand": float(it["win_c"].mean())})
    return out


def _pool(db, hero, P):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    return ProcessPoolExecutor(max_workers=P, mp_context=mp.get_context("spawn"), initializer=_init_worker,
                               initargs=(str(db.path), hero))


def _procs(procs=None) -> int:
    import os
    from .night import cpu_procs
    return procs or cpu_procs()


# ------------------------------------------------------------------ körning
def run(job, db, st, hero, get_hand, tab=None, deadline=None, procs=None) -> str:
    """Anpassa (en gång, före frysdatum) och räkna prognoser för nya river-beslut efter frysdatum."""
    import time
    try:
        import scipy  # noqa: F401
    except ImportError:
        return ("v3: paketet scipy saknas – starta programmet med startfilen (Starta Windows/Mac) så installeras det, "
                "och kör nattkörningen igen")
    S = load(db)
    H = st.ft.H
    rows = np.asarray(st.rows, dtype=np.int64)
    t_freeze = _freeze_ts()
    rng = np.random.default_rng(18)
    P = _procs(procs)
    use_pool = P > 1 and getattr(db, "path", None) is not None
    ex = None
    try:
        if "model" not in S:
            job.set("v3: bygger träningsdata (visade händer före frysdatum)")
            t0 = t_freeze - TRAIN_DAYS * 86400
            ids = [str(H["id"][j]) for j in rows if t0 <= int(H["ts"][j]) < t_freeze]
            train, cal = [], []
            if use_pool:  # 2.78.2: alla kärnor utom en, låg prioritet. 2.79: samma processer används sedan till anpassningen
                ex = _pool(db, hero, P)
                chunks = [ids[i:i + 400] for i in range(0, len(ids), 400)]
                for n, (tr, ca) in enumerate(ex.map(_feat_chunk, [(c, 18 + k) for k, c in enumerate(chunks)])):
                    train += tr
                    cal += ca
                    job.set(f"v3: träningsdata {min((n + 1) * 400, len(ids))}/{len(ids)} händer · {len(train)} visade händer · {P} processer")
                    if deadline and time.time() > deadline:
                        return "v3: tiden tog slut innan träningen var klar – fortsätter nästa natt"
            else:
                for n, hid in enumerate(ids):
                    if deadline and time.time() > deadline:
                        return "v3: tiden tog slut innan träningen var klar – fortsätter nästa natt"
                    h = get_hand(hid)
                    if h is None or len(h.board) != 5:
                        continue
                    for p in h.remaining():
                        if p != hero:
                            it = train_item(h, hero, p, tab, rng)
                            if it:
                                train.append(it)
                    it = hero_item(h, hero, tab, rng)
                    if it:
                        cal.append(it)
                    if n % 2000 == 0:
                        job.set(f"v3: träningsdata {n}/{len(ids)} händer · {len(train)} visade händer")
            if len(train) < MIN_TRAIN or len(cal) < MIN_CAL:
                return f"v3: för lite data före frysdatum ({len(train)} visade händer, {len(cal)} egna beslut)"
            job.set("v3: korsanpassning för kalibrering")
            fold = lambda hid: zlib.crc32(hid.encode()) % 2  # noqa: E731
            sets = [[t for t in train if fold(t["id"]) != 0], [t for t in train if fold(t["id"]) != 1], train]
            n_train = len(train)
            if P > 1:  # de tre anpassningarna samtidigt (indata byggs här en gång per mängd; F behövs inte längre efteråt)
                job.set("v3: anpassar modellen (tre anpassningar parallellt)")
                des = [design(x) for x in sets]
                del sets, train
                if ex is None:
                    from concurrent.futures import ProcessPoolExecutor
                    import multiprocessing as mp
                    ex = ProcessPoolExecutor(max_workers=min(P, 3), mp_context=mp.get_context("spawn"))
                futs = {k: ex.submit(_fit_arrays, des[k]) for k in (2, 0, 1)}   # största först
                del des
                fits = [futs[k].result() for k in (0, 1, 2)]
            else:
                fits = [fit(x) for x in sets]
                del sets, train
            cp, cy = [], []
            for f in (0, 1):
                m = fits[f]
                for t in cal:
                    if fold(t["id"]) == f:
                        cp.append(predict({**m, "platt": (1.0, 0.0)}, t))
                        cy.append(t["won"])
            model = fits[2]
            model["platt"] = _platt(cp, cy)
            model["hash"] = model_hash(model)
            model["trained"] = datetime.now().isoformat(timespec="seconds")
            model["n_train"], model["n_cal"] = n_train, len(cal)
            S = {"model": model, "pred": {}, "version": VERSION, "plan": PLAN}
            save(db, S)
        model = S["model"]
        pred = S.setdefault("pred", {})
        job.set("v3: prognoser för nya river-beslut")
        todo = []
        for j in rows:
            if int(H["ts"][j]) < t_freeze or not bool(H["sd"][j]):
                continue
            hid = str(H["id"][j])
            if hid in pred:
                continue
            todo.append((hid, int(j)))
        new = len(todo)
        if use_pool and len(todo) >= PRED_POOL_MIN:  # 2.79: många nya händer – dela på kärnorna (resultat i samma ordning)
            if ex is None:
                ex = _pool(db, hero, P)
            step = max(50, min(400, len(todo) // (4 * P) + 1))
            parts = [todo[i:i + step] for i in range(0, len(todo), step)]
            for part, res in zip(parts, ex.map(_pred_chunk, [([h for h, _j in part], model) for part in parts])):
                for (hid, j), r in zip(part, res):
                    pred[hid] = None if r is None else {**r, "clu": int(H["clu"][j]), "ts": int(H["ts"][j])}
        else:
            for hid, j in todo:
                h = get_hand(hid)
                it = hero_item(h, hero, tab, np.random.default_rng(zlib.crc32(hid.encode()))) if h is not None else None
                pred[hid] = None if it is None else {"kind": it["kind"], "p": predict(model, it), "won": it["won"],
                                                    "rand": float(it["win_c"].mean()), "clu": int(H["clu"][j]), "ts": int(H["ts"][j])}
    finally:
        if ex is not None:
            ex.shutdown(wait=True, cancel_futures=True)
    save(db, S)
    return f"v3: {new} nya händer kontrollerade · modell {model['hash']}"


def acceptance(db, v2_eq: dict | None = None) -> dict:
    """Förregistrerat test. v2_eq: {hand_id: v2:s vinstchans på samma river-beslut} om den finns."""
    from .statlib import cluster_se
    S = load(db)
    if "model" not in S:
        return {"status": "ingen modell", "plan": PLAN}
    P = [(k, v) for k, v in (S.get("pred") or {}).items() if v]
    first = {}
    for _k, v in P:  # passen i tidsordning (pass-id är hashade)
        first[v["clu"]] = min(first.get(v["clu"], 1 << 62), v.get("ts", 0))
    clusters = sorted(first, key=first.get)
    out = {"status": "väntar", "plan": PLAN, "hash": S["model"]["hash"], "n": len(P), "clusters": len(clusters),
           "need": LOOKS[0], "beta": S["model"]["beta"]}
    if len(clusters) < LOOKS[0]:
        return out
    K_ = max(x for x in LOOKS if x <= len(clusters))
    keep = set(clusters[:K_])
    P = [(k, v) for k, v in P if v["clu"] in keep]
    p = np.array([v["p"] for _k, v in P])
    y = np.array([v["won"] for _k, v in P])
    r = np.array([v["rand"] for _k, v in P])
    c = np.array([v["clu"] for _k, v in P])
    bias = float((p - y).mean())
    se_b = float(cluster_se(p - y, c))
    dC = (p - y) ** 2 - (r - y) ** 2
    C_ok = float(dC.mean()) + Z * float(cluster_se(dC, c)) < 0
    out.update(look=K_, bias=bias, bias_se=se_b, brier=float(((p - y) ** 2).mean()), brier_rand=float(((r - y) ** 2).mean()))
    A_ok = A_bad = None
    if v2_eq:
        m = np.array([k in v2_eq for k, _v in P])
        if m.sum() >= 30:
            q = np.array([v2_eq[k] for k, _v in P if k in v2_eq])
            dA = (p[m] - y[m]) ** 2 - (q - y[m]) ** 2
            seA = float(cluster_se(dA, c[m]))
            A_ok = float(dA.mean()) + Z * seA < 0
            A_bad = float(dA.mean()) - Z * seA > 0
            out.update(brier_v2=float(((q - y[m]) ** 2).mean()), n_v2=int(m.sum()))
    B_ok = abs(bias) + Z * se_b < 0.05
    B_bad = abs(bias) - Z * se_b > 0.05
    if A_ok and B_ok and C_ok:
        out["status"] = "godkänd"
    elif A_bad or B_bad:
        out["status"] = "underkänd"
    elif K_ >= LOOKS[-1]:
        out["status"] = "inte avgjord"
    else:
        out["status"] = "pågår"
    out.update(A=A_ok, B=B_ok, C=C_ok)
    return out


def v2_river_eq(db) -> dict:
    """v2:s vinstchans vid ditt sista river-beslut per hand (night2-tabellen), för jämförelse A."""
    try:
        rows = db.con.execute("SELECT hand_id, ord, eq FROM night2 WHERE street='river' AND eq IS NOT NULL").fetchall()
    except Exception:
        return {}
    out = {}
    for hid, o, eq in rows:
        if hid not in out or o > out[hid][0]:
            out[hid] = (o, eq)
    return {k: float(v[1]) for k, v in out.items()}


def solver_tab(db):
    """Solvertabellen för preflop-vikten (läses lokalt; inget av den sparas i v3:s resultat utom β)."""
    try:
        from .solverref import load as _load
        return _load(db)[0]
    except Exception:
        return None
