"""Vektoriserad handutvärdering (simuleringsmotorn).

Samma tabeller och samma handvärden som ev.fast_best – men tusentals händer utvärderas på en
gång med numpy i stället för en i taget i Python. Används för equity (all-in EV, uppspelning)
och simuleringar.

Kort kodas som heltal 0–51: valör = kod // 4 + 2, färg = kod % 4 (c, d, h, s).
"""
from __future__ import annotations

import random
from itertools import combinations

import numpy as np

from .ev import CATEGORY, FLUSH, NONFLUSH, PRIMES

SUITS = "cdhs"
_PR = np.array([PRIMES[r] for r in range(2, 15)], dtype=np.int64)
_NF_K = np.array(sorted(NONFLUSH), dtype=np.int64)
_NF_V = np.array([NONFLUSH[k] for k in _NF_K.tolist()], dtype=np.int32)
_FL_K = np.array(sorted(FLUSH), dtype=np.int64)
_FL_V = np.array([FLUSH[k] for k in _FL_K.tolist()], dtype=np.int32)
CATEGORY_A = np.array(CATEGORY, dtype=np.int8)
_PAIRS = {k: np.array(list(combinations(range(k), 2)), dtype=np.intp) for k in range(2, 8)}
_TRIPLES_BY = {nb: np.array(list(combinations(range(nb), 3)), dtype=np.intp) for nb in (3, 4, 5)}
_TRIPLES = _TRIPLES_BY[5]
CHUNK = 40_000


def _build_luts():
    """Direkta uppslagstabeller: (valörpar, valörtrippel) -> handvärde, utan och med färg."""
    pid = np.full((13, 13), -1, dtype=np.int32)
    pairs = []
    for a in range(13):
        for b in range(a, 13):
            pid[a, b] = pid[b, a] = len(pairs)
            pairs.append((a, b))
    tid = np.full((13, 13, 13), -1, dtype=np.int32)
    tris = []
    for a in range(13):
        for b in range(a, 13):
            for c in range(b, 13):
                i = len(tris)
                tris.append((a, b, c))
                for x, y, z in {(a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)}:
                    tid[x, y, z] = i
    nf = np.full((len(pairs), len(tris)), -1, dtype=np.int32)
    fl = np.full((len(pairs), len(tris)), -1, dtype=np.int32)
    for i, (a, b) in enumerate(pairs):
        for j, (x, y, z) in enumerate(tris):
            ranks = (a, b, x, y, z)
            prod = 1
            for r in ranks:
                prod *= int(_PR[r])
            if prod in NONFLUSH:
                nf[i, j] = NONFLUSH[prod]
            if len(set(ranks)) == 5 and prod in FLUSH:
                fl[i, j] = FLUSH[prod]
    return pid, tid, nf, fl


_PID, _TID, _NF_LUT, _FL_LUT = _build_luts()


def code(c) -> int:
    return (c[0] - 2) * 4 + SUITS.index(c[1])


def codes(cards) -> list:
    return [code(c) for c in cards]


def best_values(holes: np.ndarray, boards: np.ndarray) -> np.ndarray:
    """Bästa Omaha-handvärde (exakt två hålkort + tre bordskort) för varje rad.
    holes: (N, k) kortkoder, boards: (N, 3–5) kortkoder. Returnerar (N,) handvärden (större = bättre)."""
    holes = np.asarray(holes, dtype=np.int64)
    boards = np.asarray(boards, dtype=np.int64)
    n = len(holes)
    out = np.empty(n, dtype=np.int32)
    pi = _PAIRS[holes.shape[1]]
    for a in range(0, n, CHUNK):
        h = holes[a:a + CHUNK]
        b = boards[a:a + CHUNK]
        hr, hs = h // 4 - 0, h % 4
        br, bs = b // 4, b % 4
        p0, p1 = pi[:, 0], pi[:, 1]
        t = _TRIPLES_BY[b.shape[1]]
        pid = _PID[hr[:, p0], hr[:, p1]]                                         # (m, P)
        psuit = np.where(hs[:, p0] == hs[:, p1], hs[:, p0], -1)
        tid = _TID[br[:, t[:, 0]], br[:, t[:, 1]], br[:, t[:, 2]]]               # (m, T)
        same = (bs[:, t[:, 0]] == bs[:, t[:, 1]]) & (bs[:, t[:, 1]] == bs[:, t[:, 2]])
        tsuit = np.where(same, bs[:, t[:, 0]], -2)
        v = _NF_LUT[pid[:, :, None], tid[:, None, :]]                            # (m, P, T)
        flush = psuit[:, :, None] == tsuit[:, None, :]
        if flush.any():
            fv = _FL_LUT[pid[:, :, None], tid[:, None, :]]
            v = np.where(flush, fv, v)
        out[a:a + CHUNK] = v.reshape(len(h), -1).max(axis=1)
    return out


