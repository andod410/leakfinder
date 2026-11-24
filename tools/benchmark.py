"""Prestandatest: läs in en mapp med händer i en ny databas och mät varje steg.

    python tools/benchmark.py <mapp> --db /tmp/bench.db

Mäter inläsning, faktaextraktion, inläsning av fakta, rapport för olika urval (första gången
och med sparade resultat) och minnesanvändning.
"""
from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def rss_mb() -> float:
    """Nuvarande minne för processen (MB), från /proc när det finns."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--db", required=True)
    ap.add_argument("--skip-import", action="store_true")
    a = ap.parse_args()
    from plo_leak.db import HandDB
    from plo_leak.pipeline import build
    from plo_leak.selection import Selection
    rows = []

    def step(name, t0, extra=""):
        rows.append((name, time.time() - t0, rss_mb(), extra))
        print(f"{name:<48} {time.time() - t0:8.1f} s   minne {rss_mb():7.0f} MB  (topp {peak_mb():.0f})  {extra}", flush=True)

    db = HandDB(a.db)
    if not a.skip_import:
        t0 = time.time()
        r = db.add_paths([a.folder], lambda i, n, new: print(f"\r  inläsning {i}/{n} MB, {new} nya", end="", flush=True))
        print()
        step("Inläsning till databasen (parsning)", t0, f"{r['hands_new']} nya händer")
    t0 = time.time()
    hero = db.detect_hero()
    store = db.facts(hero)
    n = store.sync(db, lambda d, t, el: print(f"\r  fakta {d}/{t}", end="", flush=True))
    print()
    step("Fakta för nya händer (en gång per hand)", t0, f"{n} händer")
    t0 = time.time()
    n2 = store.sync(db)
    step("Fakta igen (inget nytt)", t0, f"{n2} händer")
    t0 = time.time()
    ft = store.load()
    step("Läs in faktatabellen", t0, f"{ft.n} händer")
    cache_dir = Path(a.db).parent / (Path(a.db).stem + "_resultat")
    sig = store.signature()
    for label, sel in (("Hela databasen", Selection()), ("Senaste 20 000", Selection(latest=20000)),
                       ("En nivå + period", Selection(stake=ft.vocab["stake"][0], date_from="2026-10-01"))):
        for rnd in ("första gången", "igen (sparade resultat)"):
            t0 = time.time()
            info = {}
            html = build(ft, hero, db.get_hand, sel, data_sig=sig, cache_dir=cache_dir, collect=info)
            step(f"Rapport: {label}, {rnd}", t0, f"{info['st'].hands} händer, {len(html) // 1024} kB")
            if rnd == "första gången":
                slow = sorted(info["timings"].items(), key=lambda kv: -kv[1][1])[:4]
                print("     långsammast: " + ", ".join(f"{k} {v[1]} s" for k, v in slow))
    dbsize = os.path.getsize(a.db) / 1e6
    fsize = sum(p.stat().st_size for p in store.dir.glob("*")) / 1e6
    print(f"\nDatabas {dbsize:.0f} MB · fakta {fsize:.0f} MB · minne topp {peak_mb():.0f} MB")


if __name__ == "__main__":
    main()
