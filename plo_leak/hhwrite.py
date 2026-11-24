"""Återskapa en hand i GG:s textformat från den tolkade handen.

Används vid export när originaltexten saknas i databasen (händer som lästes in av en äldre version,
innan originaltexten sparades). Allt som DriveHUD och HoldemManager behöver finns med: rubrik, bord,
platser och stackar, blinds, kort, alla handlingar per gata, bordskort, visade kort, vinster, rake
och sammanfattning. Det som inte sparades i den tolkade handen skrivs inte: handbeskrivningar som
"two pair, Aces and Tens", fördelningen mellan rake och jackpot (allt skrivs som rake) och den andra
bordsuppläggningen vid "run it twice" (vinsterna stämmer ändå).
"""
from __future__ import annotations

from .cards import card_str

STREET_HEAD = {"flop": "FLOP", "turn": "TURN", "river": "RIVER"}
STREETS = ("preflop", "flop", "turn", "river")
FOLD_TXT = {"preflop": "folded before Flop", "flop": "folded on the Flop", "turn": "folded on the Turn",
            "river": "folded on the River"}


def _m(x: float) -> str:
    s = f"{abs(x) + 0.0:.2f}".rstrip("0").rstrip(".")
    return "$" + (s or "0")


def _cards(cs) -> str:
    return " ".join(card_str(c) for c in cs)


def _is_post(a) -> bool:
    return a.kind.startswith("post")


