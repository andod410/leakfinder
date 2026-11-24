"""🌙 Nattberäkning v2 (2.72) – HYPOTES tills den klarat acceptanstestet på händer efter frysdatum.

Vad den räknar
--------------
1. **Rangemodell från poolens frekvenser per linje** (inte från visade händer, som är för starka: bluffar som får fold visas
   aldrig). För varje motståndarbeslut efter floppen räknas hur ofta poolen gör varje handling i samma läge:
   gata × vad han mötte (ingen bet / betstorlek) × position (IP/OOP) × nivå. Underlaget är bara händer FÖRE frysdatumet
   2026-11-13 (fryst modell). Läget slås ihop när underlaget är tunt: först utan nivå, sedan utan position, sedan utan
   betstorlek.
   Hans range efter en handling = de händer vars styrka på bordet just då ligger i rätt band bland de händer han kan ha
   kvar: höjning/bet = starkaste andelen f (med andelen λ bluffar från botten), syn = bandet under höjningarna,
   check = resten. Banden kedjas gata för gata (varje beslut filtrerar de händer som överlevt de tidigare).
   Preflop antas slumpade händer (förenkling).
   λ (bluffandelen) är ankaret: den väljs EN gång ur rutnätet LAMBDAS så att all-in-händer före frysdatumet (där
   motståndarens kort alltid visas, oavsett utfall) förutsägs bäst. Sedan låses den.
2. **Konvergensstyrd Monte Carlo**: equity mot rangen räknas tills medelfelet är högst 0,5 procentenheter (eller taket
   MAX_SAMPLES nås – då sparas medelfelet). Monte Carlo-felet är inte modellfelet.
3. **Turjusterat EV per hand** (förenklad AIVAT): vid varje nytt bordskort i en heads-up-pott räknas
   tur = pott × (equity efter kortet − equity före), mot samma range. Justerat resultat = all-in EV − tur.
   Gator efter en all-in hoppar över (all-in EV har redan tagit bort den turen).

Acceptans (bestämd före körning, 2026-11-14) – på händer EFTER frysdatum, klustrat per spelpass:
* kalibrering: förutsagd equity i flop/turn-all-ins mot faktisk equity mot hans visade kort – v2 ska ha lägre
  medelkvadratfel än v1 (visade händer), ensidigt 95 %;
* fold-prognos: förutsagd fold-andel mot dina river-bets mot faktisk – v2 (poolfrekvens per storlek/läge/nivå) ska slå
  v1 (poolens totala fold-andel);
* tur: medelvärdet av turjusteringen ≈ 0 (|medel| < 2 medelfel) – justerad och ojusterad winrate har samma väntevärde.
Klarar v2 inte alla tre används den inte (siffrorna visas bara här). Minst MIN_ALLIN all-ins, MIN_FOLD river-bets och
20 spelpass krävs innan något avgörs.

Samma skydd som v1: startar inte när GG körs eller när ny handhistorik kommit de senaste 10 minuterna, låg prioritet,
pausbar och fortsätter där den slutade.
"""
from __future__ import annotations

import json
import os
import pickle
import sqlite3
import time
import zlib
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

VERSION = 3   # 2.73: λ-rutnät 0–0,5 och nytt acceptanstest – allt räknas om en gång
RANGE_ID = "frekvens-v2"
SE_TARGET = 0.005
BATCH = 3000
CAND = 6000
MAX_SAMPLES = 24000
MIN_SURV = 40
MIN_LINE = 300
LAMBDAS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
MIN_ALLIN = 100
MIN_FOLD = 100
MIN_CLUSTERS = 20
CHUNK = 300
SIZES = (0.40, 0.60, 0.85, 1.10)     # gränser för betstorlek (andel av potten) – samma som betsize.py
SUIT = {"c": 0, "d": 1, "h": 2, "s": 3}
SIDX = {"flop": 1, "turn": 2, "river": 3}
NB = {1: 3, 2: 4, 3: 5}


def freeze_ts() -> int:
    from .forward import freeze_ts as f
    return f()


def code(c) -> int:
    return (c[0] - 2) * 4 + SUIT[c[1]]


def size_code(frac: float) -> int:
    for i, lim in enumerate(SIZES):
        if frac < lim:
            return i
    return len(SIZES)


# ---------------------------------------------------------------- handens förlopp
def walk(h):
    """En post per postflop-handling: dict(player, st 1–3, act, fac ('none' eller betstorlek 0–4), ip, n, pot_bb).
    fac = storleken på det spelaren mötte (syn i andel av potten före betten)."""
    from .parser import POSTFLOP_ORDER
    order = {p: i for i, p in enumerate(POSTFLOP_ORDER)}
    bb = h.bb or 1.0
    put = Counter()
    folded = set()
    out = []
    cur, contrib = None, Counter()
    for a in h.actions:
        if a.inferred:
            continue
        st = SIDX.get(a.street, 0)
        if a.street != cur:
            cur, contrib = a.street, Counter()
        if st >= 1 and not a.kind.startswith("post"):
            active = [p for p in h.seats if p not in folded]
            can = [p for p in active if h.stacks.get(p, 0.0) - put[p] > 1e-9]
            ip = bool(can) and max(can, key=lambda p: order.get(h.positions.get(p, ""), -1)) == a.player
            to_call = max(contrib.values(), default=0.0) - contrib[a.player]
            pot = float(sum(put.values()))
            if to_call > 1e-9:
                fac = size_code(to_call / max(pot - to_call, 1e-9))
            else:
                fac = "none"
            out.append({"player": a.player, "st": st, "act": a.kind, "fac": fac, "ip": int(ip), "n": len(active),
                        "pot": pot / bb, "allin": bool(getattr(a, "allin", False))})
        put[a.player] += a.added
        contrib[a.player] += a.added
        if a.kind == "fold":
            folded.add(a.player)
    return out


