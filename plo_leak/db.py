"""Egen handdatabas (SQLite).

Varje hand sparas en gång, med handnumret som nyckel. Nästa gång läser programmet
bara in händer som inte redan finns, så du kan exportera bara nya händer – eller hela
databasen igen – utan att allt behöver räknas om.

Databasen sparar också resultat av tunga beräkningar per hand (all-in EV och handstyrka
på flop/turn/river). De beror bara på handen och räknas därför bara en gång.

Plats: ~/.plo_leak_cache/plo_leak.db (kan ändras med miljövariabeln PLO_LEAK_DB).
Filen kan raderas när som helst – då byggs den upp igen vid nästa körning.
"""
from __future__ import annotations

import os
import pickle
import re
import sqlite3
import threading
import zlib
from datetime import datetime
from pathlib import Path

from .parser import (PARSER_VERSION, _decode, find_files, looks_like_hh, parse_hand, split_hands)

CALC_VERSION = 5  # 5 = 2.87 rättad all-in EV · höj när en sparad beräkning ändras
RE_ID = re.compile(r"Hand #([^\s:]+)")


def default_path() -> Path:
    p = os.environ.get("PLO_LEAK_DB")
    if p:
        return Path(p).expanduser()
    return Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache")) / "plo_leak.db"


def quick_info(path=None) -> dict:
    """Antal händer, period och gamla händer – med en egen kort anslutning, så startsidan kan
    visas medan ett jobb skriver till databasen."""
    p = Path(path) if path else default_path()
    if not p.exists():
        return {"n": 0, "first": None, "last": None, "stale": 0, "path": p}
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(hands)")}
        n, a, b = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM hands WHERE pv=?", (PARSER_VERSION,)).fetchone()
        stale = (con.execute("SELECT COUNT(*) FROM hands WHERE pv<>? AND raw IS NULL", (PARSER_VERSION,)).fetchone()[0]
                 if "raw" in cols else con.execute("SELECT COUNT(*) FROM hands WHERE pv<>?", (PARSER_VERSION,)).fetchone()[0])
    except sqlite3.Error:
        n, a, b, stale = 0, None, None, 0
    finally:
        con.close()
    return {"n": n, "first": a, "last": b, "stale": stale, "path": p}


def _parse_batch(chunks):
    """Parsar en sats händer (körs i en egen process vid stora inläsningar)."""
    rows, n_other, n_bad, bad_ex, newest = [], 0, 0, [], None
    for chunk in chunks:
        try:
            h = parse_hand(chunk)
        except Exception:
            h = None
        if not h:
            head = chunk.strip().splitlines()[0] if chunk.strip() else ""
            if "Omaha" not in head and "PLO" not in head:
                n_other += 1
                continue
            n_bad += 1
            if len(bad_ex) < 3:
                bad_ex.append(head[:120])
            continue
        d = h.date.isoformat()
        if newest is None or d > newest:
            newest = d
        h.raw = ""  # originaltexten sparas en gång, i egen kolumn (get_hand lägger tillbaka den)
        rows.append((h.id, d, f"PLO-{h.num_hole}", PARSER_VERSION,
                     zlib.compress(pickle.dumps(h, protocol=pickle.HIGHEST_PROTOCOL), 1),
                     zlib.compress(chunk.encode("utf-8"), 6)))
    return rows, n_other, n_bad, bad_ex, newest


def hand_from_row(r):
    """2.79: (blob, raw) -> Hand, exakt som HandDB.get_hand (används också av arbetsprocesser)."""
    if not r:
        return None
    h = pickle.loads(zlib.decompress(r[0]))
    if not h.raw and r[1]:
        h.raw = zlib.decompress(r[1]).decode("utf-8")
    from .parser import fix_dead_sb_positions
    fix_dead_sb_positions(h)  # samma positioner som i analysen
    return h


