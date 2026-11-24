"""2.77 (punkt 7): återkommande misstag som programmet letar efter i varje pass.

* "fel": överpar synar en check-raise/höjning på parat bord (solverlogik: parat bord + höjning = kåk/trips ofta)
* "fel": syn med lägsta stegen på bord med fyra till stege (turn/river), när minst 25 % av slumpade händer slår dig
* "granska": syn mot 4-bet eller 5-bet preflop utan par – inte ett misstag i sig (egen data +7,5 ± 2,6 bb mot fold),
  men värt att titta på tills solverlägena mot 4-bet finns
"""
from __future__ import annotations


def _four_straight(ranks) -> bool:
    rs = set(ranks) | ({1} if 14 in ranks else set())
    return any(len(rs & set(range(lo, lo + 5))) >= 4 for lo in range(1, 11))


def preflop(h, hero) -> list:
    hole = (h.hole or {}).get(hero) or []
    raises = 0
    out = []
    for a in h.actions:
        if a.street != "preflop" or a.kind.startswith("post"):
            continue
        if a.player == hero and a.kind == "call" and raises >= 3:
            ranks = [c[0] for c in hole]
            if len(set(ranks)) == len(ranks):
                out.append({"kind": "granska", "text": f"Synade en {raises + 1}-bet preflop utan par – granska (inte ett misstag i sig)"})
            break
        if a.kind == "raise":
            raises += 1
    return out


def postflop(h, hero, rows, idx) -> list:
    hole = (h.hole or {}).get(hero) or []
    out = []
    pairs = [r for r in {c[0] for c in hole} if sum(1 for c in hole if c[0] == r) >= 2]
    for x in rows:
        st, act, facing = x[idx["street"]], x[idx["action"]], x[idx["facing"]]
        board = [c for c in (h.board or [])][: {"flop": 3, "turn": 4, "river": 5}.get(st, 0)]
        if act != "call" or not board:
            continue
        top = max(c[0] for c in board)
        # 2.80: båda markeras för granskning, inte som fel – priset, dragen och hans range ingår inte i kontrollen
        if facing == "raise" and x[idx["board_paired"]] and any(p > top for p in pairs) and x[idx["hand"]] in ("par", "två par"):
            out.append({"kind": "granska", "text": f"{st.capitalize()}: synade en höjning med överpar på parat bord – granska pris och drag"})
        bf = x[idx["beat_frac"]]
        bran = [c[0] for c in board]
        if st in ("turn", "river") and x[idx["hand"]] == "stege" and _four_straight(bran) \
                and isinstance(bf, (int, float)) and bf >= 0.25 and _straight_high(hole, bran) < _nut_straight_high(bran):
            out.append({"kind": "granska", "text": f"{st.capitalize()}: synade med en stege som inte är den högsta möjliga på bord med fyra till stege ({100 * bf:.0f} % slår dig)"})
    return out


def _win(high):
    return set(range(high - 4, high + 1)) if high > 5 else {14, 2, 3, 4, 5}


def _straight_high(hole, board_ranks) -> int:
    """Högsta stege du har med exakt 2 hålkort + 3 bordskort, 0 om ingen."""
    hole_r = [c[0] for c in hole]
    br = set(board_ranks)
    for high in range(14, 4, -1):
        w = _win(high)
        if len(w & br) < 3:
            continue
        miss = w - br
        if len(miss) > 2 or not miss <= set(hole_r):
            continue
        # två hålkort: de saknade valörerna plus (vid behov) ett hålkort vars valör redan finns på bordet i fönstret
        used = list(miss)
        rest = [r for r in hole_r]
        for r in used:
            rest.remove(r)
        if len(used) == 2 or len([r for r in rest if r in w]) >= 2 - len(used):
            return high
    return 0


def _nut_straight_high(board_ranks) -> int:
    """Högsta stege som går att göra på bordet med två hålkort."""
    br = set(board_ranks)
    for high in range(14, 4, -1):
        w = set(range(high - 4, high + 1)) if high > 5 else {14, 2, 3, 4, 5}
        if len(w & br) >= 3:
            return high
    return 0
