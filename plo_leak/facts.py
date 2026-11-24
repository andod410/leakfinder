"""Faktaskiktet: allt analysen behöver om en hand räknas EN gång och sparas i kolumnform.

Varför
------
Tidigare hämtades alla kompletta händer och gicks igenom i Python vid varje analys. Det
skalar inte till miljontals händer. Nu körs den tunga genomgången av en hand (samma kod
som förut: `stats._analyze_hand`) exakt en gång – när handen läses in – och resultatet
sparas som kompakta kolumner:

* hands  – en rad per hand: tid, variant, nivå, position, resultat, rake, all-in EV, startkort …
* stat   – frekvenser (VPIP, 3-bet, c-bet …): en rad per hand och statistik
* grp    – beslut jämfört med fold (bevismotorn): en rad per beslut
* fold   – antal fold per beslutsgrupp
* pre    – preflop-beslut med resultat jämfört med fold
* riv    – river mot en bet; trn – syner mot turn-bet
* diag, samp, sd – datakvalitet, exempelhänder och showdown-förluster (glesa)

En analys väljer ut rader (ett urval) och summerar kolumnerna med numpy – det tar sekunder
även för miljontals händer, och kräver aldrig att hela händer läses in.

Strängar (positioner, nyckelnamn …) lagras som heltalskoder med en ordlista per tabell.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from datetime import datetime
from pathlib import Path

import numpy as np

FACTS_VERSION = 25  # 25 = 2.87 rättad all-in EV (låst pott + senare fold, river-fold, döda blinds, preflop exakt) · 24 = 2.86 tolv nya solverlägen · 23 = 2.85 åtta nya solverlägen · 22 = 2.84 fem nya solverlägen · 21 = 2.83 straddle per hand (strad) · 20 = 2.82 fem nya solverlägen i spx · 19 = 2.81 showdownrisk på hela händer · 18 = 2.80 väntad rake i all-in EV (evr) · 17 = 2.79 deterministisk satsordning · 16 = 2.78 extra solverlägen (spx) · 15 = 2.76 solverlägen (spn) · 13 = 2.72 betstorlekstabell (bsz) · höj när innehållet i en faktatabell ändras – då byggs fakta om automatiskt
NUT_MIN_POT_BB = 20.0
EPOCH = datetime(1970, 1, 1)
SUIT_IDX = {"c": 0, "d": 1, "h": 2, "s": 3}
SUIT_CH = "cdhs"
STREET_CODE = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
NFEAT = 12
SESSION_GAP = 30 * 60  # paus (sekunder) som avslutar ett spelpass

# kolumner per tabell: namn -> dtype (hidx = radnummer i hands-tabellen)
SCHEMA = {
    "hands": {"ts": "i8", "nh": "i1", "sb": "f8", "bb": "f8", "ttype": "i1", "nplay": "i1", "pos": "i2",
              "stake": "i2", "game": "i2", "hs": "i2", "net": "f8", "money": "f8", "rake": "f8", "rake_m": "f8", "pot_fee": "f8",
              "evr": "f8", "evr_m": "f8", "ev": "f8", "ev_m": "f8", "ai_st": "i1", "ai_eq": "f8", "clu": "i8", "bucket": "i2", "nut": "i2",
              "combo": "i2", "vpip": "?", "agg": "i2", "pas": "i2", "t_pre": "?", "t_vpip": "?", "corrupt": "?",
              "cat": "i1", "fold_st": "i1", "won": "?", "sd": "?", "pot": "f8", "rdlow": "i1", "hp": "?", "sa": "?",
              "rd": "?", "la": "i1", "ic": "f8", "ia": "f8", "strad": "?"},
    "stat": {"hidx": "i4", "key": "i2", "opps": "i1", "hits": "i1"},
    "grp": {"hidx": "i4", "key": "i2", "delta": "f8"},
    "fold": {"hidx": "i4", "key": "i2", "cnt": "i2"},
    "pre": {"hidx": "i4", "spot": "i2", "pos": "i2", "kind": "i2", "delta": "f8"},
    "riv": {"hidx": "i4", "size": "i2", "str": "i2", "kind": "i2", "delta": "f8", "bf": "f8", "cat": "i1"},
    "trn": {"hidx": "i4", "str": "i2", "delta": "f8", "path": "i2"},
    # river heads-up med dig: role 0 = du leder ut, 1 = du bettar i position efter check, 2 = check-igenom
    # med position; frac = betten i andel av potten; resp 0/1/2 = fold/syn/höjning (−1 = ingen bet);
    # bf = andel av motståndarens kombinationer som slår din hand (−1 = okänd)
    # dina postflop-beslut: gata 1–3, ip, spelare, pfa, mötte 0/1/2 (ingen/bet/höjning), handling (kind-kod),
    # ordning på gatan, vem som var aggressor på förra gatan (0 ingen, 1 du, 2 annan), handgrupp (0 svag utan drag,
    # 1 drag, 2 två par eller bättre), pott i bb, resultat räknat från beslutet, din bet/höjning i % av potten (nan = ingen)
    # och på river andelen slumpade händer som slår dig (−1 = okänd/inte river)
    "pfd": {"hidx": "i4", "st": "i1", "ip": "?", "np": "i1", "pfa": "?", "facing": "i1", "kind": "i2", "ord": "i1",
            "prev": "i1", "grp": "i1", "pot": "f8", "fh": "f8", "size": "f8", "bf": "f8", "esz": "f8"},
    "rvb": {"hidx": "i4", "role": "i1", "frac": "f8", "resp": "i1", "bf": "f8"},
    # 2.72: första bet per gata av vem som helst (betsize.bet_events): who 0 = poolen utan dig, 1 = du, 2 = poolen mot dig;
    # frac = effektiv bet / pott, out 0/1/2 = fold/syn/höjning, pot i bb
    "bsz": {"hidx": "i4", "st": "i1", "who": "i1", "frac": "f8", "np": "i1", "ip": "?", "out": "i1", "pot": "f8"},
    # 2.76: första preflopbeslutet i ett av de 14 solverlägena: node = index i solvergroups.NODES, act 0/1/2 = fold/syn/höj,
    # delta = handens resultat mot fold (bb, nan för fold)
    "spn": {"hidx": "i4", "node": "i1", "act": "i1", "delta": "f8"},
    # 2.78: heros beslut i de extra solverlägena (mot 3-bet, kallsyn, överkall, limp, 4-bet); inv = investerat före beslutet (bb)
    "spx": {"hidx": "i4", "node": "i1", "act": "i1", "inv": "f8"},
    "diag": {"hidx": "i4", "key": "i2", "cnt": "i4"},
    "samp": {"hidx": "i4", "key": "i2"},
    "sd": {"hidx": "i4", "rev": "?"},
    # river heads-up (alla händer, även där du foldat tidigare) för river-modellen; obj = situationen (pickle)
    "rsp": {"hidx": "i4"},
}
# vilken ordlista varje kodkolumn använder
VOCAB_OF = {("hands", "pos"): "pos", ("hands", "stake"): "stake", ("hands", "game"): "game", ("hands", "hs"): "hs",
            ("hands", "bucket"): "bucket", ("hands", "nut"): "nut", ("hands", "combo"): "combo",
            ("stat", "key"): "stat", ("grp", "key"): "gkey", ("fold", "key"): "fkey", ("pre", "spot"): "spot",
            ("pre", "pos"): "pos", ("pre", "kind"): "kind", ("riv", "size"): "size", ("riv", "str"): "rstr",
            ("riv", "kind"): "kind", ("pfd", "kind"): "kind", ("trn", "str"): "tstr", ("trn", "path"): "path", ("diag", "key"): "diag",
            ("samp", "key"): "samp"}
SEP = "\x1f"


def card_code(c) -> int:
    return (c[0] - 2) * 4 + SUIT_IDX[c[1]]


def decode_cards(row) -> list:
    return [(int(x) // 4 + 2, SUIT_CH[int(x) % 4]) for x in row if x >= 0]


def ts_of(d: datetime) -> int:
    return int((d - EPOCH).total_seconds())


def dt_of(ts: int) -> datetime:
    from datetime import timedelta
    return EPOCH + timedelta(seconds=int(ts))


# ---------------------------------------------------------------- bygga fakta för händer
class Builder:
    """Samlar fakta för en mängd händer och gör kolumner av dem."""

    def __init__(self):
        self.cols = {t: {c: [] for c in cols} for t, cols in SCHEMA.items()}
        self.ids: list[str] = []
        self.hole: list = []
        self.feats: list = []
        self.sdobj: list = []
        self.rspobj: list = []
        self.vocab: dict[str, dict] = {}
        # alla kolumnlistor platt (för att snabbt kunna återställa efter en trasig hand)
        self._lists = [v for cols in self.cols.values() for v in cols.values()] + \
            [self.ids, self.hole, self.feats, self.sdobj, self.rspobj]

    def code(self, vocab: str, s) -> int:
        d = self.vocab.setdefault(vocab, {})
        c = d.get(s)
        if c is None:
            c = d[s] = len(d)
        return c

    def add(self, h, hero: str) -> bool:
        """Lägg till en hand. En hand som inte går att räkna på (trasig historik) hoppas över
        utan att stoppa resten – kolumnerna återställs så att inget halvfärdigt ligger kvar."""
        lists = self._lists
        marks = [len(v) for v in lists]
        try:
            return self._add(h, hero)
        except Exception:
            for v, n in zip(lists, marks):
                del v[n:]
            self.skipped = getattr(self, "skipped", 0) + 1
            return False

    def _add(self, h, hero: str) -> bool:
        from .cards import classify_start, nut_qualities
        from .decisions import cluster_of
        from .ranges import hand_features
        from .rundowns import rundown_low
        from .stats import HeroStats, _analyze_hand, table_type
        if hero not in h.seats:
            return False
        from .parser import fix_dead_sb_positions
        fix_dead_sb_positions(h)
        st = HeroStats(hero=hero)
        _analyze_hand(st, h, hero, NUT_MIN_POT_BB)
        i = len(self.ids)
        self.ids.append(h.id)
        H = self.cols["hands"]
        pos = h.positions.get(hero, "?")
        hole = h.hole.get(hero) or []
        H["ts"].append(ts_of(h.date))
        H["nh"].append(h.num_hole)
        H["sb"].append(h.sb)
        H["bb"].append(h.bb)
        H["ttype"].append(1 if table_type(h) == "Rush & Cash" else 0)
        H["nplay"].append(len(h.seats))
        H["pos"].append(self.code("pos", pos))
        H["stake"].append(self.code("stake", f"{h.sb:g}/{h.bb:g}"))
        H["game"].append(self.code("game", f"PLO-{h.num_hole}"))
        hs_key = f"{h.header_stakes[0]:g}/{h.header_stakes[1]:g}" if h.header_stakes else "?"
        H["hs"].append(self.code("hs", hs_key))
        H["net"].append(st.net_bb)
        H["money"].append(st.net_money)
        H["rake"].append(st.rake_paid_bb)
        H["rake_m"].append(st.rake_paid_money)
        H["pot_fee"].append(h.rake / h.bb if h.bb else 0.0)
        H["ev"].append(st.ev_net_bb)
        H["ev_m"].append(st.ev_net_money)
        H["evr"].append(st.ev_rake_bb)
        H["evr_m"].append(st.ev_rake_money)
        if st.allin:
            street, a = next(iter(st.allin.items()))
            H["ai_st"].append(STREET_CODE[street])
            H["ai_eq"].append(a["eq_sum"])
        else:
            H["ai_st"].append(-1)
            H["ai_eq"].append(0.0)
        H["clu"].append(cluster_of(h))
        cls = classify_start(hole) if hole and len(hole) >= 4 else None
        H["bucket"].append(self.code("bucket", cls["bucket"]) if cls else -1)
        H["nut"].append(self.code("nut", cls["nut"]) if cls else -1)
        H["combo"].append(self.code("combo", cls["nut_combo"]) if cls else -1)
        H["vpip"].append(bool(st.by_pos[pos].vpip))
        H["agg"].append(st.agg_actions)
        H["pas"].append(st.pass_actions)
        # vägen in i potten: vem som satsade sist (1 = du, 2 = en motståndare, 0 = ingen satsning)
        # och hur mycket du själv satte in genom att syna respektive genom att betta/höja (bb).
        # En höjning delas i sin syn-del (upp till den insats du mötte) och sin höjnings-del.
        # Satsningar efter att du gått all-in räknas inte (du kunde inte svara på dem), och ett
        # bet eller en höjning som kom tillbaka osynad dras av.
        last, ic, ia = 0, 0.0, 0.0
        contrib, cur_st, hero_allin, paid = {}, None, False, 0.0
        for a in h.actions:
            if a.street != cur_st:
                contrib, cur_st = {}, a.street
            mine = contrib.get(a.player, 0.0)
            level = max(contrib.values(), default=0.0)
            if a.player == hero:
                paid += a.added
            if a.kind.startswith("post"):
                if a.kind != "post_dead":
                    contrib[a.player] = mine + a.added
                continue
            if a.kind in ("bet", "raise"):
                if not hero_allin:
                    last = 1 if a.player == hero else 2
                if a.player == hero:
                    callpart = max(0.0, min(a.added, level - mine))
                    ic += callpart
                    ia += a.added - callpart
            elif a.kind == "call" and a.player == hero:
                ic += a.added
            contrib[a.player] = mine + a.added
            if a.player == hero and a.allin:
                hero_allin = True
        back = paid - h.invested.get(hero, paid)
        if back > 1e-9:
            take = min(ia, back)
            ia -= take
            ic = max(0.0, ic - (back - take))
        bbv = h.bb or 1.0
        H["la"].append(last)
        H["ic"].append(ic / bbv)
        H["ia"].append(ia / bbv)
        H["strad"].append(any(a.kind == "post_straddle" for a in h.actions))  # 2.83
        pre = [a for a in h.actions if a.street == "preflop" and a.player == hero and not a.kind.startswith("post")]
        H["t_pre"].append(bool(pre))
        H["t_vpip"].append(any(a.kind in ("call", "raise") for a in pre))
        H["corrupt"].append(bool(h.corrupt))
        folded = h.folded_on(hero)
        H["fold_st"].append(STREET_CODE[folded] if folded in STREET_CODE else -1)
        H["won"].append(h.collected.get(hero, 0) > 0)
        H["sd"].append(folded is None and h.went_to_showdown() and len(h.board) >= 5)
        H["pot"].append(h.pot_size() / h.bb if h.bb else 0.0)
        cat = -1
        if hole and folded is None and len(h.board) >= 5:
            from .db import cached
            from .rundowns import _final_category
            c_ = cached(f"cat|{h.id}|{hero}", lambda: _final_category(h, hero))
            cat = -1 if c_ is None else int(c_)
        H["cat"].append(cat)
        if hole:
            q = nut_qualities(hole)
            low = rundown_low(hole)
            f = hand_features(hole)
            f[8] = round(f[8] * 5)  # sammanhängning lagras som heltal (0–5), delas med 5 vid användning
            self.feats.append(f.astype(np.int8))
        else:
            q, low = (False, False, False), None
            self.feats.append(np.zeros(NFEAT, np.int8))
        H["hp"].append(bool(q[0]))
        H["sa"].append(bool(q[1]))
        H["rd"].append(bool(q[2]))
        H["rdlow"].append(-1 if low is None else low)
        self.hole.append([card_code(c) for c in hole] + [-1] * (6 - len(hole)))

        S = self.cols["stat"]
        for prefix, d in (("", st.s), ("rfi|", st.rfi_by_pos), ("ep|", st.by_bucket_ep)):
            for k, s_ in d.items():
                if s_.opps:
                    S["hidx"].append(i)
                    S["key"].append(self.code("stat", prefix + k))
                    S["opps"].append(s_.opps)
                    S["hits"].append(s_.hits)
        dec = st.decisions
        G = self.cols["grp"]
        for key, g in dec.groups.items():
            kc = self.code("gkey", SEP.join(key))
            for v in g.vals:
                G["hidx"].append(i)
                G["key"].append(kc)
                G["delta"].append(v)
        F = self.cols["fold"]
        for key, n in dec.folds.items():
            F["hidx"].append(i)
            F["key"].append(self.code("fkey", SEP.join(key)))
            F["cnt"].append(n)
        P = self.cols["pre"]
        for spot, p, kind, delta, _hid, _clu, _hole in dec.pre:
            P["hidx"].append(i)
            P["spot"].append(self.code("spot", spot))
            P["pos"].append(self.code("pos", p))
            P["kind"].append(self.code("kind", kind))
            P["delta"].append(np.nan if delta is None else delta)
        from .solvergroups import node_of, ACT
        sn = node_of(h, hero) if hole and dec.pre else None
        if sn is not None and ACT.get(dec.pre[0][2]) == sn[1]:
            S_ = self.cols["spn"]
            S_["hidx"].append(i)
            S_["node"].append(sn[0])
            S_["act"].append(sn[1])
            S_["delta"].append(np.nan if dec.pre[0][3] is None else dec.pre[0][3])
        if hole:
            from .solvergroups import extra_decisions
            X_ = self.cols["spx"]
            for nd_, ac_, inv_, _o in extra_decisions(h, hero):
                X_["hidx"].append(i)
                X_["node"].append(nd_)
                X_["act"].append(ac_)
                X_["inv"].append(inv_)
        R = self.cols["riv"]
        bf_, cat_ = -1.0, -1
        if dec.river and hole and len(h.board) == 5:
            try:
                from .ev import CATEGORY, _pairs, _triples, fast_best
                cat_ = int(CATEGORY[fast_best(_pairs(hole), _triples(h.board))])
            except Exception:
                cat_ = -1
            try:
                from .board import BoardTable
                from .db import cached
                bf_ = float(cached(f"bf6|{h.id}|{hero}", lambda: BoardTable.get(h.board).beat_n(hole)))
            except Exception:
                bf_ = -1.0
        for size, rb, kind, delta, _clu, _hid in dec.river:
            R["bf"].append(bf_)
            R["cat"].append(cat_)
            R["hidx"].append(i)
            R["size"].append(self.code("size", size))
            R["str"].append(self.code("rstr", rb))
            R["kind"].append(self.code("kind", kind))
            R["delta"].append(np.nan if delta is None else delta)
        PF = self.cols["pfd"]
        if hole and len(h.board) >= 3:
            from .postflop_rows import HEADER as _PH, rows_for_hand as _rfh
            ix = {k: i for i, k in enumerate(_PH)}
            for x in _rfh(h, hero, st.ev_net_bb, light=True):
                hand = x[ix["hand"]]
                so = x[ix["straight_outs"]]
                draw = bool(x[ix["flush_draw"]]) or (so != "" and so >= 6)
                grp = 2 if hand not in ("högt kort", "par") else (1 if draw else 0)
                PF["hidx"].append(i)
                PF["st"].append({"flop": 1, "turn": 2, "river": 3}[x[ix["street"]]])
                PF["ip"].append(bool(x[ix["ip"]]))
                PF["np"].append(int(x[ix["players"]]))
                PF["pfa"].append(bool(x[ix["pfa"]]))
                PF["facing"].append({"ingen": 0, "bet": 1, "raise": 2}[x[ix["facing"]]])
                PF["kind"].append(self.code("kind", x[ix["action"]]))
                PF["ord"].append(int(x[ix["order"]]))
                PF["prev"].append({"ingen": 0, "hero": 1, "annan": 2}.get(x[ix["prev_aggressor"]], 0))
                PF["grp"].append(grp)
                PF["pot"].append(float(x[ix["pot_bb"]]))
                fh = x[ix["from_here_bb"]]
                PF["fh"].append(float(fh) if fh != "" else np.nan)
                sz = x[ix["size_pct"]]
                PF["size"].append(float(sz) if sz != "" else np.nan)
                ez = x[ix["effective_bet_pct"]]  # 2.73: storlek räknad på det motståndaren kan syna
                PF["esz"].append(float(ez) if ez != "" else np.nan)
                if x[ix["street"]] == "river":
                    if bf_ < 0 and len(h.board) == 5:
                        try:
                            from .board import BoardTable
                            from .db import cached
                            bf_ = float(cached(f"bf6|{h.id}|{hero}", lambda: BoardTable.get(h.board).beat_n(hole)))
                        except Exception:
                            bf_ = -1.0
                    PF["bf"].append(bf_)
                else:
                    PF["bf"].append(-1.0)
        V = self.cols["rvb"]
        try:
            from .river import extract as _rx
            sp = _rx(h, hero) if hole and len(h.board) >= 5 else None
        except Exception:
            sp = None
        if sp:
            keep = {k: v for k, v in sp.items() if k != "f"}
            self.cols["rsp"]["hidx"].append(i)
            self.rspobj.append(pickle.dumps(keep, protocol=pickle.HIGHEST_PROTOCOL))
        if sp and sp.get("hero_role"):
            role = None
            if sp["kind"] == "bet" and sp.get("bettor") == hero:
                role = 0 if sp["role"] == "lead" else 1
            elif sp["kind"] == "checkthrough" and sp["hero_role"] == "ip":
                role = 2
            if role is not None:
                V["hidx"].append(i)
                V["role"].append(role)
                V["frac"].append(float(sp.get("frac", np.nan)))
                V["resp"].append({"fold": 0, "call": 1, "raise": 2}.get(sp.get("response"), -1))
                V["bf"].append(float(sp["f"].get(hero, -1.0)))
        BZ = self.cols["bsz"]
        try:
            from .betsize import bet_events
            evs = bet_events(h, hero) if len(h.board) >= 3 else []
        except Exception:
            evs = []
        for st_, who, frac, np_, ip_, out_, pot_ in evs:
            BZ["hidx"].append(i)
            BZ["st"].append(st_)
            BZ["who"].append(who)
            BZ["frac"].append(frac)
            BZ["np"].append(np_)
            BZ["ip"].append(bool(ip_))
            BZ["out"].append(out_)
            BZ["pot"].append(pot_)
        T = self.cols["trn"]
        for strength, delta, _clu, path in dec.turn_calls:
            T["hidx"].append(i)
            T["str"].append(self.code("tstr", strength))
            T["delta"].append(delta)
            T["path"].append(self.code("path", path))
        D = self.cols["diag"]
        for k, n in st.diag.items():
            D["hidx"].append(i)
            D["key"].append(self.code("diag", k))
            D["cnt"].append(n)
        SP = self.cols["samp"]
        for k, ids in st.samples.items():
            for _ in ids:
                SP["hidx"].append(i)
                SP["key"].append(self.code("samp", k))
        X = self.cols["sd"]
        for e in st.big_losses:
            X["hidx"].append(i)
            X["rev"].append(any(e is r for r in st.reverse_dominated))
            self.sdobj.append(pickle.dumps(e, protocol=pickle.HIGHEST_PROTOCOL))
        return True

    def finish(self) -> "FactTable":
        t = {}
        for name, cols in SCHEMA.items():
            t[name] = {c: np.asarray(self.cols[name][c], dtype=dt) for c, dt in cols.items()}
        t["hands"]["id"] = np.asarray(self.ids, dtype=object)
        t["hands"]["hole"] = np.asarray(self.hole, dtype=np.int8).reshape(-1, 6)
        t["hands"]["feats"] = np.asarray(self.feats, dtype=np.int8).reshape(-1, NFEAT)
        t["sd"]["obj"] = np.asarray(self.sdobj, dtype=object)
        t["rsp"]["obj"] = np.asarray(self.rspobj, dtype=object)
        vocab = {k: list(d) for k, d in self.vocab.items()}
        return FactTable(t, vocab)


def extract(hands, hero: str, progress=None) -> "FactTable":
    b = Builder()
    for k, h in enumerate(hands, 1):
        b.add(h, hero)
        if progress and k % 2000 == 0:
            progress(k)
    return b.finish()


# ---------------------------------------------------------------- faktatabell
class FactTable:
    """Kolumner för en mängd händer (en hero). Raderna i hands är sorterade efter (tid, handnummer)."""

    def __init__(self, t: dict, vocab: dict, sorted_: bool = False):
        self.t = t
        self.vocab = {k: list(v) for k, v in vocab.items()}
        self._vidx = None
        if not sorted_:
            self._sort()
        self._sessionize()

    # --- grundläggande
    @property
    def n(self) -> int:
        return len(self.t["hands"]["ts"])

    @property
    def H(self) -> dict:
        return self.t["hands"]

    def codes(self, vocab: str) -> dict:
        if self._vidx is None:
            self._vidx = {}
        d = self._vidx.get(vocab)
        if d is None:
            d = self._vidx[vocab] = {s: i for i, s in enumerate(self.vocab.get(vocab, []))}
        return d

    def code(self, vocab: str, s) -> int:
        return self.codes(vocab).get(s, -999)

    def label(self, vocab: str, c: int):
        return self.vocab[vocab][c]

    def _sessionize(self, gap: int = SESSION_GAP) -> None:
        """Kluster = spelpass: alla dina händer (alla bord) i tidsordning, nytt pass efter en paus
        på mer än `gap` sekunder. Händer från samma pass delar motståndare, form och bordsbild och
        hålls därför ihop – hela passet hamnar i samma halva (upptäck/bekräfta) och bootstrap drar
        hela pass."""
        import zlib
        H = self.t["hands"]
        ts = H["ts"]
        if not len(ts):
            return
        new = np.empty(len(ts), dtype=bool)
        new[0] = True
        new[1:] = np.diff(ts) > gap
        sid = np.cumsum(new) - 1
        starts = ts[new]
        codes = np.array([zlib.crc32(f"pass|{int(t)}".encode()) for t in starts], dtype=np.int64)
        H["clu"] = codes[sid]

    def _sort(self) -> None:
        H = self.t["hands"]
        if not len(H["ts"]):
            return
        ids = H["id"].astype(str)
        order = np.lexsort((ids, H["ts"]))
        if np.array_equal(order, np.arange(len(order))):
            return
        inv = np.empty_like(order)
        inv[order] = np.arange(len(order))
        for c in list(H):
            H[c] = H[c][order]
        for name, cols in self.t.items():
            if name == "hands" or not len(cols["hidx"]):
                continue
            new_h = inv[cols["hidx"]]
            o2 = np.argsort(new_h, kind="stable")  # behåll ordningen inom en hand
            for c in list(cols):
                cols[c] = cols[c][o2]
            cols["hidx"] = new_h[o2].astype(np.int32)

    @staticmethod
    def concat(parts: list["FactTable"]) -> "FactTable":
        parts = [p for p in parts if p is not None and p.n]
        if not parts:
            return FactTable(Builder().finish().t, {}, sorted_=True)
        if len(parts) == 1:
            return parts[0]
        vocab: dict[str, list] = {}
        vidx: dict[str, dict] = {}
        remaps = []
        for p in parts:
            rm = {}
            for v, lst in p.vocab.items():
                g = vocab.setdefault(v, [])
                gi = vidx.setdefault(v, {})
                m = np.empty(len(lst), dtype=np.int32)
                for j, s in enumerate(lst):
                    c = gi.get(s)
                    if c is None:
                        c = gi[s] = len(g)
                        g.append(s)
                    m[j] = c
                rm[v] = m
            remaps.append(rm)
        t = {}
        offsets = np.cumsum([0] + [p.n for p in parts[:-1]])
        for name in list(SCHEMA):
            cols = {}
            keys = list(parts[0].t[name])
            for c in keys:
                arrs = []
                for p, rm, off in zip(parts, remaps, offsets):
                    a = p.t[name][c]
                    v = VOCAB_OF.get((name, c))
                    if v is not None and len(a):
                        m = rm.get(v)
                        a = np.where(a >= 0, m[np.maximum(a, 0)] if m is not None and len(m) else a, a).astype(a.dtype)
                    if c == "hidx":
                        a = (a + off).astype(np.int32)
                    arrs.append(a)
                cols[c] = np.concatenate(arrs) if arrs else np.zeros(0)
            t[name] = cols
        return FactTable(t, vocab)

    # --- lagring
    def save(self, path: Path) -> None:
        """Två filer: <namn>.npz (numeriska kolumner) och <namn>.meta (ordlistor och objekt)."""
        path = Path(path)
        arrs, objs = {}, {}
        for name, cols in self.t.items():
            for c, a in cols.items():
                (objs if a.dtype == object else arrs)[f"{name}.{c}"] = a
        meta = path.with_suffix(".meta")
        for p_, writer in ((meta, lambda f: pickle.dump({"vocab": self.vocab, "objs": {k: list(v) for k, v in objs.items()},
                                                          "version": FACTS_VERSION}, f, protocol=pickle.HIGHEST_PROTOCOL)),
                           (path, lambda f: np.savez(f, **arrs))):
            tmp = Path(str(p_) + ".tmp")
            with open(tmp, "wb") as f:
                writer(f)
            os.replace(tmp, p_)

    @staticmethod
    def load(path: Path) -> "FactTable":
        path = Path(path)
        with np.load(path, allow_pickle=False) as z:
            arrs = {k: z[k] for k in z.files}
        meta = pickle.loads(path.with_suffix(".meta").read_bytes())
        t = {name: {} for name in SCHEMA}
        for k, a in arrs.items():
            name, c = k.split(".", 1)
            t[name][c] = a
        for k, lst in meta["objs"].items():
            name, c = k.split(".", 1)
            t[name][c] = np.asarray(lst, dtype=object) if lst else np.zeros(0, dtype=object)
        return FactTable(t, meta["vocab"], sorted_=True)

    # --- urval
    def subset_mask(self, mask: np.ndarray, name: str) -> np.ndarray:
        """Radmask för en undertabell givet en mask över händer."""
        h = self.t[name]["hidx"]
        return mask[h] if len(h) else np.zeros(0, bool)


# ---------------------------------------------------------------- parallell extraktion
class _DictCache:
    """Sparade beräkningar (från databasens calc-tabell) för en arbetsprocess. Nya värden
    samlas i `new` och skickas tillbaka, så att de sparas i databasen."""

    def __init__(self, d):
        self.d = d
        self.new = {}

    def get(self, key, compute):
        v = self.d.get(key, _MISSING)
        if v is _MISSING:
            v = self.d[key] = self.new[key] = compute()
        return v


_MISSING = object()


def _worker_extract(args):
    """Körs i en egen process: läser en sats händer direkt ur databasen och räknar fram fakta.
    Tidigare sparade beräkningar (all-in EV, handstyrka) återanvänds från databasen.
    Returnerar (fakta, id för alla behandlade händer, nya beräkningar)."""
    db_path, rowids, hero = args
    import sqlite3
    import zlib
    from . import db as dbmod
    from .db import CALC_VERSION
    from .parser import PARSER_VERSION
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    hands = []
    for k in range(0, len(rowids), 900):
        chunk = rowids[k:k + 900]
        q = f"SELECT blob FROM hands WHERE rowid IN ({','.join('?' * len(chunk))})"
        for (b,) in con.execute(q, chunk):
            hands.append(pickle.loads(zlib.decompress(b)))
    calc = {}
    keys = []
    for h in hands:
        if hero in h.seats:
            keys += [f"{p}|{h.id}|{hero}" for p in ("ev3", "rb6", "sd", "cat", "bf6")]
            keys += [f"sb|{h.id}|{hero}|flop", f"sb|{h.id}|{hero}|turn"]
            keys += [f"bfs|{h.id}|{p}" for p in h.shown if p != hero]
    v = f"{PARSER_VERSION}.{CALC_VERSION}"
    try:
        for k in range(0, len(keys), 900):
            chunk = keys[k:k + 900]
            q = f"SELECT key, value FROM calc WHERE v=? AND key IN ({','.join('?' * len(chunk))})"
            for key, val in con.execute(q, [v] + chunk):
                calc[key] = pickle.loads(val)
    except sqlite3.Error:
        pass
    con.close()
    prev = dbmod._active
    cache = _DictCache(calc)
    dbmod.set_active(cache)
    try:
        return extract(hands, hero), [h.id for h in hands], cache.new
    finally:
        dbmod.set_active(prev)


def _worker_extract_k(kt):
    return kt[0], _worker_extract(kt[1])


class FactStore:
    """Sparade fakta på disk (en mapp per hero och databas). Bara nya händer extraheras.

    * Händer där hero inte sitter med räknas som behandlade (de läses inte om varje gång).
    * Är databasen utbytt (ny databas-id) eller saknas händer som har fakta, byggs fakta om.
    """

    def __init__(self, root: Path, hero: str, db_uid: str = ""):
        import zlib
        self.hero = hero or ""
        self.db_uid = db_uid
        self.dir = Path(root) / f"fakta_{zlib.crc32(self.hero.encode()):08x}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mpath = self.dir / "manifest.json"
        self._cache = None

    def _version_key(self) -> str:
        from .db import CALC_VERSION
        from .parser import PARSER_VERSION
        return f"{FACTS_VERSION}.{PARSER_VERSION}.{CALC_VERSION}"

    def _empty_manifest(self) -> dict:
        return {"version": self._version_key(), "hero": self.hero, "db": self.db_uid, "segments": [], "n": 0,
                "seen": 0, "next": 1}

    def manifest(self) -> dict:
        if self.mpath.exists():
            try:
                m = json.loads(self.mpath.read_text(encoding="utf-8"))
                if (m.get("version") == self._version_key() and m.get("hero") == self.hero
                        and m.get("db", "") == self.db_uid):
                    m.setdefault("seen", m["n"])
                    return m
            except Exception:
                pass
        return self._empty_manifest()

    def _write_manifest(self, m: dict) -> None:
        tmp = self.mpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(m), encoding="utf-8")
        os.replace(tmp, self.mpath)

    def clear(self) -> None:
        for p in list(self.dir.glob("seg_*.npz")) + list(self.dir.glob("seg_*.meta")) + list(self.dir.glob("*.pkl")):
            p.unlink()
        if self.mpath.exists():
            self.mpath.unlink()
        self._cache = None

    def _fact_ids(self, m: dict) -> set:
        ids = set()
        for s in m["segments"]:
            ids.update(FactTable.load(self.dir / s["file"]).H["id"].tolist())
        return ids

    def _seen_ids(self, m: dict) -> set:
        p = self.dir / "seen.pkl"
        if p.exists() and m["segments"] or p.exists() and m["seen"]:
            try:
                ids = pickle.loads(p.read_bytes())
                if len(ids) == m["seen"]:
                    return ids
            except Exception:
                pass
        return self._fact_ids(m)

    def sync(self, db, progress=None, workers: int | None = None) -> int:
        """Extrahera fakta för händer i databasen som inte behandlats. Returnerar antal nya med hero."""
        from .parser import PARSER_VERSION
        m = self.manifest()
        if not m["segments"] and not m["seen"]:
            self.clear()
            m = self._empty_manifest()
        # ORDER BY rowid: samma satsindelning som tidigare (ordlistornas koder följer händernas ordning,
        # och vissa sammanställningar ordnas efter koderna) – oberoende av vilket index SQLite väljer
        rows = db.con.execute("SELECT rowid, id FROM hands WHERE pv=? ORDER BY rowid", (PARSER_VERSION,)).fetchall()
        db_ids = {hid for _, hid in rows}
        seen = self._seen_ids(m)
        if m["n"] and len(seen) and not seen.issubset(db_ids) and not self._fact_ids(m).issubset(db_ids):
            # händer med fakta finns inte längre i databasen (t.ex. utbytt databas) – bygg om
            self.clear()
            m, seen = self._empty_manifest(), set()
        todo = [rid for rid, hid in rows if hid not in seen]
        del db_ids
        if not todo:
            return 0
        workers = workers if workers is not None else max(1, min(16, os.cpu_count() or 2))
        batch = 4000
        tasks = [(str(db.path), todo[k:k + batch], self.hero) for k in range(0, len(todo), batch)]
        parts, processed = [], []
        done = 0
        t0 = time.time()

        def on_part(res):
            nonlocal done
            k_, (ft, ids, calc) = res
            parts.append((k_, ft))
            processed.extend(ids)
            if calc:  # spara direkt – inget behöver samlas i minnet
                try:
                    db.store_calc(calc)
                except Exception:
                    pass
            done += len(ids)
            if progress:
                progress(min(done, len(todo)), len(todo), time.time() - t0)

        if workers > 1 and len(tasks) > 1:
            import multiprocessing as mp
            db.con.commit()
            with mp.get_context("spawn").Pool(min(workers, len(tasks))) as pool:
                for res in pool.imap_unordered(_worker_extract_k, enumerate(tasks)):
                    on_part(res)
        else:
            for res in map(_worker_extract_k, enumerate(tasks)):
                on_part(res)
        # 2.79: satserna slås ihop i satsordning (inte i den ordning processerna blev klara), så att
        # ordlistornas koder – och allt som ordnas efter dem – blir identiska oavsett antal kärnor.
        parts.sort(key=lambda kv: kv[0])
        new = FactTable.concat([ft for _, ft in parts])
        if new.n:
            name = f"seg_{m['next']:05d}.npz"
            new.save(self.dir / name)
            m["segments"].append({"file": name, "n": new.n})
            m["next"] += 1
            m["n"] += new.n
        old = []
        if len(m["segments"]) > 12:  # slå ihop när segmenten blir många
            allft = FactTable.concat([FactTable.load(self.dir / s["file"]) for s in m["segments"]])
            name = f"seg_{m['next']:05d}.npz"
            allft.save(self.dir / name)
            old = [s["file"] for s in m["segments"]]
            m["segments"] = [{"file": name, "n": allft.n}]
            m["next"] += 1
        seen.update(processed)
        m["seen"] = len(seen)
        # ordning vid krasch: segment -> seen -> manifest (manifestet pekar aldrig på saknade filer)
        try:
            tmp = self.dir / "seen.pkl.tmp"
            tmp.write_bytes(pickle.dumps(seen, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(tmp, self.dir / "seen.pkl")
        except OSError:
            pass
        self._write_manifest(m)
        for f in old:
            for p_ in (self.dir / f, (self.dir / f).with_suffix(".meta")):
                try:
                    p_.unlink()
                except OSError:
                    pass
        self._cache = None
        return new.n

    def signature(self) -> str:
        m = self.manifest()
        return f"{m['version']}|{m.get('db', '')}|{m['n']}|{','.join(s['file'] for s in m['segments'])}"

    def load(self) -> FactTable:
        sig = self.signature()
        if self._cache is not None and self._cache[0] == sig:
            return self._cache[1]
        m = self.manifest()
        ft = FactTable.concat([FactTable.load(self.dir / s["file"]) for s in m["segments"]])
        self._cache = (sig, ft)
        return ft