# ---------------------------------------------------------------- poolens frekvenser (fryst modell)
def line_counts(hands, hero: str) -> dict:
    """{nyckel: {handling: antal}} för alla motståndares beslut (inte dina)."""
    C = defaultdict(Counter)
    for h in hands:
        stake = f"{h.sb:g}/{h.bb:g}"
        for e in walk(h):
            if e["player"] == hero:
                continue
            act = e["act"] if e["act"] in ("check", "bet", "call", "raise", "fold") else None
            if act is None:
                continue
            fac = e["fac"]
            for k in _keys(e["st"], fac, e["ip"], stake):
                C[k][act] += 1
    return {k: dict(v) for k, v in C.items()}


def _keys(st, fac, ip, stake):
    coarse = "none" if fac == "none" else "bet"
    return (f"{st}|{fac}|{ip}|{stake}", f"{st}|{fac}|{ip}|*", f"{st}|{fac}|*|*", f"{st}|{coarse}|*|*")


def lookup(lines: dict, st, fac, ip, stake) -> tuple:
    """(frekvenser, nivå 0–3 = hur mycket som slogs ihop)."""
    for lvl, k in enumerate(_keys(st, fac, ip, stake)):
        c = lines.get(k)
        if c and sum(c.values()) >= MIN_LINE:
            return c, lvl
    k = _keys(st, fac, ip, stake)[-1]
    return lines.get(k) or {}, 3


def band(freq: dict, act: str, fac) -> tuple | None:
    """(lo, hi, aggressiv) – percentilband i hans kvarvarande range (0 = starkast)."""
    if fac == "none":
        tot = freq.get("bet", 0) + freq.get("check", 0)
        if not tot:
            return None
        fb = min(max(freq.get("bet", 0) / tot, 0.02), 0.98)
        return (0.0, fb, True) if act == "bet" else ((fb, 1.0, False) if act == "check" else None)
    tot = freq.get("fold", 0) + freq.get("call", 0) + freq.get("raise", 0)
    if not tot:
        return None
    fr = min(max(freq.get("raise", 0) / tot, 0.02), 0.9)
    fc = min(max(freq.get("call", 0) / tot, 0.02), 1.0 - fr)
    if act == "raise":
        return (0.0, fr, True)
    if act == "call":
        return (fr, min(fr + fc, 1.0), False)
    return None


# ---------------------------------------------------------------- Monte Carlo mot en range
def _survivors(rng, deck, nh, history, lam):
    """Slumpade motståndarhänder som överlever filtren i history = [(bord_kodlista, (lo, hi, aggr)), …]."""
    from .fastev_delat import vs_board
    D = len(deck)
    if D < nh + 2:
        return np.zeros((0, nh), np.int64)
    pick = np.argpartition(rng.random((CAND, D)), nh - 1, axis=1)[:, :nh]
    cand = deck[pick]
    for board, (lo, hi, aggr) in history:
        if not len(cand):
            break
        vals = vs_board(cand, board)   # 2.79: samma värden som best_values, delat bord räknas en gång
        order = np.argsort(-vals, kind="stable")
        pct = np.empty(len(cand))
        pct[order] = np.arange(len(cand)) / len(cand)
        keep = (pct >= lo) & (pct < hi)
        if aggr and lam > 0:
            width = hi - lo
            bluff = rng.random(len(cand)) < lam
            keep = np.where(bluff, pct >= 1.0 - width, keep)
        cand = cand[keep]
    return cand


