"""Bevismotor: hittar bara läckor som dina egna resultat bevisar.

Princip
-------
I varje beslut kan du alltid folda. Att folda kostar exakt det du redan lagt i
potten. För varje gång du i stället fortsatte (synade, höjde, öppnade …) räknar
vi ut hur mycket bättre eller sämre handen slutade jämfört med att folda:

    skillnad = resultat i handen (all-in EV) + det du hade investerat före beslutet

Upptäck och bekräfta (version 1.3)
----------------------------------
Händerna delas i två halvor (A och B) efter handens nummer, alltid på samma sätt.

1. Upptäckt i halva A: alla grupper testas, med en test som tar hänsyn till att
   pokerresultat är snedfördelade (Johnsons korrigering), och Benjamini–Hochberg
   över alla tester.
2. Bekräftelse i halva B, som upptäckten inte har sett: varje kandidat testas igen
   med bootstrap-t (ingen normalfördelning antas) och Bonferroni över kandidaterna.
3. Kostnaden räknas bara från halva B, så att den inte blir överskattad av urvalet.

Överlappande grupper (t.ex. "alla positioner" och "HJ") rapporteras aldrig båda.

Vad metoden INTE kan bevisa: att du borde göra något oftare (t.ex. syna mer),
eftersom vi inte vet hur händerna du foldade skulle ha gått. Sådant visas inte.
"""
from __future__ import annotations

import math
import zlib
from array import array
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .db import cached
from .statlib import (BOOT_REPS, _cluster_stats, _cr_t, _moments, _p_one_sided, bh_cutoff,  # noqa: F401
                      bootstrap_t_p, cluster_se, johnson_p)


Z_REQUIRED = 3.0          # används bara i beskrivande text/översikt
MIN_N = 100               # minsta antal beslut i VARJE halva
MIN_EFFECT_BB = 0.3
DISCOVERY_Q = 0.10        # Benjamini–Hochberg i upptäcktshalvan
CONFIRM_ALPHA = 0.05      # familjevis felrisk i bekräftelsehalvan (Bonferroni)


MIN_BIG_WINS = 5          # minst så många resultat över +BIG_WIN_BB i varje halva
BIG_WIN_BB = 10.0

SPOT_STREET = {"flop_mot_bet": 1, "flop_mot_raise": 1, "turn_mot_bet": 2, "turn_mot_raise": 2,
               "river_mot_bet": 3, "river_mot_raise": 3}  # övriga: preflop (0)


def cluster_of(h) -> int:
    """(Äldre definition, används bara per hand vid extraktionen; analysen använder spelpass, se
    facts.FactTable._sessionize.) Kluster = bord + tre-timmarsblock. Händer från samma pass delar motståndare, form och
    bordsbild, så de hålls ihop: hela klustret hamnar i samma halva och bootstrap drar hela kluster."""
    return zlib.crc32(f"{h.table}|{h.date:%Y-%m-%d}|{h.date.hour // 3}".encode())


def half_of(cluster: int) -> int:
    """0 = halva A (upptäckt), 1 = halva B (bekräftelse). Deterministiskt per kluster."""
    return (cluster >> 7) & 1

POSTFLOP_ORDER = ["SB", "BB", "UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN"]

