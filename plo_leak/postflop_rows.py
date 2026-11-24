"""Postflop-beslut som tabellrader (för djupanalysen till Claude).

En rad per beslut du tar på flop, turn och river: läget när beslutet togs (antal spelare, position,
vem som höjde preflop, pottstorlek, SPR, vad du mötte) och vad du gjorde (check, bet, syn, höjning,
fold och storlek), plus handens styrka just då (handkategori, färgdrag) och bordets struktur.
Resultatet för handen finns i hands.csv (samma hand_id).
"""
from __future__ import annotations

from collections import Counter

from .cards import CATEGORY_NAMES
from .ev import CATEGORY, _pairs, _triples, fast_best
from .parser import POSTFLOP_ORDER

STREETS = ("flop", "turn", "river")
NB = {"flop": 3, "turn": 4, "river": 5}
HEADER = ["hand_id", "street", "players", "ip", "pfa", "pot_bb", "spr", "facing", "facing_pct", "action",
          "size_pct", "hand", "flush_draw", "board_paired", "board_suits", "prev_aggressor", "order",
          "hero_in_bb", "to_call_bb", "from_here_bb", "villain_hand", "villain_better", "facing_size_pct", "beat_frac", "straight_outs",
          "pot_type", "hero_pos", "facing_allin", "hero_allin", "eff_stack_bb", "made_frac", "from_here_pot", "pot_at_decision_bb", "pot_after_call_bb", "spr_after_call", "draw_outs", "nut_outs",
          "board", "board_type", "set_rank",
          "raw_amount_bb", "effective_risk_bb", "uncalled_return_bb", "effective_bet_pct", "draw_calc_status",
          "unmatched_bb", "hand_returned_bb", "hand_returned_to_hero",
          "beat_strict", "tie_frac"]   # 2.81: river – strikt bättre / delar (beat_frac = bättre + ½ lika)


def _cat(hole, board) -> str:
    try:
        return CATEGORY_NAMES[CATEGORY[fast_best(_pairs(hole), _triples(board))]]
    except Exception:
        return ""


def _value(hole, board) -> int:
    try:
        return int(fast_best(_pairs(hole), _triples(board)))
    except Exception:
        return -1


def _villain_showdown(h, hero: str):
    """(bästa visade motståndarhand på hela bordet, 1/0 om den slår din hand) – tomt om ingen visade."""
    if len(h.board) < 5:
        return "", ""
    hole = h.hole.get(hero)
    shown = [c for p, c in (h.shown or {}).items() if p != hero and c and len(c) == len(hole or [])]
    if not shown or not hole:
        return "", ""
    best = max(shown, key=lambda c: _value(c, h.board))
    return _cat(best, h.board), int(_value(best, h.board) > _value(hole, h.board))


def _flush_draw(hole, board) -> str:
    """"nöt" / "ja" / "" – fyra till färg med exakt två hålkort (inte på river)."""
    if len(board) >= 5:
        return ""
    bs = Counter(c[1] for c in board)
    best = ""
    for s, n in bs.items():
        if n != 2:
            continue
        mine = sorted((c[0] for c in hole if c[1] == s), reverse=True)
        if len(mine) >= 2:
            on_board = {c[0] for c in board if c[1] == s}
            top = max(r for r in range(2, 15) if r not in on_board)
            if mine[0] == top:
                return "nöt"
            best = "ja"
    return best


def _has_straight_ref(hole_r, board_r) -> bool:
    """Referensversionen (långsam) – behålls för testerna som jämför mot den snabba."""
    from itertools import combinations
    hr = sorted(set(hole_r))
    for b3 in combinations(board_r, 3):
        if len(set(b3)) < 3:
            continue
        for h2 in combinations(hr, 2):
            s = set(h2) | set(b3)
            if len(s) < 5:
                continue
            lo, hi = min(s), max(s)
            if hi - lo == 4 or s == {14, 2, 3, 4, 5}:
                return True
    return False


# 2.79: stegfönstren som bitmasker (bit r = valör r). Hjulet A-2-3-4-5 har esset som bit 14.
_WINDOWS = tuple(sum(1 << r for r in range(lo, lo + 5)) for lo in range(2, 11)) + ((1 << 14) | 0b111100,)


