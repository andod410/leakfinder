"""Steg-för-steg-uppspelning av en hand, med equity per gata.

Varje steg är läget vid bordet efter en handling: stackar, insatser på gatan, potten,
vilka som foldat och vilka bordskort som syns. Equity räknas om varje gång en ny gata
delas ut eller någon foldar:

* Bara händer vars kort syns (dina och de som visades vid showdown) räknas, mot varandra.
  Spelare med okända kort räknas inte med alls, så de kända händernas andelar blir
  tillsammans 100 %. Equity visas när minst två händer med kända kort är kvar i handen.
* Flop och turn räknas exakt (alla möjliga bordskort), preflop med slumpade bord.
"""
from __future__ import annotations

import random
import zlib

from .ev import SUITS, _pairs, _triples, fast_best

STREETS = ("preflop", "flop", "turn", "river")
BOARD_N = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
STREET_NAMES = {"preflop": "Preflop", "flop": "Flop", "turn": "Turn", "river": "River"}
KIND_TEXT = {"fold": "foldar", "check": "checkar", "call": "synar", "bet": "bettar", "raise": "höjer till",
             "post_sb": "lägger small blind", "post_bb": "lägger big blind", "post_straddle": "straddlar",
             "post_dead": "lägger"}


def _equity(known: dict, n_unknown: int, n_cards: int, board: list, samples: int, seed: int) -> dict:
    """Equity för spelare med kända kort när n_unknown motståndare har okända (slumpade) kort.
    Returnerar andel per känd spelare samt '?' för de okändas sammanlagda andel."""
    used = set(board)
    for c in known.values():
        used |= set(c)
    deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    need = 5 - len(board)
    pairs = {p: _pairs(c) for p, c in known.items()}
    share = {p: 0.0 for p in known}
    share["?"] = 0.0
    rnd = random.Random(seed)
    exact = n_unknown == 0 and need <= 1
    runs = ([[c] for c in deck] if need == 1 else [[]]) if exact else range(samples)
    n = 0
    for r_ in runs:
        if exact:
            extra, opp = r_, []
        else:
            draw = rnd.sample(deck, need + n_unknown * n_cards)
            extra = draw[:need]
            opp = [draw[need + i * n_cards: need + (i + 1) * n_cards] for i in range(n_unknown)]
        tr = _triples(list(board) + list(extra))
        vals = {p: fast_best(pp, tr) for p, pp in pairs.items()}
        uv = [fast_best(_pairs(o), tr) for o in opp]
        top = max(list(vals.values()) + uv)
        win = [p for p, v in vals.items() if v == top]
        nu = sum(1 for v in uv if v == top)
        k = len(win) + nu
        for p in win:
            share[p] += 1.0 / k
        share["?"] += nu / k
        n += 1
    return {p: v / n for p, v in share.items()}