SPOT_NAMES = {
    "rfi": "när det är foldat till dig",
    "efter_limp": "efter en limp",
    "mot_hojning": "mot en öppning",
    "bb_mot_hojning": "i BB mot en öppning",
    "sb_mot_hojning": "i SB mot en öppning",
    "kall_mot_3bet": "när det redan är öppnat och 3-bettat",
    "mot_3bet_ip": "mot en 3-bet i position",
    "mot_3bet_oop": "mot en 3-bet ur position",
    "mot_4bet": "mot en 4-bet",
    "flop_mot_bet": "mot en bet på floppen",
    "turn_mot_bet": "mot en bet på turn",
    "river_mot_bet": "mot en bet på river",
    "flop_mot_raise": "mot en raise på floppen",
    "turn_mot_raise": "mot en raise på turn",
    "river_mot_raise": "mot en raise på river",
}
ACTION_VERB = {
    ("rfi", "raise"): "öppna", ("rfi", "call"): "limpa",
    ("efter_limp", "call"): "limpa efter", ("efter_limp", "raise"): "isolera (höja)",
    ("mot_hojning", "call"): "cold-calla", ("mot_hojning", "raise"): "3-betta",
    ("bb_mot_hojning", "call"): "syna", ("bb_mot_hojning", "raise"): "3-betta",
    ("sb_mot_hojning", "call"): "syna", ("sb_mot_hojning", "raise"): "3-betta",
    ("kall_mot_3bet", "call"): "cold-calla", ("kall_mot_3bet", "raise"): "4-betta",
    ("mot_3bet_ip", "call"): "syna", ("mot_3bet_ip", "raise"): "4-betta",
    ("mot_3bet_oop", "call"): "syna", ("mot_3bet_oop", "raise"): "4-betta",
    ("mot_4bet", "call"): "syna", ("mot_4bet", "raise"): "5-betta",
    ("flop_mot_bet", "call"): "syna", ("flop_mot_bet", "raise"): "raisa",
    ("turn_mot_bet", "call"): "syna", ("turn_mot_bet", "raise"): "raisa",
    ("river_mot_bet", "call"): "syna", ("river_mot_bet", "raise"): "raisa",
    ("flop_mot_raise", "call"): "syna", ("flop_mot_raise", "raise"): "re-raisa",
    ("turn_mot_raise", "call"): "syna", ("turn_mot_raise", "raise"): "re-raisa",
    ("river_mot_raise", "call"): "syna", ("river_mot_raise", "raise"): "re-raisa",
}

RIVER_BUCKETS = [  # (övre gräns för andel slumpade motståndarhänder som slår dig, namn) – se BoardTable.beat_n
    (0.10, "nöten eller nästan (under 10 % av händerna slår dig)"),
    (0.25, "nära nöten (10–25 % slår dig)"),
    (0.50, "medelstark hand (25–50 % slår dig)"),
    (0.75, "svag hand (50–75 % slår dig)"),
    (1.01, "mycket svag hand (över 75 % slår dig)"),
]


@dataclass
class Group:
    n: int = 0
    s: float = 0.0
    sq: float = 0.0
    examples: list = field(default_factory=list)
    vals: array = field(default_factory=lambda: array("d"))
    half: bytearray = field(default_factory=bytearray)
    clus: array = field(default_factory=lambda: array("q"))
    hids: list = field(default_factory=list)

    def add(self, delta: float, hid: str, cluster: int | None = None) -> None:
        if cluster is None:
            cluster = zlib.crc32(str(hid).encode())
        self.n += 1
        self.s += delta
        self.sq += delta * delta
        self.vals.append(delta)
        self.half.append(half_of(cluster))
        self.clus.append(cluster)
        self.hids.append(hid)
        self.examples.append((hid, delta))
        if len(self.examples) > 400:  # behåll de dyraste
            self.examples.sort(key=lambda x: x[1])
            del self.examples[40:]

    @property
    def mean(self) -> float:
        return self.s / self.n if self.n else 0.0

    @property
    def se(self) -> float:
        if self.n < 2:
            return float("inf")
        var = max(self.sq / self.n - self.mean ** 2, 0.0) * self.n / (self.n - 1)
        return math.sqrt(var / self.n)

    @property
    def z(self) -> float:
        se = self.se
        return self.mean / se if se and se != float("inf") else 0.0


class GroupArr:
    """En beslutsgrupp med värden i numpy-arrayer (byggs från faktatabellen)."""
    __slots__ = ("n", "s", "sq", "vals", "half", "clus", "hids", "examples")

    def __init__(self):
        self.n, self.s, self.sq = 0, 0.0, 0.0
        self.vals = np.zeros(0)
        self.half = np.zeros(0, bool)
        self.clus = np.zeros(0, np.int64)
        self.hids = np.zeros(0, np.int64)
        self.examples = []

    @classmethod
    def from_arrays(cls, vals, clus, hids, examples):
        g = cls()
        g.vals = np.asarray(vals, dtype=np.float64)
        g.clus = np.asarray(clus, dtype=np.int64)
        g.half = ((g.clus >> 7) & 1).astype(bool)
        g.hids = np.asarray(hids)
        g.n = len(g.vals)
        g.s = float(np.cumsum(g.vals)[-1]) if g.n else 0.0
        g.sq = float((g.vals * g.vals).sum())
        g.examples = list(examples)
        return g

    mean = Group.mean
    se = Group.se
    z = Group.z


