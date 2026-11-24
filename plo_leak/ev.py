"""All-in EV: vad du "borde" ha vunnit i händer där pengarna gick in före river.

När alla pengar är inne och korten visas räknas din equity ut (exakt för
turn- och flop-all-in, Monte Carlo för preflop) och ditt resultat i handen
ersätts med equity × pott − din insats. Det tar bort tur/otur i all-ins, så
att resultat och läckor kan bedömas på hur du spelade i stället för hur
korten föll. Samma princip som "All-in EV" i DriveHUD/PokerTracker.
"""
from __future__ import annotations
import zlib

import random
from itertools import combinations

from .cards import SUITS, eval5
from .parser import Hand

# ---------------------------------------------------------------- snabb utvärderare
# Varje valör får ett primtal; produkten av fem primtal identifierar valörerna
# entydigt. Två tabeller (utan/med färg) ger handvärdet med en multiplikation
# och ett uppslag – mycket snabbare än att utvärdera varje kombination från grunden.
PRIMES = {r: p for r, p in zip(range(2, 15), (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41))}
NONFLUSH: dict[int, int] = {}
FLUSH: dict[int, int] = {}
CATEGORY: list[int] = []


def _build_tables() -> None:
    from itertools import combinations_with_replacement
    vals = {}
    for ranks in combinations_with_replacement(range(2, 15), 5):
        if max(ranks.count(r) for r in ranks) > 4:
            continue
        cards = [(r, SUITS[i % 4]) for i, r in enumerate(ranks)]
        if len({c[1] for c in cards}) == 1:  # undvik oavsiktlig färg
            cards[0] = (cards[0][0], SUITS[(SUITS.index(cards[0][1]) + 1) % 4])
        key = 1
        for r in ranks:
            key *= PRIMES[r]
        vals[("n", key)] = eval5(cards)
    for ranks in combinations(range(2, 15), 5):
        key = 1
        for r in ranks:
            key *= PRIMES[r]
        vals[("f", key)] = eval5([(r, "s") for r in ranks])
    ordered = sorted(set(vals.values()))
    order = {v: i for i, v in enumerate(ordered)}
    CATEGORY.extend(v[0] for v in ordered)  # handkategori (0 = högt kort … 8 = färgstege) per värde
    for (kind, key), v in vals.items():
        (NONFLUSH if kind == "n" else FLUSH)[key] = order[v]


_build_tables()


def _pairs(hole):
    out = []
    for a, b in combinations(hole, 2):
        out.append((PRIMES[a[0]] * PRIMES[b[0]], a[1] if a[1] == b[1] else None))
    return out


def _triples(board):
    out = []
    for a, b, c in combinations(board, 3):
        out.append((PRIMES[a[0]] * PRIMES[b[0]] * PRIMES[c[0]], a[1] if a[1] == b[1] == c[1] else None))
    return out


def fast_best(pairs, triples) -> int:
    best = -1
    nf, fl = NONFLUSH, FLUSH
    for pp, ps in pairs:
        for tp, ts in triples:
            v = fl[pp * tp] if ps is not None and ps == ts else nf[pp * tp]
            if v > best:
                best = v
    return best


# ---------------------------------------------------------------- equity
def equities(holes: dict, board: list, dead: list = (), samples: int = 1500, seed: int = 0) -> dict:
    """Andel av potten varje spelare vinner i snitt. Räknas med den vektoriserade motorn
    (fastev) – samma utfall som den ursprungliga Python-versionen nedan, men snabbare."""
    from .fastev import equities as _fast
    return _fast(holes, board, dead, samples, seed)


def equities_py(holes: dict, board: list, dead: list = (), samples: int = 1500, seed: int = 0) -> dict:
    """Andel av potten varje spelare vinner i snitt (delade pottar räknas som delar).

    Exakt uppräkning om antalet utfall är litet, annars Monte Carlo."""
    used = set(board) | set(dead)
    for h in holes.values():
        used |= set(h)
    deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    need = 5 - len(board)
    pairs = {p: _pairs(h) for p, h in holes.items()}
    names = list(holes)
    share = {p: 0.0 for p in names}

    def run(extra):
        b = list(board) + list(extra)
        tr = _triples(b)
        vals = {p: fast_best(pairs[p], tr) for p in names}
        top = max(vals.values())
        win = [p for p in names if vals[p] == top]
        for p in win:
            share[p] += 1.0 / len(win)

    if need == 0:
        run(())
        n = 1
    else:
        from math import comb
        total = comb(len(deck), need)
        if total <= samples:
            n = 0
            for extra in combinations(deck, need):
                run(extra)
                n += 1
        else:
            rnd = random.Random(seed)
            n = samples
            for _ in range(samples):
                run(rnd.sample(deck, need))
    return {p: v / n for p, v in share.items()}


# ---------------------------------------------------------------- per hand
STREET_IDX = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
BOARD_AT = {0: 0, 1: 3, 2: 4}


