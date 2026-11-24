"""Statistikbiblioteket: alla tester som avgör om något är säkerställt finns här, på ett ställe.

Varje modul som drar slutsatser använder samma funktioner, så att de stränga kraven inte kan
urholkas av misstag i en enskild analys:

* kluster: händer från samma spelpass (alla bord, ny session efter 30 minuters paus) hänger ihop och räknas som en enhet
* cluster_se – klusterrobust standardfel
* johnson_p – ensidigt test med korrigering för snedfördelning (upptäckt)
* bootstrap_t_p – kluster-bootstrap-t (bekräftelse, ingen normalfördelning antas)
* bh_cutoff – Benjamini–Hochberg
* ci_cell – medel, 95 %-intervall och bedömning (lönsamt / förlorar / osäkert)
"""
from __future__ import annotations

import math

import numpy as np

BOOT_REPS = 4000
RULE_FAMILIES = 3   # tabeller som kan ge regler (nöt-egenskaper, öppningsguide, rundowns) – en gemensam korrigering
RULE_MIN_N = 100    # minsta antal händer i en ruta innan den kan bedömas (testet är för generöst med färre)
MIN_BIG_WINS = 5      # svansvakt: minst så många resultat över +BIG_WIN_BB innan en förlust kan bekräftas
BIG_WIN_BB = 10.0


def _p_one_sided(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2))  # P(Z <= z)


def _moments(x):
    n = len(x)
    m = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    mu3 = float(((x - m) ** 3).mean()) if n > 2 else 0.0
    return n, m, sd, mu3


def johnson_p(x) -> float:
    """Ensidigt p-värde för att medelvärdet är under 0, med Johnsons (1978) korrigering för
    sned fördelning. Pokerresultat har långa högersvansar (stora vinster), och då ger en vanlig
    z-test för många falska 'förluster'. Korrigeringen tar bort det mesta av det felet."""
    n, m, sd, mu3 = _moments(x)
    if n < 3 or sd <= 0:
        return 1.0
    t = (m + mu3 / (6 * sd ** 2 * n) + mu3 / (3 * sd ** 4) * m * m) / (sd / math.sqrt(n))
    return _p_one_sided(t)


def _cluster_stats(x, c):
    """Klustersummor och klusterrobust medel/standardfel."""
    _, inv = np.unique(c, return_inverse=True)
    sums = np.bincount(inv, weights=x)
    cnts = np.bincount(inv).astype(np.float64)
    return sums, cnts


def _cr_t(sums, cnts):
    n = cnts.sum()
    m = sums.sum() / n
    k = len(sums)
    resid = sums - m * cnts
    var = (resid ** 2).sum() / n ** 2 * k / max(k - 1, 1)
    return m, math.sqrt(var)


def cluster_se(x, c) -> float:
    sums, cnts = _cluster_stats(x, c)
    return _cr_t(sums, cnts)[1] if len(sums) > 1 else float("inf")


