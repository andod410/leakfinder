"""Schemalagd nattkörning (2.72): `python -m plo_leak.nightly`

Körs av Schemaläggaren (Windows) eller launchd (Mac) varje natt. I tur och ordning:
1. GG-vakt: kör inte om GG-klienten är igång eller ny handhistorik kommit de senaste 10 minuterna (kollas igen
   under körningen; nattberäkningen pausar då).
2. Säkerhetskopia av databasen (SQLite online-backup, de BACKUP_KEEP senaste sparas).
3. Läser in nya händer från den bevakade mappen och räknar fakta för dem.
4. Nattberäkning v2 (fortsätter där den slutade) till tidsgränsen.
5. Körningskvitto (JSON: version, tider, databasens fingeravtryck, vad som gjordes) och en kort morgonrapport (markdown,
   några kB) att läsa eller ladda upp till Claude i stället för en stor djupexport.

Programmet ger aldrig råd medan du spelar – allt här körs när GG är stängt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__

BACKUP_KEEP = 3
TASK_NAME = "Leakfinder nattkorning"
PLIST_ID = "se.leakfinder.natt"
DEFAULT_TIME = "03:30"
DEFAULT_STOP = "07:00"


class _Job:
    """Samma gränssnitt som jobs.Job (job.set) – skriver förloppet till loggen."""

    def __init__(self, log):
        self.log, self.stage = log, ""

    def set(self, stage, done=0, total=0):
        if stage != self.stage:
            self.stage = stage
            self.log(stage)


def cache_dir(db) -> Path:
    return db.path.parent


def receipts_dir(db) -> Path:
    d = cache_dir(db) / "nattkvitton"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reports_dir(db) -> Path:
    from . import watch
    cfg = watch.load_settings(db)
    d = Path(cfg.get("export_dir") or (cache_dir(db) / "morgonrapporter")).expanduser()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = cache_dir(db) / "morgonrapporter"
        d.mkdir(parents=True, exist_ok=True)
    return d


def fingerprint(db) -> dict:
    """Databasens fingeravtryck: antal händer, senaste hand och en hash över dem (inte hela filen – den är stor)."""
    n, last = db.con.execute("SELECT COUNT(*), MAX(date) FROM hands").fetchone()
    top = db.con.execute("SELECT id FROM hands ORDER BY date DESC, id DESC LIMIT 1000").fetchall()
    h = hashlib.sha1(f"{n}|{last}|{','.join(r[0] for r in top)}".encode()).hexdigest()[:16]
    try:
        size = db.path.stat().st_size
    except OSError:
        size = None
    return {"hands": int(n), "last": last, "hash": h, "bytes": size}


def backup(db, keep: int = BACKUP_KEEP) -> str:
    d = cache_dir(db) / "plo_leak_backup"
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"plo_leak_{datetime.now():%Y%m%d}.db"
    tmp = target.with_suffix(".tmp")
    dst = sqlite3.connect(str(tmp))
    try:
        db.con.commit()
        db.con.backup(dst)
    finally:
        dst.close()
    os.replace(tmp, target)
    # 2.87 (R8-01): inställningsfilen (rakeback-logg, regler för bevakning m.m.) följer med i backupen
    try:
        from .watch import settings_path
        sp = settings_path(db)
        if sp.is_file():
            (d / f"plo_leak_{datetime.now():%Y%m%d}_installningar.json").write_bytes(sp.read_bytes())
    except Exception:
        pass
    old = sorted(d.glob("plo_leak_*.db"))[:-keep]
    for p in old:
        try:
            p.unlink()
        except OSError:
            pass
    for p in sorted(d.glob("plo_leak_*_installningar.json"))[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass
    return str(target)


def _main_st(db, hero):
    """Statistiken för den variant du spelat mest (alla händer)."""
    import numpy as np
    from .aggregate import build_stats
    from .selection import Selection
    store = db.facts(hero)
    store.sync(db)
    ft = store.load()
    sel = Selection()
    mask = sel.mask(ft)
    return build_stats(ft, mask, hero, db.get_hand), ft


def ts_map(ft, rows=None) -> dict:
    """{hand_id: (ts, ai_eq, all-in på flop/turn)} – används för att låsa λ i nattberäkning v2 (rows = huvudvarianten)."""
    H = ft.H
    ai = H["ai_st"]
    idx = range(ft.n) if rows is None else (int(j) for j in rows)
    return {str(H["id"][j]): (int(H["ts"][j]), float(H["ai_eq"][j]), bool(ai[j] in (1, 2))) for j in idx}


def _hash_changed(db, key: str, value):
    """Sparar fingeravtrycket första gången; returnerar det gamla värdet om det har ändrats, annars None."""
    if not value:
        return None
    p = cache_dir(db) / "fingeravtryck.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        doc = {}
    old = doc.get(key)
    if old != value:
        doc[key] = value
        doc[key + "_sedan"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return old if old and old != value else None


def _ok(p) -> str:
    return "klarar" if p.get("ok") else ("klarar inte" if p.get("ok") is False else "inte avgjort")


def morning_report(db, st, hero, accept: dict | None, night_msg: str, receipt: dict) -> str:
    """Kort morgonrapport (markdown) – topp-läget, framåttesterna och gårdagens pass."""
    from .forward import FREEZE_DATE
    from .guidelines import PRIO
    from .riverbluff import bluff_test
    from .sessions import session_table
    from .sessionfile import _usd
    lines = [f"# Morgonrapport {datetime.now():%Y-%m-%d} – PLO-läckfinnaren {__version__}", "",
             "Till Claude: kort läge efter natten. Mål: maximera timlönen. Kommentera bara det viktigaste (högst 2 punkter).", ""]
    T = session_table(st, None) or {}
    S = (T.get("sessions") or [])[:3]
    if S:
        lines += ["## Senaste passen", "| Start | Längd | Händer | Resultat | All-in EV | Vila |", "|---|---|---|---|---|---|"]
        for s in S:
            lines.append(f"| {s['start']} | {s['minutes']} min | {s['hands']} | {_usd(s['money'])} | {_usd(s['ev_money'])} | "
                         f"{' '.join(s.get('rest_tags') or []) or '–'} · {s.get('gap_txt', '')} |")
        lines.append("")
    from .riverbluff import bluff_test_v2
    B = bluff_test_v2(st) or {}
    if B and B.get("spots"):
        lines += ["## 🎲 River-bluff-testet v2", f"- {B['verdict']}",
                  f"- Lägen S1 {B['spots']} (bet-arm {B.get('arm_bet', 0)}, check-arm {B.get('arm_check', 0)}) · följsamhet {B.get('comply', 0):.0f} % · S2 {B.get('s2_spots', 0)}", ""]
    try:
        from .forward import forward_test, frozen_rules
        variant = max(st.games.items(), key=lambda kv: kv[1])[0].replace("-", "") if st.games else None
        fz = frozen_rules(st, hero, cache_dir(db) / (db.path.stem + "_resultat"), variant)
        F = forward_test(st, fz) if fz else None
    except Exception:
        F = None
    if F:
        receipt["frozen_rules_hash"] = F.get("hash")
        chg = _hash_changed(db, "regler", F.get("hash"))
        lines += [f"## 🔒 Framåttest (regler frysta {FREEZE_DATE}, {F['hands_after']} händer efter)",
                  f"Fingeravtryck av de frysta reglerna: `{F.get('hash')}` (ska vara samma på alla dina datorer och i projektet)."
                  + (f" ⚠ ÄNDRAT sedan förra körningen (var `{chg}`) – de frysta reglerna har skapats om; framåttestet gäller den nya definitionen." if chg else ""), "",
                  "| Regel | Brott | Pass | Mot fold | Utfall |", "|---|---|---|---|---|"]
        for r in F["rules"]:
            m = f"{r['mean']:+.2f} ± {r['se']:.2f}" if r.get("mean") is not None and r.get("se") is not None else "–"
            lines.append(f"| {r['title']} | {r['n']} | {r['clusters']} | {m} | {r['verdict']} |")
        lines.append("")
    try:
        from .pfforward import SPECS_FROZEN_HASH, specs_hash
        ph = specs_hash()
        receipt["postflop_specs_hash"] = ph
        lines += [f"Postflop-riktlinjernas definition: `{ph}`" + ("" if ph == SPECS_FROZEN_HASH else
                  f" ⚠ skiljer sig från den låsta (`{SPECS_FROZEN_HASH}`) – tidigare händer är inte ett oberoende test."), ""]
    except Exception:
        pass
    if accept:
        P = accept.get("parts", {})
        c, f, t = P.get("kalibrering", {}), P.get("fold", {}), P.get("tur", {})
        lines += ["## 🌙 Nattberäkning v2 (hypotes)", f"- {accept.get('text', '')}",
                  f"- Plan {accept.get('plan', '–')}: avläsning vid {', '.join(str(k) for k in accept.get('checkpoints', []))} pass efter "
                  f"frysdatum; nu {accept.get('passes', 0)} pass. λ = {accept.get('lam')}."]
        if accept.get("checkpoint"):
            lines += [f"- Kalibrering: {c.get('n', 0)} all-ins" + (f", MSE v1 {c['mse_v1']:.4f} → v2 {c['mse_v2']:.4f}, avvikelse {100 * c['bias']:+.1f} ± {100 * 1.96 * c['bias_se']:.1f} pe (krav inom ±5)" if c.get("mse_v2") is not None else "") + f" → {_ok(c)}",
                      f"- Fold-prognos: {f.get('n', 0)} river-bets" + (f", Brier {f['brier_v1']:.3f} → {f['brier_v2']:.3f}, avvikelse {100 * f['bias']:+.1f} pe (krav inom ±10)" if f.get("brier_v2") is not None else "") + f" → {_ok(f)}",
                      f"- Tur: {t.get('n', 0)} händer" + (f", medel {t['mean']:+.3f} ± {1.96 * t['se']:.3f} bb/hand (krav inom ±0,05), varians {100 * t.get('var_gain', 0):.0f} % lägre (krav 20 %)" if t.get("mean") is not None else "") + f" → {_ok(t)}"]
        lines.append("")
    lines += ["## Natten", f"- {night_msg}", f"- Databas: {receipt['db_after']['hands']} händer (hash {receipt['db_after']['hash']})",
              f"- Säkerhetskopia: {receipt.get('backup') or '–'}", "",
              "## Prio-listan"] + [f"{i}. {t}" for i, (_ic, t, _d) in enumerate(PRIO, 1)]
    from .positions import to_ui
    return to_ui("\n".join(lines) + "\n")  # 2.74: HJ visas som UTG


def run_night(deadline: datetime | None = None, procs: int | None = None, log=print, db=None, prep_lock=None) -> dict:
    """prep_lock (2.75): lås som hålls under backup, inläsning och fakta – de steg som skriver i samma filer
    som analyserna. Själva beräkningen körs utan låset, så analys och export kan köras samtidigt."""
    import contextlib
    prep = prep_lock if prep_lock is not None else contextlib.nullcontext()
    from .db import HandDB
    from . import night2
    from .night import blocked
    t0 = datetime.now()
    db = db or HandDB()
    receipt = {"version": __version__, "start": t0.isoformat(timespec="seconds"), "steps": [], "db_before": fingerprint(db),
               "range_id": night2.RANGE_ID, "seed": "crc32(hand_id) per hand (deterministiskt)"}
    why = blocked(db)
    if why:
        receipt.update(status="hoppade över", reason=why, end=datetime.now().isoformat(timespec="seconds"))
        _save_receipt(db, receipt)
        log("Nattkörningen hoppade över: " + why)
        return receipt
    with prep:
        try:
            receipt["backup"] = backup(db)
            receipt["steps"].append("backup")
        except Exception as e:
            receipt["backup_error"] = str(e)
        try:
            import threading
            from . import watch
            r = watch.scan(db, threading.Lock()) or {}
            receipt["new_hands"] = int(r.get("hands_new", 0))
            receipt["steps"].append("inläsning")
        except Exception as e:
            receipt["scan_error"] = str(e)
        hero = db.detect_hero() or "Hero"
        st, ft = _main_st(db, hero)
        receipt["steps"].append("fakta")
    job = _Job(log)
    dl = deadline.timestamp() if deadline else None
    msg = night2.run(job, db, procs, deadline=dl, ts_of=ts_map(ft, st.rows))
    receipt["night2"] = msg
    receipt["steps"].append("nattberäkning v2")
    try:
        acc = night2.acceptance(db, st, hero)
        night2.meta_set(db.con, "acceptance", {**acc, "date": datetime.now().isoformat(timespec="seconds")})
    except Exception as e:
        acc = {"text": f"acceptanstestet kunde inte köras: {e}", "parts": {}}
    receipt["acceptance"] = acc.get("status")
    try:  # 2.77.6: skuggmodell v3 (förregistrerad, ger inga råd)
        from . import night3
        tab = night3.solver_tab(db)
        receipt["night3"] = night3.run(job, db, st, hero, db.get_hand, tab, deadline=dl, procs=procs)
        acc3 = night3.acceptance(db, night3.v2_river_eq(db))
        receipt["night3_status"] = acc3.get("status")
        receipt["steps"].append("skuggmodell v3")
    except Exception as e:
        receipt["night3"] = f"v3 kunde inte köras: {type(e).__name__}: {e}"
    receipt["db_after"] = fingerprint(db)
    receipt["end"] = datetime.now().isoformat(timespec="seconds")
    receipt["status"] = "klar"
    try:
        text = morning_report(db, st, hero, acc, msg, receipt)
        p = reports_dir(db) / f"morgonrapport_{datetime.now():%Y%m%d}.md"
        p.write_text(text, encoding="utf-8")
        receipt["report"] = str(p)
    except Exception as e:
        receipt["report_error"] = str(e)
    _save_receipt(db, receipt)
    log(f"Klar: {msg}")
    return receipt


def _save_receipt(db, receipt):
    p = receipts_dir(db) / f"kvitto_{datetime.now():%Y%m%d_%H%M%S}.json"
    p.write_text(json.dumps(receipt, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    old = sorted(receipts_dir(db).glob("kvitto_*.json"))[:-30]
    for q in old:
        try:
            q.unlink()
        except OSError:
            pass


def last_receipt(db) -> dict | None:
    try:
        files = sorted(receipts_dir(db).glob("kvitto_*.json"))
        return json.loads(files[-1].read_text(encoding="utf-8")) if files else None
    except Exception:
        return None


# ---------------------------------------------------------------- schemaläggning
def program_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _hhmm(s: str) -> tuple:
    h, m = (int(x) for x in s.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(s)
    return h, m


def install_schedule(at: str = DEFAULT_TIME, stop: str = DEFAULT_STOP) -> str:
    h, m = _hhmm(at)
    _hhmm(stop)
    py = sys.executable
    pdir = program_dir()
    if sys.platform == "win32":
        bat = pdir / "nattkorning.bat"
        # 2.87 (R8-03): UTF-8 för utdata – emoji i loggen kraschade nattkörningen när utdata gick till fil (cp1252)
        bat.write_text(f'@echo off\r\nchcp 65001 >nul\r\nset PYTHONIOENCODING=utf-8\r\nset PYTHONUTF8=1\r\ncd /d "%~dp0"\r\n'
                       f'"{py}" -m plo_leak.nightly --stop {stop} >> nattkorning.log 2>&1\r\n',
                       encoding="utf-8")
        r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", f"{h:02d}:{m:02d}", "/TN", TASK_NAME,
                            "/TR", f'"{bat}"'], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            return "Kunde inte schemalägga: " + (r.stderr or r.stdout).strip()
        return f"Schemalagd varje natt kl. {h:02d}:{m:02d} (Schemaläggaren: \"{TASK_NAME}\")."
    if sys.platform == "darwin":
        agents = Path.home() / "Library" / "LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        plist = agents / f"{PLIST_ID}.plist"
        log = pdir / "nattkorning.log"
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{PLIST_ID}</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>-m</string><string>plo_leak.nightly</string><string>--stop</string><string>{stop}</string></array>
  <key>WorkingDirectory</key><string>{pdir}</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>
  <key>StandardOutPath</key><string>{log}</string><key>StandardErrorPath</key><string>{log}</string>
  <key>LowPriorityIO</key><true/><key>Nice</key><integer>10</integer>
</dict></plist>
""", encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        r = subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True, text=True)
        if r.returncode:
            return "Kunde inte schemalägga: " + (r.stderr or r.stdout).strip()
        return f"Schemalagd varje natt kl. {h:02d}:{m:02d} (launchd: {PLIST_ID}). Sover datorn körs den när den vaknar."
    return "Schemaläggning stöds bara på Windows och Mac."


