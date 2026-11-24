"""Snabb, exakt relativ handstyrka på ett färdigt bord (river).

För ett bord med fem kort utvärderas alla 1 081 möjliga motståndarkombinationer
(två hålkort + tre bordskort, som Omaha kräver) på en gång med numpy. Därefter kan
vilken hand som helst få sitt mått:

    beat_frac = andel av motståndarens möjliga 2-kortskombinationer som slår handen

med korrekt kortborttagning (kombinationer som innehåller handens egna kort räknas
inte). 0 = nöten. Måttet är jämförbart mellan olika bord, vilket gör att
spelarpoolens river-ranges kan samlas från tusentals olika händer.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np

from .cards import SUITS
from .ev import FLUSH, NONFLUSH, PRIMES, _pairs, _triples, fast_best

_NF_KEYS = np.array(sorted(NONFLUSH), dtype=np.int64)
_NF_VALS = np.array([NONFLUSH[k] for k in _NF_KEYS.tolist()], dtype=np.int32)
_FL_KEYS = np.array(sorted(FLUSH), dtype=np.int64)
_FL_VALS = np.array([FLUSH[k] for k in _FL_KEYS.tolist()], dtype=np.int32)

DECK = [(r, s) for r in range(2, 15) for s in SUITS]
CARD_INDEX = {c: i for i, c in enumerate(DECK)}
_PRIME = np.array([PRIMES[c[0]] for c in DECK], dtype=np.int64)
_SUIT = np.array([SUITS.index(c[1]) for c in DECK], dtype=np.int64)
_ALL_PAIRS = np.array(list(combinations(range(52), 2)), dtype=np.int64)
_BT_CACHE: dict = {}
_RANK0 = np.array([c[0] - 2 for c in DECK], dtype=np.int64)
_PAIR_HAS = [~(_ALL_PAIRS == i).any(axis=1) for i in range(52)]  # True = paret saknar kort i


class BoardTable:
    """Alla motståndarkombinationers värde på ett givet riverbord."""

    __slots__ = ("board", "pairs", "values", "sorted_vals", "card_combos", "_rand", "_beat")

    @classmethod
    def get(cls, board) -> "BoardTable":
        """Samma tabell som BoardTable(board), men återanvänd för de senast använda borden
        (en hand räknar ofta på samma bord flera gånger: river-modellen, handstyrka, beslut).
        Tabellen och beat_n är rena funktioner av korten, så resultaten blir identiska."""
        key = tuple(board)
        try:
            bt = _BT_CACHE.get(key)
        except TypeError:  # kort som listor – ingen återanvändning
            return cls(board)
        if bt is None:
            if len(_BT_CACHE) >= 16:
                _BT_CACHE.clear()
            bt = _BT_CACHE[key] = cls(board)
        return bt

    def __init__(self, board):
        self.board = list(board)
        bidx = [CARD_INDEX[c] for c in self.board]
        mask = np.ones(len(_ALL_PAIRS), dtype=bool)
        for b_ in bidx:  # par som innehåller ett bordskort finns inte
            mask &= _PAIR_HAS[b_]
        pairs = _ALL_PAIRS[mask]
        self.pairs = pairs
        # Samma värden som NONFLUSH/FLUSH-uppslagen (valörprodukter), men via fastev:s direkta
        # tabeller (valörpar, valörtrippel) -> handvärde.
        from .fastev import _FL_LUT, _NF_LUT, _PID, _TID, _TRIPLES_BY
        t = _TRIPLES_BY.get(len(bidx))
        if t is None:  # ovanlig bordsstorlek: den ursprungliga uträkningen
            self._init_values_slow(pairs)
            return
        b = np.array([(c[0] - 2) * 4 + SUITS.index(c[1]) for c in self.board], dtype=np.int64)
        br, bs = b // 4, b % 4
        tid = _TID[br[t[:, 0]], br[t[:, 1]], br[t[:, 2]]]                                  # (T,)
        same = (bs[t[:, 0]] == bs[t[:, 1]]) & (bs[t[:, 1]] == bs[t[:, 2]])
        t_suit = np.where(same, bs[t[:, 0]], -1)
        a, b2 = pairs[:, 0], pairs[:, 1]
        pid = _PID[_RANK0[a], _RANK0[b2]]                                                   # (P,)
        p_suit = np.where(_SUIT[a] == _SUIT[b2], _SUIT[a], -2)
        nf = _NF_LUT[pid[:, None], tid[None, :]]
        flush = (p_suit[:, None] == t_suit[None, :])
        if flush.any():
            vals = np.where(flush, _FL_LUT[pid[:, None], tid[None, :]], nf)
        else:
            vals = nf
        self.values = vals.max(axis=1).astype(np.int32)
        self._finish()

    def _init_values_slow(self, pairs):
        tri = _triples(self.board)
        t_prod = np.array([t[0] for t in tri], dtype=np.int64)
        t_suit = np.array([SUITS.index(t[1]) if t[1] else -1 for t in tri], dtype=np.int64)
        a, b = pairs[:, 0], pairs[:, 1]
        p_prod = _PRIME[a] * _PRIME[b]
        p_suit = np.where(_SUIT[a] == _SUIT[b], _SUIT[a], -2)
        keys = p_prod[:, None] * t_prod[None, :]
        nf = _NF_VALS[np.searchsorted(_NF_KEYS, keys)]
        flush = (p_suit[:, None] == t_suit[None, :])
        if flush.any():
            fl_idx = np.searchsorted(_FL_KEYS, np.where(flush, keys, _FL_KEYS[0]))
            fl = _FL_VALS[np.clip(fl_idx, 0, len(_FL_VALS) - 1)]
            vals = np.where(flush, fl, nf)
        else:
            vals = nf
        self.values = vals.max(axis=1).astype(np.int32)
        self._finish()

    def _finish(self):
        self.sorted_vals = np.sort(self.values)
        self.card_combos = None
        self._rand = {}
        self._beat = {}

    def hand_value(self, hole) -> int:
        return fast_best(_pairs(hole), _triples(self.board))

    def beat_frac(self, hole) -> float:
        """Andel motståndarkombinationer (utan handens egna kort) som slår handen."""
        v = self.hand_value(hole)
        n_better = len(self.sorted_vals) - int(np.searchsorted(self.sorted_vals, v, side="right"))
        if n_better == 0:
            return 0.0
        hidx = np.array([CARD_INDEX[c] for c in hole], dtype=np.int64)
        blocked = np.isin(self.pairs, hidx).any(axis=1)
        better_blocked = int((blocked & (self.values > v)).sum())
        total = len(self.values) - int(blocked.sum())
        return (n_better - better_blocked) / total if total else 0.0


    def beat_n(self, hole, n_opp: int | None = None, samples: int = 1000) -> float:
        """Andel slumpade motståndarhänder med lika många kort som du (PLO6 = 6) som slår handen på
        river – med dina egna kort borttagna ur leken (blockers räknas). 0 = nöten. Lika = halv.

        Det här är måttet "slår dig" i programmet. Det gamla 2-kortsmåttet (beat_frac) räknar som
        Hold'em och blir alldeles för lågt i PLO, där motståndaren har 6, 15 eller fler kombinationer."""
        n = int(n_opp or len(hole))
        mkey = (tuple(hole), n, samples)
        try:
            hit = self._beat.get(mkey)
        except TypeError:
            return self._beat_n(hole, n, samples)
        if hit is not None:
            return hit
        res = self._beat_n(hole, n, samples)
        self._beat[mkey] = res
        return res

    def beat_split(self, hole, n_opp: int | None = None, samples: int = 1000) -> tuple:
        """2.81: (andel som är STRIKT bättre, andel som delar) med exakt samma dragningar som beat_n.
        beat_n = bättre + ½ · lika (förväntad pottandel). En hand som ingen giltig kombination slår är exakt 0 bättre,
        även när den ofta delas (t.ex. broadway på K-Q-T-3-7)."""
        n = int(n_opp or len(hole))
        best, v = self._sample_best(hole, n, samples)
        if best is None:
            return 0.0, 0.0
        if self.beat_frac(hole) == 0.0:
            return 0.0, float((best == v).sum()) / samples
        return float((best > v).sum()) / samples, float((best == v).sum()) / samples

    def _sample_best(self, hole, n: int, samples: int):
        v = self.hand_value(hole)
        used = {CARD_INDEX[c] for c in self.board} | {CARD_INDEX[c] for c in hole}
        rest = np.array([i for i in range(52) if i not in used])
        if n < 2 or len(rest) < n:
            return None, v
        seed = int(sum((CARD_INDEX[c] + 1) * 53 ** k for k, c in enumerate(sorted(hole) + sorted(self.board))) % (2 ** 32))
        r = np.random.default_rng(seed)
        hands = rest[r.random((samples, len(rest))).argpartition(n - 1, axis=1)[:, :n]]
        hands.sort(axis=1)
        if self.card_combos is None:
            lut = np.full((52, 52), -1, dtype=np.int64)
            lut[self.pairs[:, 0], self.pairs[:, 1]] = np.arange(len(self.pairs))
            self.card_combos = lut
        ii, jj = zip(*combinations(range(n), 2))
        return self.values[self.card_combos[hands[:, list(ii)], hands[:, list(jj)]]].max(axis=1), v

    def _beat_n(self, hole, n: int, samples: int) -> float:
        v = self.hand_value(hole)
        used = {CARD_INDEX[c] for c in self.board} | {CARD_INDEX[c] for c in hole}
        rest = np.array([i for i in range(52) if i not in used])
        if n < 2 or len(rest) < n:
            return 0.0
        seed = int(sum((CARD_INDEX[c] + 1) * 53 ** k for k, c in enumerate(sorted(hole) + sorted(self.board))) % (2 ** 32))
        r = np.random.default_rng(seed)
        hands = rest[r.random((samples, len(rest))).argpartition(n - 1, axis=1)[:, :n]]
        hands.sort(axis=1)
        if self.card_combos is None:
            lut = np.full((52, 52), -1, dtype=np.int64)
            lut[self.pairs[:, 0], self.pairs[:, 1]] = np.arange(len(self.pairs))
            self.card_combos = lut
        ii, jj = zip(*combinations(range(n), 2))
        best = self.values[self.card_combos[hands[:, list(ii)], hands[:, list(jj)]]].max(axis=1)
        return float((best > v).sum() + 0.5 * (best == v).sum()) / samples

    def random_hand_values(self, n_cards: int, samples: int = 600, seed: int = 7):
        """Värdet av slumpade n-kortshänder på det här bordet (bästa 2-kortskombination)."""
        if n_cards in self._rand:
            return self._rand[n_cards]
        r = np.random.default_rng(seed)
        bidx = {CARD_INDEX[c] for c in self.board}
        rest = np.array([i for i in range(52) if i not in bidx])
        lut = np.full((52, 52), -1, dtype=np.int64)
        lut[self.pairs[:, 0], self.pairs[:, 1]] = np.arange(len(self.pairs))
        # argpartition ger samma n minsta som argsort (ordningen spelar ingen roll – korten sorteras nedan)
        hands = rest[r.random((samples, len(rest))).argpartition(n_cards - 1, axis=1)[:, :n_cards]]
        hands.sort(axis=1)
        ii, jj = zip(*combinations(range(n_cards), 2))
        idx = lut[hands[:, list(ii)], hands[:, list(jj)]]
        best = self.values[idx].max(axis=1)
        self._rand[n_cards] = np.sort(best)
        return self._rand[n_cards]

    def strength_u(self, hole) -> float:
        """Andel slumpade händer (med lika många kort) som slår handen på det här bordet.
        0 = slår allt. Jämförbart mellan bord oavsett hur 'farligt' bordet är."""
        return self.beat_n(hole, samples=600)



def texture(board) -> str:
    """Brädtextur som styr hur nöten ser ut: parat, färgmöjlighet och hur kopplat bordet är."""
    ranks = [c[0] for c in board]
    paired = len(set(ranks)) < len(ranks)
    suits = [c[1] for c in board]
    m = max(suits.count(s) for s in set(suits))
    flush = "" if m < 3 else ("+färg" if m == 3 else "+4färg")
    u = set(ranks) | ({1} if 14 in ranks else set())
    conn = max(sum(1 for r in u if lo <= r <= lo + 4) for lo in range(1, 11))
    straight = "+kopplat" if conn >= 4 else ""
    return ("parat" if paired else "oparat") + flush + straight