def to_gg_text(h) -> str:
    hs = getattr(h, "header_stakes", None)
    sb, bb = hs if hs and len(hs) == 2 and hs[1] > 0 else (h.sb, h.bb)
    out = [f"Poker Hand #{h.id}: {h.game} ({_m(sb)}/{_m(bb)}) - {h.date:%Y/%m/%d %H:%M:%S}",
           f"Table '{h.table or 'Table'}' {h.max_seats}-max Seat #{h.button_seat} is the button"]
    seat_order = sorted(h.seats, key=lambda p: h.seats[p])
    for p in seat_order:
        out.append(f"Seat {h.seats[p]}: {p} ({_m(h.stacks.get(p, 0.0))} in chips)")
    acts = [a for a in h.actions if not a.inferred]
    # pengar som kom tillbaka (osynad insats) = allt spelaren lagt in minus det som räknats som insatt
    added = {}
    for a in acts:
        added[a.player] = added.get(a.player, 0.0) + a.added
    fee = getattr(h, "cashout_fee", None) or {}
    recv = getattr(h, "cashout_recv", None) or {}
    uncalled = {p: round(added.get(p, 0.0) + fee.get(p, 0.0) - h.invested.get(p, 0.0), 2) for p in h.seats}
    uncalled = {p: v for p, v in uncalled.items() if v > 0.004}
    last_street = {p: max((STREETS.index(a.street) for a in acts if a.player == p and a.kind in
                           ("bet", "raise", "post_sb", "post_bb", "post_straddle")), default=0) for p in uncalled}

    def write_street(st, only=None):
        mx = 0.0
        for a in [x for x in acts if x.street == st and (only is None or only(x))]:
            ai = " and is all-in" if a.allin else ""
            if a.kind == "post_sb":
                out.append(f"{a.player}: posts small blind {_m(a.added)}{ai}")
            elif a.kind == "post_bb":
                out.append(f"{a.player}: posts big blind {_m(a.added)}{ai}")
            elif a.kind == "post_straddle":
                out.append(f"{a.player}: posts straddle {_m(a.added)}{ai}")
            elif a.kind == "post_dead":
                out.append(f"{a.player}: posts dead {_m(a.added)}")
                continue
            elif a.kind == "fold":
                out.append(f"{a.player}: folds")
            elif a.kind == "check":
                out.append(f"{a.player}: checks")
            elif a.kind == "call":
                out.append(f"{a.player}: calls {_m(a.added)}{ai}")
            elif a.kind == "bet":
                out.append(f"{a.player}: bets {_m(a.added)}{ai}")
            elif a.kind == "raise":
                out.append(f"{a.player}: raises {_m(a.to - mx)} to {_m(a.to)}{ai}")
            mx = max(mx, a.to)
        if only is not None and only is _is_post:
            return
        for p, v in uncalled.items():
            if STREETS[last_street[p]] == st:
                out.append(f"Uncalled bet ({_m(v)}) returned to {p}")

    def deal():
        out.append("*** HOLE CARDS ***")
        for p in seat_order:
            c = h.hole.get(p)
            out.append(f"Dealt to {p} [{_cards(c)}]" if c else f"Dealt to {p}")

    # blinds först, sedan korten, sedan resten av preflop (insatserna räknas över hela gatan)
    write_street("preflop", _is_post)
    deal()
    pre_rest = [a for a in acts if a.street == "preflop" and not _is_post(a)]
    mx = max([a.to for a in acts if a.street == "preflop" and _is_post(a)] + [0.0])
    for a in pre_rest:
        ai = " and is all-in" if a.allin else ""
        if a.kind == "fold":
            out.append(f"{a.player}: folds")
        elif a.kind == "check":
            out.append(f"{a.player}: checks")
        elif a.kind == "call":
            out.append(f"{a.player}: calls {_m(a.added)}{ai}")
        elif a.kind == "bet":
            out.append(f"{a.player}: bets {_m(a.added)}{ai}")
        elif a.kind == "raise":
            out.append(f"{a.player}: raises {_m(a.to - mx)} to {_m(a.to)}{ai}")
        mx = max(mx, a.to)
    for p, v in uncalled.items():
        if last_street[p] == 0:
            out.append(f"Uncalled bet ({_m(v)}) returned to {p}")
    nb = {"flop": 3, "turn": 4, "river": 5}
    for st in ("flop", "turn", "river"):
        if len(h.board) < nb[st]:
            break
        if st == "flop":
            out.append(f"*** FLOP *** [{_cards(h.board[:3])}]")
        else:
            out.append(f"*** {STREET_HEAD[st]} *** [{_cards(h.board[:nb[st] - 1])}] [{card_str(h.board[nb[st] - 1])}]")
        write_street(st)
    out.append("*** SHOWDOWN ***")
    for p in seat_order:
        if p in h.shown and h.shown[p]:
            out.append(f"{p}: shows [{_cards(h.shown[p])}]")
    for p in seat_order:
        if fee.get(p):
            out.append(f"{p}: Pays Cashout Risk ({_m(fee[p])})")
    for p in seat_order:
        if h.collected.get(p):
            out.append(f"{p} collected {_m(h.collected[p])} from pot")
    for p in seat_order:
        if recv.get(p):
            out.append(f"{p}: Receives Cashout ({_m(recv[p])})")
    out.append("*** SUMMARY ***")
    total = getattr(h, "total_pot", 0.0) or sum(h.invested.values()) - sum(fee.values())
    out.append(f"Total pot {_m(total)} | Rake {_m(h.rake)} | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0")
    if h.board:
        out.append(f"Board [{_cards(h.board)}]")
    folded = {}
    for a in acts:
        if a.kind == "fold" and a.player not in folded:
            folded[a.player] = a.street
    for a in h.actions:  # härledda folds (saknades i originalet) räknas också i sammanfattningen
        if a.kind == "fold" and a.player not in folded:
            folded[a.player] = a.street
    btn = next((p for p in seat_order if h.seats[p] == h.button_seat), None)
    for p in seat_order:
        tag = ""
        pos = h.positions.get(p)
        if p == btn:
            tag = " (button)"
        elif pos == "SB":
            tag = " (small blind)"
        elif pos == "BB":
            tag = " (big blind)"
        won = h.collected.get(p, 0.0)
        if p in h.shown and h.shown[p]:
            res = f"and won ({_m(won)})" if won else "and lost"
            out.append(f"Seat {h.seats[p]}: {p}{tag} showed [{_cards(h.shown[p])}] {res}")
        elif won:
            out.append(f"Seat {h.seats[p]}: {p}{tag} collected ({_m(won)})")
        elif p in folded:
            out.append(f"Seat {h.seats[p]}: {p}{tag} {FOLD_TXT[folded[p]]}")
        else:
            out.append(f"Seat {h.seats[p]}: {p}{tag} mucked")
    return "\n".join(out)