def _rank_mask(ranks) -> int:
    m = 0
    for r in ranks:
        m |= 1 << r
    return m


def _straight_masks(hm: int, bm: int) -> bool:
    """Exakt samma svar som referensen: ett fönster W ger stege om bordet har minst tre av W:s valörer
    och de valörer i W som handen saknar alla finns på bordet och är högst tre (då fyller handen resten
    med exakt två egna valörer)."""
    for w in _WINDOWS:
        bw = bm & w
        if bw.bit_count() < 3:
            continue
        miss = w & ~hm
        if miss & ~bm == 0 and miss.bit_count() <= 3:
            return True
    return False


def _has_straight(hole_r, board_r) -> bool:
    """Omaha: exakt två hålkort och tre bordskort som bildar en stege (A räknas även som 1)."""
    return _straight_masks(_rank_mask(hole_r), _rank_mask(board_r))


def straight_outs(hole, board) -> int:
    """Antal kort kvar i leken som ger dig en stege (0 om du redan har en, eller på river)."""
    if len(board) >= 5:
        return 0
    hr = [c[0] for c in hole]
    br = [c[0] for c in board]
    hm, bm = _rank_mask(hr), _rank_mask(br)
    if _straight_masks(hm, bm):
        return 0
    seen = Counter(hr + br)
    return sum(4 - seen[r] for r in range(2, 15) if _straight_masks(hm, bm | (1 << r)))


def draw_outs_info(hole, board):
    """Distinct next cards making a straight/flush; nuts means no legal opponent pair beats it now.
    Not showdown equity, not a promise that the hand survives the following street.
    """
    from itertools import combinations
    from .fastev import best_values, best_values_hole, codes
    import numpy as np
    if len(board) not in (3, 4):
        return {"draw_outs": 0, "nut_outs": 0}
    board = list(board)
    used = set(hole) | set(board)
    rest = [(r, s) for r in range(2, 15) for s in "cdhs" if (r, s) not in used]
    rc, bc, hc = np.array(codes(rest)), np.array(codes(board)), np.array(codes(hole))
    boards = np.concatenate([np.broadcast_to(bc, (len(rc), len(bc))), rc[:, None]], axis=1)
    values = best_values_hole(hc, boards)
    hit = np.array([_has_straight([x[0] for x in hole], [x[0] for x in board + [c]])
                    or any(sum(x[1] == ss for x in hole) >= 2 and sum(x[1] == ss for x in board + [c]) >= 3
                           for ss in "cdhs") for c in rest])
    runs = np.flatnonzero(hit)
    if not len(runs):
        return {"draw_outs": 0, "nut_outs": 0}
    pairs = np.array(list(combinations(rc.tolist(), 2)))
    hs, bs, counts = [], [], []
    for i in runs:
        legal = pairs[(pairs != rc[i]).all(axis=1)]
        hs.append(legal)
        bs.append(np.broadcast_to(boards[i], (len(legal), boards.shape[1])))
        counts.append(len(legal))
    opponent_values = best_values(np.concatenate(hs), np.concatenate(bs))
    starts = np.r_[0, np.cumsum(counts)[:-1]]
    strongest = np.maximum.reduceat(opponent_values, starts)
    return {"draw_outs": int(hit.sum()), "nut_outs": int((values[runs] >= strongest).sum())}


def _board_suits(board) -> str:
    m = max(Counter(c[1] for c in board).values())
    return "färg möjlig" if m >= 3 else ("färgdrag möjligt" if m == 2 else "rainbow")



RANKS = "..23456789TJQKA"


def board_str(board) -> str:
    """Bordskorten som text (t.ex. "Ks 8d 3c") – inga namn, bara kort."""
    return " ".join(RANKS[c[0]] + c[1] for c in board)