def best_values_hole(hole_codes, boards: np.ndarray) -> np.ndarray:
    """Samma som best_values(np.broadcast_to(hole, (N, k)), boards), men för EN hand mot många bord.

    Eftersom handen är densamma i alla rader slås paren ihop i förväg: för varje valörtrippel tas
    det bästa värdet över handens alla par (utan färg), och per färg det bästa färgvärdet över
    handens par i den färgen. En färg (alla fem kort i samma färg) har alltid fem olika valörer och
    slår alltid samma valörer utan färg, så max(utan färg, färg där färgen stämmer) blir exakt
    samma värde som i best_values – men uppslagen blir N·T i stället för N·P·T."""
    hc = np.asarray(hole_codes, dtype=np.int64)
    boards = np.asarray(boards, dtype=np.int64)
    n = len(boards)
    out = np.empty(n, dtype=np.int32)
    if n == 0:
        return out
    pi = _PAIRS[len(hc)]
    hr, hs = hc // 4, hc % 4
    pid = _PID[hr[pi[:, 0]], hr[pi[:, 1]]]                                      # (P,)
    psuit = np.where(hs[pi[:, 0]] == hs[pi[:, 1]], hs[pi[:, 0]], -1)
    m_nf = _NF_LUT[pid].max(axis=0)                                            # (antal trippler,)
    m_fl = np.full((5, _FL_LUT.shape[1]), -1, dtype=np.int32)                   # rad 4 = ingen färg
    for s_ in range(4):
        sel = pid[psuit == s_]
        if len(sel):
            m_fl[s_] = _FL_LUT[sel].max(axis=0)
    t = _TRIPLES_BY[boards.shape[1]]
    for a in range(0, n, CHUNK):
        b = boards[a:a + CHUNK]
        br, bs = b // 4, b % 4
        tid = _TID[br[:, t[:, 0]], br[:, t[:, 1]], br[:, t[:, 2]]]               # (m, T)
        same = (bs[:, t[:, 0]] == bs[:, t[:, 1]]) & (bs[:, t[:, 1]] == bs[:, t[:, 2]])
        tsuit = np.where(same, bs[:, t[:, 0]], 4)
        v = np.maximum(m_nf[tid], m_fl[tsuit, tid])
        out[a:a + CHUNK] = v.max(axis=1)
    return out


def _share(vals: np.ndarray) -> np.ndarray:
    """vals: (R, P) handvärden per utfall och spelare -> summerad andel av potten per spelare."""
    top = vals.max(axis=1, keepdims=True)
    win = vals == top
    return (win / win.sum(axis=1, keepdims=True)).sum(axis=0)


