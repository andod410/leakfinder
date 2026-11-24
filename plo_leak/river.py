"""River-modell byggd på din egen spelarpool.

Varför det fungerar
-------------------
GG visar alla händer vid showdown. När någon bettar river och blir synad ser vi
alltså bettarens hand. Den som synar vet inte vad bettaren har, så de händer vi
ser är ett *opartiskt stickprov* av vad poolen bettar med i den situationen.
Samma sak gäller:

* synarens hand när en bet synas (bettaren vet inte vad synaren har),
* hur ofta poolen foldar/synar/raisar mot en viss betstorlek,
* vad spelaren utan position har när river checkas igenom (den med position
  checkar utan att veta något om motståndarens hand).

Handstyrka mäts som *andel slumpade motståndarhänder (lika många kort, dina kort
borttagna) som slår handen* på just det bordet (0 = nöten). Måttet är jämförbart mellan bord, så
tusentals river-situationer kan slås ihop.

Med det kan programmet räkna ut EV för alla alternativ i heros river-beslut –
även för de alternativ hero inte valde – och därmed hitta både för många och för
få syner, missade värdebets och dåliga bets. Varje slutsats har en felmarginal,
och modellen kontrolleras mot hur heros händer faktiskt gick (kalibrering).

Begränsningar (står även i rapporten): bara heads-up på river; bara beslut mot
en bet och beslut med position efter check; poolen behandlas som en helhet
(GG anonymiserar spelarna).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .board import BoardTable, texture

SIZE_BUCKETS = [(0.40, "liten (<40 % av potten)"), (0.80, "medel (40–80 %)"),
                (1.10, "pottstor (80–110 %)"), (99.0, "överbet (>110 %)")]
MIN_SAMPLES = 120          # minsta stickprov för en range innan vi faller tillbaka till grövre nivå
DRAWS = 400                # slumpdragningar för felmarginaler
Q_LOW = 0.025              # ett beslut räknas som säkert fel bara om även 2,5 %-percentilen visar förlust
rng = np.random.default_rng(12345)


def size_bucket(frac: float) -> str:
    for lim, name in SIZE_BUCKETS:
        if frac < lim:
            return name
    return SIZE_BUCKETS[-1][1]


# ---------------------------------------------------------------- avgifter
class FeeModel:
    """Rake+avgifter som funktion av slutpotten, per nivå (bb), skattad ur händerna."""
    EDGES = [0, 4, 8, 15, 30, 60, 120, 1e9]

    def __init__(self):
        self.table = {}

    def fit(self, hands):
        data = defaultdict(lambda: defaultdict(list))
        for h in hands:
            pot = h.pot_size()
            if pot <= 0 or not h.bb or len(h.board) < 3:  # GG tar ingen rake på preflop-händer
                continue
            pb = pot / h.bb
            for i in range(len(self.EDGES) - 1):
                if self.EDGES[i] <= pb < self.EDGES[i + 1]:
                    data[h.bb][i].append(h.rake / h.bb)
                    break
        for bb, bins in data.items():
            self.table[bb] = {i: float(np.median(v)) for i, v in bins.items() if len(v) >= 20}
        return self

    def fit_arrays(self, pot_bb, rake_bb, bb):
        """Samma sak ur faktatabellen (pott och rake i bb, big blind i dollar). Händer utan rake
        (preflop-händer) räknas inte."""
        pot_bb, rake_bb, bb = (np.asarray(x, dtype=float) for x in (pot_bb, rake_bb, bb))
        ok = (pot_bb > 0) & (rake_bb > 0)
        data = defaultdict(lambda: defaultdict(list))
        idx = np.searchsorted(np.array(self.EDGES), pot_bb[ok], side="right") - 1
        for b, i, r in zip(bb[ok].tolist(), idx.tolist(), rake_bb[ok].tolist()):
            data[b][i].append(r)
        for b, bins in data.items():
            self.table[b] = {i: float(np.median(v)) for i, v in bins.items() if len(v) >= 20}
        return self

    def fee(self, pot_bb: float, bb: float) -> float:
        t = self.table.get(bb) or (next(iter(self.table.values())) if self.table else {})
        for i in range(len(self.EDGES) - 1):
            if self.EDGES[i] <= pot_bb < self.EDGES[i + 1]:
                if i in t:
                    return t[i]
                near = [k for k in t if k <= i]
                return t[max(near)] if near else 0.0
        return 0.0


# ---------------------------------------------------------------- extraktion
def _line(h, player) -> str:
    """Vem som var aggressor på turn, sett från spelaren: 'själv', 'motståndaren' eller 'ingen'."""
    aggr = None
    for a in h.actions:
        if a.street == "turn" and a.kind in ("bet", "raise"):
            aggr = a.player
    if aggr is None:
        return "ingen"
    return "själv" if aggr == player else "motståndaren"


def extract(h, hero: str) -> dict | None:
    """Plocka ut heads-up-riversituationen i en hand (alla spelare, inte bara hero)."""
    if len(h.board) < 5 or h.run_twice:
        return None
    folded_before = {a.player for a in h.actions if a.kind == "fold" and a.street in ("preflop", "flop", "turn")}
    at_river = [p for p in h.seats if p not in folded_before]
    if len(at_river) != 2:
        return None
    river = [a for a in h.actions if a.street == "river" and not a.inferred]
    if not river:
        return None
    oop, ip = sorted(at_river, key=h.postflop_index)
    pot = sum(a.added for a in h.actions if a.street != "river")
    if pot <= 0:
        return None
    first = river[0]
    if first.player != oop:
        return None
    before = defaultdict(float)
    for a in h.actions:
        if a.street != "river":
            before[a.player] += a.added
    eff = min(h.stacks.get(p, 0.0) - before[p] for p in (oop, ip))
    spot = {"id": h.id, "bb": h.bb, "pot": pot / h.bb, "tex": texture(h.board), "oop": oop, "ip": ip,
            "hero_role": "oop" if hero == oop else ("ip" if hero == ip else None),
            "eff": max(eff, 0.0) / h.bb, "spr": spr_bucket(max(eff, 0.0) / pot)}
    if first.kind == "check":
        if len(river) < 2:
            return None
        second = river[1]
        if second.kind == "check":
            spot.update(kind="checkthrough", line_oop=_line(h, oop))
        elif second.kind == "bet":
            spot.update(kind="bet", role="ip_bet", bettor=ip, resp=oop, bet=min(second.added, max(eff, 0.0)) / h.bb,
                        raw_bet=second.added / h.bb,
                        line=_line(h, ip), response=_response(river[2:], oop))
        else:
            return None
    elif first.kind == "bet":
        spot.update(kind="bet", role="lead", bettor=oop, resp=ip, bet=min(first.added, max(eff, 0.0)) / h.bb,
                    raw_bet=first.added / h.bb,
                    line=_line(h, oop), response=_response(river[1:], ip))
    else:
        return None
    if spot["kind"] == "bet":
        # 2.71: storleken räknas på effektiv risk (det motståndaren faktiskt kan syna), inte råbeloppet
        spot["size"] = size_bucket(spot["bet"] / spot["pot"])
        spot["frac"] = spot["bet"] / spot["pot"]
    # handstyrkor för de spelare vars kort syns
    known = {}
    for p in (oop, ip):
        cards = h.hole.get(p) if p == hero else h.shown.get(p)
        if cards and len(cards) >= 4:
            known[p] = cards
    if known:
        from .db import cached
        from .ev import _pairs, _triples, fast_best

        def _bn(p, c):  # samma värde som BoardTable(h.board).beat_n(c); sparas per hand och spelare
            key = f"bf6|{h.id}|{hero}" if p == hero else f"bfs|{h.id}|{p}"
            return cached(key, lambda: BoardTable.get(h.board).beat_n(c))
        # 'bf' = styrkemått som används i modellen: andel slumpade händer som slår handen.
        spot["bf"] = {p: _bn(p, c) for p, c in known.items()}
        spot["f"] = spot["bf"]  # samma mått ("slår dig"): andel motståndarhänder med lika många kort
        tri = _triples(h.board)
        spot["val"] = {p: fast_best(_pairs(c), tri) for p, c in known.items()}
    else:
        spot["bf"], spot["f"], spot["val"] = {}, {}, {}
    spot["sd"] = len(h.remaining()) == 2  # nådde showdown
    spot["hero_net"] = h.net(hero) / h.bb if hero in h.seats else None
    return spot


def _response(rest, responder) -> str | None:
    for a in rest:
        if a.player == responder:
            return {"fold": "fold", "call": "call", "raise": "raise"}.get(a.kind)
    return None


# ---------------------------------------------------------------- poolmodell
@dataclass
class Pool:
    bet_range: dict = field(default_factory=lambda: defaultdict(list))   # bettarens styrka när synad
    call_range: dict = field(default_factory=lambda: defaultdict(list))  # synarens styrka
    resp: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(3)))  # fold/call/raise
    check_range: dict = field(default_factory=lambda: defaultdict(list))  # OOP:s styrka vid check-igenom
    sizes: dict = field(default_factory=lambda: defaultdict(list))        # faktiska betstorlekar (andel av pott)
    n_spots: int = 0
    cal: dict = field(default_factory=dict)        # namn -> (x, y) för isoton omkalibrering
    cal_info: dict = field(default_factory=dict)   # namn -> {n, före, efter}

    def finalize(self):
        for d in (self.bet_range, self.call_range, self.check_range):
            for k in list(d):
                d[k] = np.sort(np.array(d[k], dtype=float))


def spr_bucket(spr: float) -> str:
    """Stack-till-pott-kvot på river. Låg SPR = nästan alla pengar redan i potten, och då
    foldar poolen mycket mer sällan – det måste modellen veta."""
    return "låg SPR (<1)" if spr < 1 else ("medel SPR (1–3)" if spr < 3 else "hög SPR (>3)")


def _levels4(role, size, line, tex, spr=None):
    """Från mest specifik till grövst. SPR behålls längst eftersom den styr foldfrekvensen mest."""
    return [(role, size, line, tex, spr), (role, size, line, None, spr), (role, size, None, None, spr),
            (None, size, None, None, spr), (None, size, None, None, None), (None, None, None, None, None)]


def _levels2(line, tex, spr=None):
    return [(line, tex, spr), (line, None, spr), (None, tex, spr), (None, None, spr), (None, None, None)]


def build_pool(spots: list[dict], hero: str) -> Pool:
    pool = Pool()
    for s in spots:
        if s.get("kind") == "bet" and s.get("frac", 0) > 1.000001:
            continue
        pool.n_spots += 1
        if hero in (s.get("oop"), s.get("ip")):
            continue  # hero:s egna händer används bara för kontrollen, aldrig för att bygga modellen
        if s["kind"] == "checkthrough":
            oop = s["oop"]
            if oop != hero and oop in s["bf"] and s["sd"]:
                for k in _levels2(s["line_oop"], s["tex"], s["spr"]):
                    pool.check_range[k].append(s["bf"][oop])
            continue
        bettor, resp_p = s["bettor"], s["resp"]
        levels = _levels4(s["role"], s["size"], s["line"], s["tex"], s["spr"])
        if resp_p != hero and s["response"] in ("fold", "call", "raise"):
            idx = ("fold", "call", "raise").index(s["response"])
            for k in levels:
                pool.resp[k][idx] += 1
            pool.sizes[(s["role"], s["size"])].append(s["frac"])
            pool.sizes[(s["role"], s["size"], s["spr"])].append(s["frac"])
        if s["response"] == "call" and s["sd"]:
            if bettor != hero and bettor in s["bf"]:
                for k in levels:
                    pool.bet_range[k].append(s["bf"][bettor])
            if resp_p != hero and resp_p in s["bf"]:
                for k in levels:
                    pool.call_range[k].append(s["bf"][resp_p])
    pool.finalize()
    return pool


def _pav(x, y, bins: int = 30):
    """Isoton regression (pool adjacent violators) på binnad data. Returnerar brytpunkter (x, y).
    Binningen gör kurvan stabil även där det finns få händer."""
    order = np.argsort(x)
    x, y = np.asarray(x, dtype=float)[order], np.asarray(y, dtype=float)[order]
    chunks = np.array_split(np.arange(len(x)), min(bins, max(1, len(x) // 60)))
    blocks = [[float(y[c].sum()), float(len(c)), float(x[c].mean()), float(x[c].mean())] for c in chunks if len(c)]
    out = []
    for b in blocks:
        out.append(b)
        while len(out) > 1 and out[-2][0] / out[-2][1] > out[-1][0] / out[-1][1]:
            s2, w2, lo2, hi2 = out.pop()
            out[-1][0] += s2
            out[-1][1] += w2
            out[-1][3] = hi2
    xs = np.array([(b[2] + b[3]) / 2 for b in out])
    ys = np.array([b[0] / b[1] for b in out])
    return xs, ys


def _apply_cal(pool, name, p):
    c = pool.cal.get(name)
    if c is None:
        return p
    xs, ys = c
    return float(np.interp(p, xs, ys)) if np.isscalar(p) else np.interp(p, xs, ys)


def _train_calibration(pool: Pool, spots, hero):
    """Lär omkalibrering på poolens EGNA utfall (hero ingår inte) med leave-one-out,
    så att modellens sannolikheter blir rätt i snitt innan de används på heros beslut."""
    data = defaultdict(lambda: ([], []))
    for s in spots:
        bf = s["bf"]
        if s["kind"] == "checkthrough":
            oop, ip = s["oop"], s["ip"]
            if hero in (oop, ip) or oop not in bf or ip not in bf or not s["sd"]:
                continue
            arr, _ = _lookup(pool.check_range, _levels2(s["line_oop"], s["tex"], s["spr"]))
            if arr is None:
                continue
            w, n = _wins(arr, bf[ip])
            w -= _one(bf[ip], bf[oop])          # leave-one-out (samma mått som i rangen)
            n -= 1
            data["check"][0].append(w / n)
            data["check"][1].append(_res(s, ip, oop))
        elif s["response"] == "call" and s["sd"]:
            b, r = s["bettor"], s["resp"]
            if hero in (b, r) or b not in bf or r not in bf:
                continue
            keys = _levels4(s["role"], s["size"], s["line"], s["tex"], s["spr"])
            arr, _ = _lookup(pool.bet_range, keys)
            if arr is not None:
                w, n = _wins(arr, bf[r])
                w -= _one(bf[r], bf[b])
                n -= 1
                data["facing"][0].append(w / n)
                data["facing"][1].append(_res(s, r, b))
            if s["role"] == "ip_bet":
                arr, _ = _lookup(pool.call_range, keys)
                if arr is not None:
                    w, n = _wins(arr, bf[b])
                    w -= _one(bf[b], bf[r])
                    n -= 1
                    data["ipcall"][0].append(w / n)
                    data["ipcall"][1].append(_res(s, b, r))
    for name, (x, y) in data.items():
        if len(x) < 200:
            continue
        x, y = np.array(x), np.array(y)
        pool.cal[name] = _pav(x, y)
        after = np.interp(x, *pool.cal[name])
        pool.cal_info[name] = {"n": len(x), "brier_before": float(np.mean((x - y) ** 2)),
                               "brier_after": float(np.mean((after - y) ** 2))}


def _fold(hid: str) -> int:
    return sum(map(ord, hid)) % 2


class HeroCal:
    """Korsvaliderad omkalibrering på heros EGNA utfall (2-fold cross-fitting).

    Varje hands förutsägelse kalibreras med en kurva som lärts på den ANDRA halvan av
    heros händer. Därför är kontrollen mot heros utfall fortfarande en äkta test på
    data modellen inte sett, samtidigt som systematiska skillnader mellan poolen i
    stort och just heros situationer rättas."""
    MIN_POINTS = 300

    def __init__(self):
        self.models = {}

    def fit(self, name, rows):
        """rows: [(hand_id, förutsagt p, utfall 0/0.5/1)]"""
        if len(rows) < self.MIN_POINTS:
            return
        m = {}
        for f in (0, 1):
            train = [(p, y) for hid, p, y in rows if _fold(hid) != f]
            if len(train) < self.MIN_POINTS // 2:
                return
            xs, ys = _pav([p for p, _ in train], [y for _, y in train])
            # Krympning mot ingen ändring när datan är liten: vikt = n / (n + 600)
            m[f] = (xs, ys, len(train) / (len(train) + 600))
        self.models[name] = m

    def map(self, name, hid, p):
        m = self.models.get(name)
        if not m:
            return p
        xs, ys, w = m[_fold(hid)]
        return float(w * np.interp(p, xs, ys) + (1 - w) * p)


class _NoCal:
    def map(self, name, hid, p):
        return p


def _one(hb, vb):
    """Utfall för en hand med styrka hb mot vb: 1 vinst, 0.5 delad, 0 förlust."""
    return 1.0 if hb < vb else (0.5 if hb == vb else 0.0)


def _res(s, a, b):
    """Verkligt utfall för spelare a mot b i samma hand: jämför handvärdena (exakt), annars styrkemåttet."""
    v = s.get("val") or {}
    if a in v and b in v:
        return 1.0 if v[a] > v[b] else (0.5 if v[a] == v[b] else 0.0)
    return _one(s["bf"][a], s["bf"][b])


def _lookup(table, keys, min_n=MIN_SAMPLES):
    for lvl, k in enumerate(keys):
        v = table.get(k)
        if v is not None and len(v) >= min_n:
            return v, lvl
    return None, None


def _wins(sorted_arr, hb):
    """Antal (vinster + halva delningar) för en hand med styrka hb mot ett stickprov.
    Lägre bf = starkare hand; hero vinner mot de med högre bf."""
    lo = np.searchsorted(sorted_arr, hb, side="left")
    hi = np.searchsorted(sorted_arr, hb, side="right")
    return (len(sorted_arr) - hi) + 0.5 * (hi - lo), len(sorted_arr)


def _beta(k, n, size=DRAWS):
    return rng.beta(k + 0.5, n - k + 0.5, size=size)


# ---------------------------------------------------------------- heros beslut
@dataclass
class Decision:
    kind: str           # "mot_bet" eller "ip_efter_check"
    id: str
    chosen: str
    best: str
    gain: float         # punktskattning: hur mycket bättre bästa alternativet är (bb)
    gain_q05: float     # försiktig skattning (5:e percentilen)
    detail: dict
    category: str = ""


def eval_facing(s, hero, pool: Pool, fees: FeeModel, bb: float, hc=None) -> Decision | None:
    """Hero möter en bet heads-up på river: syna eller folda?"""
    hb = s["bf"].get(hero)
    if hb is None or s["response"] not in ("fold", "call"):
        return None
    arr, lvl = _lookup(pool.bet_range, _levels4(s["role"], s["size"], s["line"], s["tex"], s["spr"]))
    if arr is None:
        return None
    w, n = _wins(arr, hb)
    pc = (hc or _NoCal()).map("facing", s["id"], _apply_cal(pool, "facing", w / n))
    p = _beta(pc * n, n)
    pot, bet = s["pot"], s["bet"]
    win_amt = pot + bet - fees.fee(pot + 2 * bet, bb)
    ev_call = p * win_amt - (1 - p) * bet           # relativt fold (= 0)
    point = pc * win_amt - (1 - pc) * bet
    if s["response"] == "fold":
        gain, q05, best = point, float(np.quantile(ev_call, Q_LOW)), "call" if point > 0 else "fold"
    else:
        gain, q05, best = -point, float(np.quantile(-ev_call, Q_LOW)), "fold" if point < 0 else "call"
    need = bet / (win_amt + bet)
    return Decision("mot_bet", s["id"], s["response"], best, gain, q05,
                    {"hb": hb, "p_win": pc, "p_raw": w / n, "need": need, "pot": pot, "bet": bet, "size": s["size"],
                     "n": n, "level": lvl, "tex": s["tex"], "line": s["line"], "role": s["role"]})


def eval_ip_after_check(s, hero, pool: Pool, fees: FeeModel, bb: float, hc=None) -> Decision | None:
    """Hero har position och motståndaren checkar river: checka eller betta (och hur mycket)?"""
    hb = s["bf"].get(hero)
    if hb is None:
        return None
    line_oop = _line_from_spot(s)
    cr, _ = _lookup(pool.check_range, _levels2(line_oop, s["tex"], s["spr"]))
    if cr is None:
        return None
    pot = s["pot"]
    w, n = _wins(cr, hb)
    hc = hc or _NoCal()
    psd = hc.map("check", s["id"], _apply_cal(pool, "check", w / n))
    p_sd = _beta(psd * n, n)
    comp = {}
    ev = {"check": p_sd * (pot - fees.fee(pot, bb))}
    point = {"check": psd * (pot - fees.fee(pot, bb))}
    hero_line = s.get("line") if s["kind"] == "bet" else _line_ip(s)
    for lim, name in SIZE_BUCKETS:
        keys = _levels4("ip_bet", name, hero_line, s["tex"], s["spr"])
        r_counts = None
        for k in keys:
            c = pool.resp.get(k)
            if c is not None and c.sum() >= MIN_SAMPLES:
                r_counts = c
                break
        call_arr, _ = _lookup(pool.call_range, keys)
        sizes = pool.sizes.get(("ip_bet", name, s["spr"])) or pool.sizes.get(("ip_bet", name))
        if r_counts is None or call_arr is None or not sizes or len(sizes) < 30:
            continue
        frac = float(np.median(sizes))
        b = min(frac * pot, s["eff"], pot)  # kan inte betta mer än vad som finns kvar
        if b <= 0:
            continue
        dr = rng.dirichlet(r_counts + 0.5, size=DRAWS)
        wc, nc = _wins(call_arr, hb)
        pwc_pt = hc.map("ipwin", s["id"], _apply_cal(pool, "ipcall", wc / nc))
        pwc = _beta(pwc_pt * nc, nc)
        fee_c = fees.fee(pot + 2 * b, bb)
        fee_f = fees.fee(pot, bb)
        pr = r_counts / r_counts.sum()
        pf_new = hc.map("ipfold", s["id"], float(pr[0]))
        if abs(pf_new - pr[0]) > 1e-12:   # justera fold-chansen, fördela resten som tidigare
            rest_old = max(1 - pr[0], 1e-9)
            pr = np.array([pf_new, pr[1] / rest_old * (1 - pf_new), pr[2] / rest_old * (1 - pf_new)])
            d0 = np.clip(dr[:, 0] + (pf_new - (r_counts / r_counts.sum())[0]), 0, 1)
            other = dr[:, 1:] / np.maximum(dr[:, 1:].sum(axis=1, keepdims=True), 1e-9)
            dr = np.column_stack([d0, other * (1 - d0)[:, None]])
        comp[name] = {"pf": float(pr[0]), "pwc": float(pwc_pt)}
        val = dr[:, 0] * (pot - fee_f) + dr[:, 1] * (pwc * (pot + b - fee_c) - (1 - pwc) * b) - dr[:, 2] * b
        pt = pr[0] * (pot - fee_f) + pr[1] * (pwc_pt * (pot + b - fee_c) - (1 - pwc_pt) * b) - pr[2] * b
        ev[name] = val
        point[name] = pt
    if len(ev) < 2:
        return None
    if s["kind"] == "checkthrough":
        chosen = "check"
    else:
        chosen = s["size"]
        if chosen not in ev:
            return None
    best = max(point, key=point.get)
    gain = point[best] - point[chosen]
    q05 = float(np.quantile(ev[best] - ev[chosen], Q_LOW)) if best != chosen else 0.0
    return Decision("ip_efter_check", s["id"], chosen, best, gain, q05,
                    {"hb": hb, "pot": pot, "ev": {k: round(float(v), 2) for k, v in point.items()},
                     "p_sd": psd, "tex": s["tex"], "comp": comp})


def _line_from_spot(s):
    return s.get("line_oop") or ("motståndaren" if s.get("line") == "själv" else
                                 "själv" if s.get("line") == "motståndaren" else "ingen")


def _line_ip(s):
    lo = s.get("line_oop", "ingen")
    return "motståndaren" if lo == "själv" else ("själv" if lo == "motståndaren" else "ingen")


# ---------------------------------------------------------------- hela analysen
@dataclass
class RiverResult:
    spots: int = 0
    pool: Pool | None = None
    decisions: list = field(default_factory=list)
    calibration: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    hero_cal: list = field(default_factory=list)
    bluff: dict = field(default_factory=dict)


STR_EDGES = [(0.10, "Nöten eller nästan"), (0.25, "Nära nöten"), (0.50, "Medelstark"), (0.75, "Svag"), (1.01, "Mycket svag")]


def _str_name(f):
    for lim, name in STR_EDGES:
        if f < lim:
            return name
    return STR_EDGES[-1][1]


def hero_bet_summary(spots, hero: str) -> dict:
    """Dina egna river-bets heads-up: hur ofta motståndaren foldat per betstorlek, jämfört med hur ofta en
    ren bluff behöver lyckas (bet / (pott + bet)), och hur ofta du bettat i position när det checkats till
    dig, per handstyrka. Motståndarens fold syns alltid, så foldandelen är ett opartiskt mått."""
    by_size = {name: [0, 0, 0, []] for _, name in SIZE_BUCKETS}  # fold, call, raise, storlekar
    ip = {name: [0, 0] for _, name in STR_EDGES}                   # bet, check
    for s in spots:
        if s["kind"] == "bet" and s.get("bettor") == hero and s.get("response") in ("fold", "call", "raise"):
            b = by_size[s["size"]]
            b[("fold", "call", "raise").index(s["response"])] += 1
            b[3].append(s["frac"])
        if s.get("hero_role") == "ip" and hero in s.get("f", {}):
            if s["kind"] == "checkthrough":
                ip[_str_name(s["f"][hero])][1] += 1
            elif s["kind"] == "bet" and s.get("role") == "ip_bet" and s.get("bettor") == hero:
                ip[_str_name(s["f"][hero])][0] += 1
    rows = []
    for _, name in SIZE_BUCKETS:
        f, c, r, fr = by_size[name]
        n = f + c + r
        if n < 30:
            continue
        frac = float(np.median(fr))
        need = frac / (1 + frac)
        p = f / n
        se = float(np.sqrt(p * (1 - p) / n))
        rows.append({"size": name, "n": n, "fold_pct": 100 * p, "fold_lo": 100 * (p - 1.96 * se), "need_pct": 100 * need,
                     "frac_pct": 100 * frac, "edge": bool(p - 1.96 * se > need)})
    iprows = [{"strength": name, "bet": b, "check": c, "n": b + c, "bet_pct": 100 * b / (b + c) if b + c else None}
              for name, (b, c) in ip.items() if b + c]
    return {"sizes": rows, "ip": iprows}


def analyze_river(hands, hero: str, total_hands: int) -> RiverResult:
    fees = FeeModel().fit(hands)
    spots = []
    for h in hands:
        s = extract(h, hero)
        if s:
            spots.append(s)
    return analyze_spots(spots, hero, fees, total_hands)


def analyze_spots(spots: list, hero: str, fees: FeeModel, total_hands: int) -> RiverResult:
    """River-modellen på färdiga river-situationer (från extract) – t.ex. sparade i faktatabellen."""
    res = RiverResult()
    res.spots = len(spots)
    pool = build_pool(spots, hero)
    _train_calibration(pool, spots, hero)
    res.pool = pool
    def run(hc):
        out, ids = [], {}
        for s in spots:
            if s["hero_role"] is None:
                continue
            d = None
            if s["kind"] == "bet" and s["resp"] == hero and s["bettor"] != hero:
                d = eval_facing(s, hero, pool, fees, s["bb"], hc)
            elif s["hero_role"] == "ip" and (s["kind"] == "checkthrough" or (s["kind"] == "bet" and s["role"] == "ip_bet")):
                d = eval_ip_after_check(s, hero, pool, fees, s["bb"], hc)
            if d:
                out.append(d)
                ids[d.id] = (d, s)
        return out, ids

    # Pass 1: bara poolkalibrering. Används för att lära heros korsvaliderade omkalibrering.
    first, ids1 = run(None)
    hc = HeroCal()
    for name, rows in _outcome_rows(first, ids1, hero).items():
        hc.fit(name, rows)
    res.hero_cal = sorted(hc.models)
    # Pass 2: med korsvaliderad omkalibrering; kontrollen görs på dessa (osedda) förutsägelser.
    res.decisions, by_id = run(hc)
    res.calibration = _calibrate(res.decisions, by_id, hero)
    res.findings = _findings(res, total_hands)
    res.bluff = hero_bet_summary(spots, hero)
    res.summary = {
        "spots": res.spots, "hero_decisions": len(res.decisions),
        "pool_bet_samples": int(len(pool.bet_range.get((None, None, None, None, None), []))),
        "pool_call_samples": int(len(pool.call_range.get((None, None, None, None, None), []))),
        "pool_check_samples": int(len(pool.check_range.get((None, None, None), []))),
        "pool_responses": int(pool.resp.get((None, None, None, None, None), np.zeros(3)).sum()),
    }
    return res


CAL_NAMES = {
    "facing": "syn mot river-bet",
    "check": "check-igenom med position",
    "ipfold": "fold mot dina river-bets",
    "ipwin": "vinst när din river-bet synas",
}


def _outcome_rows(decisions, by_id, hero) -> dict:
    """(hand-id, förutsagt, utfall) per modellkomponent, för heros beslut där utfallet syns."""
    rows = defaultdict(list)
    for d in decisions:
        _, s = by_id[d.id]
        bf = s["bf"]
        if d.kind == "mot_bet":
            if d.chosen == "call" and s["sd"] and s["bettor"] in bf:
                rows["facing"].append((d.id, d.detail["p_win"], _res(s, hero, s["bettor"])))
        else:
            if d.chosen == "check":
                if s["sd"] and s["oop"] in bf:
                    rows["check"].append((d.id, d.detail["p_sd"], _res(s, hero, s["oop"])))
            else:
                c = d.detail.get("comp", {}).get(d.chosen)
                if c and s.get("response") in ("fold", "call", "raise"):
                    rows["ipfold"].append((d.id, c["pf"], 1.0 if s["response"] == "fold" else 0.0))
                    if s["response"] == "call" and s["sd"] and s["resp"] in bf:
                        rows["ipwin"].append((d.id, c["pwc"], _res(s, hero, s["resp"])))
    return rows


def _calibrate(decisions, by_id, hero) -> dict:
    """Jämför modellens förutsägelser med hur heros händer faktiskt gick (på korsvaliderade
    förutsägelser, dvs. data som kalibreringen inte sett)."""
    out = {}
    for key, rows in _outcome_rows(decisions, by_id, hero).items():
        name = CAL_NAMES[key]
        pred = np.array([p for _, p, _ in rows])
        act = np.array([y for _, _, y in rows])
        n = len(rows)
        se = float(np.sqrt(np.sum(pred * (1 - pred))) / n) if n else 0.0
        bins = []
        for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
            m = (pred >= lo) & (pred < hi)
            if m.sum() >= 10:
                bins.append({"range": f"{int(lo * 100)}–{int(min(hi, 1) * 100)} %", "n": int(m.sum()),
                             "pred": float(pred[m].mean()), "actual": float(act[m].mean())})
        z = (act.mean() - pred.mean()) / se if n and se else 0.0
        worst = 0.0
        for b in bins:
            bse = np.sqrt(max(b["pred"] * (1 - b["pred"]), 0.01) / b["n"])
            b["z"] = float((b["actual"] - b["pred"]) / bse)
            worst = max(worst, abs(b["z"]))
        out[name] = {"n": n, "pred": float(pred.mean()) if n else None, "actual": float(act.mean()) if n else None,
                     "z": float(z), "worst_bin_z": float(worst),
                     "ok": bool(n >= 50 and abs(z) < 3 and worst < 3.5), "bins": bins}
    return out


FIND_MIN_N = 30
FIND_MIN_COST100 = 0.3   # minst 0,3 bb/100 (försiktigt räknat) för att visas


def _findings(res: RiverResult, total_hands: int) -> list[dict]:
    """Säkerställda river-läckor: grupper av beslut där bättre alternativ är klart bättre."""
    cal = res.calibration
    groups = defaultdict(list)
    for d in res.decisions:
        if d.gain_q05 <= 0:
            continue
        if d.kind == "mot_bet":
            if d.chosen == "fold":
                key = ("river_fold", d.detail["size"])
            else:
                key = ("river_call", d.detail["size"])
        else:
            if d.chosen == "check":
                key = ("ip_missad_bet", "värde" if d.detail["hb"] < 0.50 else "bluff")
            elif d.best == "check":
                key = ("ip_onodig_bet", "värde" if d.detail["hb"] < 0.50 else "bluff")
            else:
                key = ("ip_fel_storlek", d.chosen)
        groups[key].append(d)
    out = []
    model_ok = {k: v["ok"] for k, v in cal.items()}
    for (kind, sub), ds in groups.items():
        if len(ds) < FIND_MIN_N:
            continue
        cons = sum(d.gain_q05 for d in ds)
        point = sum(d.gain for d in ds)
        cons100 = 100 * cons / total_hands
        if cons100 < FIND_MIN_COST100:
            continue
        if kind.startswith("river_"):
            validated = model_ok.get("syn mot river-bet", False)
        else:
            needed = ["check-igenom med position", "fold mot dina river-bets", "vinst när din river-bet synas"]
            validated = all(model_ok.get(k, False) for k in needed)
        out.append({"kind": kind, "sub": sub, "n": len(ds), "gain": point, "gain_cons": cons,
                    "cost100": 100 * point / total_hands, "cost100_cons": cons100,
                    "validated": bool(validated),
                    "examples": sorted(((d.id, -d.gain, d.detail) for d in ds), key=lambda x: x[1])[:6],
                    "avg_p": float(np.mean([d.detail.get("p_win", d.detail.get("p_sd", 0)) for d in ds])),
                    "avg_need": float(np.mean([d.detail.get("need", 0) for d in ds])),
                    "best_counts": dict(__import__("collections").Counter(d.best for d in ds))})
    out.sort(key=lambda f: f["cost100_cons"], reverse=True)
    return out


def frequency_table(res: RiverResult) -> list[dict]:
    """Per betstorlek: hur ofta hero foldar mot river-bets vs hur ofta modellen säger att fold är rätt."""
    if not component_ok(res, "mot_bet"):
        return []
    rows = defaultdict(lambda: {"n": 0, "fold": 0, "should_fold": 0, "need": [], "pwin_calls": []})
    for d in res.decisions:
        if d.kind != "mot_bet":
            continue
        r = rows[d.detail["size"]]
        r["n"] += 1
        r["fold"] += d.chosen == "fold"
        r["should_fold"] += d.detail["p_win"] < d.detail["need"]
        r["need"].append(d.detail["need"])
    out = []
    for _, name in SIZE_BUCKETS:
        r = rows.get(name)
        if not r or r["n"] < 20:
            continue
        out.append({"size": name, "n": r["n"], "fold_pct": 100 * r["fold"] / r["n"],
                    "model_fold_pct": 100 * r["should_fold"] / r["n"], "need": 100 * float(np.mean(r["need"]))})
    return out


def component_ok(res: RiverResult, kind: str) -> bool:
    """Är den del av modellen som beslutet bygger på godkänd i kontrollen mot heros utfall?"""
    ok = {k: v["ok"] for k, v in res.calibration.items()}
    if kind == "mot_bet":
        return ok.get("syn mot river-bet", False)
    return all(ok.get(k, False) for k in ("check-igenom med position", "fold mot dina river-bets",
                                          "vinst när din river-bet synas"))


def review_queue(res: RiverResult, limit: int = 25) -> list:
    """De dyraste säkra river-misstagen, för genomgång hand för hand.
    Bara beslut vars modelldel klarat kontrollen visas – annars vore listan ett råd utan grund."""
    ds = [d for d in res.decisions if d.gain_q05 > 0 and component_ok(res, d.kind)]
    ds.sort(key=lambda d: d.gain, reverse=True)
    return ds[:limit]