class PreRows:
    """Preflop-beslut i kolumnform (spot, position, handling, resultat mot fold) för ett urval.

    Kolumner: spot/pos/kind (koder), delta (NaN = fold), hidx (rad i handtabellen), clu.
    Handens egenskaper (nöt-egenskaper, startkort, handpoäng) hämtas från faktatabellen via hidx.
    Att iterera ger samma tupler som tidigare: (spot, pos, kind, delta|None, hand-id, kluster, hålkort)."""

    def __init__(self, ft=None, mask=None):
        self.ft = ft
        if ft is None or mask is None:
            self.spot = self.pos = self.kind = np.zeros(0, np.int16)
            self.delta = np.zeros(0)
            self.hidx = np.zeros(0, np.int32)
            self.clu = np.zeros(0, np.int64)
            return
        P = ft.t["pre"]
        m = ft.subset_mask(mask, "pre")
        self.spot, self.pos, self.kind = P["spot"][m], P["pos"][m], P["kind"][m]
        self.delta, self.hidx = P["delta"][m], P["hidx"][m]
        self.clu = ft.H["clu"][self.hidx] if len(self.hidx) else np.zeros(0, np.int64)

    def __len__(self):
        return len(self.delta)

    def is_spot(self, *names) -> np.ndarray:
        if self.ft is None:
            return np.zeros(0, bool)
        codes = [self.ft.code("spot", n) for n in names]
        return np.isin(self.spot, codes)

    def label(self, col: str, code: int) -> str:
        return self.ft.label({"spot": "spot", "pos": "pos", "kind": "kind"}[col], int(code))

    def played(self) -> np.ndarray:
        return ~np.isnan(self.delta)

    def hole(self, j: int):
        from .facts import decode_cards
        return decode_cards(self.ft.H["hole"][self.hidx[j]])

    def __iter__(self):
        if self.ft is None:
            return iter(())
        from .facts import decode_cards
        lab = self.ft.vocab
        ids = self.ft.H["id"]
        holes = self.ft.H["hole"]
        return ((lab["spot"][s], lab["pos"][p], lab["kind"][k], None if d != d else float(d), ids[h], int(c),
                 decode_cards(holes[h]))
                for s, p, k, d, h, c in zip(self.spot, self.pos, self.kind, self.delta, self.hidx, self.clu))


@dataclass
class Decisions:
    groups: dict = field(default_factory=lambda: defaultdict(Group))   # (spot, pos, bucket, action) -> Group
    folds: dict = field(default_factory=lambda: defaultdict(int))      # (spot, pos, bucket) -> antal fold
    tests: int = 0
    candidates: int = 0
    pre: list = field(default_factory=list)  # preflop-beslut med hålkort: (spot, pos, kind, delta|None, hid, kluster, hole)
    river: list = field(default_factory=list)  # river mot bet: (storlek, handstyrka, kind, delta|None, kluster, hid)
    turn_calls: list = field(default_factory=list)  # syn mot turn-bet: (handstyrka på turn, delta mot fold på turn, kluster, vad som hände på river)


def _river_bucket(hole, board, hid) -> str:
    from .board import BoardTable
    frac = BoardTable.get(board).beat_n(hole)  # andel motståndarhänder (lika många kort) som slår handen
    for limit, name in RIVER_BUCKETS:
        if frac < limit:
            return name
    return RIVER_BUCKETS[-1][1]