def _pots(contrib: dict, live: set, dead: float = 0.0) -> list[tuple[float, list, float]]:
    """Dela upp potten i huvud- och sidopotter: [(belopp, [spelare som kan vinna], nedre nivå)].

    contrib = levande insats per spelare. Döda pengar (dead/missed blinds) bestämmer ingen nivå –
    de läggs i huvudpotten, som GG gör (2.87)."""
    levels = sorted({c for p, c in contrib.items() if p in live and c > 0})
    pots = []
    prev = 0.0
    for lvl in levels:
        amount = sum(min(c, lvl) - min(c, prev) for c in contrib.values())
        elig = [p for p in live if contrib.get(p, 0) >= lvl - 1e-9]
        if amount > 1e-9:
            pots.append((amount, elig, prev))
        prev = lvl
    # pengar över högsta nivån (från foldade spelare) läggs i sista potten
    extra = sum(max(c - prev, 0) for c in contrib.values())
    if extra > 1e-9 and pots:
        pots[-1] = (pots[-1][0] + extra, pots[-1][1], pots[-1][2])
    if dead > 1e-9 and pots:
        pots[0] = (pots[0][0] + dead, pots[0][1], pots[0][2])
    return pots


def allin_ev(h: Hand, hero: str, samples: int = 1500):
    """Returnerar (ev_net_i_pengar, equity, gata) eller None om handen inte är en all-in före river."""
    live = set(h.remaining())
    if hero not in live or len(live) < 2:
        return None
    acts = [a for a in h.actions if not a.kind.startswith("post") and not a.inferred]
    if not acts:
        return None
    if len(h.board) < 5:
        return None
    holes = {}
    for p in live:
        cards = h.hole.get(p) if p == hero else h.shown.get(p)
        if not cards or len(cards) < 4:
            return None
        holes[p] = cards
    contrib = {p: h.contrib(p) for p in h.seats}
    total = sum(contrib.values())
    # 2.87: döda pengar (dead/missed blinds) räknas inte som levande insats
    dead_of = {}
    for a in h.actions:
        if a.kind == "post_dead":
            dead_of[a.player] = dead_of.get(a.player, 0.0) + max(a.added, 0.0)
    live_c = {p: max(contrib[p] - dead_of.get(p, 0.0), 0.0) for p in contrib}
    if total <= 0:
        return None
    fee_rate = min(max(h.rake / total, 0.0), 0.5)
    ev_won = 0.0
    eq_cache = {}
    hero_eq_main = None
    frozen = []
    hero_ai_st = None
    if h.stacks.get(hero, 0.0) - contrib.get(hero, 0.0) <= 1e-6:
        put = [STREET_IDX.get(a.street, 3) for a in h.actions if a.player == hero and a.added > 0]
        hero_ai_st = max(put) if put else 0
    # Known cards remain unavailable even when their owner cannot win a side pot.
    all_known = dict(holes)
    all_known.update({p: cs for p, cs in h.shown.items() if cs})
    for amount, elig, lo in _pots(live_c, live, sum(dead_of.values())):
        if hero not in elig:
            continue
        if len(elig) == 1:
            ev_won += amount * (1 - fee_rate)
            continue
        cap = min(live_c[p] for p in elig)
        if not any(h.stacks.get(p, 0.0) - contrib[p] <= 1e-6 for p in elig):
            return None  # no all-in locking this pot
        paid = {p: 0.0 for p in elig}
        lock = None
        for ai, a in enumerate(h.actions):
            if a.player in paid and a.kind != "post_dead":
                paid[a.player] += max(a.added, 0.0)
            if all(v >= cap - 1e-6 for v in paid.values()):
                lock = (ai, STREET_IDX.get(a.street, 3))
                break
        if lock is None:
            return None
        ai, last = lock
        # 2.87: en spelare som har pengar i potten och foldar senare kunde ha vunnit den här potten
        # fram till sin fold. Potten frys därför först efter den sista sådana folden (i stället för att
        # hela handen räknades med faktiskt resultat). Fold på river → faktiskt resultat som förut.
        later = [STREET_IDX.get(a.street, 3) for a in h.actions[ai + 1:]
                 if a.kind == "fold" and live_c.get(a.player, 0) > lo + 1e-9]
        if later:
            last = max(last, max(later))
        if last >= 3 and hero_ai_st is not None and hero_ai_st < 3:
            # 2.87: du var all-in före river men någon foldade först på river. Samma konvention som
            # HUD-program: frys vid din all-in mot spelarna som gick till showdown (den som foldade
            # förlorar sin andel; hans pengar ligger kvar i potten).
            last = hero_ai_st
        if last >= 3:
            return None  # preserve actual result when a hero pot remains unlocked until river
        board = h.board[:BOARD_AT[last]]
        dead = [c for p, cs in all_known.items() if p not in elig for c in cs]
        key = (tuple(sorted(elig)), last, tuple(sorted(dead)))
        if key not in eq_cache:
            # 2.87: preflop räknas EXAKT – alla möjliga bord (heads-up 658 008, trevägs 278 256 …; förut
            # 1 500–6 000 slumpade bord, upp till ±$5 brus per hand). Flop och turn har alltid räknats exakt.
            # samples < 1500 = snabbläge (nattberäkningen).
            n = max(samples, 700_000) if last == 0 and samples >= 1500 else samples
            eq_cache[key] = equities({p: holes[p] for p in elig}, board, dead=dead, samples=n,
                                     seed=zlib.crc32(h.id.encode()) & 0xFFFF)
        eq = eq_cache[key][hero]
        if hero_eq_main is None:
            hero_eq_main = eq
        frozen.append(last)
        ev_won += eq * amount * (1 - fee_rate)
    if not frozen:
        return None
    last = min(frozen)
    # EV räknas utan GG:s EV Cashout (premien och utbetalningen är en försäkring, inte en del av potten)
    ev_net = ev_won - contrib[hero]
    return ev_net, hero_eq_main, ["preflop", "flop", "turn"][last]
