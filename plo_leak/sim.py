"""Simulering: vad kan en rundown göra, oberoende av hur spelarna spelar?

Datorn delar ut riktiga PLO6-händer: din hand (en ren rundown med ett visst lägsta kort),
motståndarnas händer och ett helt bord. Ingen satsning simuleras – bara korten. Det
svarar exakt (med liten felmarginal) på frågor om händernas egenskaper:

* Hur ofta gör handen en stege vid river, och hur ofta är den nötstegen?
* Hur ofta förlorar stegen ändå mot en motståndare (högre stege, färg, kåk)?
* När du har stegen och vinner – har motståndaren något som kan betala (två par, set)?
* Floppar du en stege – hur ofta är den nötstegen, och hur ofta har motståndaren set eller bättre?
* Din andel av potten om alla går till showdown (equity).

Antagande om motståndarna (påverkar svaren mer än antalet simuleringar):
"spelbara" = slumpade händer med minst en nöt-egenskap (högt par, suited ess eller
rundown) – ungefär de händer en lös pool spelar. Kan ändras till helt slumpade händer.
"""
from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from .cards import SUITS, nut_qualities
from .ev import CATEGORY, NONFLUSH, PRIMES, _pairs, _triples, fast_best
from .rundowns import GROUPS, group_of

SIM_VERSION = 2  # 2 = vektoriserad motor (samma frågor, andra slumptal)
STRAIGHT = 4

# handvärde -> stegens högsta kort (5 = A-2-3-4-5 … 14 = T-J-Q-K-A)
_STRAIGHT_HIGH = {}
for _h in range(5, 15):
    _ranks = [14, 2, 3, 4, 5] if _h == 5 else list(range(_h - 4, _h + 1))
    _k = 1
    for _r in _ranks:
        _k *= PRIMES[_r]
    _STRAIGHT_HIGH[NONFLUSH[_k]] = _h


def _nut_straight_high(board) -> int | None:
    """Högsta stege som är möjlig på bordet (minst tre av stegens valörer på bordet)."""
    rs = {c[0] for c in board}
    if 14 in rs:
        rs.add(1)
    for h in range(14, 4, -1):
        if len(rs & set(range(h - 4, h + 1))) >= 3:
            return h
    return None


# ---------------------------------------------------------------- dra händer per grupp (vektoriserat)
def _sample_groups(n_per_group: int, seed: int, pure: bool = True) -> dict:
    rng = np.random.default_rng(seed)
    out = {g: [] for g in GROUPS}
    out["Alla händer"] = []
    need = lambda: any(len(v) < n_per_group for v in out.values())  # noqa: E731
    while need():
        N = 400_000
        hands = rng.random((N, 52)).argpartition(6, axis=1)[:, :6]
        ranks = hands // 4 + 2
        suits = hands % 4
        rows = np.repeat(np.arange(N), 6)
        cnt = np.bincount(rows * 13 + (ranks.ravel() - 2), minlength=N * 13).reshape(N, 13)
        scnt = np.bincount(rows * 4 + suits.ravel(), minlength=N * 4).reshape(N, 4)
        present = cnt > 0
        ext = np.concatenate([present[:, 12:13], present], axis=1)  # kolumn v-1 = valör v (1 = ess lågt)
        low = np.zeros(N, dtype=np.int64)
        for L in range(10, 0, -1):
            win = ext[:, L - 1:L + 4]
            c = win.sum(axis=1)
            ok = (c >= 4) & (low == 0)
            first = win[:, 0]
            low[ok] = np.where(first[ok] & (c[ok] == 4), L, L + 1)
        hp = ((cnt[:, 9:13] == 2).any(axis=1))
        ace = ranks == 14
        sc_of_card = np.take_along_axis(scnt, suits, axis=1)
        sa = (ace & (sc_of_card >= 2) & (sc_of_card <= 3)).any(axis=1)
        for i in range(N):
            if len(out["Alla händer"]) < n_per_group:
                out["Alla händer"].append(hands[i])
            if low[i] == 0 or (pure and (hp[i] or sa[i])):
                continue
            g = group_of(int(low[i]))
            if len(out[g]) < n_per_group:
                out[g].append(hands[i])
            if not need():
                break
    return out


