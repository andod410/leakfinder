"""Bygger hero-statistiken (HeroStats) för ett urval ur faktatabellen – med numpy, utan att
läsa in några kompletta händer. Resultatet är samma objekt som den gamla genomgången gav,
så alla analyser och rapporten fungerar som förut."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from .decisions import Decisions, GroupArr, PreRows
from .facts import SEP, STREET_CODE, FactTable, dt_of
from .stats import Bucket, HeroStats, Stat

STREET_NAME = {v: k for k, v in STREET_CODE.items()}
EXAMPLES_KEEP = 40


class LazyHands:
    """Ersätter den gamla ordlistan med alla händer: hämtar en hand först när den behövs."""

    def __init__(self, lookup, ft: FactTable | None = None, rows=None):
        self._lookup = lookup
        self._cache = {}
        self._ft = ft
        self._rows = rows

    def __getstate__(self):  # databaskopplingen sparas inte (senaste analysen på disk)
        d = dict(self.__dict__)
        d["_lookup"], d["_cache"] = None, {}
        return d

    def get(self, hid, default=None):
        if hid in self._cache:
            return self._cache[hid]
        h = self._lookup(hid) if self._lookup else None
        if h is None:
            return default
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[hid] = h
        return h

    def __getitem__(self, hid):
        h = self.get(hid)
        if h is None:
            raise KeyError(hid)
        return h

    def __contains__(self, hid):
        return self.get(hid) is not None

    def __len__(self):
        return len(self._rows) if self._rows is not None else 0


def _seq_sum(x) -> float:
    return float(np.cumsum(x)[-1]) if len(x) else 0.0


def _worst(ids, vals, keep=EXAMPLES_KEEP, idx=None) -> list:
    """De `keep` lägsta värdena med hand-id, i samma ordning som en stabil sortering
    (lika värden i tidsordning). ids[idx[i]] är id för vals[i] (idx=None: ids[i])."""
    n = len(vals)
    if not n:
        return []
    if n > 4 * keep:
        thr = vals[np.argpartition(vals, keep - 1)[:keep]].max()
        cand = np.flatnonzero(vals <= thr)
        o = cand[np.lexsort((cand, vals[cand]))][:keep]
    else:
        o = np.argsort(vals, kind="stable")[:keep]
    if idx is None:
        return [(ids[i], float(vals[i])) for i in o]
    return [(ids[idx[i]], float(vals[i])) for i in o]


def build_stats(ft: FactTable, mask: np.ndarray | None = None, hero: str = "Hero", lookup=None) -> HeroStats:
    H = ft.H
    if mask is None:
        mask = np.ones(ft.n, dtype=bool)
    rows = np.flatnonzero(mask)
    st = HeroStats(hero=hero)
    st.ft, st.mask, st.rows = ft, mask, rows
    n = len(rows)
    st.hands = n
    if n == 0:
        st.decisions = Decisions()
        st.decisions.pre = PreRows(ft, np.zeros(0, bool))
        st.hands_by_id = LazyHands(lookup, ft, rows)
        return st
    ids = H["id"]
    net, money, rake, rake_m, ev, ev_m = (H[c][rows] for c in ("net", "money", "rake", "rake_m", "ev", "ev_m"))
    st.cumulative = np.cumsum(net)
    st.cumulative_ev = np.cumsum(ev)
    st.cumulative_rake = np.cumsum(rake)
    st.cumulative_money = np.cumsum(money)
    st.cumulative_ev_money = np.cumsum(ev_m)
    st.cumulative_rake_money = np.cumsum(rake_m)
    if "evr" in H:   # 2.80
        st.ev_rake_bb = _seq_sum(H["evr"][rows])
        st.ev_rake_money = _seq_sum(H["evr_m"][rows])
    sd = H["sd"][rows].astype(bool)  # du gick till showdown (inte foldat, hela bordet utdelat)
    st.cumulative_sd = np.cumsum(np.where(sd, net, 0.0))
    st.cumulative_nsd = np.cumsum(np.where(sd, 0.0, net))
    st.cumulative_sd_money = np.cumsum(np.where(sd, money, 0.0))
    st.cumulative_nsd_money = np.cumsum(np.where(sd, 0.0, money))
    st.net_bb = float(st.cumulative[-1])
    st.ev_net_bb = float(st.cumulative_ev[-1])
    st.rake_paid_bb = float(st.cumulative_rake[-1])
    st.net_money = float(st.cumulative_money[-1])
    st.ev_net_money = float(st.cumulative_ev_money[-1])
    st.rake_paid_money = float(st.cumulative_rake_money[-1])
    st.first_date = dt_of(H["ts"][rows[0]])
    st.last_date = dt_of(H["ts"][rows[-1]])

    def counter(col, vocab):
        """Antal per kod, i ordning för första förekomst (som den gamla genomgången)."""
        arr = H[col][rows]
        c = Counter()
        for k in _ordered_codes(arr):
            c[ft.label(vocab, k)] = int((arr == k).sum())
        return c

    st.stakes = defaultdict(int, counter("stake", "stake"))
    st.games = defaultdict(int, counter("game", "game"))
    pl = Counter()
    for k, c in zip(*np.unique(H["nplay"][rows], return_counts=True)):
        pl[int(k)] = int(c)
    st.players = defaultdict(int, pl)

    # resultat per nivå
    sc = H["stake"][rows]
    by_stake = {}
    for lab in st.stakes:
        m = sc == ft.code("stake", lab)
        by_stake[lab] = {"hands": int(m.sum()), "net_bb": _seq_sum(net[m]), "rake_bb": _seq_sum(rake[m]),
                         "net_money": _seq_sum(money[m]), "rake_money": _seq_sum(rake_m[m]),
                         "ev_bb": _seq_sum(ev[m]),
                         **({"evr_bb": _seq_sum(H["evr"][rows][m]), "evr_money": _seq_sum(H["evr_m"][rows][m])} if "evr" in H else {})}
    st.by_stake = by_stake

    # all-in per gata
    ai = H["ai_st"][rows]
    for code in sorted(set(ai.tolist()) - {-1}):
        m = ai == code
        st.allin[STREET_NAME[code]] = {"hands": int(m.sum()), "actual_bb": _seq_sum(net[m]), "ev_bb": _seq_sum(ev[m]),
                                       "eq_sum": _seq_sum(H["ai_eq"][rows][m]),
                                       "actual_money": _seq_sum(H["money"][rows][m]), "ev_money": _seq_sum(H["ev_m"][rows][m])}

    # positioner och handtyper
    vp = H["vpip"][rows]
    pos = H["pos"][rows]
    for code in _ordered_codes(pos):
        m = pos == code
        b = st.by_pos[ft.label("pos", code)]
        b.hands, b.net, b.vpip = int(m.sum()), _seq_sum(ev[m]), int(vp[m].sum())
    for col, target, keyf in (("bucket", st.by_bucket, lambda c: ft.label("bucket", c)),
                              ("nut", st.by_nut, lambda c: ft.label("nut", c)),
                              ("combo", st.by_nut_combo, lambda c: ft.label("combo", c))):
        arr = H[col][rows]
        for code in _ordered_codes(arr[arr >= 0]):
            m = arr == code
            b = target[keyf(code)]
            b.hands, b.net, b.vpip = int(m.sum()), _seq_sum(ev[m]), int(vp[m].sum())
            b.net_played = _seq_sum(ev[m & vp])
    nut = H["nut"][rows]
    has = nut >= 0
    pairs = nut.astype(np.int64) * 100 + pos
    for code in _ordered_codes(pairs[has]):
        m = (pairs == code) & has
        b = st.by_nut_pos[(ft.label("nut", int(code // 100)), ft.label("pos", int(code % 100)))]
        b.hands, b.net, b.vpip = int(m.sum()), _seq_sum(ev[m]), int(vp[m].sum())
        b.net_played = _seq_sum(ev[m & vp])

    st.agg_actions = int(H["agg"][rows].sum())
    st.pass_actions = int(H["pas"][rows].sum())

    # frekvenser
    S = ft.t["stat"]
    sm = ft.subset_mask(mask, "stat")
    sh, sk, so, sht = S["hidx"][sm], S["key"][sm], S["opps"][sm].astype(np.int64), S["hits"][sm].astype(np.int64)
    sev = H["ev"][sh]
    if len(sk):
        order = np.argsort(sk, kind="stable")          # gruppera en gång i stället för en mask per nyckel
        bounds = np.flatnonzero(np.diff(sk[order])) + 1
        segs = {int(sk[seg[0]]): seg for seg in np.split(order, bounds)}
    else:
        segs = {}
    for code in _ordered_codes(sk):
        seg = segs[code]
        key = ft.label("stat", code)
        s_ = Stat()
        o, hh, e = so[seg], sht[seg], sev[seg]
        s_.opps, s_.hits = int(o.sum()), int(hh.sum())
        oe, he = o * e, hh * e
        s_.net_all, s_.sq_all = float(oe.sum()), float((oe * e).sum())
        s_.net_hit, s_.sq_hit = float(he.sum()), float((he * e).sum())
        hid_m = sh[seg]
        if (o == 1).all():   # vanligast: en gång per hand – inga upprepningar behövs
            hm = hh.astype(bool)
            s_.hit_examples = _worst(ids, e[hm], idx=hid_m[hm])
            s_.miss_examples = _worst(ids, e[~hm], idx=hid_m[~hm])
        else:
            hit_rows = np.repeat(np.arange(len(e)), hh)
            miss_rows = np.repeat(np.arange(len(e)), o - hh)
            s_.hit_examples = _worst(ids, e[hit_rows], idx=hid_m[hit_rows])
            s_.miss_examples = _worst(ids, e[miss_rows], idx=hid_m[miss_rows])
        if key.startswith("rfi|"):
            st.rfi_by_pos[key[4:]] = s_
        elif key.startswith("ep|"):
            st.by_bucket_ep[key[3:]] = s_
        else:
            st.s[key] = s_

    # tilt: VPIP i händerna direkt efter en stor förlust
    big, window = 60.0, 30
    trig = net <= -big
    idx = np.arange(n)
    last = np.maximum.accumulate(np.where(trig, idx, -10 ** 9))
    prev_last = np.concatenate([[-10 ** 9], last[:-1]])
    after_m = (idx - prev_last) <= window
    tp, tv = H["t_pre"][rows], H["t_vpip"][rows]
    after, normal = Stat(), Stat()
    for s_, m in ((after, tp & after_m), (normal, tp & ~after_m)):
        e, hit = ev[m], tv[m]
        s_.opps, s_.hits = int(m.sum()), int(hit.sum())
        s_.net_all, s_.sq_all = float(e.sum()), float((e * e).sum())
        s_.net_hit, s_.sq_hit = float(e[hit].sum()), float((e[hit] ** 2).sum())
        rm = rows[m]
        s_.hit_examples = _worst(ids, e[hit], idx=rm[hit])
        s_.miss_examples = _worst(ids, e[~hit], idx=rm[~hit])
    st.tilt = {"after": after, "normal": normal, "triggers": int(trig.sum()), "threshold": big, "window": window}

    # showdown-förluster, datakvalitet, exempel
    X = ft.t["sd"]
    xm = ft.subset_mask(mask, "sd")
    if xm.any():
        import pickle
        rev = X["rev"][xm]
        objs = X["obj"][xm]
        st.reverse_dominated = [pickle.loads(o) for o in objs[rev]]   # bara de som används
    D = ft.t["diag"]
    dm = ft.subset_mask(mask, "diag")
    if dm.any():
        tot = np.bincount(D["key"][dm].astype(np.int64), weights=D["cnt"][dm], minlength=len(ft.vocab.get("diag", [])))
        for code in _ordered_codes(D["key"][dm]):
            st.diag[ft.label("diag", code)] += int(tot[code])
    SP = ft.t["samp"]
    spm = ft.subset_mask(mask, "samp")
    if spm.any():
        kk, hh_ = SP["key"][spm], SP["hidx"][spm]
        for code in _ordered_codes(kk):
            st.samples[ft.label("samp", code)] = [ids[h] for h in hh_[kk == code][:8]]
    if lookup is not None:
        hs = H["hs"][rows]
        for code in _ordered_codes(hs)[:40]:
            j = rows[int(np.argmax(hs == code))]
            h = lookup(ids[j])
            if h is not None:
                st.header_examples[ft.label("hs", code)] = h.raw.split("\n", 1)[0]

    st.decisions = build_decisions(ft, mask)
    st.hands_by_id = LazyHands(lookup, ft, rows)
    return st


def _ordered_codes(arr) -> list:
    """Unika koder i ordning för första förekomst."""
    if not len(arr):
        return []
    u, first = np.unique(arr, return_index=True)
    return [int(x) for x in u[np.argsort(first)]]


def build_decisions(ft: FactTable, mask: np.ndarray) -> Decisions:
    H = ft.H
    dec = Decisions()
    ids = H["id"]
    clu_all = H["clu"]
    G = ft.t["grp"]
    gm = ft.subset_mask(mask, "grp")
    gh, gk, gd = G["hidx"][gm], G["key"][gm], G["delta"][gm]
    if len(gk):
        order = np.argsort(gk, kind="stable")
        bounds = np.flatnonzero(np.diff(gk[order])) + 1
        for seg in np.split(order, bounds):
            key = tuple(ft.label("gkey", int(gk[seg[0]])).split(SEP))
            vals = gd[seg]
            hids = gh[seg].astype(np.int64)
            clus = clu_all[hids]
            dec.groups[key] = GroupArr.from_arrays(vals, clus, hids, _worst(ids, vals, idx=hids))
    F = ft.t["fold"]
    fm = ft.subset_mask(mask, "fold")
    if fm.any():
        fk = F["key"][fm].astype(np.int64)
        tot = np.bincount(fk, weights=F["cnt"][fm], minlength=len(ft.vocab.get("fkey", [])))
        for code in _ordered_codes(fk):
            dec.folds[tuple(ft.label("fkey", code).split(SEP))] += int(tot[code])
    dec.pre = PreRows(ft, mask)
    R = ft.t["riv"]
    rm = ft.subset_mask(mask, "riv")
    lab = ft.vocab
    dec.river = [(lab["size"][s], lab["rstr"][r], lab["kind"][k], None if np.isnan(d) else float(d), int(clu_all[h]), ids[h])
                 for s, r, k, d, h in zip(R["size"][rm], R["str"][rm], R["kind"][rm], R["delta"][rm], R["hidx"][rm])]
    T = ft.t["trn"]
    tm = ft.subset_mask(mask, "trn")
    dec.turn_calls = [(lab["tstr"][s], float(d), int(clu_all[h]), lab["path"][p])
                      for s, d, h, p in zip(T["str"][tm], T["delta"][tm], T["hidx"][tm], T["path"][tm])]
    return dec