def board_type(board) -> str:
    """Floppens struktur (de tre första korten): parat, monotont, högt torrt, högt sammanhängande,
    lågt sammanhängande eller mellan/övrigt. Samma indelning som analyserna 2026-11-12."""
    fl = board[:3]
    fr = sorted((c[0] for c in fl), reverse=True)
    if len(set(fr)) < 3:
        return "parat"
    if len({c[1] for c in fl}) == 1:
        return "monotont"
    vals = set(fr) | ({1} if 14 in fr else set())
    conn = any(len([x for x in vals if lo <= x <= lo + 4]) >= 3 for lo in range(1, 11))
    if fr[0] >= 12 and not conn:
        return "högt torrt"
    if fr[0] >= 11 and conn:
        return "högt sammanhängande"
    if fr[0] <= 9 and conn:
        return "lågt sammanhängande"
    return "mellan/övrigt"


def set_rank(hole, board) -> str:
    """"topp"/"mellan"/"botten" när du har set (par på handen + ett kort på ett oparat bord), annars tom."""
    br = [c[0] for c in board]
    if len(set(br)) < len(br):
        return ""
    hr = Counter(c[0] for c in hole)
    sets = [r for r in br if hr.get(r, 0) == 2]
    if not sets:
        return ""
    srt = sorted(set(br), reverse=True)
    i = srt.index(max(sets))
    return "topp" if i == 0 else ("botten" if i == len(srt) - 1 else "mellan")


def actual_return(h, hero: str):
    """Faktisk återbetalning i handen enligt originaltexten ("Uncalled bet (X) returned to NAMN"): (belopp i bb, 1 om den
    gick till Hero annars 0). ("", "") när originaltexten saknas. 2.73: skiljer bokförd återbetalning från det Hero inte
    kan matcha (unmatched_bb), som delvis kan hamna i en sidopott mellan andra spelare."""
    raw = getattr(h, "raw", None)
    if not raw:
        return "", ""
    from .parser import RE_UNCALLED, _num
    tot, to_hero = 0.0, 0
    for line in raw.splitlines():
        m = RE_UNCALLED.match(line.strip())
        if m:
            tot += _num(m.group(1))
            if m.group("name").strip() == hero:
                to_hero = 1
    return round(tot / (h.bb or 1.0), 2), to_hero