def full_raise_flags(h) -> dict:
    """id(action) -> True om en preflop-höjning är en hel höjning. En kort all-in som höjer
    mindre än föregående höjning öppnar inte upp nya höjningar och räknas inte som en
    höjningsnivå (t.ex. inte som en 3-bet)."""
    cur = max([a.to for a in h.actions if a.street == "preflop" and a.kind in ("post_bb", "post_straddle")]
              or [h.bb or 0.0])
    last_inc = cur  # minsta höjning = största blind/straddle
    flags = {}
    for a in h.actions:
        if a.street != "preflop" or a.kind != "raise":
            continue
        inc = a.to - cur
        full = not (a.allin and inc < last_inc - 1e-9)
        flags[id(a)] = full
        if a.to > cur:
            if full:
                last_inc = inc
            cur = a.to
    return flags


def collect(dec: Decisions, h, hero: str, net_ev_bb: float, pos: str, bucket: str | None) -> None:
    """Registrera heros beslut i handen med skillnaden mot att folda."""
    bb = h.bb or 1.0
    inv = 0.0          # vad hero lagt i potten hittills
    raises = 0
    raises_any = 0     # även korta all-in-höjningar
    lvl_offset = 0
    limpers = 0
    raisers = []
    hero_pre = 0       # antal preflop-beslut hittills
    opened = False
    threebet = False
    facing_done = set()
    street_bet = {"flop": 0.0, "turn": 0.0, "river": 0.0}
    street_contrib = {}
    street_aggr = defaultdict(int)   # antal bet/raise på gatan hittills
    hero_aggr = set()                # gator där hero själv bettat/höjt
    cur_street = "preflop"
    hole = h.hole.get(hero)
    hb = bucket or "okänd"
    full = full_raise_flags(h)
    clu = cluster_of(h)
    pot = 0.0
    first_bet = {}  # gata -> (betens storlek, potten före beten)
    turn_call = None  # (handstyrka, delta) om hero synade en bet på turn
    river_first = None  # hero:s första river-handling: ("mot", kind) eller ("egen", kind)

    def rec(spot, p, b, kind, inv_before):
        key = (spot, p, b)
        pre_spot = spot not in SPOT_STREET
        if kind == "fold":
            dec.folds[key] += 1
            if pre_spot and hole:
                dec.pre.append((spot, p, "fold", None, h.id, clu, hole))
            return
        if kind not in ("call", "raise"):
            return
        delta = net_ev_bb + inv_before / bb
        dec.groups[(spot, p, b, kind)].add(delta, h.id, clu)
        if pre_spot and hole:
            dec.pre.append((spot, p, kind, delta, h.id, clu, hole))

    for a in h.actions:
        if a.street != cur_street:
            cur_street = a.street
            street_contrib = {}
            street_bet[cur_street] = 0.0
        if a.inferred:
            continue
        if a.street == "preflop":
            pot += a.added
            if a.kind.startswith("post"):
                if a.player == hero:
                    inv += a.added
                continue
            if a.player == hero:
                k = a.kind
                if hero_pre == 0 and k == "check":
                    hero_pre += 1   # straddlarens/BB:s option – inget öppningsbeslut
                    inv += a.added
                    continue
                if hero_pre == 0:
                    # första beslutet: hela höjningar avgör nivån, men en kort all-in som enda höjning
                    # är ändå en höjning för den som inte agerat (inte "foldat till dig")
                    lvl = raises if raises > 0 else min(raises_any, 1)
                    lvl_offset = lvl - raises  # 1 när enda höjningen var en kort all-in (räknas som nivå 1)
                    if lvl == 0 and pos != "BB":
                        rec("rfi" if limpers == 0 else "efter_limp", pos, hb, k, inv)
                        opened = k == "raise" and limpers == 0
                    elif lvl == 0 and k == "raise":
                        rec("efter_limp", pos, hb, k, inv)  # BB höjer över limpers
                    elif lvl == 1:
                        spot = {"BB": "bb_mot_hojning", "SB": "sb_mot_hojning"}.get(pos, "mot_hojning")
                        rec(spot, pos, hb, k, inv)
                        threebet = k == "raise"
                    elif lvl == 2:
                        rec("kall_mot_3bet", pos, hb, k, inv)
                elif hero_pre >= 1:
                    if opened and raises == 2 and "3b" not in facing_done:
                        facing_done.add("3b")
                        tb = raisers[-1]
                        ip = _idx(h, hero) > _idx(h, tb)
                        rec("mot_3bet_ip" if ip else "mot_3bet_oop", pos, hb, k, inv)
                    elif threebet and raises + lvl_offset == 3 and "4b" not in facing_done:
                        facing_done.add("4b")
                        rec("mot_4bet", pos, hb, k, inv)
                hero_pre += 1
                inv += a.added
            if a.kind == "raise":
                raises_any += 1
                if full.get(id(a), True):
                    raises += 1
                    raisers.append(a.player)
            elif a.kind == "call" and raises_any == 0:
                limpers += 1
            continue

        # postflop
        st_ = a.street
        if a.player == hero:
            facing = street_bet.get(st_, 0.0) > street_contrib.get(hero, 0.0) + 1e-9
            if facing and st_ not in facing_done and a.kind in ("fold", "call", "raise"):
                facing_done.add(st_)
                # "mot en bet": en enda bet på gatan och hero har inte själv bettat. Annars "mot en raise".
                kind_ = "mot_bet" if street_aggr[st_] == 1 and st_ not in hero_aggr else "mot_raise"
                spot = f"{st_}_{kind_}"
                if st_ == "river":
                    rb = (cached(f"rb6|{h.id}|{hero}", lambda: _river_bucket(hole, h.board, h.id))
                          if hole and len(h.board) == 5 else None)
                    if a.kind == "fold":
                        dec.folds[(spot, "alla", rb or "alla")] += 1  # med handstyrka, som flop/turn
                    elif rb:
                        rec(spot, "alla", rb, a.kind, inv)
                    if kind_ == "mot_bet" and st_ in first_bet and rb:
                        b_, p_ = first_bet[st_]
                        dec.river.append((size_bucket(b_ / p_ if p_ > 0 else 1.0), rb, a.kind,
                                          None if a.kind == "fold" else net_ev_bb + inv / bb, clu, h.id))
                elif hole and len(h.board) >= (3 if st_ == "flop" else 4):
                    b = cached(f"sb|{h.id}|{hero}|{st_}",
                               lambda: _street_bucket(hole, h.board[:3] if st_ == "flop" else h.board[:4]))
                    rec(spot, "alla", b, a.kind, inv)
                    if st_ == "turn" and kind_ == "mot_bet" and a.kind == "call":
                        turn_call = (b, net_ev_bb + inv / bb)
            if st_ == "river" and river_first is None and a.kind in ("fold", "call", "raise", "bet", "check"):
                river_first = ("mot" if facing else "egen", a.kind)
            if a.kind in ("bet", "raise"):
                hero_aggr.add(st_)
            inv += a.added
        if a.kind == "bet" and st_ not in first_bet:
            first_bet[st_] = (a.added, pot)
        pot += a.added
        if a.kind in ("bet", "raise", "call") or a.player == hero:
            street_contrib[a.player] = a.to
        if a.kind in ("bet", "raise"):
            street_bet[st_] = max(street_bet.get(st_, 0.0), a.to)
            street_aggr[st_] += 1
    if turn_call is not None:
        if river_first is None:
            path = "ingen river (all-in eller handen slut)"
        elif river_first[0] == "mot":
            path = {"fold": "foldade mot river-bet", "call": "synade river-bet",
                    "raise": "höjde river-bet"}.get(river_first[1], "övrigt")
        else:
            path = {"bet": "bettade själv river", "raise": "bettade själv river", "check": None}.get(river_first[1], "övrigt")
            if path is None:  # hero checkade: blev det check-check eller en bet efteråt?
                path = "check-check river"
                for a2 in h.actions:
                    if a2.street == "river" and a2.player == hero and a2.kind in ("fold", "call", "raise") and not a2.inferred:
                        path = {"fold": "foldade mot river-bet", "call": "synade river-bet",
                                "raise": "höjde river-bet"}[a2.kind]
                        break
        dec.turn_calls.append((turn_call[0], turn_call[1], clu, path))



