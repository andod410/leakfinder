"""2.81: fasta avläsningar för framåttest och hypoteser (granskningen av 2.79.1, P1 metod).

Tidigare räknades testet om på allt underlag varje gång nya händer kom in, med en vanlig fast gräns. Upprepade
avläsningar gör då att "håller" kan komma för tidigt. Nu:

* Avläsning bara när 20, 40 och 80 spelpass finns efter startdatum. Varje avläsning använder exakt de första K
  passen (i tidsordning) – senare händer ändrar aldrig ett avläst resultat.
* Felrisken delas på avläsningarna (Bonferroni över antal avläsningar × antal regler).
* Första "håller" eller "håller inte" står kvar (stopp vid avgörande). Annars gäller den senaste avläsningen.
"""
from __future__ import annotations

import numpy as np

LOOKS = (20, 40, 80)


def pass_order(ts: np.ndarray, clu: np.ndarray) -> list:
    """Spelpassen i tidsordning (efter första hand i passet)."""
    first: dict = {}
    for c, t in zip(clu.tolist(), ts.tolist()):
        if c not in first or t < first[c]:
            first[c] = t
    return sorted(first, key=first.get)


def cohorts(ts: np.ndarray, clu: np.ndarray) -> list:
    """[(K, mängd pass-id)] för varje avläsning som nåtts."""
    order = pass_order(ts, clu)
    return [(k, set(order[:k])) for k in LOOKS if len(order) >= k]


def sequential(cell_fn, x_clu, cohorts_: list, families: int) -> dict:
    """cell_fn(mask, families) -> dict med 'verdict'. Kör avläsningarna i ordning."""
    fam = max(families, 1) * len(LOOKS)
    last = None
    for k, ids in cohorts_:
        m = np.isin(x_clu, list(ids))
        res = cell_fn(m, fam)
        res["look"] = k
        last = res
        if res.get("verdict") in ("håller", "håller inte"):
            return res
    if last is None:
        return {"verdict": "för få", "look": 0}
    return last


def next_look(n_pass: int):
    return next((k for k in LOOKS if k > n_pass), None)