def _card(c):
    return (int(c) // 4 + 2, SUITS[int(c) % 4])


# ---------------------------------------------------------------- en arbetsuppgift
def _run_chunk(args):
    group, hero_hands, seed, n_opp, playable = args
    rnd = random.Random(seed)
    deck_all = list(range(52))
    acc = defaultdict(float)
    for hh in hero_hands:
        hero_set = set(int(x) for x in hh)
        hero = [_card(c) for c in hh]
        rest = [c for c in deck_all if c not in hero_set]
        while True:
            rnd.shuffle(rest)
            opps, ok = [], True
            pos = 0
            for _ in range(n_opp):
                cards = [_card(c) for c in rest[pos:pos + 6]]
                pos += 6
                if playable and sum(nut_qualities(cards)) == 0:
                    ok = False
                    break
                opps.append(cards)
            if ok:
                break
        board = [_card(c) for c in rest[pos:pos + 5]]
        flop = board[:3]
        hp_, ft, rt = _pairs(hero), _triples(flop), _triples(board)
        opp_p = [_pairs(o) for o in opps]
        hv = fast_best(hp_, rt)
        ov = [fast_best(p, rt) for p in opp_p]
        best_o = max(ov)
        acc["n"] += 1
        # equity (andel av potten vid showdown)
        if hv > best_o:
            acc["equity"] += 1
        elif hv == best_o:
            acc["equity"] += 1 / (1 + ov.count(hv))
        cat = CATEGORY[hv]
        if cat == STRAIGHT:
            acc["river_straight"] += 1
            if _STRAIGHT_HIGH.get(hv) == _nut_straight_high(board):
                acc["river_nut"] += 1
            if best_o > hv:
                acc["straight_lost"] += 1
            elif hv > best_o:
                acc["straight_won"] += 1
                oc = CATEGORY[best_o]
                if oc >= 2:
                    acc["won_vs_twopair"] += 1
                if oc >= 3:
                    acc["won_vs_set"] += 1
        if cat >= STRAIGHT:
            acc["river_straight_plus"] += 1
        fv = fast_best(hp_, ft)
        if CATEGORY[fv] == STRAIGHT:
            acc["flop_straight"] += 1
            if _STRAIGHT_HIGH.get(fv) == _nut_straight_high(flop):
                acc["flop_nut"] += 1
            ofc = max(CATEGORY[fast_best(p, ft)] for p in opp_p)
            if ofc >= 3:
                acc["flop_opp_set"] += 1
            if ofc >= 2:
                acc["flop_opp_twopair"] += 1
            if hv > best_o:
                acc["flop_straight_won"] += 1
    return group, dict(acc)


# ---------------------------------------------------------------- vektoriserad arbetsuppgift
_SH = None


def _straight_high_array():
    global _SH
    if _SH is None:
        arr = np.full(len(CATEGORY), -1, dtype=np.int16)
        for v, hi in _STRAIGHT_HIGH.items():
            arr[v] = hi
        _SH = arr
    return _SH


def _nut_high_vec(board_codes: np.ndarray) -> np.ndarray:
    """Högsta möjliga stege på varje bord (minst tre av stegens valörer på bordet). 0 = ingen."""
    n = len(board_codes)
    pres = np.zeros((n, 15), dtype=bool)          # index 1–14 (1 = ess lågt)
    r = board_codes // 4 + 2
    for j in range(board_codes.shape[1]):
        pres[np.arange(n), r[:, j]] = True
    pres[:, 1] = pres[:, 14]
    out = np.zeros(n, dtype=np.int16)
    for h in range(14, 4, -1):
        hit = (pres[:, h - 4:h + 1].sum(axis=1) >= 3) & (out == 0)
        out[hit] = h
    return out


def _nut_any_vec(hands: np.ndarray) -> np.ndarray:
    """Minst en nöt-egenskap (högt par, suited ess, rundown) per hand – samma regler som cards.nut_qualities."""
    n = len(hands)
    r = hands // 4 + 2
    s = hands % 4
    rows = np.arange(n)[:, None]
    rc = np.zeros((n, 15), dtype=np.int8)
    np.add.at(rc, (np.broadcast_to(rows, r.shape), r), 1)
    sc = np.zeros((n, 4), dtype=np.int8)
    np.add.at(sc, (np.broadcast_to(rows, s.shape), s), 1)
    high_pair = (rc[:, 11:15] == 2).any(axis=1)
    suit_cnt_of_card = np.take_along_axis(sc, s, axis=1)
    suited_ace = ((r == 14) & (suit_cnt_of_card >= 2) & (suit_cnt_of_card <= 3)).any(axis=1)
    pres = rc > 0
    rundown = np.zeros(n, bool)
    for lo in range(5, 12):
        rundown |= pres[:, lo:min(lo + 4, 14) + 1].sum(axis=1) >= 4
    return high_pair | suited_ace | rundown


def _run_chunk_vec(args):
    group, hero_hands, seed, n_opp, playable = args
    from .fastev import CATEGORY_A, best_values
    H = np.asarray(hero_hands, dtype=np.int64)
    N = len(H)
    rng = np.random.default_rng(seed)
    need = 6 * n_opp + 5
    draw = np.empty((N, need), dtype=np.int64)
    todo = np.arange(N)
    while len(todo):
        keys = rng.random((len(todo), 52))
        keys[np.arange(len(todo))[:, None], H[todo]] = 2.0  # hero:s kort dras aldrig
        d = np.argsort(keys, axis=1)[:, :need]
        ok = np.ones(len(todo), bool)
        if playable:
            for o in range(n_opp):
                ok &= _nut_any_vec(d[:, 6 * o:6 * o + 6])
        draw[todo[ok]] = d[ok]
        todo = todo[~ok]
    opps = [draw[:, 6 * o:6 * o + 6] for o in range(n_opp)]
    board = draw[:, 6 * n_opp:]
    flop = board[:, :3]
    hv = best_values(H, board)
    ov = np.stack([best_values(o, board) for o in opps], axis=1)
    best_o = ov.max(axis=1)
    cat = CATEGORY_A[hv]
    SH = _straight_high_array()
    acc = defaultdict(float)
    acc["n"] = N
    win = hv > best_o
    tie = hv == best_o
    ties = (ov == hv[:, None]).sum(axis=1)
    acc["equity"] = float(win.sum() + (1.0 / (1 + ties[tie])).sum())
    strt = cat == STRAIGHT
    nut_r = _nut_high_vec(board)
    acc["river_straight"] = float(strt.sum())
    acc["river_nut"] = float((strt & (SH[hv] == nut_r)).sum())
    acc["straight_lost"] = float((strt & (best_o > hv)).sum())
    sw = strt & win
    acc["straight_won"] = float(sw.sum())
    oc = CATEGORY_A[best_o]
    acc["won_vs_twopair"] = float((sw & (oc >= 2)).sum())
    acc["won_vs_set"] = float((sw & (oc >= 3)).sum())
    acc["river_straight_plus"] = float((cat >= STRAIGHT).sum())
    fv = best_values(H, flop)
    fcat = CATEGORY_A[fv]
    fs = fcat == STRAIGHT
    acc["flop_straight"] = float(fs.sum())
    acc["flop_nut"] = float((fs & (SH[fv] == _nut_high_vec(flop))).sum())
    ofc = np.max(np.stack([CATEGORY_A[best_values(o, flop)] for o in opps], axis=1), axis=1)
    acc["flop_opp_set"] = float((fs & (ofc >= 3)).sum())
    acc["flop_opp_twopair"] = float((fs & (ofc >= 2)).sum())
    acc["flop_straight_won"] = float((fs & win).sum())
    return group, dict(acc)


def _summarize(acc: dict) -> dict:
    n = acc.get("n", 0) or 1

    def p(a, b):
        b = acc.get(b, 0) if isinstance(b, str) else b
        return None if not b else 100.0 * acc.get(a, 0) / b

    rs = acc.get("river_straight", 0)
    fs = acc.get("flop_straight", 0)
    sw = acc.get("straight_won", 0)
    return {
        "n": int(acc.get("n", 0)),
        "equity": 100.0 * acc.get("equity", 0) / n,
        "river_straight": 100.0 * rs / n,
        "river_nut_of_straights": p("river_nut", "river_straight"),
        "straight_lost": p("straight_lost", "river_straight"),
        "won_vs_twopair": p("won_vs_twopair", "straight_won"),
        "won_vs_set": p("won_vs_set", "straight_won"),
        "flop_straight": 100.0 * fs / n,
        "flop_nut_of_straights": p("flop_nut", "flop_straight"),
        "flop_opp_set": p("flop_opp_set", "flop_straight"),
        "flop_straight_won": p("flop_straight_won", "flop_straight"),
        "n_river_straights": int(rs), "n_flop_straights": int(fs), "n_straight_won": int(sw),
    }


def cache_path(n_per_group, n_opp, playable, pure, seed: int = 2026) -> Path:
    d = Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache"))
    d.mkdir(parents=True, exist_ok=True)
    # 2.81: fröet ingår i filnamnet – ett annat frö får aldrig tillbaka en tidigare körnings resultat
    return d / f"sim_v{SIM_VERSION}_{n_per_group}_{n_opp}_{int(playable)}_{int(pure)}_s{seed}.json"


def run_simulation(n_per_group: int = 125_000, n_opp: int = 2, playable: bool = True, pure: bool = True,
                   seed: int = 2026, processes: int | None = None, progress=None, use_cache: bool = True) -> dict:
    """Kör (eller läser sparad) simulering. Resultatet sparas, så den körs bara en gång."""
    cp = cache_path(n_per_group, n_opp, playable, pure, seed)
    if use_cache and cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    samples = _sample_groups(n_per_group, seed, pure)
    tasks = []
    chunk = 5_000
    for gi, (g, hands) in enumerate(samples.items()):
        for k in range(0, len(hands), chunk):
            tasks.append((g, hands[k:k + chunk], seed * 1000 + gi * 100_000 + k, n_opp, playable))
    accs = defaultdict(lambda: defaultdict(float))
    procs = processes or max(1, (os.cpu_count() or 2) - 0)
    if procs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(procs) as pool:
            for i, (g, acc) in enumerate(pool.imap_unordered(_run_chunk_vec, tasks), 1):
                for k_, v in acc.items():
                    accs[g][k_] += v
                if progress:
                    progress(i, len(tasks))
    else:
        for i, t in enumerate(tasks, 1):
            g, acc = _run_chunk_vec(t)
            for k_, v in acc.items():
                accs[g][k_] += v
            if progress:
                progress(i, len(tasks))
    res = {"settings": {"n_per_group": n_per_group, "opponents": n_opp, "playable_opponents": playable,
                        "pure_rundowns": pure, "seed": seed, "total_deals": sum(len(h) for h in samples.values()),
                        "sim_version": SIM_VERSION, "numpy": __import__("numpy").__version__},
           "groups": [{"group": g, **_summarize(accs[g])} for g in GROUPS + ["Alla händer"] if g in accs]}
    try:
        cp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return res


def load_cached(n_per_group: int = 125_000, n_opp: int = 2, playable: bool = True, pure: bool = True, seed: int = 2026):
    cp = cache_path(n_per_group, n_opp, playable, pure, seed)
    for f in (cp, Path(__file__).parent / "data" / "sim_default.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                s = d.get("settings", {})
                if (s.get("n_per_group"), s.get("opponents"), s.get("playable_opponents"), s.get("pure_rundowns"),
                        s.get("seed", 2026)) == (n_per_group, n_opp, playable, pure, seed):
                    return d
            except Exception:
                pass
    return None