SIZE_BUCKETS = [(0.40, "liten (under 40 % av potten)"), (0.60, "medel (40–60 %)"),
                (0.85, "stor (60–85 %)"), (9e9, "pott eller mer (över 85 %)")]


def size_bucket(frac: float) -> str:
    for lim, name in SIZE_BUCKETS:
        if frac < lim:
            return name
    return SIZE_BUCKETS[-1][1]


def _street_bucket(hole, board) -> str:
    """Handtyp på flop/turn: hur stark den färdiga handen är just nu (mot slumpade händer på
    samma bord) och om den har ett stort drag (minst 8 kort som ger stege eller bättre)."""
    from .board import BoardTable
    from .ev import CATEGORY, _pairs, _triples, fast_best
    bt = BoardTable.get(board)
    u = bt.strength_u(hole)
    pairs = _pairs(hole)
    cur = CATEGORY[fast_best(pairs, _triples(board))]
    target = max(4, cur + 1)
    # antal kort som ger stege eller bättre (och bättre än nu) – alla kort utvärderas på en gång
    from .fastev import CATEGORY_A, best_values_hole, code
    used = set(hole) | set(board)
    rem = [code((r, su)) for r in range(2, 15) for su in "cdhs" if (r, su) not in used]
    bc = [code(c) for c in board]
    boards = np.array([bc + [c] for c in rem], dtype=np.int64)
    vals = best_values_hole([code(c) for c in hole], boards)
    outs = int((CATEGORY_A[vals] >= target).sum())
    made = "stark hand" if u < 0.15 else ("medelstark hand" if u < 0.45 else "svag hand")
    return made + (" + stort drag" if outs >= 8 else "")


