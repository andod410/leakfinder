"""2.77: GG-stopp.

GG förbjuder från 15 okt 2026 all tredjepartsmjukvara för poker som körs samtidigt som klienten, och klienten
varnar från 1 dec 2026. Att bara dölja sidor räcker inte om programmet körs i bakgrunden. Därför:

* programmet (webbservern och nattkörningen) vägrar starta när GG-klienten körs;
* en vakt kontrollerar var 5:e sekund och avslutar hela processen direkt om GG startar.
  Nattberäkningen sparar per omgång, så inget arbete går förlorat utöver den pågående omgången.

Utvecklingsläget (2.87): högst 24 h per påslag och aldrig från 2026-12-01 (dev_mode_active).

"okänd" (processlistan gick inte att läsa) stoppar inte programmet – då skulle det aldrig gå att starta på en dator
där processlistan inte kan läsas – men solverdata visas inte (se solvergrinden i web.py).
"""
from __future__ import annotations

import os
import sys
import threading
import time

INTERVAL = 5.0
# 2.87.1 (Andreas 2026-11-22): körs GG när programmet startas frågar kommandofönstret om du vill starta ändå (j/n).
# Programmet stängs inte heller när GG startas senare. Solverdata (Solver, Träna, Översikt) visas fortfarande aldrig
# medan GG körs – solver_gate i web.py och sidspärren i webbläsaren. Nattkörningen (ingen som kan svara) stoppas som förut.
ASK_ON_START = True
MESSAGE = ("GG-klienten körs. Leakfinder får inte köras samtidigt som GG (GG:s regler från 1 dec 2026). "
           "Stäng GG helt och starta Leakfinder igen. Stäng också PLO Trainer-fliken och andra pokerprogram innan du startar GG.")
STATE = {"started": False, "stopped_by_gg": False, "override": False}


def dev_mode() -> bool:
    """2.79: utvecklingsläge (Andreas 2026-11-18) – programmet får köras när GG är igång. Solverdata visas ändå aldrig
    när GG körs (solver_gate i web.py kräver gg_status() == "nej"). Läses från inställningsfilen bredvid databasen."""
    import json
    from types import SimpleNamespace
    try:
        from .db import default_path
        from .watch import settings_path
        d = json.loads(settings_path(SimpleNamespace(path=default_path())).read_text(encoding="utf-8"))
        return dev_mode_active(d)
    except Exception:
        return False


DEV_HARD_STOP = (2026, 12, 1)   # 2.87 (R7-04): GG förbjuder tredjepartsprogram – utvecklingsläget fungerar aldrig efter detta
DEV_MAX_H = 24                  # 2.87: utvecklingsläget gäller högst ett dygn per påslag


def dev_mode_active(d: dict, now: float | None = None) -> bool:
    """2.87: på bara om inställningen är satt, giltighetstiden (dev_mode_until) inte gått ut och datumet är före
    DEV_HARD_STOP. Gamla inställningsfiler utan giltighetstid räknas som avslagna."""
    import datetime as _dt
    now = time.time() if now is None else now
    if not d.get("dev_mode"):
        return False
    if _dt.date.fromtimestamp(now) >= _dt.date(*DEV_HARD_STOP):
        return False
    try:
        return float(d.get("dev_mode_until", 0)) > now
    except Exception:
        return False


def _status() -> str:
    from .night import gg_status
    return gg_status()


def _interactive() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def refuse_if_gg(status_fn=None, ask_fn=None) -> bool:
    """True om GG körs (då ska anroparen avsluta). Skriver meddelandet."""
    s = (status_fn or _status)()
    if s == "ja" and ASK_ON_START and (ask_fn is not None or _interactive()):
        print("=" * 70)
        print("GG-klienten körs. Från 1 dec 2026 förbjuder GG tredjepartsprogram som körs samtidigt som klienten.")
        print("Solver, Träna och Översikt är dolda så länge GG är igång.")
        try:
            ans = (ask_fn or input)("Starta Leakfinder ändå? Skriv j och tryck Enter (annat = avsluta): ")
        except (EOFError, KeyboardInterrupt):
            ans = ""
        print("=" * 70)
        if str(ans).strip().lower() in ("j", "ja", "y", "yes"):
            STATE["override"] = True
            return False
        return True
    if s == "ja" and dev_mode():
        print("🧪 Utvecklingsläge: GG körs, men Leakfinder startar ändå. Solverdata visas inte medan GG körs.")
        return False
    if s == "ja":
        print("=" * 70)
        print(MESSAGE)
        print("=" * 70)
        return True
    if s == "okänd":   # 2.81: säg till i stället för att tyst starta
        print("⚠ Det gick inte att kontrollera om GG-klienten körs (processlistan kunde inte läsas). Leakfinder startar, "
              "men solverdata visas inte förrän kontrollen fungerar. Stäng GG innan du använder programmet.")
    return False


def start(status_fn=None, exit_fn=None, interval: float = INTERVAL, kill: bool = True) -> threading.Thread | None:
    """Starta vakten (en gång per process). exit_fn anropas när GG upptäcks; standard = avsluta processen direkt."""
    if STATE["started"]:
        return None
    STATE["started"] = True
    fn = status_fn or _status

    def _exit():
        STATE["stopped_by_gg"] = True
        print("\n" + "=" * 70 + "\nGG-klienten startades – Leakfinder stänger sig nu.\n" + "=" * 70, flush=True)
        os._exit(0)

    ex = exit_fn or _exit

    noted = [False]

    def loop():
        while True:
            time.sleep(interval)
            try:
                if fn() == "ja" and not dev_mode():
                    if kill and not STATE["override"]:
                        ex()
                        return
                    if not noted[0]:   # 2.87.1: webbprogrammet fortsätter – solverdelen döljs av solver_gate
                        noted[0] = True
                        print("\nGG-klienten körs – Leakfinder fortsätter. Solver, Träna och Översikt är dolda tills GG är stängt.",
                              flush=True)
                else:
                    noted[0] = False
            except Exception:
                pass

    t = threading.Thread(target=loop, daemon=True, name="gg-vakt")
    t.start()
    return t


def reset_for_tests():
    STATE["started"] = False
    STATE["stopped_by_gg"] = False
    STATE["override"] = False