def rows_for_hand(h, hero: str, ev_bb: float | None = None, light: bool = False, draws: bool = True) -> list:
    """ev_bb = handens resultat för dig (all-in EV, efter rake). from_here_bb = ev_bb + det du redan lagt i
    potten före beslutet = resultatet räknat från beslutet. Att folda ger 0 härifrån, så för beslut mot en bet
    är from_here_bb exakt skillnaden mot att folda."""
    hole = h.hole.get(hero)
    if not hole or len(h.board) < 3:
        return []
    bb = h.bb or 1.0
    # 2.80: härledda folds (fold-raden saknas i texten) ingår i bordsläget – annars räknas en spelare som foldat
    # som kvar i handen (fel antal spelare, fel position). De är alltid folds med 0 insats.
    acts = [a for a in h.actions if not a.inferred or a.kind == "fold"]
    ret_bb, ret_hero = actual_return(h, hero)
    folded = set()
    put = Counter()
    pre_raiser = None
    for a in acts:
        if a.street != "preflop":
            break
        put[a.player] += a.added
        if a.kind == "fold":
            folded.add(a.player)
        if a.kind == "raise":
            pre_raiser = a.player
    if hero in folded:
        return []
    order = {p: i for i, p in enumerate(POSTFLOP_ORDER)}
    n_raise = sum(1 for a in acts if a.street == "preflop" and a.kind == "raise")
    pot_type = {0: "limp", 1: "enkel höjning", 2: "3-bet"}.get(n_raise, "4-bet+")
    hpos = h.positions.get(hero, "")
    vh, vb = ("", "") if light else _villain_showdown(h, hero)
    out = []
    prev_aggr = "hero" if pre_raiser == hero else ("annan" if pre_raiser else "ingen")
    for st in STREETS:
        if len(h.board) < NB[st]:
            break
        sacts = [a for a in acts if a.street == st]
        board = h.board[:NB[st]]
        active = [p for p in h.seats if p not in folded]
        if hero not in active or len(active) < 2:
            break
        ip = max(active, key=lambda p: order.get(h.positions.get(p, ""), -1)) == hero
        pot = float(sum(put.values()))
        rem = {p: h.stacks.get(p, 0.0) - put[p] for p in active}
        eff = min(rem[hero], max((rem[p] for p in active if p != hero), default=0.0))
        cat = _cat(hole, board)
        # 2.79: de tunga måtten används bara i raderna för dina beslut – räknas inte på en gata där du inte agerar
        decides = any(a.player == hero and not a.kind.startswith("post") for a in sacts)
        so = straight_outs(hole, board) if st != "river" and decides else ""
        bfrac = bstrict = btie = ""
        if st == "river" and not light and decides:
            try:
                from .board import BoardTable
                _bt = BoardTable(board)
                bfrac = round(float(_bt.beat_n(hole)), 4)
                _s, _t = _bt.beat_split(hole)
                bstrict, btie = round(_s, 4), round(_t, 4)
            except Exception:
                bfrac = bstrict = btie = ""
        fd = _flush_draw(hole, board)
        paired = int(len({c[0] for c in board}) < len(board))
        suits = _board_suits(board)
        contrib = Counter()
        aggr = 0
        last_aggr = None
        last_aggr_allin = False
        aggr_size_pct = None   # 2.80: senaste bet/höjningens storlek i % av potten vid aggressorns handling
        k = 0
        made = ""
        if st != "river" and not light and decides:
            try:
                from .board import BoardTable
                from .db import cached
                made = round(float(cached(f"mf6|{h.id}|{hero}|{st}", lambda: BoardTable(board).strength_u(hole))), 4)
            except Exception:
                made = ""
        draw_info = {"draw_outs": "", "nut_outs": ""}
        if draws and not light and decides and st != "river" and cat in ("högt kort", "par") and (fd or so):
            from .db import cached
            draw_info = cached(f"draw270|{h.id}|{hero}|{st}", lambda: draw_outs_info(hole, board))
        for a in sacts:
            active = [p for p in h.seats if p not in folded]
            can_act = [p for p in active if h.stacks.get(p, 0.0) - put[p] > 1e-9]
            ip = bool(can_act) and max(can_act, key=lambda p: order.get(h.positions.get(p, ""), -1)) == hero
            cur_pot = pot + sum(contrib.values())
            if a.player == hero and not a.kind.startswith("post"):
                k += 1
                raw_call = max(contrib.values(), default=0.0) - contrib[hero]
                facing = "ingen" if raw_call <= 1e-9 else ("bet" if aggr <= 1 else "raise")
                hero_left = h.stacks.get(hero, 0.0) - put[hero]
                opp_left = max((h.stacks.get(p, 0.0) - put[p] for p in h.seats if p not in folded and p != hero), default=0.0)
                # 2.71: synen begränsas till Heros kvarvarande stack; det motståndare satsat utöver det kan Hero inte vinna
                # (återbetalas eller blir sidopott mellan andra). cur_pot räknas om till den pott Hero kan vinna.
                to_call = min(max(raw_call, 0.0), max(hero_left, 0.0))
                cap = contrib[hero] + to_call
                cur_pot = pot + sum(min(c, cap) if p != hero else c for p, c in contrib.items())
                if a.kind in ("bet", "raise"):
                    raw_amt = a.added
                    match = max((contrib[p] + h.stacks.get(p, 0.0) - put[p] for p in h.seats if p not in folded and p != hero),
                                default=0.0)
                    eff_tot = min(contrib[hero] + a.added, match)
                    eff_risk = max(eff_tot - contrib[hero], 0.0)
                    ret = max(a.added - eff_risk, 0.0)
                    eff_pct = round(100.0 * max(eff_risk - to_call, 0.0) / (cur_pot + to_call), 1) if cur_pot + to_call > 0 else ""
                elif a.kind == "call":
                    raw_amt, eff_risk, ret, eff_pct = raw_call, to_call, max(raw_call - to_call, 0.0), ""
                else:
                    raw_amt, eff_risk, ret, eff_pct = 0.0, 0.0, 0.0, ""
                if st == "river":
                    dstat = "river"
                elif light:
                    dstat = "light_export"
                elif cat not in ("högt kort", "par"):
                    dstat = "made_hand_not_evaluated"
                elif not (fd or so):
                    dstat = "no_qualifying_draw"
                elif draw_info.get("draw_outs") in ("", None):
                    dstat = "not_computed"
                else:
                    dstat = "zero_outs" if int(draw_info["draw_outs"]) == 0 else "computed"
                eff_now = min(hero_left, opp_left)
                fh = round(ev_bb + put[hero] / bb, 2) if ev_bb is not None else ""
                size = ""
                if a.kind in ("bet", "raise") and cur_pot > 0:
                    size = round(100.0 * (a.added - max(to_call, 0.0)) / (cur_pot + max(to_call, 0.0)), 1)
                out.append([h.id, st, len(active), int(ip), int(pre_raiser == hero), round(pot / bb, 2),
                            round(eff / pot, 2) if pot > 0 else "", facing,
                            round(100.0 * to_call / cur_pot, 1) if to_call > 1e-9 and cur_pot > 0 else "",
                            a.kind, size, cat, fd, paired, suits, prev_aggr, k, round(put[hero] / bb, 2),
                            round(max(to_call, 0.0) / bb, 2),
                            round(ev_bb + put[hero] / bb, 2) if ev_bb is not None else "", vh, vb,
                            # storleken på det du mötte i procent av potten när betten/höjningen gjordes (2.80: en syn
                            # efter betten ändrar inte storleken). Effektivt: begränsas av vad du kan syna.
                            (round(min(aggr_size_pct[0], max(to_call - aggr_size_pct[2], 0.0)) / aggr_size_pct[1] * 100.0, 1)
                             if to_call > 1e-9 and aggr_size_pct and aggr_size_pct[1] > 0 else
                             (round(100.0 * to_call / (cur_pot - to_call), 1) if to_call > 1e-9 and cur_pot - to_call > 0 else "")),
                            bfrac, so, pot_type, hpos,
                            int(bool(last_aggr_allin)) if to_call > 1e-9 else "", int(bool(getattr(a, "allin", False))),
                            round(eff_now / bb, 1), made if st != "river" else bfrac,
                            round(fh / (cur_pot / bb), 3) if fh != "" and cur_pot > 0 else "",
                            round(cur_pot / bb, 4), round((cur_pot + max(to_call, 0)) / bb, 4),
                            max(min(hero_left - max(to_call, 0), opp_left), 0) / (cur_pot + max(to_call, 0)) if cur_pot + max(to_call, 0) > 0 else "",
                            draw_info["draw_outs"], draw_info["nut_outs"],
                            board_str(board), board_type(board), set_rank(hole, board),
                            round(raw_amt / bb, 2), round(eff_risk / bb, 2), round(ret / bb, 2), eff_pct, dstat,
                            round(ret / bb, 2), ret_bb, ret_hero, bstrict, btie])
            if a.kind in ("bet", "raise") and a.player != hero:
                agg_call = max(max(contrib.values(), default=0.0) - contrib[a.player], 0.0)
                # (storlek utöver synen, pott efter aggressorns syn, vad Hero redan behövde syna före höjningen)
                aggr_size_pct = (max(a.added - agg_call, 0.0), pot + sum(contrib.values()) + agg_call,
                                 max(max(contrib.values(), default=0.0) - contrib[hero], 0.0))
            elif a.kind in ("bet", "raise"):
                aggr_size_pct = None
            contrib[a.player] += a.added
            put[a.player] += a.added
            if a.kind == "fold":
                folded.add(a.player)
            if a.kind in ("bet", "raise"):
                aggr += 1
                last_aggr = a.player
                last_aggr_allin = bool(getattr(a, "allin", False)) or h.stacks.get(a.player, 0.0) - put[a.player] <= 1e-9
        prev_aggr = "hero" if last_aggr == hero else ("annan" if last_aggr else "ingen")
        if hero in folded:
            break
    return out


