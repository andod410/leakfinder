"""🌙 Nattberäkning: tunga beräkningar per beslut som körs på din dator när du INTE spelar.

Varför: djupexporten räknar handstyrka mot slumpade händer och grova outs. Nattberäkningen räknar för varje
postflop-beslut (flop/turn/river):

* nut_outs  – kort som ger dig nöten (ingen möjlig hand slår dig) utan att para bordet; varje kort räknas en gång
* nut2_outs – kort som ger dig näst bästa möjliga hand (inte nöten) utan att para bordet
* pair_outs – kort som parar bordet (farliga mot set/tvåpar)
* eq_pool   – din equity mot poolens VISADE händer på samma gata (Monte Carlo). range_id = vilken version av
  "poolens range" som användes. OBS: visade händer är starkare än poolens verkliga range (bluffar som får fold visas
  aldrig) – därför är eq_pool en försiktig (låg) uppskattning.

Regler (GG förbjuder realtidshjälp):
* startas bara med en knapp och ger aldrig råd medan du spelar;
* vägrar starta / pausar om GG-klienten körs eller om en handhistorikfil i den bevakade mappen ändrats de senaste
  10 minuterna;
* körs med låg prioritet i flera processer; kan pausas och fortsätter där den slutade (resultat sparas per omgång).

Rådgivning: två oberoende agenter 2026-11-12 (projektdokumenten granskning-2026-11-12/n1-varde.md och n2-teknik.md).
"""
from __future__ import annotations

import os
import pickle
import random
import sqlite3
import sys
import time
import zlib
from collections import Counter
from itertools import combinations

VERSION = 1
RANGE_ID = "visade-v1"
CHUNK = 400
BANK_MAX = 60000          # visade händer per gata och kortantal
VILLAINS = 40             # motståndarhänder per beslut
RUNOUTS = 50              # utdelningar per motståndarhand
QUIET_MIN = 10            # minuter utan ny handhistorik innan beräkningen får starta
STOP = {"flag": False}

GG_PROCS = ("ggnet", "ggpoker", "ggpcom")


# ---------------------------------------------------------------- skydd
def gg_status() -> str:
    """"ja" = GG-klienten körs, "nej" = körs inte, "okänd" = det gick inte att kontrollera (2.73: räknas inte som nej).
    Windows: tasklist, Mac/Linux: ps."""
    import subprocess
    try:
        if sys.platform == "win32":
            # 2.87 (R7-05): bytes + OEM-kodsida – text=True gav UnicodeDecodeError på svensk Windows (å/ä/ö i
            # tasklist-rubriker) och därmed "okänd" varje gång.
            r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = _decode_oem(r.stdout)
        else:
            r = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=10,
                               errors="replace")
            out = r.stdout or ""
    except Exception:
        return "okänd"
    if r.returncode != 0 or not out.strip():
        return "okänd"
    low = out.lower()
    return "ja" if any(p in low for p in GG_PROCS) else "nej"


def _decode_oem(b) -> str:
    """2.87: avkoda tasklist-utdata. Försöker konsolens OEM-kodsida (cp850 på svensk Windows), sedan utf-8 och
    sist latin-1 (som aldrig misslyckas) – processnamnen är ASCII, så rätt namn hittas i alla fall."""
    if not b:
        return ""
    if isinstance(b, str):
        return b
    encs = []
    try:
        import ctypes
        encs.append(f"cp{ctypes.windll.kernel32.GetOEMCP()}")  # type: ignore[attr-defined]
    except Exception:
        pass
    encs += ["cp850", "utf-8", "latin-1"]
    for e in encs:
        try:
            return b.decode(e)
        except Exception:
            continue
    return b.decode("latin-1", errors="replace")


def gg_running() -> bool:
    return gg_status() == "ja"


def recent_hh(db, minutes: int = QUIET_MIN) -> bool:
    """Har en handhistorikfil i den bevakade mappen ändrats de senaste minuterna (du spelar troligen)?"""
    from pathlib import Path
    from . import watch
    try:
        folder = watch.folder_of(watch.load_settings(db))
        if not folder:
            return False
        root = Path(folder).expanduser()
        lim = time.time() - minutes * 60
        for f in root.rglob("*"):
            if f.suffix.lower() in (".txt", ".zip") and f.stat().st_mtime > lim:
                return True
    except Exception:
        return False
    return False


