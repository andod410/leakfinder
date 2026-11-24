"""Räknar fram hero-statistik ur parsade händer."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .cards import CATEGORY_NAMES, classify_start
from .decisions import Decisions, collect as collect_decisions
from .ev import allin_ev
from .parser import Hand

POSITIONS = ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
EARLY = {"UTG", "UTG+1", "MP", "LJ", "HJ"}
# Gränser för "andra-bästa"-analysen: andel motståndarkombinationer som slår dig.
COOLER_FRAC = 0.01   # under 1 %: du hade (nästan) nöten – cooler, inget misstag
WEAK_FRAC = 0.02     # minst 2 %: tydligt slagbar hand – här ligger läckan
STEAL_POS = {"CO", "BTN", "SB"}


@dataclass
class Stat:
    """En frekvens: hits / opps, plus exempelhänder och resultat i spotten."""

    hits: int = 0
    opps: int = 0
    net_hit: float = 0.0  # bb vunnet/förlorat i händer där hit inträffade
    net_all: float = 0.0
    hit_examples: list = field(default_factory=list)
    miss_examples: list = field(default_factory=list)
    sq_hit: float = 0.0  # kvadratsummor för felmarginaler
    sq_all: float = 0.0
    keep: bool = True  # spara exempelhänder (av för motståndare, sparar minne)

    def add(self, hand: Hand, hit: bool, net_bb: float) -> None:
        self.opps += 1
        self.net_all += net_bb
        self.sq_all += net_bb * net_bb
        if hit:
            self.hits += 1
            self.net_hit += net_bb
            self.sq_hit += net_bb * net_bb
            if self.keep:
                self.hit_examples.append((hand.id, net_bb))
        elif self.keep:
            self.miss_examples.append((hand.id, net_bb))

    # medel och standardfel för händerna med respektive utan handlingen
    def mean_hit(self):
        return self.net_hit / self.hits if self.hits else None

    def mean_miss(self):
        n = self.opps - self.hits
        return (self.net_all - self.net_hit) / n if n else None

    def se_hit(self):
        return _se(self.hits, self.net_hit, self.sq_hit)

    def se_miss(self):
        return _se(self.opps - self.hits, self.net_all - self.net_hit, self.sq_all - self.sq_hit)

    @property
    def pct(self):
        return 100.0 * self.hits / self.opps if self.opps else None

    def worst_hits(self, n=5):
        return sorted(self.hit_examples, key=lambda x: x[1])[:n]

    def worst_misses(self, n=5):
        return sorted(self.miss_examples, key=lambda x: x[1])[:n]


def _se(n, total, sq):
    if n < 2:
        return None
    mean = total / n
    var = max(sq / n - mean * mean, 0.0) * n / (n - 1)
    return (var / n) ** 0.5


def _light_stat():
    return Stat(keep=False)


@dataclass
class Bucket:
    hands: int = 0
    net: float = 0.0
    vpip: int = 0
    net_played: float = 0.0  # resultat bara i händer där du frivilligt gick in

    @property
    def per_played(self):
        return self.net_played / self.vpip if self.vpip else 0.0

    @property
    def bb100(self):
        return 100.0 * self.net / self.hands if self.hands else 0.0


@dataclass
class HeroStats:
    hero: str
    hands: int = 0
    net_bb: float = 0.0
    net_money: float = 0.0
    rake_paid_bb: float = 0.0
    rake_paid_money: float = 0.0
    stakes: dict = field(default_factory=lambda: defaultdict(int))
    games: dict = field(default_factory=lambda: defaultdict(int))
    s: dict = field(default_factory=lambda: defaultdict(Stat))
    by_pos: dict = field(default_factory=lambda: defaultdict(Bucket))
    rfi_by_pos: dict = field(default_factory=lambda: defaultdict(Stat))
    by_bucket: dict = field(default_factory=lambda: defaultdict(Bucket))
    by_nut: dict = field(default_factory=lambda: defaultdict(Bucket))        # antal nöt-egenskaper
    by_nut_combo: dict = field(default_factory=lambda: defaultdict(Bucket))  # vilka egenskaper
    by_nut_pos: dict = field(default_factory=lambda: defaultdict(Bucket))    # (antal, position)
    by_bucket_ep: dict = field(default_factory=lambda: defaultdict(Stat))  # VPIP i tidig position per handtyp
    cumulative: list = field(default_factory=list)
    big_losses: list = field(default_factory=list)
    reverse_dominated: list = field(default_factory=list)
    river_calls: list = field(default_factory=list)
    agg_actions: int = 0
    pass_actions: int = 0
    tilt: dict = field(default_factory=dict)
    first_date: object = None
    last_date: object = None
    hands_by_id: dict = field(default_factory=dict)
    diag: dict = field(default_factory=lambda: defaultdict(int))
    samples: dict = field(default_factory=lambda: defaultdict(list))  # syfte -> [hand-id] för exportfilen
    header_examples: dict = field(default_factory=dict)  # rubrikens blinds -> exempel på rubrikrad
    players: dict = field(default_factory=lambda: defaultdict(int))
    by_stake: dict = field(default_factory=dict)  # nivå -> händer, resultat, rake
    ev_net_bb: float = 0.0       # resultat med all-in-EV (bb)
    ev_net_money: float = 0.0
    ev_rake_bb: float = 0.0      # 2.80: väntad rake i all-in-EV-världen (equity × pottavgift), annars faktisk rake
    ev_rake_money: float = 0.0
    cumulative_ev: list = field(default_factory=list)
    cumulative_rake: list = field(default_factory=list)
    cumulative_money: list = field(default_factory=list)
    cumulative_ev_money: list = field(default_factory=list)
    cumulative_rake_money: list = field(default_factory=list)
    cumulative_sd: list = field(default_factory=list)
    cumulative_nsd: list = field(default_factory=list)
    cumulative_sd_money: list = field(default_factory=list)
    cumulative_nsd_money: list = field(default_factory=list)
    decisions: Decisions = field(default_factory=Decisions)
    ev_by_id: dict = field(default_factory=dict)
    allin: dict = field(default_factory=lambda: defaultdict(lambda: {"hands": 0, "actual_bb": 0.0, "ev_bb": 0.0, "eq_sum": 0.0, "actual_money": 0.0, "ev_money": 0.0}))
    light: bool = False  # lätt läge för motståndare: inga exempel, ingen showdown-analys

    def __getstate__(self):  # för den sparade senaste analysen: defaultdict med lambda går inte att spara
        d = dict(self.__dict__)
        d["allin"] = {k: dict(v) for k, v in self.allin.items()}
        return d

    def __setstate__(self, d):
        a = defaultdict(lambda: {"hands": 0, "actual_bb": 0.0, "ev_bb": 0.0, "eq_sum": 0.0, "actual_money": 0.0, "ev_money": 0.0})
        a.update(d.get("allin") or {})
        d["allin"] = a
        self.__dict__.update(d)

    def __post_init__(self):
        if self.light:
            self.s = defaultdict(_light_stat)
            self.rfi_by_pos = defaultdict(_light_stat)
            self.by_bucket_ep = defaultdict(_light_stat)

    @property
    def bb100(self):
        return 100.0 * self.net_bb / self.hands if self.hands else 0.0

    @property
    def ev_bb100(self):
        return 100.0 * self.ev_net_bb / self.hands if self.hands else 0.0

    @property
    def agg_freq(self):
        tot = self.agg_actions + self.pass_actions
        return 100.0 * self.agg_actions / tot if tot else None


def _ip(hand: Hand, a: str, b: str) -> bool:
    """True om spelare a agerar efter b postflop."""
    return hand.postflop_index(a) > hand.postflop_index(b)


def analyze(hands: list[Hand], hero: str = "Hero", nut_min_pot_bb: float = 20.0) -> HeroStats:
    """Analys av en lista händer i minnet: fakta extraheras per hand och summeras sedan –
    samma väg som när fakta kommer från den sparade databasen."""
    from .aggregate import build_stats
    from .facts import extract
    ft = extract(hands, hero)
    by_id = {h.id: h for h in hands}
    return build_stats(ft, None, hero, lookup=by_id.get)


def analyze_legacy(hands: list[Hand], hero: str = "Hero", nut_min_pot_bb: float = 20.0) -> HeroStats:
    """Den ursprungliga genomgången (används bara i tester för att jämföra med faktavägen)."""
    st = HeroStats(hero=hero)
    hands = [h for h in hands if hero in h.seats]
    hands.sort(key=lambda h: (h.date, h.id))
    running = 0.0
    for h in hands:
        _analyze_hand(st, h, hero, nut_min_pot_bb)
        running += h.net_bb(hero)
        st.cumulative.append(running)
        st.cumulative_ev.append(st.ev_net_bb)
        st.cumulative_rake.append(st.rake_paid_bb)
        st.cumulative_money.append(st.net_money)
        st.cumulative_ev_money.append(st.ev_net_money)
        st.cumulative_rake_money.append(st.rake_paid_money)
    _tilt(st, hands, hero)
    return st


def _analyze_hand(st: HeroStats, h: Hand, hero: str, nut_min_pot_bb: float) -> None:
    S = st.s
    net = h.net_bb(hero)
    pos = h.positions.get(hero, "?")
    st.hands += 1
    st.net_bb += net
    st.net_money += h.net(hero)
    st.stakes[f"{h.sb:g}/{h.bb:g}"] += 1
    st.games[f"PLO-{h.num_hole}"] += 1
    st.first_date = st.first_date or h.date
    st.last_date = h.date
    if not st.light:
        _hero_bookkeeping(st, h, hero)

    # All-in-EV: byt ut utfallet mot förväntat resultat när pengarna gick in före river.
    # Spot-statistik och resultat per position/handtyp räknas på EV (mindre slump).
    net_ev = net
    if not st.light:
        from .db import cached
        ev = cached(f"ev3|{h.id}|{hero}", lambda: allin_ev(h, hero))
        if ev is not None:
            ev_money, eq, street = ev
            net_ev = ev_money / h.bb
            # 2.80: EV före rake = Σ equity × pott (utan avgift). Avgiften är en andel f av varje pott, så den väntade
            # avgiften = (EV efter avgift + insats) · f/(1 − f) – samma f som i allin_ev.
            tot_c = sum(h.contrib(p) for p in h.seats)
            f_ = min(max(h.rake / tot_c, 0.0), 0.5) if tot_c > 0 else 0.0
            exp_fee = (ev_money + h.contrib(hero)) * f_ / (1 - f_) if f_ < 1 else 0.0
            st.ev_rake_money += exp_fee
            st.ev_rake_bb += exp_fee / h.bb
            a = st.allin[street]
            a["hands"] += 1
            a["actual_bb"] += net
            a["ev_bb"] += net_ev
            a["eq_sum"] += eq or 0.0
            a["actual_money"] += h.net(hero)
            a["ev_money"] += ev_money
            st.ev_net_money += ev_money
        else:
            st.ev_net_money += h.net(hero)
            st.ev_rake_bb += _hero_rake_bb(h, hero)
            st.ev_rake_money += _hero_rake_bb(h, hero) * h.bb
        st.ev_net_bb += net_ev
        row = st.by_stake[f"{h.sb:g}/{h.bb:g}"]
        row["ev_bb"] = row.get("ev_bb", 0.0) + net_ev

    hole = h.hole.get(hero)
    cls = classify_start(hole) if hole and len(hole) >= 4 else None
    _analyze_actions(st, h, hero, nut_min_pot_bb, net_ev, pos, cls)
    if not st.light:
        st.ev_by_id[h.id] = net_ev
        collect_decisions(st.decisions, h, hero, net_ev, pos, cls["nut"] if cls else None)


def _hero_bookkeeping(st: HeroStats, h: Hand, hero: str) -> None:
    st.hands_by_id[h.id] = h
    st.players[len(h.seats)] += 1
    hs_key = f"{h.header_stakes[0]:g}/{h.header_stakes[1]:g}" if h.header_stakes else "?"
    if hs_key not in st.header_examples and len(st.header_examples) < 40:
        st.header_examples[hs_key] = h.raw.split("\n", 1)[0]
    if h.header_stakes and abs(h.header_stakes[1] - h.bb) > 1e-9:
        st.diag["header_mismatch"] += 1
        _sample(st, "header_mismatch", h.id)
    for p_, street_ in h.inferred:
        if p_ == hero:
            st.diag[f"inferred_{street_}"] += 1
            _sample(st, f"inferred_fold_{street_}", h.id)
    rake_bb = 0.0
    if h.collected.get(hero) and h.total_pot:
        rake_bb = h.rake * h.collected[hero] / max(h.total_pot - h.rake, 1e-9) / h.bb
        st.rake_paid_bb += rake_bb
        st.rake_paid_money += rake_bb * h.bb
    row = st.by_stake.setdefault(f"{h.sb:g}/{h.bb:g}", {"hands": 0, "net_bb": 0.0, "rake_bb": 0.0, "net_money": 0.0,
                                                        "rake_money": 0.0})
    row["hands"] += 1
    row["net_bb"] += h.net_bb(hero)
    row["rake_bb"] += rake_bb
    row["rake_money"] = row.get("rake_money", 0.0) + rake_bb * h.bb
    row["net_money"] += h.net(hero)


def _hero_rake_bb(h, hero) -> float:
    if h.collected.get(hero) and h.total_pot:
        return h.rake * h.collected[hero] / max(h.total_pot - h.rake, 1e-9) / h.bb
    return 0.0


def _analyze_actions(st: HeroStats, h: Hand, hero: str, nut_min_pot_bb: float, net: float, pos: str, cls) -> None:
    S = st.s

    # ------------------------------------------------------------ preflop
    pre = [a for a in h.actions if a.street == "preflop" and not a.kind.startswith("post")]
    raises = 0          # hela höjningar (öppnar upp för spelare som redan agerat)
    raises_any = 0      # alla höjningar, även korta all-in – det spelare som inte agerat än möter
    limpers = 0
    raisers: list[str] = []
    raisers_any: list[str] = []
    offset = 0
    hero_acts = []  # (kind, raises_before, limpers_before, raisers_before)
    from .decisions import full_raise_flags
    full = full_raise_flags(h)
    for a in pre:
        if a.player == hero:
            first = not hero_acts or (len(hero_acts) == 1 and hero_acts[0][0] == "check")
            # en kort all-in som enda höjning är ändå en höjning för den som inte agerat (inte "foldat till dig")
            short_only = first and raises == 0 and raises_any > 0
            if short_only:
                offset = 1  # senare nivåer räknas från den (t.ex. hero 3-bettar, möter 4-bet)
            hero_acts.append((a.kind, 1 if short_only else raises + offset, limpers,
                              list(raisers_any[:1] if short_only else raisers)))
        if a.kind == "raise":
            raises_any += 1
            raisers_any.append(a.player)
            if full.get(id(a), True):
                raises += 1
                raisers.append(a.player)
        elif a.kind == "call" and raises_any == 0:
            limpers += 1
    pfa = raisers[-1] if raisers else None

    vpip = any(k in ("call", "raise") for k, *_ in hero_acts)
    pfr = any(k == "raise" for k, *_ in hero_acts)
    walk = not hero_acts
    if not walk:
        S["vpip"].add(h, vpip, net)
        S["pfr"].add(h, pfr, net)
    bp = st.by_pos[pos]
    bp.hands += 1
    bp.net += net
    bp.vpip += int(vpip)
    if cls:
        bk = st.by_bucket[cls["bucket"]]
        bk.hands += 1
        bk.net += net
        bk.vpip += int(vpip)
        if vpip:
            bk.net_played += net
        for d_, k_ in ((st.by_nut, cls["nut"]), (st.by_nut_combo, cls["nut_combo"]),
                       (st.by_nut_pos, (cls["nut"], pos))):
            b_ = d_[k_]
            b_.hands += 1
            b_.net += net
            b_.vpip += int(vpip)
            if vpip:
                b_.net_played += net

    if hero_acts and hero_acts[0][0] == "check":
        hero_acts = hero_acts[1:]  # straddle-/BB-option: inget öppningsbeslut
        opt_checked = True
    else:
        opt_checked = False
    if hero_acts and not opt_checked:
        k0, r0, l0, rs0 = hero_acts[0]
        if r0 == 0 and l0 == 0 and pos != "BB":
            st.rfi_by_pos[pos].add(h, k0 == "raise", net)
            S["rfi"].add(h, k0 == "raise", net)
            if pos != "SB":
                S["open_limp"].add(h, k0 == "call", net)
            else:
                S["sb_limp"].add(h, k0 == "call", net)
            if pos in STEAL_POS:
                S["steal"].add(h, k0 == "raise", net)
            if pos in EARLY and cls:
                if cls["weak"]:
                    S["ep_weak_open"].add(h, k0 == "raise", net)
                st.by_bucket_ep[cls["bucket"]].add(h, k0 == "raise", net)
        elif r0 == 0 and l0 > 0 and pos != "BB":
            S["overlimp"].add(h, k0 == "call", net)
        elif r0 == 1:
            opener = rs0[0]
            S["3bet"].add(h, k0 == "raise", net)
            if pos != "BB":
                S["cold_call"].add(h, k0 == "call", net)
            opener_pos = h.positions.get(opener, "")
            if pos in ("SB", "BB") and opener_pos in STEAL_POS and l0 == 0:
                S[f"{pos.lower()}_fold_steal"].add(h, k0 == "fold", net)
            if pos == "BB":
                S["bb_defend"].add(h, k0 != "fold", net)
        elif r0 == 2:
            S["cold_call_3bet"].add(h, k0 == "call", net)
            _sample(st, f"cold_3bet_{k0}", h.id)
            S["fold_vs_3bet_cold"].add(h, k0 == "fold", net)

        # hero öppnade och möter en 3-bet
        if k0 == "raise" and r0 == 0 and len(hero_acts) > 1:
            k1, r1, _, rs1 = hero_acts[1]
            if r1 == 2:
                threebettor = rs1[-1]
                S["fold_to_3bet"].add(h, k1 == "fold", net)
                _sample(st, f"faced_3bet_{k1}", h.id)
                S["4bet"].add(h, k1 == "raise", net)
                oop = not _ip(h, hero, threebettor)
                if oop:
                    S["call_3bet_oop"].add(h, k1 == "call", net)
                    S["fold_3bet_oop"].add(h, k1 == "fold", net)
        # hero 3-bettade och möter 4-bet
        if r0 == 1 and k0 == "raise" and len(hero_acts) > 1:
            k1, r1, _, _ = hero_acts[1]
            if r1 == 3:
                S["fold_to_4bet"].add(h, k1 == "fold", net)

    # ------------------------------------------------------------ postflop
    saw_flop = len(h.board) >= 3 and h.folded_on(hero) != "preflop"

    collected = h.collected.get(hero, 0.0) > 0
    if not saw_flop:
        return

    S["saw_flop"].add(h, True, net)
    flop_players = [p for p in h.seats if h.folded_on(p) != "preflop"]
    multiway = len(flop_players) > 2
    hero_is_pfa = pfa == hero

    street_info = {}
    for street in ("flop", "turn", "river"):
        acts = h.street_actions(street)
        info = _street(acts, hero)
        street_info[street] = info
        for a in acts:
            if a.player != hero:
                continue
            if a.kind in ("bet", "raise"):
                st.agg_actions += 1
            elif a.kind in ("call", "check", "fold"):
                st.pass_actions += 1

    f = street_info["flop"]
    # c-bet
    if hero_is_pfa and f["hero_first"] is not None and f["bets_before_hero"] == 0:
        key = "cbet_mw" if multiway else "cbet_hu"
        S[key].add(h, f["hero_first"] == "bet", net)
        # turn-barrel
        t = street_info["turn"]
        if f["hero_first"] == "bet" and not f["raised_after_hero"] and t["hero_first"] is not None \
                and t["bets_before_hero"] == 0:
            S["turn_barrel"].add(h, t["hero_first"] == "bet", net)
            r = street_info["river"]
            if t["hero_first"] == "bet" and not t["raised_after_hero"] and r["hero_first"] is not None \
                    and r["bets_before_hero"] == 0:
                S["river_barrel"].add(h, r["hero_first"] == "bet", net)
    # möter c-bet
    if pfa and pfa != hero and f["first_bettor"] == pfa and f["facing"] and f["facing"][0][1] == 1:
        resp = f["facing"][0][0]
        S["fold_to_cbet"].add(h, resp == "fold", net)
        S["raise_cbet"].add(h, resp == "raise", net)
    # check-raise
    if f["hero_first"] == "check" and f["facing_after_check"] is not None:
        S["flop_xr"].add(h, f["facing_after_check"] == "raise", net)
        S["flop_xf"].add(h, f["facing_after_check"] == "fold", net)

    for street in ("turn", "river"):
        info = street_info[street]
        if info["facing"] and info["facing"][0][1] == 1:  # en ren bet, inte en raise
            resp = info["facing"][0][0]
            S[f"fold_{street}_bet"].add(h, resp == "fold", net)
            if street == "river" and resp == "call":
                won = collected
                S["river_call_won"].add(h, won, net)

    showdown = h.went_to_showdown() and h.folded_on(hero) is None
    S["wtsd"].add(h, showdown, net)
    S["wwsf"].add(h, collected, net)
    if showdown:
        S["wsd"].add(h, collected, net)

    # ------------------------------------------------------------ showdown-analys
    pot_bb = h.pot_size() / h.bb
    hole = h.hole.get(hero)
    if not st.light and showdown and hole and len(h.board) == 5 and not h.run_twice and pot_bb >= nut_min_pot_bb:
        winners = [p for p in h.collected if p != hero and p in h.shown]
        if not collected and winners:
            from .db import cached
            w = winners[0]

            def _sd():
                from .board import BoardTable
                from .ev import CATEGORY
                bt = BoardTable.get(h.board)
                hc = CATEGORY[bt.hand_value(hole)]
                wc = CATEGORY[bt.hand_value(h.shown[w])]
                same = wc == hc and hc >= 3
                # 2.81: risken räknas på hela slumpade händer med lika många kort (blockers och beroende par ingår),
                # inte som 1 − (1 − f)^15, som behandlade de 15 paren som oberoende och överskattade
                risk = bt.beat_split(hole, len(h.shown[w]), samples=4000)[0] if same else None
                return hc, wc, (bt.beat_frac(hole) if same else None), risk
            hero_cat, w_cat, sd_frac, sd_risk = cached(f"sd2|{h.id}|{hero}", _sd)
            same_cat = w_cat == hero_cat and hero_cat >= 3
            entry = {
                "id": h.id,
                "net": net,
                "pot": pot_bb,
                "hero_hand": CATEGORY_NAMES[hero_cat],
                "villain_hand": CATEGORY_NAMES[w_cat],
                "same_cat": same_cat,
                "beats_pct": None,
                "risk_pct": None,
                "kind": "",
                "hero_cards": hole,
                "board": h.board,
                "villain_cards": h.shown[w],
            }
            if same_cat:
                frac = sd_frac
                combos = len(h.shown[w]) * (len(h.shown[w]) - 1) // 2
                entry["beats_pct"] = 100.0 * frac
                # chans att EN motståndare med n hålkort har minst en kombination som slår dig
                entry["risk_pct"] = 100.0 * sd_risk if sd_risk is not None else 100.0 * (1 - (1 - frac) ** combos)
                entry["kind"] = "cooler" if frac < COOLER_FRAC else ("gray" if frac < WEAK_FRAC else "weak")
                st.reverse_dominated.append(entry)
            st.big_losses.append(entry)



def _sample(st: HeroStats, key: str, hid: str, limit: int = 8) -> None:
    if st.light:
        return
    lst = st.samples[key]
    if len(lst) < limit:
        lst.append(hid)


def _street(acts, hero) -> dict:
    """Sammanfattar en gata ur heros perspektiv."""
    bets = 0
    hero_first = None
    bets_before_hero = None
    first_bettor = None
    facing = []  # (heros svar, antal bet/raise före)
    hero_bet_index = None
    raised_after_hero = False
    hero_checked = False
    facing_after_check = None
    cur_to = 0.0
    hero_to = 0.0
    for i, a in enumerate(acts):
        if a.player == hero:
            if hero_first is None:
                hero_first = a.kind
                bets_before_hero = bets
                hero_checked = a.kind == "check"
            if cur_to > hero_to + 1e-9 and a.kind in ("fold", "call", "raise"):
                facing.append((a.kind, bets))
                if hero_checked and facing_after_check is None and len(facing) == 1:
                    facing_after_check = a.kind
            if a.kind in ("bet", "raise"):
                hero_bet_index = i
            hero_to = a.to
        else:
            if a.kind in ("bet", "raise") and hero_bet_index is not None:
                raised_after_hero = True
        if a.kind in ("bet", "raise"):
            bets += 1
            if first_bettor is None:
                first_bettor = a.player
            cur_to = max(cur_to, a.to)
    return {
        "hero_first": hero_first,
        "bets_before_hero": bets_before_hero,
        "first_bettor": first_bettor,
        "facing": facing,
        "raised_after_hero": raised_after_hero,
        "facing_after_check": facing_after_check,
    }


def _tilt(st: HeroStats, hands: list[Hand], hero: str, big_loss_bb: float = 60.0, window: int = 30) -> None:
    """Jämför VPIP i händerna direkt efter en stor förlust med normal-VPIP."""
    after = Stat()
    normal = Stat()
    countdown = 0
    triggers = 0
    for h in hands:
        pre = [a for a in h.actions if a.street == "preflop" and a.player == hero and not a.kind.startswith("post")]
        if pre:
            vpip = any(a.kind in ("call", "raise") for a in pre)
            (after if countdown > 0 else normal).add(h, vpip, st.ev_by_id.get(h.id, h.net_bb(hero)))
        if countdown > 0:
            countdown -= 1
        if h.net_bb(hero) <= -big_loss_bb:
            countdown = window
            triggers += 1
    st.tilt = {"after": after, "normal": normal, "triggers": triggers, "threshold": big_loss_bb, "window": window}


def control_numbers(st: HeroStats) -> list[tuple[str, str]]:
    """Grundsiffror att jämföra mot DriveHUD (samma händer/filter) för att kontrollera att
    parsningen stämmer. Små skillnader beror på olika definitioner; stora tyder på fel."""
    S = st.s

    def pct(*keys):
        hits = sum(S[k].hits for k in keys if k in S)
        opps = sum(S[k].opps for k in keys if k in S)
        return f"{100 * hits / opps:.1f}%" if opps else "–"

    return [
        ("Händer", f"{st.hands}"),
        ("Vinst (pengar)", f"{st.net_money:+.2f}"),
        ("All-in EV (pengar)", f"{st.ev_net_money:+.2f}"),
        ("bb/100", f"{st.bb100:+.2f}"),
        ("All-in EV bb/100", f"{st.ev_bb100:+.2f}"),
        ("$EV Diff (EV − faktiskt)", f"{st.ev_net_money - st.net_money:+.2f}"),
        ("Rake + avgifter i vunna pottar (bb)", f"{st.rake_paid_bb:.0f}"),
        ("Rake + avgifter (pengar)", f"{st.rake_paid_money:.2f}"),
        ("Rake bb/100", f"{100 * st.rake_paid_bb / st.hands if st.hands else 0:.2f}"),
        ("bb/100 före rake", f"{100 * (st.net_bb + st.rake_paid_bb) / st.hands if st.hands else 0:+.2f}"),
        ("All-in EV bb/100 före rake", f"{100 * (st.ev_net_bb + st.ev_rake_bb) / st.hands if st.hands else 0:+.2f}"),
        ("VPIP", pct("vpip")),
        ("PFR", pct("pfr")),
        ("3-Bet", pct("3bet")),
        ("Fold to 3-Bet", pct("fold_to_3bet")),
        ("Flop C-Bet", pct("cbet_hu", "cbet_mw")),
        ("Fold to Flop C-Bet", pct("fold_to_cbet")),
        ("WTSD", pct("wtsd")),
        ("W$SD", pct("wsd")),
        ("WWSF", pct("wwsf")),
    ]


def money_summary(st) -> list[dict]:
    """Resultat, all-in EV och rake – totalt (bb och pengar) och per 100 händer."""
    n = st.hands or 1
    rows = [
        ("Vunnet (faktiskt)", st.net_bb, st.net_money),
        ("All-in EV", st.ev_net_bb, st.ev_net_money),
        ("Rake + avgifter betald", st.rake_paid_bb, st.rake_paid_money),
        ("Vunnet före rake", st.net_bb + st.rake_paid_bb, st.net_money + st.rake_paid_money),
        ("All-in EV före rake", st.ev_net_bb + st.ev_rake_bb, st.ev_net_money + st.ev_rake_money),
    ]
    return [{"label": l, "bb": bb, "money": m, "bb100": 100 * bb / n} for l, bb, m in rows]


def stake_table(st, min_hands: int = 100) -> list[dict]:
    """Resultat per nivå: faktiskt, all-in EV, rake och före rake – i pengar och bb/100.
    Nivåer med färre än min_hands händer slås ihop till "Övriga"."""
    rows, other = [], {"hands": 0, "net_bb": 0.0, "rake_bb": 0.0, "net_money": 0.0, "rake_money": 0.0,
                       "ev_bb": 0.0, "ev_money": 0.0}

    def bbsize(k):
        try:
            return float(k.split("/")[1])
        except (IndexError, ValueError):
            return 0.0

    def row(name, v):
        n = v["hands"] or 1
        ev_bb = v.get("ev_bb", v["net_bb"])
        ev_money = v.get("ev_money", ev_bb * bbsize(name))
        return {"stake": name, "hands": v["hands"], "net_money": v["net_money"], "bb100": 100 * v["net_bb"] / n,
                "ev_money": ev_money, "ev100": 100 * ev_bb / n,
                "rake_money": v.get("rake_money", 0.0), "rake100": 100 * v["rake_bb"] / n,
                "pre_money": v["net_money"] + v.get("rake_money", 0.0), "pre100": 100 * (v["net_bb"] + v["rake_bb"]) / n,
                "ev_pre_money": ev_money + v.get("evr_money", v.get("rake_money", 0.0)),
                "ev_pre100": 100 * (ev_bb + v.get("evr_bb", v["rake_bb"])) / n}

    for k, v in sorted(st.by_stake.items(), key=lambda kv: -bbsize(kv[0])):
        if v["hands"] >= min_hands:
            rows.append(row(k, v))
        else:
            for f in ("hands", "net_bb", "rake_bb", "net_money", "rake_money"):
                other[f] += v.get(f, 0.0)
            other["ev_bb"] += v.get("ev_bb", v["net_bb"])
            other["ev_money"] += v.get("ev_bb", v["net_bb"]) * bbsize(k)
            other["evr_bb"] = other.get("evr_bb", 0.0) + v.get("evr_bb", v["rake_bb"])
            other["evr_money"] = other.get("evr_money", 0.0) + v.get("evr_money", v.get("rake_money", 0.0))
    if other["hands"]:
        rows.append(row("Övriga", other))
    if len(rows) > 1:
        tot = {"hands": st.hands, "net_bb": st.net_bb, "rake_bb": st.rake_paid_bb, "net_money": st.net_money,
               "rake_money": st.rake_paid_money, "ev_bb": st.ev_net_bb, "ev_money": st.ev_net_money,
               "evr_bb": st.ev_rake_bb, "evr_money": st.ev_rake_money}
        t = row("Totalt", tot)
        t["total"] = True
        rows.append(t)
    return rows


def table_type(h) -> str:
    return "Rush & Cash" if h.id.startswith("RC") or "rush" in (h.table or "").lower() else "Vanliga bord"