def _idx(h, p) -> int:
    pos = h.positions.get(p, "")
    return POSTFLOP_ORDER.index(pos) if pos in POSTFLOP_ORDER else -1


# ---------------------------------------------------------------- utvärdering
def _merged(dec: Decisions):
    """Lägg till aggregerade grupper (alla positioner / alla handtyper)."""
    parts = defaultdict(list)
    for (spot, pos, b, act), g in dec.groups.items():
        for key in {(spot, pos, b, act), (spot, pos, "alla", act), (spot, "alla", b, act), (spot, "alla", "alla", act)}:
            parts[key].append(g)
    out = {}
    for key, gs in parts.items():
        m = GroupArr()
        m.vals = np.concatenate([np.asarray(g.vals, dtype=np.float64) for g in gs])
        m.clus = np.concatenate([np.asarray(g.clus, dtype=np.int64) for g in gs])
        m.half = ((m.clus >> 7) & 1).astype(bool)
        m.hids = np.concatenate([np.asarray(g.hids) if not isinstance(g.hids, list) else np.array(g.hids, dtype=object)
                                 for g in gs])
        m.n = sum(g.n for g in gs)
        m.s = sum(g.s for g in gs)
        m.sq = sum(g.sq for g in gs)
        for g in gs:
            m.examples.extend(g.examples)
        out[key] = m
    return out


class Half:
    """Ena halvan av en grupps beslut: värden, kluster och hand-id."""
    __slots__ = ("x", "c", "ids")

    def __init__(self, x, c, ids):
        self.x, self.c, self.ids = x, c, ids

    def __len__(self):
        return len(self.x)

    def without(self, drop: set) -> "Half":
        if not drop:
            return self
        ids = np.asarray(self.ids)
        if ids.dtype == object:
            keep = np.array([i not in drop for i in ids], dtype=bool)
        else:
            keep = ~np.isin(ids, np.fromiter(drop, dtype=ids.dtype, count=len(drop)))
        return Half(self.x[keep], self.c[keep], ids[keep])


def _split(g):
    x = np.asarray(g.vals, dtype=np.float64)
    c = np.asarray(g.clus, dtype=np.int64)
    hb = ((c >> 7) & 1).astype(bool)
    ids = np.asarray(g.hids) if not isinstance(g.hids, list) else np.array(g.hids, dtype=object)
    return (Half(x[~hb], c[~hb], ids[~hb]), Half(x[hb], c[hb], ids[hb]))