def replay_steps(h, hero: str, samples: int = 20000) -> dict:
    bb = h.bb or 1.0
    seats = sorted(h.seats.items(), key=lambda kv: kv[1])
    names = [n for n, _ in seats]
    n_cards = h.num_hole
    known = {p: c for p, c in h.hole.items() if c and len(c) == n_cards}
    for p, c in h.shown.items():
        if c and len(c) == n_cards:
            known[p] = c
    label = {p: ("Du" if p == hero else (h.positions.get(p) or f"Plats {h.seats[p]}")) for p in names}
    players = [{"id": i, "name": label[p], "pos": h.positions.get(p, ""), "hero": p == hero,
                "cards": [[c[0], c[1]] for c in sorted(known[p], key=lambda c: (-c[0], c[1]))] if p in known else None,
                "stack": round(h.stacks.get(p, 0.0) / bb, 1)} for i, p in enumerate(names)]
    idx = {p: i for i, p in enumerate(names)}
    stack = {p: h.stacks.get(p, 0.0) for p in names}
    bet = {p: 0.0 for p in names}
    folded = set()
    pot = 0.0
    eq_cache = {}

    def equity(street):
        live = [p for p in names if p not in folded]
        kn = {p: known[p] for p in live if p in known}
        board = h.board[:BOARD_N[street]]
        if len(kn) < 2 or len(board) < BOARD_N[street]:
            return None
        # samma kända händer och samma bord ger samma equity, oavsett hur många okända som foldat
        # 2.81: kända kort hos spelare som foldat är döda – de kan inte komma på bordet
        dead = tuple(sorted(c for p in names if p in folded and p in known for c in known[p]))
        key = (street, tuple(kn), dead)
        if key not in eq_cache:
            from .fastev import equity_vs_unknown
            e = equity_vs_unknown(kn, 0, n_cards, board, samples,
                                  seed=zlib.crc32(f"{h.id}|{street}|{'|'.join(kn)}".encode()), dead=dead)
            eq_cache[key] = {str(idx[p]): round(100 * v, 1) for p, v in e.items() if p != "?"}
        out = {"by": eq_cache[key], "unknown": None, "n_unknown": 0, "ignored": len(live) - len(kn)}
        return out

    steps = []

    def snap(street, actor, text):
        steps.append({"street": STREET_NAMES[street], "board": [[c[0], c[1]] for c in h.board[:BOARD_N[street]]],
                      "pot": round(pot / bb, 1), "actor": idx.get(actor) if actor else None, "text": text,
                      "hero_act": actor == hero,
                      "seats": [{"stack": round(stack[p] / bb, 1), "bet": round(bet[p] / bb, 1),
                                 "folded": p in folded} for p in names],
                      "eq": equity(street)})

    def settle():
        """2.81: osynad bet/höjning återbetalas när gatan är slut (som "Uncalled bet ... returned" i texten)."""
        nonlocal pot
        if not bet:
            return
        top = max(bet, key=lambda p: bet[p])
        second = max((v for p, v in bet.items() if p != top), default=0.0)
        ex = bet[top] - second
        if ex > 1e-9:
            bet[top] -= ex
            stack[top] += ex
            pot -= ex

    cur = "preflop"
    posts = [a for a in h.actions if a.kind.startswith("post")]
    for a in posts:
        stack[a.player] -= a.added
        bet[a.player] += a.added
        pot += a.added
    snap("preflop", None, "Korten är utdelade. Blindarna är lagda.")
    for a in h.actions:
        if a.kind.startswith("post"):
            continue
        if a.street != cur:
            if a.street not in BOARD_N:
                continue
            settle()
            cur = a.street
            bet = {p: 0.0 for p in names}
            snap(cur, None, f"{STREET_NAMES[cur]} delas ut.")
        if a.kind == "fold":
            folded.add(a.player)
        stack[a.player] -= a.added
        bet[a.player] += a.added
        pot += a.added
        amt = a.to if a.kind == "raise" else a.added
        txt = f"{label[a.player]} {KIND_TEXT.get(a.kind, a.kind)}"
        if a.kind in ("call", "bet", "raise") and amt:
            txt += f" {amt / bb:.1f} bb"
        if a.allin:
            txt += " (all-in)"
        snap(cur, a.player, txt)
    settle()
    # bordskort som delades ut efter all-in utan fler handlingar
    for s_ in STREETS[STREETS.index(cur) + 1:]:
        if len(h.board) >= BOARD_N[s_] and len([p for p in names if p not in folded]) >= 2:
            cur = s_
            bet = {p: 0.0 for p in names}
            snap(cur, None, f"{STREET_NAMES[cur]} delas ut.")
    # resultat
    bet = {p: 0.0 for p in names}
    res = []
    for p in names:
        if h.collected.get(p):
            res.append(f"{label[p]} vinner {h.collected[p] / bb:.1f} bb")
    steps.append({**steps[-1], "actor": None, "hero_act": False, "text": ". ".join(res) + "." if res else "Handen är slut.",
                  "pot": round(h.pot_size() / bb, 1),
                  "seats": [{**s_, "bet": 0.0, "won": round(h.collected.get(p, 0.0) / bb, 1),
                             "stack": round((h.stacks.get(p, 0.0) - h.invested.get(p, 0.0) + h.collected.get(p, 0.0)
                                             + h.cashout_recv.get(p, 0.0)) / bb, 1)}
                            for s_, p in zip(steps[-1]["seats"], names)],
                  "final": True})
    return {"players": players, "steps": steps, "hero": idx.get(hero), "n_cards": n_cards,
            "net": round(h.net_bb(hero), 1), "stake": f"${h.sb:g}/${h.bb:g}", "date": h.date.strftime("%Y-%m-%d %H:%M"),
            "id": h.id}