def bootstrap_t_p(x, c=None, reps: int = BOOT_REPS, seed: int = 0) -> float:
    """Ensidigt p-värde (medel < 0) med kluster-bootstrap-t: hela kluster (spelpass) dras,
    så att händer från samma pass inte räknas som oberoende. Ingen normalfördelning antas."""
    if c is None:
        c = np.arange(len(x))
    if len(x) < 3:
        return 1.0
    sums, cnts = _cluster_stats(x, c)
    k = len(sums)
    if k < 20:
        return 1.0  # för få oberoende kluster för att bekräfta något
    m, se = _cr_t(sums, cnts)
    if se <= 0:
        return 1.0
    t_obs = m / se
    rng = np.random.default_rng(seed)
    hits = 0
    chunk = max(1, int(2_000_000 // k))
    done = 0
    while done < reps:
        b = min(chunk, reps - done)
        idx = rng.integers(0, k, size=(b, k))
        S, C = sums[idx], cnts[idx]
        N = C.sum(axis=1)
        mb = S.sum(axis=1) / N
        resid = S - mb[:, None] * C
        seb = np.sqrt((resid ** 2).sum(axis=1) / N ** 2 * k / (k - 1))
        tb = (mb - m) / np.maximum(seb, 1e-12)
        hits += int((tb <= t_obs).sum())
        done += b
    return (hits + 1) / (reps + 1)




def bh_cutoff(pvals, q: float) -> float:
    """Största p-värde som klarar Benjamini–Hochberg på nivå q (0 = inget)."""
    m = len(pvals)
    cutoff = 0.0
    for rank, p in enumerate(sorted(pvals), 1):
        if p <= rank / m * q:
            cutoff = p
    return cutoff


def ci_cell(x, c, min_n: int = 30, z: float = 1.96, empty: str = "för få", m_tests: int = 1,
            alpha: float = 0.05, reps: int = 2000) -> dict:
    """Medel och klusterrobust 95 %-intervall (beskrivande) med bedömning.

    Bedömningen "lönsamt"/"förlorar" kräver mer än att intervallet ligger på ena sidan om noll:
    ett ensidigt kluster-bootstrap-t-test (ingen normalfördelning antas – pokerresultat är sneda)
    ska klara Bonferroni över alla m_tests celler som bedöms samtidigt (tvåsidigt: alpha / 2m).
    Under min_n värden: ingen bedömning."""
    import zlib
    n = len(x)
    if n == 0:
        return {"n": 0, "mean": None, "lo": None, "hi": None, "verdict": empty}
    x = np.asarray(x, dtype=float)
    m = float(x.mean())
    if n < min_n:
        return {"n": n, "mean": m, "lo": None, "hi": None, "verdict": "för få"}
    c = np.asarray(c, dtype=np.int64)
    se = cluster_se(x, c)
    lo, hi = m - z * se, m + z * se
    verdict = "jämnt / osäkert"
    # En "förlust" i en grupp där stora vinster är sällsynta kan bero på att ingen stor vinst råkade
    # komma med – samma svansvakt som i bevismotorn: minst MIN_BIG_WINS resultat över +BIG_WIN_BB.
    tail_ok = hi >= 0 or int((x > BIG_WIN_BB).sum()) >= MIN_BIG_WINS
    if hi < 0 and not tail_ok:
        # 2.73: visa att det är svansvakten som stoppar – intervallet ligger under noll, men gruppen har för få stora
        # vinster (> +10 bb) för att en förlust ska kunna bekräftas. Försiktighetsregel, inte ett bevis åt något håll.
        return {"n": n, "mean": m, "lo": lo, "hi": hi, "verdict": "osäkert (svansvakt)", "tail_blocked": True}
    if (lo > 0 or hi < 0) and tail_ok:
        sign = -1.0 if lo > 0 else 1.0     # testa "medel > 0" som "−x < 0"
        need = alpha / (2 * max(m_tests, 1))
        if boot_confirms(sign * x, c, need, seed=zlib.crc32(f"{n}|{m:.6f}".encode()), base_reps=reps):
            verdict = "lönsamt" if lo > 0 else "förlorar"
    return {"n": n, "mean": m, "lo": lo, "hi": hi, "verdict": verdict}


def boot_confirms(x, c, need: float, seed: int = 0, base_reps: int = 2000) -> bool:
    """Klarar kluster-bootstrap-t (ensidigt, medel < 0) nivån `need`? Antalet omdragningar anpassas
    så att p-värdet kan bli tillräckligt litet (minst 30 / need), men avbryts tidigt när det
    redan är tydligt att nivån inte nås."""
    import math as _m
    target = max(base_reps, int(_m.ceil(30 / need)))
    hits, done, k = 0, 0, 0
    while done < target:
        r = min(base_reps if done == 0 else 4 * base_reps, target - done)
        p = bootstrap_t_p(x, c, reps=r, seed=seed + k)
        if p >= 1.0 and done == 0:
            return False                        # för få kluster eller inget att testa
        hits += int(round(p * (r + 1))) - 1
        done += r
        k += 1
        if (hits + 1) / (done + 1) > 5 * need:  # tydligt för stort – sluta
            return False
    return (hits + 1) / (done + 1) <= need


def ci_cells(pairs, min_n: int = 30, empty: str = "för få", **kw) -> list:
    """ci_cell för flera celler som bedöms tillsammans (Bonferroni över de celler som har minst min_n)."""
    m = sum(1 for x, _ in pairs if len(x) >= min_n)
    return [ci_cell(x, c, min_n=min_n, empty=empty, m_tests=m, **kw) for x, c in pairs]