def equities(holes: dict, board: list, dead: list = (), samples: int = 1500, seed: int = 0) -> dict:
    """Som ev.equities – exakt samma utfall (samma uppräkning och samma slumpdragningar) – men
    alla utfall utvärderas på en gång."""
    used = set(board) | set(dead)
    for h in holes.values():
        used |= set(h)
    # samma lek och samma ordning som förut, men som kortkoder (urvalet beror bara på lekens längd)
    deck = [code((r, s)) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    need = 5 - len(board)
    names = list(holes)
    if need == 0:
        runs = [()]
    else:
        from math import comb
        if comb(len(deck), need) <= samples:
            runs = list(combinations(deck, need))
        else:
            runs = _sample_runs(random.Random(seed), deck, need, samples)
    R = len(runs)
    bcodes = np.array(codes(board), dtype=np.int64)
    extra = np.array(runs, dtype=np.int64).reshape(R, need)
    boards = np.concatenate([np.broadcast_to(bcodes, (R, len(bcodes))), extra], axis=1)
    vals = np.empty((R, len(names)), dtype=np.int32)
    for j, p in enumerate(names):
        vals[:, j] = best_values_hole(codes(holes[p]), boards)
    sh = _share(vals) / R
    return {p: float(sh[j]) for j, p in enumerate(names)}


def _sample_runs_ref(rnd, deck, need, samples):
    return [rnd.sample(deck, need) for _ in range(samples)]


def _sample_runs_fast(rnd, deck, need, samples):
    """Exakt samma dragningar som [rnd.sample(deck, need) for _ in range(samples)] (CPython:s
    random.sample med mängdmetoden, som används när leken är större än 21 kort och need <= 5),
    utan anropskostnaden per dragning. Kontrolleras mot random.sample när modulen laddas."""
    n = len(deck)
    if need > 5 or n <= 21:
        return _sample_runs_ref(rnd, deck, need, samples)
    k = n.bit_length()
    getrandbits = rnd.getrandbits
    out = []
    for _ in range(samples):
        sel = []
        for _i in range(need):
            j = getrandbits(k)
            while j >= n:
                j = getrandbits(k)
            while j in sel:
                j = getrandbits(k)
                while j >= n:
                    j = getrandbits(k)
            sel.append(j)
        out.append([deck[j] for j in sel])
    return out


def _check_fast_sampler() -> bool:
    try:
        for seed in (0, 1, 7, 12345, 65535):
            for n in (22, 30, 37, 40, 43, 45):
                for need in (1, 2, 3, 4, 5):
                    deck = list(range(100, 100 + n))
                    if (_sample_runs_fast(random.Random(seed), deck, need, 40)
                            != _sample_runs_ref(random.Random(seed), deck, need, 40)):
                        return False
        return True
    except Exception:
        return False


_sample_runs = _sample_runs_fast if _check_fast_sampler() else _sample_runs_ref


def equity_vs_unknown(known: dict, n_unknown: int, n_cards: int, board: list, samples: int, seed: int,
                      dead=()) -> dict:
    """Equity för spelare med kända kort när n_unknown motståndare har slumpade kort.
    Returnerar andel per känd spelare och '?' för de okändas sammanlagda andel.
    dead: kända kort som inte är med i handen längre (t.ex. en foldad spelares visade kort) – 2.81."""
    used = set(board) | set(dead)
    for c in known.values():
        used |= set(c)
    deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    deck_c = np.array(codes(deck), dtype=np.int64)
    need = 5 - len(board)
    names = list(known)
    bcodes = np.array(codes(board), dtype=np.int64)
    if n_unknown == 0 and need <= 2:  # alla kända: räkna alla möjliga bordskort exakt (flop, turn, river)
        if need == 2:
            i, j = np.triu_indices(len(deck_c), 1)
            extra = np.stack([deck_c[i], deck_c[j]], axis=1)
        elif need == 1:
            extra = deck_c.reshape(-1, 1)
        else:
            extra = np.zeros((1, 0), np.int64)
        R = len(extra)
        opp = np.zeros((R, 0, n_cards), np.int64)
    else:
        R = samples
        rng = np.random.default_rng(seed)
        k = need + n_unknown * n_cards
        draw = np.argsort(rng.random((R, len(deck_c))), axis=1)[:, :k]
        d = deck_c[draw]
        extra = d[:, :need]
        opp = d[:, need:].reshape(R, n_unknown, n_cards)
    boards = np.concatenate([np.broadcast_to(bcodes, (R, len(bcodes))), extra], axis=1)
    cols = []
    for p in names:
        hc = np.array(codes(known[p]), dtype=np.int64)
        cols.append(best_values_hole(hc, boards))
    for u in range(n_unknown):
        cols.append(best_values(opp[:, u, :], boards))
    vals = np.stack(cols, axis=1) if cols else np.zeros((R, 0), np.int32)
    sh = _share(vals) / R
    out = {p: float(sh[j]) for j, p in enumerate(names)}
    out["?"] = float(sh[len(names):].sum()) if n_unknown else 0.0
    return out