def remove_schedule() -> str:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Schemat är borttaget." if not r.returncode else "Inget schema fanns."
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_ID}.plist"
        if plist.exists():
            subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True)
            plist.unlink()
            return "Schemat är borttaget."
        return "Inget schema fanns."
    return "Schemaläggning stöds bara på Windows och Mac."


def schedule_status() -> dict:
    try:
        if sys.platform == "win32":
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"], capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"supported": True, "on": r.returncode == 0, "text": r.stdout.strip()[:400]}
        if sys.platform == "darwin":
            plist = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_ID}.plist"
            txt = plist.read_text(encoding="utf-8") if plist.exists() else ""
            same = str(program_dir()) in txt
            return {"supported": True, "on": plist.exists(), "this_version": same,
                    "text": "" if same or not txt else "Schemat pekar på en annan version – schemalägg igen från den här."}
    except Exception as e:
        return {"supported": True, "on": False, "text": str(e)}
    return {"supported": False, "on": False, "text": ""}


def _utf8_streams():
    """2.87 (R8-03): skriv aldrig ut med en kodsida som inte klarar emoji (Windows + omdirigerad utdata)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    _utf8_streams()
    ap = argparse.ArgumentParser(prog="plo_leak.nightly", description="Nattkörning: backup, inläsning, nattberäkning v2, morgonrapport.")
    ap.add_argument("--stop", default=DEFAULT_STOP, help="Sluta senast denna tid (HH:MM), standard 07:00")
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--schemalagg", default=None, metavar="HH:MM", help="Schemalägg varje natt vid denna tid")
    ap.add_argument("--ta-bort-schema", action="store_true")
    a = ap.parse_args(argv)
    if a.schemalagg:
        print(install_schedule(a.schemalagg, a.stop))
        return 0
    if a.ta_bort_schema:
        print(remove_schedule())
        return 0
    from . import ggguard
    if ggguard.refuse_if_gg():
        return 0
    ggguard.start()
    h, m = _hhmm(a.stop)
    now = datetime.now()
    stop = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if stop <= now:
        stop += timedelta(days=1)
    log = lambda s: print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {s}", flush=True)  # noqa: E731
    run_night(stop, a.procs, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
