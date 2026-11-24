"""Riktvärden från vinnande spelare i DIN egen databas.

Alla händer du spelat innehåller också dina motståndares beslut. Programmet
räknar samma statistik för varje motståndare med stort urval, väljer ut de som
vunnit, och använder spridningen bland dem som riktvärde. Det ger riktvärden
för just din variant, dina nivåer och din spelarpool, i stället för gissningar.

Begränsningar (står även i rapporten):
- Motståndarnas vinst mäts bara i händer där du satt med. Med några tusen
  händer är vinstmåttet brusigt, så "vinnare" är delvis tur.
- Fungerar bara om sajten ger motståndare samma namn/ID över tid.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .parser import Hand
from .stats import HeroStats, _analyze_hand

MIN_STAT_OPPS = 30  # minsta antal tillfällen för att en spelares värde ska räknas
MIN_PLAYERS = 8     # minsta antal spelare för att ett riktvärde ska användas


@dataclass
class Benchmark:
    lo: float      # 10:e percentilen
    p25: float
    median: float
    p75: float
    hi: float      # 90:e percentilen
    n: int         # antal spelare
    group: str     # "vinnare" eller "regs"


@dataclass
class Pool:
    min_hands: int
    players_total: int = 0
    regs: int = 0
    winners: int = 0
    group: str = ""
    ranges: dict = field(default_factory=dict)      # stat-nyckel -> Benchmark
    rfi: dict = field(default_factory=dict)         # position -> Benchmark
    extra: dict = field(default_factory=dict)       # "agg", "gap", "vpip", "pfr" -> Benchmark
    reg_rows: list = field(default_factory=list)    # sammanfattning per reg (anonym)
    hands_per_player: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return bool(self.ranges)

    @property
    def anonymized(self) -> bool:
        """Många olika namn men ingen med många händer = sajten anonymiserar (t.ex. GG)."""
        return self.players_total >= 1000 and self.hands_per_player.get("≥1 000", 0) == 0


def _pct(vals: list[float], q: float) -> float:
    vals = sorted(vals)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * q
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def _bench(vals: list[float], group: str) -> Benchmark | None:
    if len(vals) < MIN_PLAYERS:
        return None
    lo, med, hi = _pct(vals, 0.10), _pct(vals, 0.5), _pct(vals, 0.90)
    # Minst ±3 procentenheter runt medianen, så att en väldigt likartad pool
    # inte gör att små avvikelser flaggas som läckor.
    lo, hi = min(lo, med - 3), max(hi, med + 3)
    return Benchmark(max(lo, 0.0), _pct(vals, 0.25), med, _pct(vals, 0.75), min(hi, 100.0), len(vals), group)


def analyze_pool(hands: list[Hand], hero: str, min_hands: int = 3000, progress=None) -> Pool:
    counts = Counter(p for h in hands for p in h.seats if p != hero)
    pool = Pool(min_hands=min_hands, players_total=len(counts))
    pool.hands_per_player = {
        "≥1 000": sum(1 for c in counts.values() if c >= 1000),
        "≥3 000": sum(1 for c in counts.values() if c >= 3000),
        "≥10 000": sum(1 for c in counts.values() if c >= 10000),
    }
    eligible = {p for p, c in counts.items() if c >= min_hands}
    pool.regs = len(eligible)
    if not eligible:
        return pool

    stats = {p: HeroStats(hero=p, light=True) for p in eligible}
    for i, h in enumerate(sorted(hands, key=lambda h: (h.date, h.id))):
        for p in h.seats:
            if p in stats:
                _analyze_hand(stats[p], h, p, 0.0)
        if progress and i % 20000 == 0:
            progress(i, len(hands))

    winners = [st for st in stats.values() if st.bb100 > 0]
    pool.winners = len(winners)
    group_stats, group = (winners, "vinnare") if len(winners) >= MIN_PLAYERS else (list(stats.values()), "regs")
    pool.group = group

    keys = set()
    for st in group_stats:
        keys.update(st.s.keys())
    for k in keys:
        vals = [st.s[k].pct for st in group_stats if k in st.s and st.s[k].opps >= MIN_STAT_OPPS]
        b = _bench(vals, group)
        if b:
            pool.ranges[k] = b
    positions = set()
    for st in group_stats:
        positions.update(st.rfi_by_pos.keys())
    for pos in positions:
        vals = [st.rfi_by_pos[pos].pct for st in group_stats
                if pos in st.rfi_by_pos and st.rfi_by_pos[pos].opps >= MIN_STAT_OPPS]
        b = _bench(vals, group)
        if b:
            pool.rfi[pos] = b
    aggs = [st.agg_freq for st in group_stats if st.agg_freq is not None and st.agg_actions + st.pass_actions >= 200]
    gaps = [st.s["vpip"].pct - st.s["pfr"].pct for st in group_stats if st.s["vpip"].opps >= 300]
    for name, vals in (("agg", aggs), ("gap", gaps)):
        b = _bench(vals, group)
        if b:
            pool.extra[name] = b

    for st in sorted(stats.values(), key=lambda s: -s.hands):
        pool.reg_rows.append({
            "hands": st.hands, "bb100": round(st.bb100, 1),
            "vpip": round(st.s["vpip"].pct or 0, 1), "pfr": round(st.s["pfr"].pct or 0, 1),
            "fold_to_3bet": round(st.s["fold_to_3bet"].pct, 1) if st.s["fold_to_3bet"].opps else None,
            "winner": st.bb100 > 0,
        })
    return pool