def cpu_procs(reserve: int = 1, cap: int = 24) -> int:
    """2.78.2: antal arbetsprocesser = alla kärnor utom `reserve` (en kvar till datorn), högst `cap`.
    Windows 10600K: 12 trådar -> 11. Mac M4 / M4 Pro / M4 Max: 10/12–14/14–16 kärnor -> 9/11–13/13–15.
    Varje arbetsprocess får en tråd för numpys räknebibliotek (Accelerate/OpenBLAS), annars konkurrerar trådarna."""
    import os
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(k, "1")
    if os.environ.get("PLO_PROCS", "").isdigit():   # 2.79: för test och felsökning
        return max(1, int(os.environ["PLO_PROCS"]))
    return max(1, min(cap, (os.cpu_count() or 2) - reserve))


FORCE = {"until": 0.0}   # 2.78.1: "starta direkt" – hoppar över väntan på 10 min efter ny handhistorik (GG måste ändå vara stängt)


def force_for(hours: float = 12.0) -> None:
    FORCE["until"] = time.time() + hours * 3600


def blocked(db) -> str:
    g = gg_status()
    if g == "ja":
        from .ggguard import dev_mode
        if dev_mode():
            g = "nej"  # 2.79: utvecklingsläge – nattkörningen får köras när GG är igång
    if g == "ja":
        return "GG-klienten körs. Nattberäkningen körs bara när du inte spelar – stäng GG och försök igen."
    if g == "okänd":
        return ("Det gick inte att kontrollera om GG-klienten körs (processlistan kunde inte läsas). Nattberäkningen startar "
                "inte när det är oklart – försök igen, eller starta programmet om.")
    if time.time() >= FORCE["until"] and recent_hh(db):
        return (f"Ny handhistorik har kommit in de senaste {QUIET_MIN} minuterna – du spelar troligen. "
                "Nattberäkningen väntar tills du slutat spela.")
    return ""


def _low_priority():
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(10)
    except Exception:
        pass


