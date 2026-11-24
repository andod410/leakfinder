"""Genererar syntetisk GGPoker-handhistorik (PLO6, 6-max) för test och demo.

Hero får medvetet inbyggda läckor så att man kan se att analysen hittar dem:
för lös preflop, synar 3-bets ur position, c-bettar för mycket, foldar för
mycket mot c-bets och betalar av för mycket på river.

    python tools/generate_sample.py --hands 5000 --out sample_hands/
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plo_leak.cards import RANKS, SUITS, best_omaha, classify_start, card_str  # noqa: E402

SB, BB = 0.25, 0.5
POS6 = ["BTN", "SB", "BB", "LJ", "HJ", "CO"]
POS_BONUS = {"LJ": -1.0, "HJ": -0.6, "CO": 0.0, "BTN": 0.8, "SB": -0.3, "BB": 0.5}

REG = dict(open_thr=5.2, call_thr=5.6, threebet_thr=7.6, fourbet_thr=8.6, call3b_thr=6.4, oop_pen=0.8,
           cold3b_thr=8.2, cbet=0.55, barrel=0.5, bluff=0.12, call_adj=0.0, river_call_adj=0.0,
           xr=0.5, fold_cbet_extra=0.0, limp=0.0)
HERO = dict(REG, open_thr=4.0, call_thr=4.6, threebet_thr=8.2, call3b_thr=5.0, oop_pen=-0.4,
            cold3b_thr=6.8, cbet=0.85, barrel=0.35, fold_cbet_extra=0.25, river_call_adj=-0.22,
            limp=0.10, xr=0.15)


def score_hand(hole) -> float:
    c = classify_start(hole)
    s = 3.0
    s += 2.2 if c["suited_ace"] else 0
    s += {6: 3.0, 5: 2.2, 4: 1.2}.get(c["conn"], 0)
    s += {"TS": 1.0, "DS": 0.6, "SS": 0}.get(c["suit"], 0)
    s += 1.5 if c["aa"] else 0
    s += sum(0.15 for r, _ in hole if r >= 10)
    if c["bucket"].startswith("Trips"):
        s -= 2.5
    return s + random.gauss(0, 0.7)


def strength(hole, board) -> float:
    cat = best_omaha(hole, board)[0]
    st = [0.05, 0.2, 0.4, 0.6, 0.72, 0.82, 0.92, 1.0, 1.0][cat]
    if len(board) < 5:
        for su in SUITS:
            if sum(1 for c in board if c[1] == su) == 2 and sum(1 for c in hole if c[1] == su) >= 2:
                st += 0.3 if any(c[0] == 14 and c[1] == su for c in hole) else 0.15
                break
    return min(st + random.gauss(0, 0.08), 1.0)


def fmt(x: float) -> str:
    x = round(x + 1e-9, 2)
    return f"${x:g}" if x != int(x) else f"${int(x)}"


class Table:
    def __init__(self, seed: int):
        random.seed(seed)
        self.names = ["Hero"] + [f"{random.randrange(16**6):06x}" for _ in range(5)]
        self.btn = 0
        self.t = datetime(2026, 9, 1, 19, 0, 0)
        self.hid = 900000000 + seed * 1000000

    def play(self) -> str:
        self.hid += 1
        self.t += timedelta(seconds=random.randint(25, 70))
        if random.random() < 0.004:  # spelpass på i snitt ~250 händer, sedan en paus på 1–20 timmar
            self.t += timedelta(hours=random.randint(1, 20), minutes=random.randint(0, 59))
        n = 6
        order = [(self.btn + i) % n for i in range(n)]  # BTN, SB, BB, LJ, HJ, CO
        pos = {self.names[s]: POS6[i] for i, s in enumerate(order)}
        prof = {nm: (HERO if nm == "Hero" else REG) for nm in self.names}
        deck = [(r, s) for r in range(2, 15) for s in SUITS]
        random.shuffle(deck)
        hole = {nm: [deck.pop() for _ in range(6)] for nm in self.names}
        board_all = [deck.pop() for _ in range(5)]
        stack = {nm: 100 * BB for nm in self.names}
        L = []
        L.append(f"Poker Hand #PS{self.hid}: PLO-6 ({fmt(SB)}/{fmt(BB)}) - {self.t:%Y/%m/%d %H:%M:%S}")
        L.append(f"Table 'PLO6 Gold 7' 6-max Seat #{self.btn + 1} is the button")
        for i, nm in enumerate(self.names):
            L.append(f"Seat {i + 1}: {nm} ({fmt(stack[nm])} in chips)")
        sbp, bbp = self.names[order[1]], self.names[order[2]]
        L.append(f"{sbp}: posts small blind {fmt(SB)}")
        L.append(f"{bbp}: posts big blind {fmt(BB)}")
        L.append("*** HOLE CARDS ***")
        for nm in self.names:
            L.append(f"Dealt to {nm} " + (f"[{' '.join(card_str(c) for c in hole[nm])}]" if nm == "Hero" else ""))

        invested = {nm: 0.0 for nm in self.names}
        active = list(self.names)
        allin = set()
        pot = 0.0

        def post_order(street):
            seq = [self.names[s] for s in order]
            if street == "preflop":
                seq = seq[3:] + seq[:3]
            else:
                seq = seq[1:] + seq[:1]
            return [p for p in seq if p in active]

        scores = {nm: score_hand(hole[nm]) for nm in self.names}
        pfa = None

        def betting(street, init_contrib=None):
            nonlocal pot, pfa
            contrib = dict(init_contrib or {})
            cur = max(contrib.values()) if contrib else 0.0
            raises = 1 if street == "preflop" else 0
            raisers = []
            acted = set()
            board = board_all[:{"flop": 3, "turn": 4, "river": 5}.get(street, 0)]
            seq = post_order(street)
            idx = 0
            last_aggr = None
            while True:
                pending = [p for p in seq if p in active and p not in allin
                           and (p not in acted or contrib.get(p, 0) < cur - 1e-9)]
                if len([p for p in active if p not in allin]) <= 1 and all(
                        contrib.get(p, 0) >= cur - 1e-9 for p in active if p not in allin):
                    break
                if not pending or len(active) == 1:
                    break
                p = seq[idx % len(seq)]
                idx += 1
                if p not in pending:
                    continue
                pr = prof[p]
                mine = contrib.get(p, 0.0)
                to_call = cur - mine
                pot_now = pot + sum(contrib.values())
                if street == "preflop":
                    act, size = self._pre_decide(p, pos[p], pr, scores[p], raises, raisers, to_call)
                else:
                    act, size = self._post_decide(p, pr, hole[p], board, street, to_call, pfa,
                                                  last_aggr, len(active))
                if act in ("raise", "bet") and raises >= 4:
                    act = "call" if to_call > 0 else "check"
                if act == "fold" and to_call <= 1e-9:
                    act = "check"
                if act == "check" and to_call > 1e-9:
                    act = "fold"
                acted.add(p)
                if act == "fold":
                    active.remove(p)
                    L.append(f"{p}: folds")
                elif act == "check":
                    L.append(f"{p}: checks")
                elif act == "call":
                    amt = min(to_call, stack[p])
                    stack[p] -= amt
                    contrib[p] = mine + amt
                    tag = " and is all-in" if stack[p] <= 1e-9 else ""
                    if tag:
                        allin.add(p)
                    L.append(f"{p}: calls {fmt(amt)}{tag}")
                else:
                    potsize = pot_now + to_call
                    target = cur + max(size * potsize, BB if cur == 0 else cur - 0)
                    target = min(target, cur + potsize)
                    target = round(min(target, mine + stack[p]), 2)
                    if target <= cur + 1e-9:
                        amt = min(to_call, stack[p])
                        stack[p] -= amt
                        contrib[p] = mine + amt
                        L.append(f"{p}: calls {fmt(amt)}")
                        continue
                    added = target - mine
                    stack[p] -= added
                    contrib[p] = target
                    tag = " and is all-in" if stack[p] <= 1e-9 else ""
                    if tag:
                        allin.add(p)
                    if cur == 0:
                        L.append(f"{p}: bets {fmt(added)}{tag}")
                    else:
                        L.append(f"{p}: raises {fmt(target - cur)} to {fmt(target)}{tag}")
                    cur = target
                    raises += 1
                    raisers.append(p)
                    last_aggr = p
                    acted = {p}
                    if street == "preflop":
                        pfa = p
            # uncalled
            if contrib:
                srt = sorted(contrib.items(), key=lambda kv: -kv[1])
                top, topv = srt[0]
                second = srt[1][1] if len(srt) > 1 else 0.0
                callers = [p for p in active if p != top]
                if topv > second + 1e-9 and (len(active) == 1 or all(contrib.get(c, 0) <= second + 1e-9 for c in callers)):
                    ret = topv - second
                    contrib[top] = second
                    stack[top] += ret
                    L.append(f"Uncalled bet ({fmt(ret)}) returned to {top}")
            for k, v in contrib.items():
                invested[k] += v
            pot += sum(contrib.values())

        stack[sbp] -= SB
        stack[bbp] -= BB
        betting("preflop", {sbp: SB, bbp: BB})
        for street, n_cards, title in (("flop", 3, "FLOP"), ("turn", 4, "TURN"), ("river", 5, "RIVER")):
            if len(active) < 2:
                break
            b = board_all[:n_cards]
            if street == "flop":
                L.append(f"*** FLOP *** [{' '.join(card_str(c) for c in b)}]")
            else:
                L.append(f"*** {title} *** [{' '.join(card_str(c) for c in b[:-1])}] [{card_str(b[-1])}]")
            if len([p for p in active if p not in allin]) >= 2:
                betting(street)
        board_seen = board_all if len(active) >= 2 else None
        L.append("*** SHOWDOWN ***")
        rake = 0.0
        if any(l.startswith("*** FLOP") for l in L):
            rake = round(min(pot * 0.05, 2 * BB), 2)
        win_amt = round(pot - rake, 2)
        winners = []
        if len(active) == 1:
            winners = active
        else:
            vals = {p: best_omaha(hole[p], board_all) for p in active}
            best = max(vals.values())
            winners = [p for p in active if vals[p] == best]
            for p in active:
                L.append(f"{p}: shows [{' '.join(card_str(c) for c in hole[p])}]")
        share = round(win_amt / len(winners), 2)
        for w in winners:
            L.append(f"{w} collected {fmt(share)} from pot")
        L.append("*** SUMMARY ***")
        L.append(f"Total pot {fmt(pot)} | Rake {fmt(rake)} | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0")
        if board_seen:
            L.append(f"Board [{' '.join(card_str(c) for c in board_all)}]")
        self.btn = (self.btn + 1) % 6
        return "\n".join(L)

    @staticmethod
    def _pre_decide(p, pos, pr, s, raises, raisers, to_call):
        s += POS_BONUS[pos]
        if raises == 1:  # bara blinds
            if s > pr["open_thr"]:
                return "raise", 1.0
            if pos == "BB":
                return "check", 0
            if random.random() < pr["limp"] and s > pr["open_thr"] - 1.5:
                return "call", 0
            return "fold", 0
        if raises == 2:
            bonus = 1.2 if pos == "BB" else 0.0
            if s > pr["threebet_thr"]:
                return "raise", 1.0
            if s + bonus > pr["call_thr"]:
                return "call", 0
            return "fold", 0
        if raises == 3:
            if p in raisers:  # öppnaren möter 3-bet
                oop = pos in ("SB", "BB") or (pos == "LJ") or (pos == "HJ" and raisers[-1] in ("CO", "BTN"))
                if s > pr["fourbet_thr"]:
                    return "raise", 1.0
                if s > pr["call3b_thr"] + (pr["oop_pen"] if oop else 0):
                    return "call", 0
                return "fold", 0
            return ("call", 0) if s > pr["cold3b_thr"] else ("fold", 0)
        return ("call", 0) if s > 8.0 else ("fold", 0)

    @staticmethod
    def _post_decide(p, pr, hole, board, street, to_call, pfa, last_aggr, n_active):
        st = strength(hole, board)
        if to_call <= 1e-9:
            if st > 0.7:
                return "bet", random.choice([0.5, 0.75, 1.0])
            if street == "flop" and pfa == p and random.random() < pr["cbet"] * (0.6 if n_active > 2 else 1):
                return "bet", random.choice([0.33, 0.5, 0.66])
            if street != "flop" and last_aggr is None and pfa == p and random.random() < pr["barrel"]:
                return "bet", 0.66
            if random.random() < pr["bluff"]:
                return "bet", 0.5
            return "check", 0
        thr = {"flop": 0.35, "turn": 0.48, "river": 0.62}[street] + pr["call_adj"]
        if street == "river":
            thr += pr["river_call_adj"]
        if street == "flop" and last_aggr == pfa and pfa != p:
            thr += pr["fold_cbet_extra"]
        if st > 0.88 or (st > 0.75 and random.random() < pr["xr"]):
            return "raise", 1.0
        if st > thr:
            return "call", 0
        return "fold", 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=5000)
    ap.add_argument("--out", default="sample_hands")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = [Table(a.seed + i) for i in range(4)]
    per = a.hands // len(tables)
    for i, t in enumerate(tables):
        hands = [t.play() for _ in range(per)]
        (out / f"GG_PLO6_table{i + 1}.txt").write_text("\n\n\n".join(hands) + "\n", encoding="utf-8")
    print(f"Skrev {per * len(tables)} händer till {out}/")


if __name__ == "__main__":
    main()