def _tail_ok(x) -> bool:
    """Grupper där vinsterna är sällsynta men stora (t.ex. limpar) kan se ut som säkra förluster
    bara för att ingen stor vinst råkade hamna i urvalet. Kräv att svansen faktiskt syns."""
    return int((x > BIG_WIN_BB).sum()) >= MIN_BIG_WINS


def _overlaps(k1, k2) -> bool:
    s1, p1, b1, a1 = k1
    s2, p2, b2, a2 = k2
    if (s1, a1) != (s2, a2):
        return False
    return (p1 == p2 or "alla" in (p1, p2)) and (b1 == b2 or "alla" in (b1, b2))


def _confirm(a: Half, b: Half, alpha: float, key) -> dict | None:
    if len(a) < MIN_N or len(b) < MIN_N:
        return None
    if not (_tail_ok(a.x) and _tail_ok(b.x)):
        return None
    if float(a.x.mean()) > -MIN_EFFECT_BB or float(b.x.mean()) > -MIN_EFFECT_BB:
        return None
    p_b = bootstrap_t_p(b.x, b.c, seed=zlib.crc32(repr(key).encode()))
    if p_b > alpha:
        return None
    return {"p_b": p_b}


def proven_leaks(dec: Decisions, total_hands: int) -> list[dict]:
    groups = _merged(dec)
    tested = []
    for key, g in groups.items():
        a, b = _split(g)
        if len(a) >= MIN_N and len(b) >= MIN_N:
            tested.append((key, g, a, b))
    dec.tests = len(tested)
    dec.candidates = 0
    if not tested:
        return []
    # 1) upptäckt i halva A: Johnson-korrigerad test + Benjamini–Hochberg över alla tester
    pa = [johnson_p(a.x) for _, _, a, _ in tested]
    cutoff = bh_cutoff(pa, DISCOVERY_Q)
    cands = [(t, pa[i]) for i, t in enumerate(tested)
             if cutoff > 0 and pa[i] <= cutoff and float(t[2].x.mean()) <= -MIN_EFFECT_BB and _tail_ok(t[2].x)]
    dec.candidates = len(cands)
    if not cands:
        return []
    alpha = CONFIRM_ALPHA / len(cands)
    # 2) bekräftelse i halva B – senare gator först. Resultatet av ett tidigt beslut innehåller
    #    allt som händer senare i handen. När en läcka på en senare gata är bekräftad tas de
    #    händerna bort från de tidigare gatornas grupper, så att samma förlust inte skylls på
    #    t.ex. flop-synen också och inte räknas två gånger.
    cands.sort(key=lambda t: -SPOT_STREET.get(t[0][0][0], 0))
    claimed: dict[int, set] = defaultdict(set)   # gata -> hand-id som tillhör bekräftade läckor
    confirmed = []
    for (key, g, a, b), p_a in cands:
        street = SPOT_STREET.get(key[0], 0)
        drop = set().union(*[ids for st_, ids in claimed.items() if st_ > street]) if claimed else set()
        a2, b2 = a.without(drop), b.without(drop)
        res = _confirm(a2, b2, alpha, key)
        if res is None:
            continue
        claimed[street].update(a2.ids)
        claimed[street].update(b2.ids)
        confirmed.append((key, g, a2, b2, p_a, res["p_b"], len(drop & set(g.hids))))
    # 3) kostnad från halva B; överlappande grupper rapporteras bara en gång
    rows = []
    for key, g, a, b, p_a, p_b, removed in confirmed:
        nb, mb, _, _ = _moments(b.x)
        se_b = cluster_se(b.x, b.c)
        n_used = len(a) + len(b)
        total = mb * n_used
        hi = min(mb + 1.96 * se_b, 0.0)  # försiktig gräns: förlusten är minst så stor
        rows.append((key, g, {"n": n_used, "n_a": len(a), "n_b": nb, "mean": mb, "mean_a": float(a.x.mean()),
                              "se": se_b, "z": mb / se_b if se_b else 0.0, "p_a": p_a, "p_b": p_b,
                              "removed_later_street": removed, "total": total,
                              "cost100": -100.0 * total / total_hands if total_hands else 0.0,
                              "cost100_low": -100.0 * hi * n_used / total_hands if total_hands else 0.0}))
    rows.sort(key=lambda r: (sum(x == "alla" for x in r[0][1:3]), -r[2]["cost100"]))
    out, chosen = [], []
    for key, g, d in rows:
        if any(_overlaps(key, k) for k in chosen):
            continue
        chosen.append(key)
        spot, pos, bkt, act = key
        fold_n = sum(v for (s2, p2, b2), v in dec.folds.items()
                     if s2 == spot and (pos == "alla" or p2 == pos) and (bkt == "alla" or b2 == bkt))
        d.update({"spot": spot, "pos": pos, "bucket": bkt, "action": act, "folds": fold_n,
                  "examples": sorted(g.examples, key=lambda x: x[1])[:5]})
        out.append(d)
    out.sort(key=lambda d: d["cost100"], reverse=True)
    return out