def eq_range(hole, board, history, lam=0.2, seed=0, new_card=None):
    """Equity mot rangen. new_card: räkna också equity efter att det kortet kommit (samma motståndarhänder).
    Returnerar (eq, se, n) eller ((eq, se, n), (eq_efter, se, n)) med new_card; None om rangen blev tom."""
    from .fastev import best_values
    rng = np.random.default_rng(seed)
    hc = [code(c) for c in hole]
    bc = [code(c) for c in board]
    used = set(hc) | set(bc)
    deck = np.array([c for c in range(52) if c not in used], np.int64)
    nh = len(hole)
    surv = []
    tries = 0
    hist = [([code(c) for c in b], bd) for b, bd in history]
    from .fastev_delat import hole_tables, hole_vs_boards, vs_board
    htab = hole_tables(hc)
    while sum(len(s) for s in surv) < MIN_SURV * 4 and tries < 8:
        surv.append(_survivors(rng, deck, nh, hist, lam))
        tries += 1
    V = np.concatenate(surv) if surv else np.zeros((0, nh), np.int64)
    if len(V) < MIN_SURV:
        return None

    def run(Vs, bcodes):
        need = 5 - len(bcodes)
        dk = np.array([c for c in range(52) if c not in set(hc) | set(bcodes)], np.int64)
        lut = np.full(52, -1, np.int64)
        lut[dk] = np.arange(len(dk))
        out = []
        n = 0
        vV = None if need else vs_board(Vs, bcodes)   # river: hans värden räknas en gång per hand i rangen
        while n < MAX_SAMPLES:
            idx = rng.integers(0, len(Vs), BATCH)
            vil = Vs[idx]
            if need:
                keys = rng.random((BATCH, len(dk)))
                pos = lut[vil]
                keys[np.repeat(np.arange(BATCH), nh), pos.ravel()] = 9.0  # hans kort kan inte komma
                ro = dk[np.argpartition(keys, need - 1, axis=1)[:, :need]]
                boards = np.concatenate([np.broadcast_to(np.asarray(bcodes, np.int64), (BATCH, len(bcodes))), ro], axis=1)
            else:
                boards = np.broadcast_to(np.asarray(bcodes, np.int64), (BATCH, 5))
            hv = hole_vs_boards(htab, boards)   # 2.79: samma värden som best_values (heros hand är fast)
            vv = best_values(vil, boards) if need else vV[idx]
            out.append(np.where(hv > vv, 1.0, np.where(hv == vv, 0.5, 0.0)))
            n += BATCH
            x = np.concatenate(out)
            se = float(x.std() / np.sqrt(len(x)))
            if se <= SE_TARGET or (not need and n >= len(Vs) * 4):
                break
        x = np.concatenate(out)
        return float(x.mean()), float(x.std() / np.sqrt(len(x))), int(len(x))

    before = run(V, bc)
    if new_card is None:
        return before
    nc = code(new_card)
    V2 = V[~(V == nc).any(axis=1)]
    if len(V2) < MIN_SURV // 2:
        return before, None
    return before, run(V2, bc + [nc])


# ---------------------------------------------------------------- per hand
def _history(evs, villain, upto, board_of, lines, stake):
    """Villainens filter fram till (men inte med) händelse-index upto."""
    hist = []
    for e in evs[:upto]:
        if e["player"] != villain:
            continue
        freq, _lvl = lookup(lines, e["st"], e["fac"], e["ip"], stake)
        bd = band(freq, e["act"], e["fac"])
        if bd is not None:
            hist.append((board_of(e["st"]), bd))
    return hist


def hand_calc(h, hero: str, lines: dict, lam: float, do_decisions=True, do_luck=True, lam_grid=None, bank=None):
    """(beslutsrader, handrad). Beslut: (hand_id, gata, ordning, eq, se). Handrad: dict med tur och all-in-prognoser."""
    hole = (h.hole or {}).get(hero)
    if not hole or len(h.board) < 3 or hero not in h.seats:
        return [], None
    stake = f"{h.sb:g}/{h.bb:g}"
    evs = walk(h)
    board_of = lambda st: list(h.board[:NB[st]])  # noqa: E731
    seed0 = zlib.crc32(h.id.encode()) & 0x7FFFFFFF
    dec = []
    ordn = Counter()
    for i, e in enumerate(evs):
        if e["player"] != hero:
            continue
        ordn[e["st"]] += 1
        if not do_decisions or e["n"] != 2 or len(h.board) < NB[e["st"]]:
            continue
        others = [p for p in h.seats if p != hero and not any(x["player"] == p and x["act"] == "fold" for x in evs[:i])
                  and _alive_pre(h, p)]
        if len(others) != 1:
            continue
        hist = _history(evs, others[0], i, board_of, lines, stake)
        r = eq_range(hole, board_of(e["st"]), hist, lam, seed0 + 31 * i)
        if r is not None:
            dec.append((h.id, ["", "flop", "turn", "river"][e["st"]], int(ordn[e["st"]]), round(r[0], 4), round(r[1], 4)))
    hrow = {"hand_id": h.id, "luck": 0.0, "trans": 0, "ai": None}
    # all-in-prognos (flop/turn, heads-up, motståndarens kort visade)
    lock = None
    try:
        from .ev import allin_ev
        aev = allin_ev(h, hero, samples=200)
        lock = SIDX.get(aev[2]) if aev else None
    except Exception:
        lock = None
    if lam_grid and lock in (1, 2):
        live = [p for p in h.remaining() if p != hero]
        if len(live) == 1 and (h.shown or {}).get(live[0]):
            v = live[0]
            hist = _history(evs, v, len([e for e in evs if e["st"] <= lock]), board_of, lines, stake)
            preds = {}
            for lm in lam_grid:
                r = eq_range(hole, board_of(lock), hist, lm, seed0 + 7)
                preds[str(lm)] = None if r is None else round(r[0], 4)
            p1 = None
            if bank:
                from .night import eq_vs_pool
                key = f"{['', 'flop', 'turn'][lock]}|{len(hole)}"
                p1 = eq_vs_pool(hole, board_of(lock), bank.get(key), seed0 + 11)
            hrow["ai"] = {"street": lock, "v2": preds, "v1": None if p1 is None else round(p1, 4)}
    if do_luck:
        luck, nt = 0.0, 0
        for st in (1, 2):
            if len(h.board) < NB[st] + 1 or (lock is not None and st >= lock):
                break
            last_i = max((k for k, e in enumerate(evs) if e["st"] <= st), default=-1)
            alive = [p for p in h.seats if _alive_pre(h, p) and not any(x["player"] == p and x["act"] == "fold"
                                                                           for x in evs[:last_i + 1])]
            if hero not in alive or len(alive) != 2:
                break
            v = [p for p in alive if p != hero][0]
            hist = _history(evs, v, last_i + 1, board_of, lines, stake)
            r = eq_range(hole, board_of(st), hist, lam, seed0 + 101 * st, new_card=h.board[NB[st]])
            if r is None or r[1] is None:
                break
            pot = _pot_after(h, st)
            luck += pot * (r[1][0] - r[0][0])
            nt += 1
        hrow.update(luck=round(luck, 3), trans=nt)
    return dec, hrow