class HandDB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)  # 2.75: nattkön skriver samtidigt
        self._tl = threading.local()  # en läsanslutning per tråd för enstaka händer (webbsidornas uppspelning)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.executescript("""
            CREATE TABLE IF NOT EXISTS hands (
                id TEXT PRIMARY KEY, date TEXT, game TEXT, pv INTEGER, blob BLOB);
            CREATE INDEX IF NOT EXISTS hands_date ON hands(date);
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, pv INTEGER);
            CREATE TABLE IF NOT EXISTS calc (
                key TEXT PRIMARY KEY, v TEXT, value BLOB);
        """)
        self.con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        r = self.con.execute("SELECT v FROM meta WHERE k='uid'").fetchone()
        if r is None:
            import uuid
            self.uid = uuid.uuid4().hex
            self.con.execute("INSERT INTO meta VALUES ('uid', ?)", (self.uid,))
            self.con.commit()
        else:
            self.uid = r[0]
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(hands)")}
        if "raw" not in cols:  # äldre databaser saknar originaltexten
            self.con.execute("ALTER TABLE hands ADD COLUMN raw BLOB")
            self.con.commit()
        # 2.79: index så att antal, period, gamla händer och listan över handnummer kan läsas utan att
        # gå igenom hela tabellen (med alla sparade händer). Skapas en gång (några sekunder i en stor databas).
        self.con.execute("CREATE INDEX IF NOT EXISTS hands_pv ON hands(pv, date, id)")
        self.con.execute("CREATE INDEX IF NOT EXISTS hands_noraw ON hands(pv) WHERE raw IS NULL")
        self.con.commit()
        self.upgraded = self._upgrade_old()
        self.repaired_incomplete = self._repair_incomplete()
        self._calc: dict | None = None
        self._calc_new: dict = {}

    def _repair_incomplete(self) -> int:
        """2.80 (en gång per databas): händer som sparats från en ofärdig text (ingen SUMMARY-rad) tas bort, och
        fillistan töms så att de läses in igen – komplett – vid nästa inläsning/bevakning."""
        try:
            if self.con.execute("SELECT v FROM meta WHERE k='incomplete_v1'").fetchone():
                return 0
            bad = []
            for hid, raw in self.con.execute("SELECT id, raw FROM hands WHERE raw IS NOT NULL"):
                try:
                    if b"*** SUMMARY ***" not in zlib.decompress(raw):
                        bad.append((hid,))
                except Exception:
                    continue
            if bad:
                self.con.executemany("DELETE FROM hands WHERE id=?", bad)
                self.con.execute("DELETE FROM files")
            self.con.execute("INSERT OR REPLACE INTO meta VALUES ('incomplete_v1', ?)", (str(len(bad)),))
            self.con.commit()
            return len(bad)
        except Exception:
            return 0

    # ------------------------------------------------------------------ händer
    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM hands WHERE pv=?", (PARSER_VERSION,)).fetchone()[0]

    def span(self):
        r = self.con.execute("SELECT MIN(date), MAX(date) FROM hands WHERE pv=?", (PARSER_VERSION,)).fetchone()
        return r if r and r[0] else (None, None)

    def stale_count(self) -> int:
        """Händer sparade av en äldre programversion som inte kan läsas om automatiskt
        (originaltexten sparades inte då). De syns inte i analysen förrän filerna läses in igen."""
        return self.con.execute("SELECT COUNT(*) FROM hands WHERE pv<>? AND raw IS NULL",
                                (PARSER_VERSION,)).fetchone()[0]

    def _upgrade_old(self) -> int:
        """Läs om händer som sparats av en äldre version men där originaltexten finns."""
        # pv<? och pv>? var för sig (i stället för pv<>?) så att indexet används – annars läses hela tabellen vid varje start
        rows = self.con.execute("SELECT id, raw FROM hands WHERE pv<? AND raw IS NOT NULL UNION ALL "
                                "SELECT id, raw FROM hands WHERE pv>? AND raw IS NOT NULL",
                                (PARSER_VERSION, PARSER_VERSION)).fetchall()
        n = 0
        for hid, raw in rows:
            try:
                h = parse_hand(zlib.decompress(raw).decode("utf-8"))
            except Exception:
                h = None
            if h:
                h.raw = ""
                self.con.execute("UPDATE hands SET date=?, game=?, pv=?, blob=? WHERE id=?",
                                 (h.date.isoformat(), f"PLO-{h.num_hole}", PARSER_VERSION,
                                  zlib.compress(pickle.dumps(h, protocol=pickle.HIGHEST_PROTOCOL), 1), hid))
                n += 1
        if rows:
            self.con.commit()
        return n

    def count_between(self, date_from=None, date_to=None) -> int:
        q, args = "SELECT COUNT(*) FROM hands WHERE pv=?", [PARSER_VERSION]
        if date_from:
            q += " AND date >= ?"; args.append(date_from)
        if date_to:
            q += " AND date < ?"; args.append(_next_day(date_to))
        return self.con.execute(q, args).fetchone()[0]

    def _known_ids(self) -> set:
        return {r[0] for r in self.con.execute("SELECT id FROM hands WHERE pv=?", (PARSER_VERSION,))}

    def missing_raw_count(self) -> int:
        """Händer i analysen som saknar originaltext (inlästa av en äldre version). De exporteras
        ändå (återskapade), men läser du in filerna igen får de tillbaka sin exakta originaltext."""
        return self.con.execute("SELECT COUNT(*) FROM hands WHERE pv=? AND raw IS NULL",
                                (PARSER_VERSION,)).fetchone()[0]

    def add_paths(self, paths, progress=None, workers: int | None = None, require_player: str | None = None,
                  fill_raw: bool = False) -> dict:
        """Läs in filer/mappar. Bara händer som inte redan finns parsas och sparas.
        Filer som inte ändrats sedan förra gången hoppas över helt. Stora inläsningar parsas
        parallellt i flera processer. progress(klart_MB, totalt_MB, nya_händer)."""
        from . import parser as _parser
        del _parser.ZIP_REJECTED[:]
        files = find_files(paths)
        known = self._known_ids()
        # kända händer utan originaltext får den från filerna (då läses även oförändrade filer igen)
        need_raw = {r[0] for r in self.con.execute("SELECT id FROM hands WHERE pv=? AND raw IS NULL",
                                                   (PARSER_VERSION,))} if fill_raw else set()
        raw_upd: list = []
        # 2.80: en fil som lästs med spelarfilter räknas som läst bara för filtrerad läsning (pv = −PV)
        pvs = (PARSER_VERSION, -PARSER_VERSION) if require_player else (PARSER_VERSION,)
        seen_files = {r[0]: (r[1], r[2]) for r in self.con.execute(
            f"SELECT path, size, mtime FROM files WHERE pv IN ({','.join('?' * len(pvs))})", pvs)} \
            if not self.stale_count() and not need_raw else {}
        stats = {"files": len(files), "files_skipped": 0, "hands_seen": 0, "hands_new": 0,
                 "hands_known": 0, "hands_unreadable": 0, "hands_other_games": 0, "unreadable_examples": [], "newest": None}
        todo, file_rows = [], []
        for f in files:
            try:
                st = f.stat()
                key = str(f.resolve())
            except OSError:
                continue
            if seen_files.get(key) == (st.st_size, st.st_mtime_ns):
                stats["files_skipped"] += 1
                continue
            todo.append((f, st.st_size, key))
            file_rows.append((key, st.st_size, st.st_mtime_ns, PARSER_VERSION))
        total_mb = max(1, int(sum(sz for _, sz, _k in todo) / 1e6))
        partial: dict = {}   # 2.80: fil -> "filter" (bara dina händer lästes) eller "ofullständig" (läses om nästa gång)
        done_bytes = [0]

        def batches():
            """Nya, oparsade händer i satser om 3 000 (dubbletter och kända händer hoppas över)."""
            cur = []
            for f, size, fkey in todo:
                try:
                    texts = list(self._texts(f)) if f.suffix.lower() != ".zip" else self._texts(f)
                except (OSError, ValueError):
                    texts = []  # filen försvann eller gick inte att läsa – hoppas över
                    stats["files_failed"] = stats.get("files_failed", 0) + 1
                for text in texts:
                    for chunk in split_hands(text):
                        m = RE_ID.search(chunk[:200])
                        if not m:
                            continue
                        stats["hands_seen"] += 1
                        if "*** SUMMARY ***" not in chunk:
                            # 2.80: handen är inte färdigskriven (avbruten nedladdning eller fil som skrivs) – sparas
                            # inte, och filen läses om nästa gång i stället för att låsa ett felaktigt resultat
                            stats["hands_incomplete"] = stats.get("hands_incomplete", 0) + 1
                            partial[fkey] = "ofullständig"
                            continue
                        if require_player and f"Dealt to {require_player} [" not in chunk:
                            stats["hands_other_player"] = stats.get("hands_other_player", 0) + 1
                            partial.setdefault(fkey, "filter")
                            continue  # bevakad mapp: bara händer där du själv fick kort
                        hid = m.group(1)
                        if hid in known:
                            stats["hands_known"] += 1
                            if hid in need_raw:
                                need_raw.discard(hid)
                                raw_upd.append((zlib.compress(chunk.encode("utf-8"), 6), hid))
                                if len(raw_upd) >= 5000:
                                    self._fill_raw(raw_upd)
                            continue
                        known.add(hid)
                        cur.append(chunk)
                        if len(cur) >= 3000:
                            yield cur
                            cur = []
                done_bytes[0] += size
            if cur:
                yield cur

        workers = workers if workers is not None else max(1, min(16, os.cpu_count() or 1))
        parallel = workers > 1 and total_mb >= 20
        rows = []
        pool = None

        def handle(res):
            new_rows, n_other, n_bad, bad_ex, newest = res
            stats["hands_other_games"] += n_other
            stats["hands_unreadable"] += n_bad
            for e in bad_ex:
                if len(stats["unreadable_examples"]) < 3:
                    stats["unreadable_examples"].append(e)
            if newest and (stats["newest"] is None or newest > stats["newest"]):
                stats["newest"] = newest
            stats["hands_new"] += len(new_rows)
            rows.extend(new_rows)
            if len(rows) >= 6000:
                self._flush(rows)
            if progress:
                progress(min(int(done_bytes[0] / 1e6), total_mb), total_mb, stats["hands_new"])

        try:
            if parallel:
                import multiprocessing as mp
                from collections import deque
                pool = mp.get_context("spawn").Pool(workers)
                pending = deque()
                for b in batches():  # högst 2 satser per process i kö – begränsar minnet
                    pending.append(pool.apply_async(_parse_batch, (b,)))
                    while len(pending) > 2 * workers:
                        handle(pending.popleft().get())
                while pending:
                    handle(pending.popleft().get())
            else:
                for b in batches():
                    handle(_parse_batch(b))
        finally:
            if pool is not None:
                pool.close()
                pool.join()
        self._flush(rows)
        self._fill_raw(raw_upd)
        stats["raw_filled"] = self._raw_filled
        self._raw_filled = 0
        rejected_zips = {r[0] for r in _parser.ZIP_REJECTED}
        rows_f = []
        for key, sz, mt, pv in file_rows:
            why = partial.get(key)
            if why == "ofullständig" or key in rejected_zips or Path(key).name in {Path(z).name for z in rejected_zips}:
                continue   # läses om nästa gång (avvisat innehåll eller ofärdig hand)
            rows_f.append((key, sz, mt, -pv if why == "filter" else pv))
        self.con.executemany("INSERT OR REPLACE INTO files VALUES (?,?,?,?)", rows_f)
        self.con.commit()
        if progress:
            progress(total_mb, total_mb, stats["hands_new"])
        stats["rejected"] = [list(r) for r in _parser.ZIP_REJECTED]
        return stats

    @staticmethod
    def _texts(f: Path):
        """Texten i en fil. Zip-filer (även zip i zip) packas upp i minnet, fil för fil – inget
        behöver packas upp på disken, och originalfilen lämnas orörd."""
        import io
        import zipfile
        from .parser import ZIP_ERRORS, ZIP_MAX_DEPTH, zip_member_texts, zip_members
        if f.suffix.lower() == ".zip":
            budget = {"total": 0}   # 2.81: en gemensam budget för hela arkivet, alla nivåer

            def walk(src, depth=0):
                try:
                    with zipfile.ZipFile(src) as zf:
                        for info in zip_members(zf, budget):
                            if info.filename.lower().endswith(".zip"):
                                if depth < ZIP_MAX_DEPTH:
                                    yield from walk(io.BytesIO(zf.read(info)), depth + 1)
                                continue
                            yield from zip_member_texts(zf, info)
                except ZIP_ERRORS:
                    return  # trasig, krypterad eller ofullständig zip hoppas över
            yield from walk(f)
        else:
            yield _decode(f.read_bytes())

    _raw_filled = 0

    def _fill_raw(self, batch):
        if batch:
            cur = self.con.executemany("UPDATE hands SET raw=? WHERE id=? AND raw IS NULL", batch)
            self._raw_filled += max(cur.rowcount, 0)
            batch.clear()

    def _flush(self, batch):
        if batch:
            self.con.executemany("INSERT OR REPLACE INTO hands (id, date, game, pv, blob, raw) VALUES (?,?,?,?,?,?)", batch)
            batch.clear()

    def load(self, date_from: str | None = None, date_to: str | None = None, progress=None) -> list:
        """Alla händer i databasen (valfritt mellan två datum, ÅÅÅÅ-MM-DD), sorterade i tidsordning."""
        q = "SELECT blob, raw FROM hands WHERE pv=?"
        args: list = [PARSER_VERSION]
        if date_from:
            q += " AND date >= ?"
            args.append(date_from)
        if date_to:
            q += " AND date < ?"
            args.append(_next_day(date_to))
        q += " ORDER BY date, id"
        out = []
        for i, (b, raw) in enumerate(self.con.execute(q, args), 1):
            h = pickle.loads(zlib.decompress(b))
            if not h.raw and raw:
                h.raw = zlib.decompress(raw).decode("utf-8")
            from .parser import fix_dead_sb_positions
            fix_dead_sb_positions(h)
            out.append(h)
            if progress and i % 5000 == 0:
                progress(i)
        return out

    def get_hand(self, hid):
        """En enskild hand (för uppspelning och exempel)."""
        con = getattr(self._tl, "con", None)
        if con is None:
            con = self._tl.con = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        return hand_from_row(con.execute("SELECT blob, raw FROM hands WHERE id=?", (hid,)).fetchone())

    def detect_hero(self, sample: int = 3000) -> str | None:
        """Vanligaste spelarnamnet bland de senaste händerna."""
        from collections import Counter
        c = Counter()
        for (b,) in self.con.execute("SELECT blob FROM hands WHERE pv=? ORDER BY date DESC LIMIT ?",
                                     (PARSER_VERSION, sample)):
            h = pickle.loads(zlib.decompress(b))
            c.update(name for name, cards in h.hole.items() if cards)
        return c.most_common(1)[0][0] if c else None

    def facts(self, hero: str):
        from .facts import FactStore
        return FactStore(self.path.parent / (self.path.stem + "_fakta"), hero, self.uid)

    def store_calc(self, entries: dict) -> None:
        """Spara beräkningar (all-in EV, handstyrka …) som räknats i arbetsprocesser."""
        v = self._calc_version()
        self.con.executemany("INSERT OR REPLACE INTO calc VALUES (?,?,?)",
                             [(k, v, pickle.dumps(val, protocol=pickle.HIGHEST_PROTOCOL)) for k, val in entries.items()])
        self.con.commit()
        if self._calc is not None:
            self._calc.update(entries)


    def clear(self) -> None:
        import shutil
        for suffix in ("_fakta", "_resultat"):
            d = self.path.parent / (self.path.stem + suffix)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        import uuid
        self.con.executescript("DELETE FROM hands; DELETE FROM files; DELETE FROM calc;")
        self.uid = uuid.uuid4().hex  # ny identitet: gamla fakta och resultat gäller inte längre
        self.con.execute("INSERT OR REPLACE INTO meta VALUES ('uid', ?)", (self.uid,))
        self.con.commit()
        self.con.execute("VACUUM")

    # ------------------------------------------------------------------ sparade beräkningar
    def _calc_version(self) -> str:
        return f"{PARSER_VERSION}.{CALC_VERSION}"

    def calc_cache(self) -> "CalcCache":
        if self._calc is None:
            v = self._calc_version()
            self._calc = {k: pickle.loads(val) for k, val in
                          self.con.execute("SELECT key, value FROM calc WHERE v=?", (v,))}
        return CalcCache(self)

    def save_calc(self) -> None:
        if not self._calc_new:
            return
        v = self._calc_version()
        self.con.executemany("INSERT OR REPLACE INTO calc VALUES (?,?,?)",
                             [(k, v, pickle.dumps(val, protocol=pickle.HIGHEST_PROTOCOL))
                              for k, val in self._calc_new.items()])
        self.con.commit()
        self._calc_new.clear()

    def close(self) -> None:
        self.save_calc()
        self.con.close()


class CalcCache:
    """Minnescache för tunga beräkningar per hand, backad av databasen."""
    MISSING = object()

    def __init__(self, db: HandDB):
        self.db = db

    def get(self, key, compute):
        d = self.db._calc
        val = d.get(key, self.MISSING)
        if val is self.MISSING:
            val = compute()
            d[key] = val
            self.db._calc_new[key] = val
        return val


def _next_day(d: str) -> str:
    from datetime import timedelta
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


# Global krok som analysen använder (None = ingen cache)
_active: CalcCache | None = None


def set_active(cache: CalcCache | None) -> None:
    global _active
    _active = cache


def cached(key: str, compute):
    return _active.get(key, compute) if _active is not None else compute()