def iter_rows(db, ids, hero: str, progress=None, ev_of: dict | None = None):
    """Alla postflop-rader för händerna (läses ur databasen i omgångar, så minnet räcker)."""
    import pickle
    import zlib
    ids = list(ids)
    for a in range(0, len(ids), 2000):
        chunk = ids[a:a + 2000]
        q = "SELECT blob, raw FROM hands WHERE id IN (%s)" % ",".join("?" * len(chunk))
        for b, raw in db.con.execute(q, chunk):
            try:
                from .db import hand_from_row   # 2.80: samma handladdning som överallt (originaltext + positioner)
                h = hand_from_row((b, raw))
            except Exception:
                continue
            yield from rows_for_hand(h, hero, (ev_of or {}).get(h.id))
        if progress:
            progress(min(a + 2000, len(ids)), len(ids))


CTX_HEADER = ["hand_id", "opener_pos", "opener_id", "open_size_bb", "limpers", "callers_before_hero", "threebettor_pos",
              "players_to_flop", "pot_type", "hero_opened"]
OPP_HEADER = ["hand_id", "opp_id", "pos", "vpip", "pfr", "to_flop", "showed"]


def _hasher(salt: str):
    import hashlib
    return lambda name: hashlib.sha1((salt + "|" + name).encode("utf-8")).hexdigest()[:10]