def _alive_pre(h, p) -> bool:
    return not any(a.player == p and a.kind == "fold" and a.street == "preflop" for a in h.actions)


def _pot_after(h, st) -> float:
    """Potten (bb) när gata st är slut."""
    bb = h.bb or 1.0
    names = ["preflop", "flop", "turn", "river"][:st + 1]
    return sum(a.added for a in h.actions if a.street in names) / bb


# ---------------------------------------------------------------- lagring
def ensure_tables(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS night2 (hand_id TEXT, street TEXT, ord INTEGER, eq REAL, se REAL, ver INTEGER,
            PRIMARY KEY (hand_id, street, ord));
        CREATE TABLE IF NOT EXISTS night2_hand (hand_id TEXT PRIMARY KEY, luck REAL, trans INTEGER, ai TEXT, ver INTEGER);
        CREATE TABLE IF NOT EXISTS night2_ai (hand_id TEXT PRIMARY KEY, ai TEXT, ver INTEGER);
        CREATE TABLE IF NOT EXISTS night2_meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    con.commit()
    _meta_version(con)


def _meta_version(con):
    """Ny modellversion: ankaret och acceptansen från den gamla versionen gäller inte längre."""
    r = con.execute("SELECT v FROM night2_meta WHERE k='ver'").fetchone()
    if r is None or json.loads(r[0]) != VERSION:
        con.execute("DELETE FROM night2_meta WHERE k IN ('lam', 'lam_info', 'acceptance', 'acceptance_final')")
        con.execute("INSERT OR REPLACE INTO night2_meta VALUES ('ver', ?)", (json.dumps(VERSION),))
        con.commit()


def meta_get(con, k):
    r = con.execute("SELECT v FROM night2_meta WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else None


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO night2_meta VALUES (?,?)", (k, json.dumps(v)))
    con.commit()


def main_game(db) -> str:
    """Varianten du spelat mest (t.ex. "PLO-6"). v2 räknar bara den – PLO4/PLO5 skulle blanda poolens frekvenser."""
    r = db.con.execute("SELECT game, COUNT(*) AS n FROM hands GROUP BY game ORDER BY n DESC LIMIT 1").fetchone()
    return r[0] if r else "PLO-6"


def status(db) -> dict:
    ensure_tables(db.con)
    done = db.con.execute("SELECT COUNT(*) FROM night2_hand WHERE ver=?", (VERSION,)).fetchone()[0]
    total = db.con.execute("SELECT COUNT(*) FROM hands WHERE game=?", (main_game(db),)).fetchone()[0]
    return {"done": int(done), "total": int(total), "version": VERSION, "range_id": RANGE_ID,
            "lam": meta_get(db.con, "lam"), "lines": bool(meta_get(db.con, "lines_info"))}


# ---------------------------------------------------------------- arbetare
_W = {}


def _init(path, hero, lines, lam, grid, bank):
    from .night import _low_priority
    _low_priority()
    _W.update(con=sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False), hero=hero,
              lines=lines, lam=lam, grid=grid, bank=bank)


def _work(args):
    ids, phase = args
    con, hero = _W["con"], _W["hero"]
    out_d, out_h = [], []
    q = "SELECT id, blob FROM hands WHERE id IN (%s)" % ",".join("?" * len(ids))
    for hid, b in con.execute(q, ids):
        try:
            h = pickle.loads(zlib.decompress(b))
            if phase == "ai":
                _d, hr = hand_calc(h, hero, _W["lines"], 0.0, do_decisions=False, do_luck=False,
                                   lam_grid=_W["grid"], bank=_W["bank"])
            else:
                _d, hr = hand_calc(h, hero, _W["lines"], _W["lam"])
                out_d += _d
        except Exception:
            hr = None
        out_h.append((hid, hr))
    return ids, out_d, out_h


def _blocked(db):
    from .night import blocked
    return blocked(db)


def build_lines(db, hero, job=None):
    from .forward import FREEZE_DATE
    cut = FREEZE_DATE
    C = defaultdict(Counter)
    n = 0
    for (b,) in db.con.execute("SELECT blob FROM hands WHERE date < ? AND game = ?", (cut, main_game(db))):
        try:
            h = pickle.loads(zlib.decompress(b))
        except Exception:
            continue
        for k, v in line_counts([h], hero).items():
            C[k].update(v)
        n += 1
        if job and n % 20000 == 0:
            job.set(f"🌙 v2: poolens frekvenser per linje – {n:,} händer".replace(",", " "))
    lines = {k: dict(v) for k, v in C.items()}
    meta_set(db.con, "lines", lines)
    meta_set(db.con, "lines_info", {"hands": n, "before": cut, "keys": len(lines), "range_id": RANGE_ID, "game": main_game(db)})
    return lines


def fit_lambda(con, cut_ts, ts_of) -> float | None:
    """Ankaret: λ som ger minst kvadratfel mot faktisk equity i all-ins FÖRE frysdatumet. ts_of: hand_id -> ts, eq."""
    rows = con.execute("SELECT hand_id, ai FROM night2_ai WHERE ver=?", (VERSION,)).fetchall()
    err = defaultdict(list)
    for hid, ai in rows:
        info = ts_of.get(hid)
        if not ai or info is None or info[0] >= cut_ts:
            continue
        a = json.loads(ai)
        if not a:
            continue
        for lm, p in (a.get("v2") or {}).items():
            if p is not None:
                err[lm].append((p - info[1]) ** 2)
    if not err or min(len(v) for v in err.values()) < 50:
        return None
    return float(min(err, key=lambda k: np.mean(err[k])))


def run(job, db, processes: int | None = None, deadline: float | None = None, ts_of: dict | None = None) -> str:
    """Kör/fortsätter v2. ts_of = {hand_id: (ts, ai_eq)} (från faktatabellen) behövs för att låsa λ."""
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp
    from .night import STOP, build_bank, ensure_tables as ensure_v1, load_bank
    STOP["flag"] = False
    why = _blocked(db)
    if why:
        return "⏸ " + why
    ensure_tables(db.con)
    ensure_v1(db.con)
    hero = db.detect_hero() or "Hero"
    lines = meta_get(db.con, "lines") or build_lines(db, hero, job)
    from .night import cpu_procs
    procs = processes or cpu_procs()
    ctx = mp.get_context("spawn")
    t0 = time.time()
    msg = ""
    # fas A: all-in-prognoser (alla λ i rutnätet + v1) – grunden för ankaret och kalibreringstestet
    lam = meta_get(db.con, "lam")
    done_ai = {r[0] for r in db.con.execute("SELECT hand_id FROM night2_ai WHERE ver=?", (VERSION,))}
    if ts_of is not None:
        ai_ids = [hid for hid in ts_of if hid not in done_ai and ts_of[hid][2]]
    else:
        ai_ids = []
    if ai_ids:
        job.set("🌙 v2: poolens visade händer (för jämförelsen med v1)")
        # 2.81: v1-baslinjen byggs bara av händer före frysdatumet (fryst) och utan dina egna visade kort
        from .forward import FREEZE_DATE as _FZ
        bank = load_bank(db, tag="fz") or build_bank(db, job.set, before=_FZ, tag="fz", hero=hero)
        msg = _pool(job, db, ctx, procs, ai_ids, "ai", hero, lines, 0.0, LAMBDAS, bank, deadline, t0)
        if msg:
            return msg
    if lam is None and ts_of is not None:
        lam = fit_lambda(db.con, freeze_ts(), ts_of)
        if lam is not None:
            meta_set(db.con, "lam", lam)
            meta_set(db.con, "lam_info", {"fitted": datetime.now().strftime("%Y-%m-%d %H:%M"), "grid": LAMBDAS,
                                          "on": "all-ins före frysdatumet"})
    lam_use = 0.2 if lam is None else float(lam)
    # 2.81: en hand räknas som klar bara om den är beräknad med det λ som gäller nu (sparas per rad). Rader från före
    # 2.81 saknar λ och antas vara räknade med standardvärdet 0,2 (det enda som användes innan ankaret fanns).
    done = set()
    for hid, info in db.con.execute("SELECT hand_id, ai FROM night2_hand WHERE ver=?", (VERSION,)):
        try:
            row_lam = (json.loads(info) or {}).get("lam", 0.2) if info else 0.2
        except Exception:
            row_lam = 0.2
        if abs(float(row_lam) - lam_use) < 1e-9:
            done.add(hid)
    ids = [r[0] for r in db.con.execute("SELECT id FROM hands WHERE game=? ORDER BY date DESC", (main_game(db),))
           if r[0] not in done]  # nyast först
    if not ids:
        return f"🌙 v2: allt är redan beräknat ({len(done):,} händer).".replace(",", " ")
    msg = _pool(job, db, ctx, procs, ids, "main", hero, lines, lam_use, None, None, deadline, t0)
    if msg:
        return msg
    return f"🌙 v2 klar: {len(ids):,} händer på {(time.time() - t0) / 60:.0f} min (λ = {lam_use:g}).".replace(",", " ")


def _pool(job, db, ctx, procs, ids, phase, hero, lines, lam, grid, bank, deadline, t0) -> str:
    from concurrent.futures import ProcessPoolExecutor
    from .night import STOP
    chunks = [ids[i:i + CHUNK] for i in range(0, len(ids), CHUNK)]
    n_done, paused = 0, ""
    if procs <= 1:  # i samma process (tester, svaga datorer): inga arbetsprocesser
        _W.update(con=sqlite3.connect(f"file:{db.path}?mode=ro", uri=True, check_same_thread=False), hero=hero,
                  lines=lines, lam=lam, grid=grid, bank=bank)
        for c in chunks:
            cid, drows, hrows = _work((c, phase))
            _store(db, phase, drows, hrows, lam)
            n_done += len(cid)
            job.set(f"🌙 v2: {n_done:,} av {len(ids):,} händer".replace(",", " "))
            if STOP["flag"]:
                return "⏸ Pausad – tryck Starta igen för att fortsätta där den slutade."
            if deadline and time.time() > deadline:
                return "⏸ Tidsgränsen för natten nåddes – fortsätter nästa natt."
        return ""
    with ProcessPoolExecutor(max_workers=procs, mp_context=ctx, initializer=_init,
                             initargs=(str(db.path), hero, lines, lam, grid, bank)) as ex:
        futs = [ex.submit(_work, (c, phase)) for c in chunks[:procs * 2]]
        nxt = procs * 2
        while futs:
            cid, drows, hrows = futs.pop(0).result()
            _store(db, phase, drows, hrows, lam)
            n_done += len(cid)
            rate = n_done / max(time.time() - t0, 1)
            left = (len(ids) - n_done) / rate / 60 if rate > 0 else 0
            lab = "all-in-prognoser" if phase == "ai" else "beslut och tur"
            job.set(f"🌙 v2 {lab}: {n_done:,} av {len(ids):,} händer · ca {left:.0f} min kvar".replace(",", " "))
            if not paused:
                if STOP["flag"]:
                    paused = "⏸ Pausad – tryck Starta igen för att fortsätta där den slutade."
                elif deadline and time.time() > deadline:
                    paused = "⏸ Tidsgränsen för natten nåddes – fortsätter nästa natt."
                elif nxt % (procs * 4) == 0:
                    why = _blocked(db)
                    if why:
                        paused = "⏸ " + why
            if not paused and nxt < len(chunks):
                futs.append(ex.submit(_work, (chunks[nxt], phase)))
                nxt += 1
    return paused + (f" ({n_done:,} av {len(ids):,})".replace(",", " ") if paused else "")


def _lam_ok(info, lam) -> bool:
    """2.81: raden är räknad med λ (rader utan sparat λ antas ha 0,2)."""
    if lam is None:
        return True
    try:
        row_lam = (json.loads(info) or {}).get("lam", 0.2) if info else 0.2
        return row_lam is not None and abs(float(row_lam) - float(lam)) < 1e-9
    except Exception:
        return False


def _store(db, phase, drows, hrows, lam=None):
    if phase == "ai":
        db.con.executemany("INSERT OR REPLACE INTO night2_ai VALUES (?,?,?)",
                           [(hid, json.dumps((hr or {}).get("ai")), VERSION) for hid, hr in hrows])
    else:
        db.con.executemany("INSERT OR REPLACE INTO night2 VALUES (?,?,?,?,?,%d)" % VERSION, drows)
        db.con.executemany("INSERT OR REPLACE INTO night2_hand VALUES (?,?,?,?,?)",
                           [(hid, (hr or {}).get("luck"), (hr or {}).get("trans", 0),
                             json.dumps({"lam": lam, "ok": hr is not None}), VERSION) for hid, hr in hrows])
    db.con.commit()


# ---------------------------------------------------------------- acceptans
def _cmean_se(x, c):
    from .fatigue import _cluster_mean_se
    m, se = _cluster_mean_se(np.asarray(x, float), np.asarray(c))
    return float(m), float(se)


# ---- acceptansplan 2.73 (förregistrerad 2026-11-14, efter extern granskning; två pass efter frysdatum hade då setts) ----
ACCEPT_PLAN = "2.73/2026-11-14"
CHECKPOINTS = (20, 40, 80)   # avläsning bara när så många spelpass finns efter frysdatumet (de första K passen används)
CAL_BIAS = 0.05              # kalibrering: |prognos − faktisk equity| ska visas ligga inom 5 procentenheter
FOLD_BIAS = 0.10             # fold-prognos: |prognos − faktisk fold-andel| inom 10 procentenheter
LUCK_MARGIN = 0.05           # tur: medel ska visas ligga inom ±0,05 bb/hand (±5 bb/100) – ekvivalenstest, inte "ingen avvikelse".
                             # (Justeringen är väntevärdesriktig av konstruktion om koden är rätt; testet fångar fel i den. Snävare
                             # marginal går inte att visa med färre än ~100 000 händer.)
VAR_GAIN = 0.20              # turjusteringen ska sänka variansen med minst 20 %, annars tillför den inget


def _z_look() -> float:
    from statistics import NormalDist
    return NormalDist().inv_cdf(1 - 0.05 / len(CHECKPOINTS))   # ensidigt 5 % delat på avläsningarna (≈ 2,13)


def _three(better, worse):
    return True if better else (False if worse else None)


def _equiv(m, se, margin, z):
    """Ekvivalens: True om hela intervallet ligger inom ±margin, False om det ligger helt utanför, annars None."""
    if m is None or se is None or not np.isfinite(se):
        return None
    return _three(abs(m) + z * se < margin, abs(m) - z * se > margin)


def acceptance(db, st, hero: str = "Hero") -> dict:
    """Acceptanstestet på händer efter frysdatum (plan 2.73). Tre delar, alla måste klaras:

    1. Kalibrering mot all-ins: lägre kvadratfel än v1 OCH liten absolut avvikelse (prognos − faktisk equity inom ±5 pe,
       visat med intervall). "Bättre än v1" räcker inte – v1 kan vara dålig.
    2. Fold-prognos för dina river-bets: lägre Brier än poolens totala fold-andel OCH prognos − faktisk inom ±10 pe.
       (Prövar linjefrekvenserna, inte hela rangemodellen.)
    3. Tur: ekvivalenstest – medel inom ±0,05 bb/hand – OCH variansen minst 20 % lägre än all-in EV.
    Avläsning bara vid 20, 40 och 80 spelpass efter frysdatumet (de första K passen), med kritiskt värde justerat för tre
    avläsningar. Första avgörandet (godkänd/underkänd) sparas och är slutligt för den här modellversionen."""
    ensure_tables(db.con)
    final = meta_get(db.con, "acceptance_final")
    if final and final.get("plan") == ACCEPT_PLAN and final.get("ver") == VERSION:
        return {**final, "stored": True}
    ft = st.ft
    H = ft.H
    cut = freeze_ts()
    from .forward import FREEZE_DATE
    rows = np.asarray(st.rows, dtype=np.int64)
    lam = meta_get(db.con, "lam")
    out = {"lam": lam, "freeze": FREEZE_DATE, "parts": {}, "plan": ACCEPT_PLAN, "ver": VERSION, "checkpoints": list(CHECKPOINTS)}
    post = rows[H["ts"][rows] >= cut]
    first = {}
    for j in post.tolist():
        c = int(H["clu"][j]); t = int(H["ts"][j])
        if c not in first or t < first[c]:
            first[c] = t
    order = sorted(first, key=first.get)
    npass = len(order)
    cp = max((k for k in CHECKPOINTS if k <= npass), default=0)
    out.update(passes=npass, checkpoint=cp)
    if lam is None:
        out.update(status="väntar", text="🌙 Nattberäkning v2 är inte körd (ankaret λ saknas) – används inte.")
        return out
    if not cp:
        out.update(status="väntar", text=f"⏳ {npass} av {CHECKPOINTS[0]} spelpass efter frysdatumet – första avläsningen görs vid "
                                         f"{CHECKPOINTS[0]} pass. v2 används inte. Inga mellanresultat visas (förbestämd plan).")
        return out
    use = set(order[:cp])
    rows_cp = np.array([j for j in post.tolist() if int(H["clu"][j]) in use], dtype=np.int64)
    id2row = {str(H["id"][j]): int(j) for j in rows_cp.tolist()}
    # 2.80: ingen avläsning (och inget slutbesked) förrän varje hand i avläsningens pass är beräknad
    done_ids = set()
    ids = list(id2row)
    for a in range(0, len(ids), 900):
        part = ids[a:a + 900]
        done_ids.update(r[0] for r in db.con.execute(
            f"SELECT hand_id, ai FROM night2_hand WHERE ver=? AND hand_id IN ({','.join('?' * len(part))})", [VERSION] + part)
            if _lam_ok(r[1], lam))
    if len(done_ids) < len(ids):
        out.update(status="väntar", coverage=(len(done_ids), len(ids)),
                   text=f"⏳ Avläsningen vid {cp} pass väntar på nattberäkningen: {len(done_ids)} av {len(ids)} händer är "
                        "beräknade. Inget besked förrän alla är klara.")
        return out
    z = _z_look()
    # 1) kalibrering mot all-ins
    cal = {"n": 0}
    p1s, p2s, es, cl = [], [], [], []
    for hid, ai in db.con.execute("SELECT hand_id, ai FROM night2_ai WHERE ver=?", (VERSION,)):
        j = id2row.get(hid)
        if j is None or not ai:
            continue
        a = json.loads(ai)
        if not a:
            continue
        p2 = (a.get("v2") or {}).get(str(lam))
        p1 = a.get("v1")
        if p2 is None or p1 is None:
            continue
        p1s.append(p1); p2s.append(p2); es.append(float(H["ai_eq"][j])); cl.append(int(H["clu"][j]))
    if p2s:
        p1a, p2a, ea = np.array(p1s), np.array(p2s), np.array(es)
        m, se = _cmean_se((p1a - ea) ** 2 - (p2a - ea) ** 2, cl)
        bm, bse = _cmean_se(p2a - ea, cl)
        bins = []
        for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
            mm = (p2a >= lo) & (p2a < hi)
            if mm.sum():
                bins.append({"bin": f"{int(lo * 100)}–{int(min(hi, 1) * 100)} %", "n": int(mm.sum()),
                             "pred": float(p2a[mm].mean()), "actual": float(ea[mm].mean())})
        cal = {"n": len(p2s), "clusters": len(set(cl)), "mse_v1": float(((p1a - ea) ** 2).mean()),
               "mse_v2": float(((p2a - ea) ** 2).mean()), "diff": m, "se": se, "bias": bm, "bias_se": bse, "bins": bins}
    cal["ok"] = _part_ok(cal, MIN_ALLIN, CAL_BIAS, z)
    out["parts"]["kalibrering"] = cal
    # 2) fold-prognos
    out["parts"]["fold"] = _fold_part(ft, rows, cut, hero, allowed_new=set(rows_cp.tolist()), z=z)
    # 3) tur
    lk, cl, evs = [], [], []
    for hid, luck, info in db.con.execute("SELECT hand_id, luck, ai FROM night2_hand WHERE ver=?", (VERSION,)):
        if not _lam_ok(info, lam):
            continue   # 2.81: bara rader räknade med det låsta λ
        j = id2row.get(hid)
        if j is None or luck is None:
            continue
        lk.append(float(luck)); cl.append(int(H["clu"][j])); evs.append(float(H["ev"][j]))
    luck = {"n": len(lk), "ok": None}
    if len(lk) >= 2:
        m, se = _cmean_se(lk, cl)
        ev = np.array(evs)
        adj = ev - np.array(lk)
        gain = 1.0 - float(adj.var()) / float(ev.var()) if float(ev.var()) > 0 else 0.0
        luck.update(clusters=len(set(cl)), mean=m, se=se, ev100=100 * float(ev.mean()), adj100=100 * float(adj.mean()),
                    var_ev=float(ev.var()), var_adj=float(adj.var()), var_gain=gain, margin=LUCK_MARGIN)
        if len(set(cl)) >= MIN_CLUSTERS and len(lk) >= 2000:
            eq = _equiv(m, se, LUCK_MARGIN, z)
            if eq is False or gain < VAR_GAIN / 2:
                luck["ok"] = False
            elif eq is True and gain >= VAR_GAIN:
                luck["ok"] = True
    out["parts"]["tur"] = luck
    oks = [p.get("ok") for p in out["parts"].values()]
    last = cp == CHECKPOINTS[-1]
    if any(o is False for o in oks):
        out.update(status="underkänd", text=f"❌ v2 klarade inte acceptanstestet vid {cp} pass – används inte (hypotesen förkastad).")
    elif all(o is True for o in oks):
        out.update(status="godkänd", text=f"✅ v2 klarade alla tre delarna vid {cp} pass efter frysdatum – turjusterat resultat visas "
                                          "(experimentellt mått, ersätter inte all-in EV).")
    elif last:
        out.update(status="inte avgjord", text=f"⏹ Inte avgjort efter {cp} pass (sista avläsningen) – v2 används inte.")
    else:
        nxt = next(k for k in CHECKPOINTS if k > cp)
        out.update(status="väntar", text=f"⏳ Inte avgjort vid {cp} pass – nästa avläsning vid {nxt} pass. v2 används inte än.")
    if out["status"] != "väntar":
        meta_set(db.con, "acceptance_final", {**out, "decided": datetime.now().strftime("%Y-%m-%d %H:%M")})
    return out


def _part_ok(p, nmin, bias_margin, z):
    """Klarar delen? Kräver både förbättring mot baslinjen och liten absolut avvikelse (2.73)."""
    if p.get("n", 0) < nmin or p.get("clusters", 0) < MIN_CLUSTERS or p.get("se") is None or not np.isfinite(p["se"]):
        return None
    better = _three(p["diff"] - z * p["se"] > 0, p["diff"] + z * p["se"] < 0)
    close = _equiv(p.get("bias"), p.get("bias_se"), bias_margin, z)
    if better is False or close is False:
        return False
    return True if (better is True and close is True) else None


def _fold_part(ft, rows, cut, hero, allowed_new=None, z=1.645) -> dict:
    """Fold-prognosen: poolens svar på river-bets (river-situationerna i faktatabellen)."""
    H = ft.H
    R = ft.t.get("rsp")
    if R is None or not len(R.get("hidx", [])):
        return {"n": 0, "ok": None}
    allowed = set(np.asarray(rows).tolist())
    cnt, tot = Counter(), Counter()
    fwd = []
    for hi, o in zip(R["hidx"], R["obj"]):
        if int(hi) not in allowed:
            continue
        try:
            s = pickle.loads(o)
        except Exception:
            continue
        if s.get("kind") != "bet" or s.get("response") not in ("fold", "call", "raise"):
            continue
        hi = int(hi)
        key = (size_code(float(s.get("frac") or 1.0)), str(s.get("role", "")), f"{H['sb'][hi]:g}/{H['bb'][hi]:g}")
        fold = s["response"] == "fold"
        mine = s.get("bettor") == hero
        if int(H["ts"][hi]) < cut and not s.get("hero_role"):
            for k in (key, key[:2], key[:1], ()):
                cnt[k] += int(fold)
                tot[k] += 1
        elif int(H["ts"][hi]) >= cut and mine and (allowed_new is None or hi in allowed_new):
            fwd.append((key, int(fold), int(H["clu"][hi])))
    if not tot.get(()):
        return {"n": 0, "ok": None}
    base = cnt[()] / tot[()]
    p1, p2, y, cl = [], [], [], []
    for key, f, c in fwd:
        k = next((kk for kk in (key, key[:2], key[:1]) if tot.get(kk, 0) >= 100), ())
        p2.append(cnt[k] / tot[k]); p1.append(base); y.append(f); cl.append(c)
    res = {"n": len(y), "base": base}
    if y:
        p1a, p2a, ya = np.array(p1), np.array(p2), np.array(y, float)
        d = (p1a - ya) ** 2 - (p2a - ya) ** 2
        m, se = _cmean_se(d, cl)
        bm, bse = _cmean_se(p2a - ya, cl)
        res.update(clusters=len(set(cl)), brier_v1=float(((p1a - ya) ** 2).mean()), brier_v2=float(((p2a - ya) ** 2).mean()),
                   diff=m, se=se, bias=bm, bias_se=bse, actual=100 * float(ya.mean()), pred=100 * float(p2a.mean()))
    res["ok"] = _part_ok(res, MIN_FOLD, FOLD_BIAS, z)
    return res


def export_rows(db, ids) -> list:
    try:
        ensure_tables(db.con)
    except Exception:
        return []
    ids = list(ids)
    out = []
    for a in range(0, len(ids), 900):
        ch = ids[a:a + 900]
        q = ("SELECT n.hand_id, n.street, n.ord, n.eq, n.se, h.luck FROM night2 n LEFT JOIN night2_hand h "
             "ON h.hand_id = n.hand_id WHERE n.ver=? AND n.hand_id IN (%s)" % ",".join("?" * len(ch)))
        out += [list(r) + [RANGE_ID] for r in db.con.execute(q, [VERSION, *ch])]
    return out


NIGHT2_HEADER = ["hand_id", "street", "order", "eq_v2", "se_v2", "luck_bb_hand", "range_id"]
