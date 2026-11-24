"""Urvalet: vilka händer en analys gäller. Samma begrepp överallt – webben, rapporten och
kommandoraden beskriver urvalet med ett Selection-objekt, och varje analys får samma urval."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .facts import EPOCH, FactTable

TABLE_CODES = {"vanliga": 0, "rush": 1}


@dataclass(frozen=True)
class Selection:
    games: tuple = ()          # t.ex. ("PLO6",) eller ("PLO4", "PLO6"); tomt = den variant du spelat mest
    table: str = ""            # "", "vanliga" eller "rush"
    stake: str = ""            # "" eller t.ex. "0.5/1"
    date_from: str | None = None   # ÅÅÅÅ-MM-DD
    date_to: str | None = None
    latest: int | None = None  # bara de senaste N händerna (efter övriga val)

    @property
    def mixed(self) -> bool:
        return len(self.games) > 1

    @property
    def full(self) -> bool:
        """Hela databasen för en variant, utan andra val – då sparas reglerna."""
        return not (self.table or self.stake or self.date_from or self.date_to or self.latest or self.mixed)

    def key(self) -> str:
        return repr((self.games, self.table, self.stake, self.date_from, self.date_to, self.latest))

    # --- masker
    def period_mask(self, ft: FactTable) -> np.ndarray:
        ts = ft.H["ts"]
        m = np.ones(ft.n, dtype=bool)
        if self.date_from:
            m &= ts >= _day_ts(self.date_from)
        if self.date_to:
            m &= ts < _day_ts(self.date_to) + 86400
        return m

    def resolve_games(self, ft: FactTable, base: np.ndarray | None = None) -> tuple:
        if self.games:
            return tuple(self.games)
        nh = ft.H["nh"] if base is None else ft.H["nh"][base]
        if not len(nh):
            return ()
        vals, cnt = np.unique(nh, return_counts=True)
        return (f"PLO{int(vals[np.argmax(cnt)])}",)

    def mask(self, ft: FactTable) -> np.ndarray:
        m = self.period_mask(ft)
        games = self.resolve_games(ft, m)
        if games:
            m &= np.isin(ft.H["nh"], [int(g[-1]) for g in games])
        if self.table in TABLE_CODES:
            m &= ft.H["ttype"] == TABLE_CODES[self.table]
        if self.stake:
            m &= ft.H["stake"] == ft.code("stake", self.stake)
        if self.latest and self.latest > 0:
            idx = np.flatnonzero(m)
            if len(idx) > self.latest:
                m = m.copy()
                m[idx[:-self.latest]] = False
        return m


def _day_ts(d: str) -> int:
    return int((datetime.strptime(d, "%Y-%m-%d") - EPOCH).total_seconds())


def game_table_ft(ft: FactTable, mask: np.ndarray) -> list[dict]:
    """Resultat per speltyp (PLO4/5/6 × vanliga bord / Rush & Cash) ur faktatabellen."""
    from collections import Counter
    from .facts import dt_of
    H = ft.H
    rows = np.flatnonzero(mask)
    if not len(rows):
        return []
    order = {6: 0, 5: 1, 4: 2}
    out = []

    def row(name, kind, r):
        n = len(r) or 1
        net, rake, ev = H["net"][r].sum(), H["rake"][r].sum(), H["ev"][r].sum()
        st = Counter(H["stake"][r].tolist())
        return {"game": name, "kind": kind, "hands": int(len(r)), "net_money": float(H["money"][r].sum()),
                "bb100": 100 * net / n, "ev_money": float(H["ev_m"][r].sum()), "ev100": 100 * ev / n,
                "rake_money": float(H["rake_m"][r].sum()), "rake100": 100 * rake / n,
                "pre100": 100 * (net + rake) / n, "ev_pre100": 100 * (ev + rake) / n,
                "stakes": ", ".join("$" + ft.label("stake", k).replace("/", "/$") for k, _ in st.most_common(3)),
                "first": dt_of(H["ts"][r[0]]).strftime("%Y-%m-%d"), "last": dt_of(H["ts"][r[-1]]).strftime("%Y-%m-%d")}

    nh, tt = H["nh"][rows], H["ttype"][rows]
    for g in sorted(set(nh.tolist()), key=lambda g: order.get(g, 9)):
        for t, tname in ((0, "Vanliga bord"), (1, "Rush & Cash")):
            r = rows[(nh == g) & (tt == t)]
            if len(r):
                out.append(row(f"PLO{g}", tname, r))
    if len(out) > 1:
        t_ = row("Alla speltyper", "", rows)
        t_["total"] = True
        out.append(t_)
    return out