def detectable_effect(dec: Decisions) -> list[dict]:
    """Ungefär hur stor förlust per beslut (bb) som kan bekräftas i varje grupp med ditt urval."""
    rows = []
    for (spot, pos, b, act), g in _merged(dec).items():
        if pos != "alla" or b != "alla":
            continue
        a, bh = _split(g)
        if len(bh) < MIN_N:
            continue
        se = cluster_se(bh.x, bh.c)
        rows.append({"spot": spot, "action": act, "n": g.n, "mde": 3.5 * se})
    return rows


def tested_overview(dec: Decisions) -> list[dict]:
    """Alla testade grupper med resultat – för den som vill se underlaget."""
    rows = []
    for (spot, pos, b, act), g in _merged(dec).items():
        if g.n < MIN_N:
            continue
        rows.append({"spot": spot, "pos": pos, "bucket": b, "action": act, "n": g.n,
                     "mean": round(g.mean, 3), "se": round(g.se, 3), "z": round(g.z, 2)})
    rows.sort(key=lambda r: (r["z"], r["spot"], r["pos"], r["bucket"], r["action"]))
    return rows


# ---------------------------------------------------------------- krympta skattningar (empirisk Bayes)
def shrunk_groups(dec: Decisions) -> list[dict]:
    """Krympta skattningar för de finaste, icke-överlappande grupperna.

    Många samtidiga tester ger alltid några som ser dåliga ut av ren slump. Empirisk Bayes
    tar hänsyn till det: spridningen mellan alla grupper avgör hur mycket varje grupps
    resultat ska dras mot noll. Ut kommer en realistisk skattning av förlusten och
    sannolikheten att den verkligen är en förlust."""
    rows = [(k, g) for k, g in dec.groups.items() if g.n >= MIN_N and g.se not in (0, float("inf"))]
    if len(rows) < 5:
        return []
    by_spot = defaultdict(list)
    for k, g in rows:
        by_spot[k[0]].append((k, g))
    out = []
    for spot, items in by_spot.items():
        means = [g.mean for _, g in items]
        ses = [g.se for _, g in items]
        tau2 = max(sum(m * m - s * s for m, s in zip(means, ses)) / len(items), 0.25)
        for (sp, pos, b, act), g in items:
            w = tau2 / (tau2 + g.se ** 2)
            pm = w * g.mean
            psd = math.sqrt(w) * g.se
            p_loss = 0.5 * math.erfc(pm / (psd * math.sqrt(2))) if psd > 0 else float(pm < 0)
            out.append({"spot": sp, "pos": pos, "bucket": b, "action": act, "n": g.n, "mean": g.mean,
                        "se": g.se, "z": g.z, "post_mean": pm, "post_sd": psd, "p_loss": p_loss,
                        "total": pm * g.n, "folds": dec.folds.get((sp, pos, b), 0),
                        "examples": sorted(g.examples, key=lambda x: x[1])[:5]})
    return out