# ---------------------------------------------------------------- tabeller
def ensure_tables(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS night (hand_id TEXT, street TEXT, ord INTEGER, nut_outs INTEGER, nut2_outs INTEGER,
            pair_outs INTEGER, eq_pool REAL, range_id TEXT, ver INTEGER, PRIMARY KEY (hand_id, street, ord));
        CREATE TABLE IF NOT EXISTS night_done (hand_id TEXT PRIMARY KEY, ver INTEGER);
        CREATE TABLE IF NOT EXISTS night_bank (key TEXT PRIMARY KEY, n INTEGER, data BLOB);
    """)
    con.commit()


def status(db) -> dict:
    ensure_tables(db.con)
    done = db.con.execute("SELECT COUNT(*) FROM night_done WHERE ver=?", (VERSION,)).fetchone()[0]
    total = db.con.execute("SELECT COUNT(*) FROM hands").fetchone()[0]
    rows = db.con.execute("SELECT COUNT(*) FROM night WHERE ver=?", (VERSION,)).fetchone()[0]
    return {"done": int(done), "total": int(total), "rows": int(rows), "version": VERSION, "range_id": RANGE_ID}


# ---------------------------------------------------------------- nöt-outs (snabb utvärdering med tabellerna i ev.py)
def _val(hole_pairs, triples):
    from .ev import fast_best
    return fast_best(hole_pairs, triples)


def top_two(board, dead) -> tuple:
    """Bästa och näst bästa (distinkta) handvärde som en motståndare kan ha på bordet, med de döda korten borttagna.
    Räknar per valörpar (+ per färgpar för färg) i stället för alla 2-kortskombinationer – samma svar, ~6 gånger snabbare."""
    from .ev import FLUSH, NONFLUSH, PRIMES, _triples
    tri = _triples(board)
    left = Counter()
    suit_left = {}
    for r in range(2, 15):
        for s in "shdc":
            if (r, s) not in dead and (r, s) not in board:
                left[r] += 1
                suit_left.setdefault(s, []).append(r)
    vals = set()
    rs = [r for r in range(2, 15) if left[r]]
    for i, a in enumerate(rs):
        for b in rs[i:]:
            if a == b and left[a] < 2:
                continue
            pp = PRIMES[a] * PRIMES[b]
            vals.add(max(NONFLUSH[pp * tp] for tp, _ in tri))
    for s, cards in suit_left.items():
        ft = [tp for tp, ts in tri if ts == s]
        if not ft:
            continue
        for a, b in combinations(cards, 2):
            pp = PRIMES[a] * PRIMES[b]
            vals.add(max(FLUSH[pp * tp] for tp in ft))
    v = sorted(vals, reverse=True)
    return (v[0], v[1] if len(v) > 1 else -1)


def outs(hole, board) -> tuple:
    """(nut_outs, nut2_outs, pair_outs) för nästa kort. Ett kort räknas en gång."""
    from .ev import _pairs, _triples
    hp = _pairs(hole)
    br = {c[0] for c in board}
    dead = set(hole) | set(board)
    n1 = n2 = np_ = 0
    for r in range(2, 15):
        for s in "shdc":
            c = (r, s)
            if c in dead:
                continue
            if r in br:
                np_ += 1
                continue
            nb = board + [c]
            hv = _val(hp, _triples(nb))
            t1, t2 = top_two(nb, set(hole) | {c})
            if hv >= t1:
                n1 += 1
            elif hv >= t2:
                n2 += 1
    return n1, n2, np_


# ---------------------------------------------------------------- poolens visade händer
def build_bank(db, progress=None, before: str | None = None, tag: str = "", hero: str | None = None) -> dict:
    """Visade motståndarhänder per (gata, antal kort): händer som nådde showdown – gatan = sista gatan de såg.
    2.81: before = bara händer före det datumet (v2-jämförelsens baslinje får inte se testperiodens kort), tag = egen
    lagring, hero = ditt riktiga spelarnamn (tidigare bara den bokstavliga texten "Hero"). Reservoaren räknar
    kandidater per nyckel."""
    bank = {}
    seen: dict = {}
    rng = random.Random(7)
    n = 0
    q, args = "SELECT blob FROM hands", []
    if before:
        q, args = q + " WHERE date < ?", [before]
    for (b,) in db.con.execute(q, args):
        n += 1
        try:
            h = pickle.loads(zlib.decompress(b))
        except Exception:
            continue
        shown = getattr(h, "shown", None) or {}
        if not shown:
            continue
        nb = len(h.board)
        st = {3: "flop", 4: "turn", 5: "river"}.get(nb)
        if not st:
            continue
        for p, cards in shown.items():
            if p == (hero or "Hero") or p == "Hero" or not cards:
                continue
            for street in ("flop", "turn", "river")[: ("flop", "turn", "river").index(st) + 1]:
                key = f"{street}|{len(cards)}"
                L = bank.setdefault(key, [])
                seen[key] = seen.get(key, 0) + 1
                if len(L) < BANK_MAX:
                    L.append(tuple(cards))
                elif rng.random() < BANK_MAX / seen[key]:
                    L[rng.randrange(BANK_MAX)] = tuple(cards)
        if progress and n % 20000 == 0:
            progress(f"Läser poolens visade händer: {n} händer")
    con = db.con
    pre = f"{RANGE_ID}{('#' + tag) if tag else ''}"
    for k, L in bank.items():
        con.execute("INSERT OR REPLACE INTO night_bank VALUES (?,?,?)", (f"{pre}|{k}", len(L),
                                                                          zlib.compress(pickle.dumps(L))))
    con.commit()
    return bank


def load_bank(db, tag: str = "") -> dict:
    out = {}
    pre = f"{RANGE_ID}{('#' + tag) if tag else ''}"
    for key, _n, data in db.con.execute("SELECT key, n, data FROM night_bank WHERE key LIKE ?", (f"{pre}|%",)):
        out[key.split("|", 1)[1]] = pickle.loads(zlib.decompress(data))
    return out


def eq_vs_pool(hole, board, bank_list, seed: int) -> float | None:
    from .ev import equities
    if not bank_list:
        return None
    rng = random.Random(seed)
    dead = set(hole) | set(board)
    tot = 0.0
    k = 0
    tries = 0
    while k < VILLAINS and tries < VILLAINS * 20:
        tries += 1
        v = bank_list[rng.randrange(len(bank_list))]
        if dead & set(v):
            continue
        try:
            e = equities({"h": list(hole), "v": list(v)}, list(board), samples=RUNOUTS, seed=seed + k)["h"]
        except Exception:
            continue
        tot += e
        k += 1
    return tot / k if k else None


# ---------------------------------------------------------------- arbetare (egen process)
_W = {}


def _init(path, bank, hero):
    _low_priority()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    _W.update(con=con, bank=bank, hero=hero)


def _work(ids):
    from .postflop_rows import HEADER, rows_for_hand
    ix = {k: i for i, k in enumerate(HEADER)}
    con, bank, hero = _W["con"], _W["bank"], _W["hero"]
    out = []
    q = "SELECT id, blob FROM hands WHERE id IN (%s)" % ",".join("?" * len(ids))
    for hid, b in con.execute(q, ids):
        try:
            h = pickle.loads(zlib.decompress(b))
        except Exception:
            continue
        hole = (h.hole or {}).get(hero)
        if not hole or len(h.board) < 3:
            continue
        try:
            rows = rows_for_hand(h, hero, None, light=True)
        except Exception:
            rows = []
        cache = {}
        for r in rows:
            st = r[ix["street"]]
            nb = {"flop": 3, "turn": 4, "river": 5}[st]
            board = list(h.board[:nb])
            if st not in cache:
                n1 = n2 = npair = None
                if st != "river":
                    try:
                        n1, n2, npair = outs(list(hole), board)
                    except Exception:
                        pass
                seed = zlib.crc32(f"{hid}|{st}".encode())
                eq = eq_vs_pool(hole, board, bank.get(f"{st}|{len(hole)}"), seed)
                cache[st] = (n1, n2, npair, eq)
            n1, n2, npair, eq = cache[st]
            out.append((hid, st, int(r[ix["order"]]), n1, n2, npair, None if eq is None else round(eq, 4)))
    return ids, out


# ---------------------------------------------------------------- jobbet
def run(job, db, processes: int | None = None) -> str:
    """Kör (eller fortsätter) nattberäkningen. Returnerar en sammanfattning."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp
    STOP["flag"] = False
    why = blocked(db)
    if why:
        return "⏸ " + why
    ensure_tables(db.con)
    hero = db.detect_hero() or "Hero"
    job.set("Bygger poolens range (visade händer)")
    bank = load_bank(db) or build_bank(db, job.set)
    done = {r[0] for r in db.con.execute("SELECT hand_id FROM night_done WHERE ver=?", (VERSION,))}
    ids = [r[0] for r in db.con.execute("SELECT id FROM hands") if r[0] not in done]
    total = len(ids) + len(done)
    if not ids:
        return f"Allt är redan beräknat ({total} händer)."
    procs = processes or cpu_procs()
    chunks = [ids[i:i + CHUNK] for i in range(0, len(ids), CHUNK)]
    t0 = time.time()
    n_done = len(done)
    paused = ""
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=procs, mp_context=ctx, initializer=_init,
                             initargs=(str(db.path), bank, hero)) as ex:
        futs = [ex.submit(_work, c) for c in chunks[:procs * 2]]
        nxt = procs * 2
        while futs:
            f = futs.pop(0)
            cid, rows = f.result()
            db.con.executemany("INSERT OR REPLACE INTO night VALUES (?,?,?,?,?,?,?,'%s',%d)" % (RANGE_ID, VERSION), rows)
            db.con.executemany("INSERT OR REPLACE INTO night_done VALUES (?,?)", [(i, VERSION) for i in cid])
            db.con.commit()
            n_done += len(cid)
            rate = (n_done - len(done)) / max(time.time() - t0, 1)
            left = (total - n_done) / rate / 60 if rate > 0 else 0
            job.set(f"🌙 {n_done:,} av {total:,} händer · ca {left:.0f} min kvar".replace(",", " "))
            if not paused:
                if STOP["flag"]:
                    paused = "⏸ Pausad – tryck Starta igen för att fortsätta där den slutade."
                elif nxt % (procs * 4) == 0:
                    why = blocked(db)
                    if why:
                        paused = "⏸ " + why
            if not paused and nxt < len(chunks):
                futs.append(ex.submit(_work, chunks[nxt]))
                nxt += 1
    if paused:
        return paused + f" ({n_done:,} av {total:,} händer klara)".replace(",", " ")
    return f"🌙 Klar: {n_done:,} händer beräknade på {(time.time() - t0) / 60:.0f} min.".replace(",", " ")


def export_rows(db, ids) -> list:
    """Rader till night_hands.csv för händerna i urvalet."""
    try:
        ensure_tables(db.con)
    except Exception:
        return []
    ids = list(ids)
    out = []
    for a in range(0, len(ids), 900):
        ch = ids[a:a + 900]
        q = ("SELECT hand_id, street, ord, nut_outs, nut2_outs, pair_outs, eq_pool, range_id FROM night "
             "WHERE ver=? AND hand_id IN (%s)" % ",".join("?" * len(ch)))
        out += [list(r) for r in db.con.execute(q, [VERSION, *ch])]
    return out


NIGHT_HEADER = ["hand_id", "street", "order", "nut_outs", "nut2_outs", "pair_outs", "eq_pool", "range_id"]
