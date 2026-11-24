"""River-bluff-testet (2.72): randomiserat framåttest av "betta pott med luft när det checkas till dig".

Varför randomiserat: när du själv väljer när du bluffar blir jämförelsen bet mot check snedvriden (du bluffar oftare på
bra kort, i små pottar osv.). Den oberoende granskningen 2026-11-14 visade just det. Här avgör en slumpregel vid bordet:

    River, heads-up, du är i position, det checkas till dig och du har luft (minst 60 % av slumpade händer slår dig):
    titta på sekundvisaren – jämn sekund = betta pott, udda = checka.

Programmet visar aldrig något under spel (GG förbjuder realtidshjälp). I efterhand räknar det lägena efter
TEST_START, hur ofta du bettade (ska vara ~50 % om slumpregeln följs), fold-andelen mot dina pott-bets och utfallet
bet mot check. Break-even för en pottstor bluff är ~60 % fold (luft som checkas vinner ~22 % vid showdown).
2.73 (efter extern granskning): fold-andelen räknas bara på pott-bets (effektiv storlek ≥ 85 %), jämförelsen är pott-bet mot
check, och ett grönt slutbesked kräver båda armarna, bet-andel 35–65 %, minst 20 pass och en skattad skillnad. Siffrorna läses
av bara vid 300 och 500 lägen (förbestämt) – testet avbryts om fold-andelen då är under 62 %.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np

TEST_START = "2026-11-14"
STOP_FOLD = 62.0
SPOTS_CHECK = 300     # första avläsningen
SPOTS_DONE = 500      # andra och sista avläsningen
POT_SIZE = 85.0       # bet ≥ 85 % av potten (effektiv storlek) räknas som "pott"
AIR = 0.6
SHARE_OK = (35.0, 65.0)   # andel bets som är förenlig med slumpregeln
MIN_ARM = 60          # minst så många lägen i varje arm (pott-bet / check) för ett slutbesked
MIN_KNOWN = 60        # minst så många pott-bets med känt svar
MIN_CLUSTERS = 20     # minst så många spelpass
FUTILE_FOLD = 51.0    # säkerhetsstopp när som helst: hela 95 %-intervallet under ren break-even med rake (b/(b+1−r))


def start_ts() -> int:
    """Teststart i handtid (samma tidsräkning som faktatabellen – inte datorns tidszon, 2.73)."""
    from .facts import ts_of
    return ts_of(datetime.strptime(TEST_START, "%Y-%m-%d"))


def _wilson(k, n, z=1.96):
    if n <= 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def _cluster_diff(y, g, c):
    from .pfforward import _cluster_diff as cd
    return cd(y, g, c)


def bluff_test(st, since_ts: int | None = None) -> dict:
    ft = getattr(st, "ft", None)
    P = ft.t.get("pfd") if ft is not None else None
    if P is None or "bf" not in P or not len(P["hidx"]):
        return {}
    since = start_ts() if since_ts is None else since_ts
    rows = np.asarray(st.rows, dtype=np.int64)
    mask = np.zeros(ft.n, bool)
    mask[rows[ft.H["ts"][rows] >= since]] = True
    m = ft.subset_mask(mask, "pfd")
    kv = ft.codes("kind")
    k_bet, k_chk = kv.get("bet", -9), kv.get("check", -9)
    sel = (m & (P["st"] == 3) & (P["np"] == 2) & P["ip"] & (P["facing"] == 0) & (P["ord"] == 1)
           & (P["bf"] > AIR) & ((P["kind"] == k_bet) | (P["kind"] == k_chk)))
    ix = np.flatnonzero(sel)
    n = len(ix)
    out = {"start": TEST_START, "spots": n, "stop_fold": STOP_FOLD, "need": SPOTS_CHECK, "done_at": SPOTS_DONE,
           "rule": "Heads-up i position, det checkas till dig och du har luft på river: sekundvisaren jämn = betta pott, udda = checka."}
    if not n:
        out.update(verdict="⏳ Inga lägen än", tone="", bets=0, checks=0)
        return out
    hidx = P["hidx"][ix]
    bet = P["kind"][ix] == k_bet
    nb = int(bet.sum())
    esz = P["esz"][ix] if "esz" in P else P["size"][ix]
    potbet = bet & (esz >= POT_SIZE)          # 2.73: effektiv storlek (det motståndaren kan syna)
    small = bet & ~potbet                     # bets som inte följer protokollet (för små)
    check = ~bet
    pot_bets, n_small, n_chk = int(potbet.sum()), int(small.sum()), int(check.sum())
    clu = ft.H["clu"][hidx]
    n_clu = int(len(np.unique(clu)))
    # motståndarens svar på din bet: rvb role 1 (du bettar i position efter check)
    V = ft.t.get("rvb")
    resp = np.full(n, -1, np.int8)
    if V is not None and len(V["hidx"]):
        r1 = V["role"] == 1
        lut = dict(zip(V["hidx"][r1].tolist(), V["resp"][r1].tolist()))
        resp = np.array([lut.get(int(h), -1) for h in hidx], np.int8)
    known = potbet & (resp >= 0)              # 2.73: bara pott-bets räknas i fold-andelen
    folds = int((known & (resp == 0)).sum())
    nk = int(known.sum())
    fold_pct = 100.0 * folds / nk if nk else None
    lo, hi = _wilson(folds, nk)
    y = P["fh"][ix] / np.maximum(P["pot"][ix], 1e-9)
    arm = potbet | check                      # jämförelsen gäller pott-bet mot check
    ok = np.isfinite(y) & arm
    diff = se = None
    if ok.sum() >= 4 and 0 < potbet[ok].sum() < ok.sum():
        diff, se, _k = _cluster_diff(y[ok], potbet[ok], clu[ok])
    bet_share = 100.0 * nb / n
    # protokollkontroll: allt måste stämma för ett grönt slutbesked (ett brott kan aldrig skrivas över)
    problems = []
    if n >= 60 and not SHARE_OK[0] <= bet_share <= SHARE_OK[1]:
        problems.append(f"du bettade i {bet_share:.0f} % av lägena (slumpregeln ger ~50 %)")
    if nb >= 20 and n_small > 0.2 * nb:
        problems.append(f"{n_small} av {nb} bets var mindre än pott (under {POT_SIZE:.0f} %)")
    lacking = []
    if int((potbet & np.isfinite(y)).sum()) < MIN_ARM or int((check & np.isfinite(y)).sum()) < MIN_ARM:
        lacking.append(f"minst {MIN_ARM} pott-bets och {MIN_ARM} checkar")
    if nk < MIN_KNOWN:
        lacking.append(f"minst {MIN_KNOWN} pott-bets med känt svar")
    if n_clu < MIN_CLUSTERS:
        lacking.append(f"minst {MIN_CLUSTERS} spelpass")
    if diff is None:
        lacking.append("en skattad skillnad bet minus check")
    # avläsning bara vid två förbestämda tillfällen (300 och 500 lägen) – ingen löpande tjuvtitt på intervallet
    look = 2 if n >= SPOTS_DONE else (1 if n >= SPOTS_CHECK else 0)
    tone, verdict = "", ""
    if problems:
        tone, verdict = "bad-soft", ("⚠ Protokollet följs inte: " + "; ".join(problems) + ". Följ sekundvisaren och betta pott – "
                                     "annars mäter testet ditt eget urval igen, och det kan inte bli klart.")
    elif nk >= MIN_KNOWN and hi < FUTILE_FOLD:
        tone, verdict = "bad", (f"🛑 Avbryt testet nu: fold {fold_pct:.0f} % ({lo:.0f}–{hi:.0f} %) mot {nk} pott-bets – hela intervallet "
                                f"ligger under {FUTILE_FOLD:.0f} %, där en pottbluff förlorar även utan hänsyn till check. Checka luft igen.")
        look = max(look, 1)
    elif look and nk >= MIN_KNOWN and fold_pct < STOP_FOLD:
        tone, verdict = "bad", (f"🛑 Avbryt testet: fold {fold_pct:.0f} % ({lo:.0f}–{hi:.0f} %) mot pott-bets efter {n} lägen är under "
                                f"{STOP_FOLD:.0f} %. Checka luft igen.")
    elif look == 2 and lacking:
        tone, verdict = "bad-soft", f"⏳ {n} lägen, men testet kan inte avslutas: det saknas " + ", ".join(lacking) + "."
    elif look == 2:
        tone, verdict = "good", (f"✅ Testet är klart: fold {fold_pct:.0f} % ({lo:.0f}–{hi:.0f} %) mot {nk} pott-bets, bet minus check "
                                 f"{diff:+.2f} ± {1.96 * se:.2f} pott över {n} lägen och {n_clu} pass. Ta med siffrorna till Claude "
                                 "för beslut om en riktlinje (hypotes – inget är bekräftat av testet ensamt).")
    else:
        nxt = SPOTS_CHECK if n < SPOTS_CHECK else SPOTS_DONE
        verdict = f"⏳ Pågår: {n} av {nxt} lägen till nästa avläsning (avläses bara vid {SPOTS_CHECK} och {SPOTS_DONE})"
    out.update(bets=nb, checks=n_chk, bet_share=bet_share, pot_bets=pot_bets, small_bets=n_small, folds=folds, known=nk,
               clusters=n_clu, fold_pct=fold_pct if look else None, fold_lo=lo if look else None, fold_hi=hi if look else None,
               diff_pot=diff if look else None, diff_se=se if look else None, verdict=verdict, tone=tone, look=look,
               problems=problems, lacking=lacking)
    return out


# ====================================================================== 2.77: test v2 (v1 är ogiltigt och visas inte)
# Förregistrerat 2026-11-18 (projektdokumentet river-bluff-test-v2-2026-11-18.md). Ändras inget av detta efter start.
V2_START = "2026-11-19"
V2_AIR = 0.75            # minst 75 % av slumpade händer slår dig
V2_SIZE = (60.0, 90.0)   # ¾ pott (effektiv storlek) räknas som följd storlek
V2_LOOKS = (100, 200)    # avläsningar (lager S1)
V2_BE = 51.0             # break-even för ¾ pott inkl. checkens värde
V2_COMPLY = 80.0
V2_BET_SUITS = ("h", "d")
V2_PROTOCOL = ("v2.1 (2026-11-19): fasta prefix 100/200, grönt kräver även positiv ITT-skillnad, fold på river behåller läget, "
               "ny stege = högsta möjliga stege ändras")   # river ♥️/🔷 = betta ¾ pott, ♠️/☘️ = checka
V2_RULE = ("River, heads-up, i position, checkat till dig, minst 75 % av slumpade händer slår dig, effektiv stack ≥ pott och "
           "rivern ändrar nöten (ny färg, ny stege eller parat bord): river ♥️/🔷 = betta ¾ pott, ♠️/☘️ = checka. "
           "Ny färg som enda ändring kräver ett kort i färgen, annars ingår läget inte (förregistrerat veto).")


def _straight_possible(ranks) -> bool:
    rs = set(ranks) | ({1} if 14 in ranks else set())
    return any(len(rs & set(range(lo, lo + 5))) >= 3 for lo in range(1, 11))


def river_change(board, hole) -> dict:
    """S1/S2 och veto för rivern (board = 5 kort). Ny färg = turnen hade < 3 i färgen och rivern ger 3."""
    from collections import Counter
    t, rv = board[:4], board[4]
    ts = Counter(c[1] for c in t)
    new_flush = ts[rv[1]] == 2
    # 2.81 (protokoll v2.1): "ny stege" = den högsta möjliga stegen ändras (t.ex. 9-hög → T-hög), inte bara att en
    # stege blir möjlig för första gången
    from .misstag import _nut_straight_high
    new_straight = _nut_straight_high([c[0] for c in board]) != _nut_straight_high([c[0] for c in t])
    paired = rv[0] in {c[0] for c in t}
    changes = new_flush or new_straight or paired
    veto = new_flush and not new_straight and not paired and not any(c[1] == rv[1] for c in (hole or []))
    return {"s1": bool(changes), "veto": bool(veto), "flush": new_flush, "straight": new_straight, "paired": paired}


def _eff_ok(h, hero) -> bool:
    pre = [a for a in h.actions if a.street != "river"]
    pot = sum(a.added for a in pre)
    put = {}
    for a in pre:
        put[a.player] = put.get(a.player, 0.0) + a.added
    # 2.80: bordsläget omedelbart före river – en fold PÅ river (svaret på din bet) får inte ta bort läget
    folded = {a.player for a in pre if a.kind == "fold"}
    live = [p for p in h.seats if p not in folded and p != hero]
    if len(live) != 1 or hero not in h.stacks:
        return False
    v = live[0]
    eff = min(h.stacks[hero] - put.get(hero, 0.0), h.stacks.get(v, 0.0) - put.get(v, 0.0))
    return eff >= pot


def bluff_test_v2(st, since_ts: int | None = None, get_hand=None) -> dict:
    """Intention-to-treat: armen bestäms av river-kortets färg, oavsett vad du gjorde. S1 avgör testet, S2 redovisas."""
    from .facts import decode_cards, ts_of
    ft = getattr(st, "ft", None)
    P = ft.t.get("pfd") if ft is not None else None
    out = {"version": 2, "start": V2_START, "rule": V2_RULE, "looks": list(V2_LOOKS), "spots": 0}
    if P is None or "bf" not in P or not len(P["hidx"]):
        out.update(verdict="⏳ Inga lägen än", tone="")
        return out
    since = ts_of(datetime.strptime(V2_START, "%Y-%m-%d")) if since_ts is None else since_ts
    rows = np.asarray(st.rows, dtype=np.int64)
    mask = np.zeros(ft.n, bool)
    mask[rows[ft.H["ts"][rows] >= since]] = True
    m = ft.subset_mask(mask, "pfd")
    kv = ft.codes("kind")
    k_bet, k_chk = kv.get("bet", -9), kv.get("check", -9)
    sel = (m & (P["st"] == 3) & (P["np"] == 2) & P["ip"] & (P["facing"] == 0) & (P["ord"] == 1)
           & (P["bf"] >= V2_AIR) & ((P["kind"] == k_bet) | (P["kind"] == k_chk)))
    ix = np.flatnonzero(sel)
    getter = get_hand or (getattr(getattr(st, "hands_by_id", None), "get", None))
    hero = getattr(st, "hero", "Hero")
    V = ft.t.get("rvb")
    lut = {}
    if V is not None and len(V["hidx"]):
        r1 = V["role"] == 1
        lut = dict(zip(V["hidx"][r1].tolist(), V["resp"][r1].tolist()))
    rec = []
    for i in ix:
        j = int(P["hidx"][i])
        hole = decode_cards(ft.H["hole"][j])
        h = getter(str(ft.H["id"][j])) if getter else None
        if h is None or len(h.board) != 5:
            continue
        rc = river_change(h.board, hole)
        if rc["veto"] or not _eff_ok(h, hero):
            continue
        bet = P["kind"][i] == k_bet
        esz = float(P["esz"][i] if "esz" in P else P["size"][i])
        rec.append({"ts": int(ft.H["ts"][j]), "s1": rc["s1"], "arm_bet": h.board[4][1] in V2_BET_SUITS, "bet": bool(bet), "esz": esz,
                    "y": float(P["fh"][i] / max(P["pot"][i], 1e-9)), "clu": int(ft.H["clu"][j]), "resp": int(lut.get(j, -1))})
    rec.sort(key=lambda r: r["ts"])   # 2.80: kronologisk ordning – avläsningarna gäller fasta prefix
    S1_all = [r for r in rec if r["s1"]]
    S2 = [r for r in rec if not r["s1"]]
    n_all = len(S1_all)
    # 2.80 (protokoll v2.1, ändrat 19 nov före första avläsningen): avläsning 1 = exakt de första 100 S1-lägena,
    # avläsning 2 = exakt de första 200. Senare händer ändrar aldrig ett redan avläst besked.
    S1 = S1_all[:V2_LOOKS[1]] if n_all >= V2_LOOKS[1] else (S1_all[:V2_LOOKS[0]] if n_all >= V2_LOOKS[0] else S1_all)
    n = len(S1)
    out["spots"], out["s2_spots"], out["protocol"] = n_all, len(S2), V2_PROTOCOL
    if not n:
        out.update(verdict="⏳ Inga lägen än i lager S1 (rivern ändrar nöten)", tone="")
        return out
    comply = [(r["bet"] and V2_SIZE[0] <= r["esz"] <= V2_SIZE[1]) if r["arm_bet"] else (not r["bet"]) for r in S1]
    comply_pct = 100.0 * sum(comply) / n
    bets_known = [r for r in S1 if r["arm_bet"] and r["bet"] and r["resp"] >= 0]
    nk = len(bets_known)
    folds = sum(1 for r in bets_known if r["resp"] == 0)
    fold_pct = 100.0 * folds / nk if nk else None
    lo95, hi95 = _wilson(folds, nk)
    lo995, _ = _wilson(folds, nk, z=2.807)
    y = np.array([r["y"] for r in S1])
    g = np.array([r["arm_bet"] for r in S1])
    c = np.array([r["clu"] for r in S1])
    diff = se = None
    ok = np.isfinite(y)
    if ok.sum() >= 4 and 0 < g[ok].sum() < ok.sum():
        diff, se, _k = _cluster_diff(y[ok], g[ok], c[ok])
    look = 2 if n >= V2_LOOKS[1] else (1 if n >= V2_LOOKS[0] else 0)
    warn = f" ⚠ Du följde slumpregeln i {comply_pct:.0f} % av lägena (mål ≥ {V2_COMPLY:.0f} %) – bara ITT räknas." if n >= 30 and comply_pct < V2_COMPLY else ""
    if nk >= 20 and hi95 is not None and hi95 < V2_BE:
        tone, verdict = "bad", f"🛑 Avbryt: fold {fold_pct:.0f} % ({lo95:.0f}–{hi95:.0f} %) mot {nk} bets – hela intervallet under {V2_BE:.0f} %."
        look = max(look, 1)
    elif look == 1 and lo995 is not None and lo995 > V2_BE and diff is not None and diff > 0:
        tone, verdict = "good", f"✅ Klart vid första avläsningen: fold {fold_pct:.0f} % (nedre 99,5 %-gräns {lo995:.0f} % > {V2_BE:.0f} %)."
    elif look == 2:
        if lo95 is not None and lo95 > V2_BE and diff is not None and diff > 0:
            tone, verdict = "good", (f"✅ Testet är klart: fold {fold_pct:.0f} % ({lo95:.0f}–{hi95:.0f} %), bet-arm minus check-arm "
                                     f"{diff:+.2f} ± {1.96 * se:.2f} pott (ITT). Ta med siffrorna till Claude.")
        else:
            tone, verdict = "bad-soft", f"⏹ Testet är slut utan grönt besked: fold {fold_pct if fold_pct is not None else 0:.0f} % mot {nk} bets. Bluffa inte luft här som standard."
    else:
        tone, verdict = "", f"⏳ Pågår: {n_all} av {V2_LOOKS[0] if n_all < V2_LOOKS[0] else V2_LOOKS[1]} lägen till nästa avläsning."
    out.update(verdict=verdict + warn, tone=tone, look=look, comply=comply_pct, known=nk,
               bets=sum(1 for r in S1 if r["bet"]), checks=sum(1 for r in S1 if not r["bet"]),
               arm_bet=int(g.sum()), arm_check=int((~g).sum()),
               fold_pct=fold_pct if look else None, fold_lo=lo95 if look else None, fold_hi=hi95 if look else None,
               diff_pot=diff if look else None, diff_se=se if look else None,
               clusters=int(len(np.unique(c))))
    return out