def context_rows(h, hero: str, hid_of) -> tuple:
    """Preflop-läget i handen (vem öppnade, hur stort, hur många syner före dig) och en rad per motståndare
    (VPIP, PFR, till flop, visade kort). Motståndarna har bara ett anonymt id (samma id i alla exporter)."""
    bb = h.bb or 1.0
    pre = [a for a in h.actions if a.street == "preflop" and not a.inferred and not a.kind.startswith("post")]
    raisers = [a for a in pre if a.kind == "raise"]
    opener = raisers[0] if raisers else None
    limpers = sum(1 for a in pre if a.kind == "call" and (opener is None or pre.index(a) < pre.index(opener)))
    hero_first = next((i for i, a in enumerate(pre) if a.player == hero), None)
    callers = 0
    if opener is not None and hero_first is not None:
        oi = pre.index(opener)
        callers = sum(1 for a in pre[oi + 1:hero_first] if a.kind == "call")
    folded = {a.player for a in pre if a.kind == "fold"}
    n_raise = len(raisers)
    ctx = [h.id, h.positions.get(opener.player, "") if opener else "", hid_of(opener.player) if opener and opener.player != hero else ("hero" if opener else ""),
           round(opener.to / bb, 2) if opener and opener.to else "", limpers, callers,
           h.positions.get(raisers[1].player, "") if n_raise > 1 else "",
           len([p for p in h.seats if p not in folded]) if len(h.board) >= 3 else 1,
           {0: "limp", 1: "enkel höjning", 2: "3-bet"}.get(n_raise, "4-bet+"), int(bool(opener and opener.player == hero))]
    opps = []
    for p in h.seats:
        if p == hero:
            continue
        mine = [a for a in pre if a.player == p]
        opps.append([h.id, hid_of(p), h.positions.get(p, ""), int(any(a.kind in ("call", "raise") for a in mine)),
                     int(any(a.kind == "raise" for a in mine)), int(p not in folded and len(h.board) >= 3),
                     int(bool((h.shown or {}).get(p)))])
    return ctx, opps


def iter_all(db, ids, hero: str, progress=None, ev_of: dict | None = None, salt: str = ""):
    """En genomgång av händerna: ("post", rad), ("ctx", rad) och ("opp", rad)."""
    import pickle
    import zlib
    hid_of = _hasher(salt)
    ids = list(ids)
    for a in range(0, len(ids), 2000):
        chunk = ids[a:a + 2000]
        q = "SELECT blob, raw FROM hands WHERE id IN (%s)" % ",".join("?" * len(chunk))
        for b, raw in db.con.execute(q, chunk):
            try:
                from .db import hand_from_row   # 2.80: samma handladdning som överallt (originaltext + positioner)
                h = hand_from_row((b, raw))
            except Exception:
                continue
            for r in rows_for_hand(h, hero, (ev_of or {}).get(h.id)):
                yield "post", r
            try:
                c, o = context_rows(h, hero, hid_of)
            except Exception:
                continue
            yield "ctx", c
            for r in o:
                yield "opp", r
        if progress:
            progress(min(a + 2000, len(ids)), len(ids))
