"""2.79: snabbare handvärden när många händer delar samma bord (eller samma hålkort).

Exakt samma tabeller och samma värden som fastev.best_values – bara uträknat smartare:
* Samma bord för alla händer (nattkörningens kandidathänder): för varje bord räknas EN gång, för vart och ett av de
  91 valörparen, bästa värdet över bordets trippler (utan färg, och med färg per färg). En hands värde blir sedan
  största värdet över dess 15 kortpar – ett uppslag per par i stället för 15 × (antal trippler).
* Samma hålkort mot många bord (heros hand i Monte Carlo): för vart och ett av de 455 valörtripplarna räknas EN gång
  bästa värdet över handens par.
Det går eftersom färgvärdet för fem kort aldrig är lägre än värdet utan färg för samma valörer (kontrolleras när
modulen laddas).
"""
from __future__ import annotations

import numpy as np

from .fastev import _FL_LUT, _NF_LUT, _PAIRS, _PID, _TID, _TRIPLES_BY, best_values

_V = _FL_LUT >= 0
OK = bool(np.all(_FL_LUT[_V] >= _NF_LUT[_V]))
assert OK, "fastev_delat: färgvärde lägre än utan färg – tabellerna har ändrats, räkna med fastev.best_values"
_NP = _NF_LUT.shape[0]
_NT = _NF_LUT.shape[1]


def pairs_of(holes):
    """(parindex (N, P), parfärg (N, P) – −1 om olika färg) för händernas kortpar."""
    c = np.asarray(holes, dtype=np.int64)
    pi = _PAIRS[c.shape[1]]
    hr, hs = c // 4, c % 4
    p0, p1 = pi[:, 0], pi[:, 1]
    return _PID[hr[:, p0], hr[:, p1]], np.where(hs[:, p0] == hs[:, p1], hs[:, p0], -1)


def _triples(boards):
    boards = np.asarray(boards, dtype=np.int64)
    t = _TRIPLES_BY[boards.shape[1]]
    br, bs = boards // 4, boards % 4
    tid = _TID[br[:, t[:, 0]], br[:, t[:, 1]], br[:, t[:, 2]]]                              # (B, T)
    same = (bs[:, t[:, 0]] == bs[:, t[:, 1]]) & (bs[:, t[:, 1]] == bs[:, t[:, 2]])
    return tid, np.where(same, bs[:, t[:, 0]], -2)


def board_tables(boards):
    """Per bord: bästa värde per valörpar utan färg (B, 91) och med färg per färg (B, 5, 91; rad 4 = ingen färg)."""
    tid, ts = _triples(boards)
    B = len(tid)
    nf = _NF_LUT[:, tid]                                                                     # (91, B, T)
    bn = nf.max(axis=2).T
    bf = np.full((B, 5, _NP), -1, dtype=_FL_LUT.dtype)
    if (ts >= 0).any():
        fl = _FL_LUT[:, tid]
        for s in range(4):
            m = ts == s
            if m.any():
                bf[:, s, :] = np.where(m[None], fl, -1).max(axis=2).T
    return bn, bf


def vs_boards(pid, ps, boards):
    """Värde för N händer (par från pairs_of) mot vart och ett av B bord: (B, N). Samma som best_values rad för rad."""
    bn, bf = board_tables(boards)
    psi = np.where(ps < 0, 4, ps)
    v = bn[:, pid]                                                                           # (B, N, P)
    f = bf[:, psi, pid]
    return np.maximum(v, f).max(axis=2)


def vs_board(holes, board):
    """best_values(holes, samma bord på varje rad) – (N,)."""
    pid, ps = pairs_of(holes)
    return vs_boards(pid, ps, np.asarray(board, dtype=np.int64)[None, :])[0]


def hole_tables(hole):
    """För en hand: bästa värde per valörtrippel utan färg (455,) och med färg per bordsfärg (5, 455; rad 4 = ingen)."""
    pid, ps = pairs_of(np.asarray(hole, dtype=np.int64)[None, :])
    pid, ps = pid[0], ps[0]
    hn = _NF_LUT[pid, :].max(axis=0)
    hf = np.full((5, _NT), -1, dtype=_FL_LUT.dtype)
    for s in range(4):
        m = ps == s
        if m.any():
            hf[s] = _FL_LUT[pid[m], :].max(axis=0)
    return hn, hf


def hole_vs_boards(tabs, boards):
    """En hands värde mot B bord: (B,). tabs = hole_tables(hand). Samma som best_values(hand upprepad, boards)."""
    hn, hf = tabs
    tid, ts = _triples(boards)
    v = hn[tid]
    f = hf[np.where(ts < 0, 4, ts), tid]
    return np.maximum(v, f).max(axis=1)

