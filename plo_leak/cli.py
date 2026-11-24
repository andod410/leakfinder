"""Kommandorad:  python -m plo_leak <filer eller mappar> [--out rapport.html]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .parser import detect_hero, load_paths
from .pool import analyze_pool
from .river import analyze_river
from .stats import control_numbers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plo_leak", description="Hitta läckor i ditt PLO-spel (GGPoker-handhistorik).")
    ap.add_argument("paths", nargs="*", help="Handhistorik: .txt-filer, .zip-filer eller mappar. "
                    "Utelämna för att bara analysera händerna som redan finns i databasen.")
    ap.add_argument("--utan-databas", action="store_true",
                    help="Använd inte databasen: analysera bara de angivna filerna")
    ap.add_argument("--databas", default=None, help="Sökväg till databasfilen (standard: ~/.plo_leak_cache/plo_leak.db)")
    ap.add_argument("--rensa-databas", action="store_true", help="Töm databasen innan inläsning")
    ap.add_argument("--senaste", type=int, nargs="?", const=15000, default=None,
                    help="Analysera bara de senaste N händerna efter datum och tid (utan tal: 15 000)")
    ap.add_argument("--fran", default=None, help="Analysera bara händer från och med detta datum (ÅÅÅÅ-MM-DD)")
    ap.add_argument("--till", default=None, help="Analysera bara händer till och med detta datum (ÅÅÅÅ-MM-DD)")
    ap.add_argument("--hero", default=None, help="Ditt namn i handhistoriken (hittas automatiskt om det utelämnas)")
    ap.add_argument("--out", default="plo_rapport.html", help="Var HTML-rapporten ska sparas")
    ap.add_argument("--profile", choices=["PLO6", "PLO4"], help="Tvinga riktvärden (annars autodetekteras)")
    ap.add_argument("--export", default="plo_analys_till_claude.json",
                    help="Fil att ladda upp till Claude (statistik + anonymiserade exempelhänder)")
    ap.add_argument("--pool-min-hands", type=int, default=3000,
                    help="Minsta antal händer för att en motståndare ska ingå i riktvärdena (0 = stäng av)")
    ap.add_argument("--visa-hypoteser", action="store_true",
                    help="Visa även obevisade läckor baserade på riktvärden (av som standard)")
    ap.add_argument("--river-modell", action="store_true",
                    help="Bygg även den beskrivande river-modellen (ger inga läckor, tar längre tid)")
    ap.add_argument("--simulera", action="store_true",
                    help="Kör simuleringen av rundowns (1,1 miljon utdelningar, några minuter första gången, sparas sedan)")
    ap.add_argument("--game", choices=["PLO4", "PLO5", "PLO6", "alla"], help="Vilken variant som analyseras (standard: den du spelat mest)")
    a = ap.parse_args(argv)
    # 2.81: samma GG-spärr som webben och nattkörningen (utvecklingsläget gäller även här)
    from . import ggguard
    if ggguard.refuse_if_gg():
        return 2
    print(f"PLO-läckfinnare version {__version__}")
    from datetime import datetime
    for d in (a.fran, a.till):
        if d:
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                print(f"Datum ska skrivas ÅÅÅÅ-MM-DD och finnas i kalendern (fick {d}).")
                return 1
    import time
    from .facts import extract
    from .pipeline import EmptySelection, build
    from .selection import Selection

    t0 = time.time()
    db = None
    hands = None
    imports = []
    if a.utan_databas:
        if not a.paths:
            print("Ange filer eller mappar när databasen inte används.")
            return 1
        hands = load_paths(a.paths, lambda i, n, c: print(f"\rLäser filer: {i}/{n}  ({c} händer)", end="", flush=True))
        print()
        if not hands:
            print("Hittade inga PLO-händer. Kontrollera att filerna är GGPoker-handhistorik (.txt eller .zip).")
            return 1
        hero = a.hero or detect_hero(hands)
        if not hero:
            print("Hittade inget spelarnamn med hålkort i filerna. Använd --hero.")
            return 1
        ft = extract(hands, hero, lambda k: print(f"\rRäknar fram fakta: {k}/{len(hands)}", end="", flush=True))
        print()
        by_id = {h.id: h for h in hands}
        lookup, sig, cache_dir = by_id.get, None, None
    else:
        from .db import HandDB
        db = HandDB(a.databas)
        if a.rensa_databas:
            db.clear()
            print("Databasen är tömd.")
        if a.paths:
            r = db.add_paths(a.paths, lambda i, n, new: print(f"\rLäser filer: {i}/{n} MB  ({new} nya händer)", end="", flush=True))
            print()
            imports.append(("Filer", r))
            print(f"{r['hands_seen']} händer hittade: {r['hands_new']} nya sparades, {r['hands_known']} fanns redan"
                  + (f", {r['hands_other_games']} andra spel hoppades över" if r['hands_other_games'] else "")
                  + (f", {r['hands_unreadable']} kunde inte läsas" if r['hands_unreadable'] else "")
                  + f" ({r['files_skipped']} oförändrade filer hoppades över).")
            for e in r["unreadable_examples"]:
                print(f"   Kunde inte läsas: {e}")
        if db.stale_count():
            print(f"OBS: {db.stale_count()} händer är sparade av en äldre version – ange mappen med dina händer en gång så läses de in igen.")
        a_, b_ = db.span()
        print(f"Databasen innehåller {db.count()} händer" + (f", {a_[:10]} – {b_[:16].replace('T', ' ')}" if a_ else "") + f" ({db.path}).")
        if not db.count():
            print("Hittade inga PLO-händer. Kontrollera att filerna är GGPoker-handhistorik (.txt eller .zip).")
            return 1
        hero = a.hero or db.detect_hero()
        if not hero:
            print("Hittade inget spelarnamn med hålkort i databasen. Använd --hero.")
            return 1
        store = db.facts(hero)
        n_new = store.sync(db, lambda d, t, el: print(f"\rRäknar fram fakta för nya händer: {d}/{t}", end="", flush=True))
        if n_new:
            print()
        ft = store.load()
        lookup, sig = db.get_hand, store.signature()
        cache_dir = db.path.parent / (db.path.stem + "_resultat")
    if not ft.n:
        print(f"Ingen spelare som heter '{hero}' hittades. Använd --hero.")
        return 1
    games = ()
    if a.game == "alla":
        import numpy as np
        games = tuple(f"PLO{int(g)}" for g in sorted(np.unique(ft.H["nh"]), reverse=True))
    elif a.game:
        games = (a.game,)
    sel = Selection(games=games, date_from=a.fran, date_to=a.till, latest=a.senaste)
    strict = not a.visa_hypoteser
    pool = river = None
    if not strict or a.river_modell:
        if hands is None:
            hands = db.load(a.fran, a.till)
        hands = [h for h in hands if h.num_hole == int((sel.resolve_games(ft) or ("PLO6",))[0][-1])]
        if not strict and a.pool_min_hands > 0:
            print("Räknar riktvärden från motståndarna …")
            pool = analyze_pool(hands, hero, a.pool_min_hands)
        if a.river_modell:
            print("Bygger den beskrivande river-modellen …")
            river = analyze_river(hands, hero, len(hands))
    sim = None
    if a.simulera:
        from .sim import run_simulation
        print("Simulerar rundowns …")
        sim = run_simulation(progress=lambda i, n: print(f"\r   {i}/{n}", end="", flush=True))
        print()
    info = {}
    try:
        html = build(ft, hero, lookup, sel, use_db=db is not None, sim=sim, imports=imports, data_sig=sig,
                     cache_dir=cache_dir, strict=strict, pool=pool, river=river, profile=a.profile, collect=info,
                     progress=lambda s: print(f"   {s}", flush=True))
    except EmptySelection as e:
        print(str(e))
        return 1
    st, leaks, top3, ranges = info["st"], info["leaks"], info["top3"], info["ranges"]
    print(f"\n{st.hands} händer analyserade ({info['profile']}) · {st.net_bb:+.0f} bb · {st.bb100:+.1f} bb/100")
    print(f"Vunnet: {st.net_money:+.2f} · All-in EV: {st.ev_net_money:+.2f} ({st.ev_bb100:+.1f} bb/100)\n")
    from .stats import money_summary, stake_table
    print("Resultat och rake:")
    for r in money_summary(st):
        print(f"   {r['label']:<24} {r['bb']:>+10.0f} bb  {r['money']:>+12.2f}  {r['bb100']:>+8.2f} bb/100")
    srows = stake_table(st)
    if srows:
        print("\nResultat per nivå:")
        for r in srows:
            print(f"   {r['stake']:<10}{r['hands']:>9}{r['net_money']:>+12.2f}{r['bb100']:>+9.2f} bb/100  "
                  f"EV {r['ev_money']:>+11.2f}  rake {r['rake100']:.2f} bb/100")
    print("\nKontrollsiffror (jämför med DriveHUD för samma händer):")
    print("   " + " · ".join(f"{k} {v}" for k, v in control_numbers(st)) + "\n")
    R = info["results"]
    if strict:
        print(f"Strikt läge: {R['leaks']['tests']} beslutsgrupper testade i halva A, "
              f"{R['leaks']['candidates']} kandidater, {len(leaks)} bekräftade i halva B.\n")
        for i, l in enumerate(top3, 1):
            low = f", minst {l.severity_low:.2f}" if l.severity_low is not None else ""
            print(f"  {i}. {l.title}  – kostar ca {l.severity:.2f} bb/100{low}")
            print(f"     {l.fix[0]}")
    if not leaks:
        print("Inga säkerställda läckor." if strict else "Inga tydliga läckor hittades med nuvarande urval.")
    if ranges:
        print("\nVAR GÅR GRÄNSEN FÖR LÖNSAMMA STARTHÄNDER?")
        for r in ranges:
            cut = "lönsamt genom allt du spelar" if r["cutoff_pct"] is None else f"gräns ca topp {r['cutoff_pct']:.0f} % (80 %: {r['lo_pct']:.0f}–{r['hi_pct']:.0f} %)"
            mark = {"wide": "FÖR BRETT", "ok": "ok", "unclear": "oklart"}[r["verdict"]["kind"]]
            print(f"   {r['name']:<38} {r['pos']:<4} du {r['verb']} {r['play_pct']:>3.0f} % · {cut} · {mark}")
    out = Path(a.out)
    out.write_text(html, encoding="utf-8")
    print(f"\nFull rapport: {out.resolve()}")
    exp = Path(a.export)
    exp.write_text(info["export_json"], encoding="utf-8")
    print(f"Fil att ladda upp till Claude: {exp.resolve()}  ({exp.stat().st_size // 1024} kB)")
    if db is not None:
        db.save_calc()
    print(f"Klart på {time.time() - t0:.0f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
