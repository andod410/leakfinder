"""2.76: handgrupper och preflopläge i samma indelning som en PLO6-preflopsolver (PLO Trainer).

Den här filen är programmets egen kod och innehåller ingen solverdata. Den delar in en 6-kortshand i
samma tre nivåer som solverns lösningar (par/färgstruktur → rundown/parvalör → undergrupp) och avgör
vilket av de 14 solverlägena ett första preflopbeslut hör till. Själva frekvenserna läses från en fil
som spelaren själv lägger in (solverref.py) och följer aldrig med programmet.
"""
from __future__ import annotations

from collections import Counter

CLASSIFIER_VERSION = 1

# de 14 lägena (solverns nodkoder) i fast ordning – index sparas i faktatabellen
NODES = ["root", "F", "F-F", "F-F-F", "RC5", "RC5-F", "RC5-F-F", "RC5-F-F-F", "F-RC5", "F-RC5-F", "F-RC5-F-F",
         "F-F-RC5", "F-F-RC5-F", "F-F-F-RC4"]
NODE_LABEL = {"root": "UTG öppnar", "F": "CO öppnar", "F-F": "BTN öppnar", "F-F-F": "SB öppnar",
              "RC5": "CO mot UTG", "RC5-F": "BTN mot UTG", "RC5-F-F": "SB mot UTG", "RC5-F-F-F": "BB mot UTG",
              "F-RC5": "BTN mot CO", "F-RC5-F": "SB mot CO", "F-RC5-F-F": "BB mot CO",
              "F-F-RC5": "SB mot BTN", "F-F-RC5-F": "BB mot BTN", "F-F-F-RC4": "BB mot SB"}
OPEN_NODES = {"root", "F", "F-F", "F-F-F"}
# intern positionskod (HJ = UTG) -> nod
_RFI = {"HJ": "root", "CO": "F", "BTN": "F-F", "SB": "F-F-F"}
_VS = {("CO", "HJ"): "RC5", ("BTN", "HJ"): "RC5-F", ("SB", "HJ"): "RC5-F-F", ("BB", "HJ"): "RC5-F-F-F",
       ("BTN", "CO"): "F-RC5", ("SB", "CO"): "F-RC5-F", ("BB", "CO"): "F-RC5-F-F",
       ("SB", "BTN"): "F-F-RC5", ("BB", "BTN"): "F-F-RC5-F", ("BB", "SB"): "F-F-F-RC4"}
ACT = {"fold": 0, "call": 1, "raise": 2}


def node_of(h, hero: str):
    """(nodindex, handling 0/1/2) för heros första preflopbeslut, eller None om läget inte finns i solvern
    (limpare före, synare efter öppningen, straddle, 3-bet före dig, check i BB, inte 6 kort)."""
    if getattr(h, "num_hole", 0) != 6:
        return None
    pre = [a for a in h.actions if a.street == "preflop"]
    if any(a.kind == "post_straddle" for a in pre):
        return None
    raises, calls = [], 0
    for a in pre:
        if a.kind.startswith("post"):
            continue
        if a.player == hero:
            if a.kind not in ACT:
                return None
            pos = h.positions.get(hero, "")
            if not raises and not calls:
                nd = _RFI.get(pos)
            elif len(raises) == 1 and calls == 0:
                nd = _VS.get((pos, h.positions.get(raises[0].player, "")))
            else:
                nd = None
            return None if nd is None else (NODES.index(nd), ACT[a.kind])
        if a.kind == "raise":
            raises.append(a)
        elif a.kind == "call":
            calls += 1
    return None


def _rv(r) -> int:
    return r if isinstance(r, int) else "23456789TJQKA".index(r) + 2


def classify(cards):
    """cards: sex kort som (valör 2–14, färg). Svar: (nivå 0, nivå 1, [kandidater för nivå 2], har ess) eller
    None för trips/quads (finns inte i solvern)."""
    if len(cards) != 6:
        return None
    rk = [_rv(c[0]) for c in cards]
    st = [c[1] for c in cards]
    rc, sc = Counter(rk), Counter(st)
    if max(rc.values()) >= 3:
        return None
    pairs = sorted((r for r, v in rc.items() if v == 2), reverse=True)
    npair = len(pairs)
    cnt = sorted(sc.values(), reverse=True)
    n2 = sum(1 for v in cnt if v >= 2)
    suit0 = {3: "Triple Suited", 2: "Double Suited", 1: "Single Suited"}[min(max(n2, 1), 3)]
    l0 = ["Unpaired", "One Pair", "Two Pair", "Three Pair"][npair] + " " + suit0
    mx = cnt[0]
    if suit0 == "Double Suited":
        sub = {2: "Pure", 3: "Trip Suited"}.get(mx, "Quad Suited")
    elif suit0 == "Single Suited":
        sub = {2: "Pure", 3: "Trip Suited"}.get(mx, "Quad+ Suited")
    else:
        sub = None
    has_a = 14 in rc
    ace_suited = any(sc[s] >= 2 for r, s in zip(rk, st) if r == 14)
    bw = sum(1 for r in rk if r >= 10 and rc[r] == 1)  # klädda kort utanför paren
    if npair == 0:
        vals = set(rk) | ({1} if 14 in rk else set())
        best = 0
        v = sorted(vals)
        for n in (6, 5, 4):
            for lo in v:
                if sum(1 for x in v if lo <= x <= lo + n + 1) >= n:  # n valörer inom n + 2 steg (0–2 luckor)
                    best = max(best, n)
        l1 = {6: "6Card Rundowns (0,1,2 gaps)", 5: "5Card Rundowns (0,1,2 gaps)", 4: "4Card Rundowns (0,1,2 gaps)"}.get(best)
        if not l1:
            l1 = "3 Broadway" if len({r for r in rk if r >= 10}) >= 3 else "Ragged"
    else:
        p = pairs[0]
        l1 = {14: "AA", 13: "KK", 12: "QQ", 11: "JJ-TT", 10: "JJ-TT", 9: "99-88", 8: "99-88", 7: "77-66", 6: "77-66",
              5: "55-44", 4: "55-44", 3: "33-22", 2: "33-22"}[p]
    if suit0 == "Triple Suited":
        if l1 == "AA":
            cands = ["2+ Broadway" if bw >= 2 else "Other"]
        else:
            cands = ["Ace-high" if has_a else ("2+ Broadway" if bw >= 2 else "Other")]
    elif l1 == "AA":
        nut = sum(1 for r, s in zip(rk, st) if r == 14 and sc[s] >= 2)
        if suit0 == "Single Suited":
            t = "Suited Ace" if nut else "Unsuited Ace"
            # 2.80: en hand utan ess i färg får aldrig gruppen "Suited Ace" (granskningen P4)
            cands = [f"{sub}, {t}"] + ([f"{sub}, Suited Ace"] if t == "Suited Ace" else []) + ["Quad Suited", "Quad+ Suited"]
        elif sub == "Quad Suited":
            cands = ["Quad Suited", "Quad+ Suited"]
        else:
            cands = [f"{sub}, {['No Nut Suit', '1 Nut Suit', '2 Nut Suits'][min(nut, 2)]}"]
    else:
        tail = "Suited Ace" if (has_a and ace_suited) else ("Unsuited Ace" if has_a else ("2+ Broadway" if bw >= 2 else "Other"))
        alt = list(dict.fromkeys([sub] + (["Quad Suited", "Quad+ Suited"] if sub and sub.startswith("Quad") else [])))
        cands = [f"{s}, {tail}" for s in alt]
        if tail in ("Suited Ace", "Unsuited Ace"):
            cands += ([f"{s}, 2+ Broadway" for s in alt] if bw >= 2 else []) + [f"{s}, Other" for s in alt]
        if tail == "2+ Broadway":
            cands += [f"{s}, Other" for s in alt]
    return l0, l1, cands, has_a


def short(l0: str, l1: str, l2: str | None) -> str:
    """Kort svensk text för en grupp."""
    t = (l0.replace("Unpaired", "Inget par").replace("One Pair", "Ett par").replace("Two Pair", "Två par")
         .replace("Three Pair", "Tre par").replace("Double Suited", "ds").replace("Single Suited", "ss")
         .replace("Triple Suited", "trippelsuited"))
    t1 = l1.replace("Card Rundowns (0,1,2 gaps)", "-korts rundown").replace("Ragged", "osammanhängande").replace("3 Broadway", "3 klädda")
    out = f"{t} · {t1}"
    if l2:
        out += " · " + (l2.replace("Pure", "rena färger").replace("Trip Suited", "3 i en färg").replace("Quad+ Suited", "4+ i en färg")
                        .replace("Quad Suited", "4 i en färg").replace("Suited Ace", "suited ess").replace("Unsuited Ace", "ess utan färg")
                        .replace("2+ Broadway", "2+ klädda").replace("Other", "övrigt").replace("Ace-high", "med ess")
                        .replace("2 Nut Suits", "2 nötfärger").replace("1 Nut Suit", "1 nötfärg").replace("No Nut Suit", "ingen nötfärg"))
    return out


# ------------------------------------------------------------------ 2.78: fler solverlägen (manuellt hämtade 2026-11-18)
EXTRA_LABEL = {
    "F-F-RC5-F-RC15": "BTN öppnade, BB 3-bettar",
    "F-F-RC5-RC16-F": "BTN öppnade, SB 3-bettar",
    "F-RC5-RC17-F-F": "CO öppnade, BTN 3-bettar",
    "F-RC5-F-F-RC15": "CO öppnade, BB 3-bettar",
    "RC5-F-RC17-F-F": "UTG öppnade, BTN 3-bettar",
    "F-F-F-RC4-RC12": "SB öppnade, BB 3-bettar",
    "F-F-RC5-RC16": "BB: BTN öppnar, SB 3-bettar (kallsyn)",
    "F-RC5-C-F": "BB: CO öppnar, BTN synar",
    "F-F-RC5-C": "BB: BTN öppnar, SB synar",
    "F-F-F-C": "BB mot SB-limp",
    "F-F-RC5-F-RC15-RC45": "BB 3-bettade mot BTN, möter 4-bet",
    "F-RC5-RC17-F-F-RC51": "BTN 3-bettade mot CO, möter 4-bet",
    # 2.82: hämtade 2026-11-19 (de fem lägen som kostat mest bland de saknade)
    "RC5-F-C-F": "BB: UTG öppnar, BTN synar",
    "F-RC5-F-C": "BB: CO öppnar, SB synar",
    "F-RC5-C": "SB: CO öppnar, BTN synar",
    "RC5-F-C": "SB: UTG öppnar, BTN synar",
    "RC5-RC17": "BTN: UTG öppnar, CO 3-bettar",
    # 2.84: hämtade 2026-11-19 em (de fem saknade lägen där du förlorat mest mot fold, 247k händer)
    "RC5-RC17-F": "SB: UTG öppnar, CO 3-bettar",
    "F-RC5-RC17": "SB: CO öppnar, BTN 3-bettar",
    "RC5-C-C-F": "BB: UTG öppnar, CO och BTN synar",
    "F-F-RC5-C-RC21": "BTN öppnade, SB synar, BB squeezar",
    "F-RC5-F-C-RC21": "CO öppnade, SB synar, BB squeezar",
    # 2.85: hämtade 2026-11-20 (3-bet-delen komplett + squeeze/multiway; trädet saknar limp för UTG/CO/BTN)
    "RC5-RC17-F-F-F": "UTG öppnade, CO 3-bettar",
    "RC5-F-F-RC16-F": "UTG öppnade, SB 3-bettar",
    "RC5-F-F-F-RC15": "UTG öppnade, BB 3-bettar",
    "F-RC5-F-RC16-F": "CO öppnade, SB 3-bettar",
    "RC5-C-C": "SB: UTG öppnar, CO och BTN synar",
    "F-RC5-C-C-RC28": "CO öppnade, BTN och SB synar, BB squeezar",
    "RC5-C-C-F-RC29": "UTG öppnade, CO och BTN synar, BB squeezar",
    "RC5-F-F-C-RC21": "UTG öppnade, SB synar, BB squeezar",
    # 2.86: hämtade 2026-11-20 kväll (7) och 2026-11-21 fm (5)
    "RC5-RC17-RC58-F-F": "UTG öppnade, CO 3-bettar, BTN 4-bettar",
    "RC5-F-F-C-RC21-C": "SB: UTG öppnade, du synade, BB squeezar, UTG synar",
    "RC5-F-F-RC16-C": "UTG öppnade, SB 3-bettar, BB synar",
    "RC5-C-RC24": "SB: UTG öppnar, CO synar, BTN squeezar",
    "RC5-RC17-C-F": "BB: UTG öppnar, CO 3-bettar, BTN synar",
    "RC5-F-C-C": "BB: UTG öppnar, BTN och SB synar",
    "RC5-C-C-C": "BB: UTG öppnar, CO, BTN och SB synar",
    "RC5-RC17-F-F": "BB: UTG öppnar, CO 3-bettar",
    "RC5-C-RC24-F": "BB: UTG öppnar, CO synar, BTN squeezar",
    "RC5-F-RC17-F": "BB: UTG öppnar, BTN 3-bettar",
    "RC5-F-RC17-C-F": "UTG öppnade, BTN 3-bettar, SB synar",
    "RC5-C-F-F": "BB: UTG öppnar, CO synar",
}
EXTRA_NODES = list(EXTRA_LABEL)
ALL_NODES = NODES + EXTRA_NODES
NODE_LABEL.update(EXTRA_LABEL)
# handlingen före läget (för träningens handurval): (läge, kolumn) som spelaren måste ha valt för att hamna här
EXTRA_PRIOR = {"F-F-RC5-F-RC15": ("F-F", 2), "F-F-RC5-RC16-F": ("F-F", 2), "F-RC5-RC17-F-F": ("F", 2),
               "F-RC5-F-F-RC15": ("F", 2), "RC5-F-RC17-F-F": ("root", 2), "F-F-F-RC4-RC12": ("F-F-F", 2),
               "F-F-RC5-F-RC15-RC45": ("F-F-RC5-F", 2), "F-RC5-RC17-F-F-RC51": ("F-RC5", 2),
               "F-F-RC5-C-RC21": ("F-F", 2), "F-RC5-F-C-RC21": ("F", 2),
               "RC5-RC17-F-F-F": ("root", 2), "RC5-F-F-RC16-F": ("root", 2), "RC5-F-F-F-RC15": ("root", 2),
               "F-RC5-F-RC16-F": ("F", 2), "F-RC5-C-C-RC28": ("F", 2), "RC5-C-C-F-RC29": ("root", 2),
               "RC5-F-F-C-RC21": ("root", 2),
               "RC5-RC17-RC58-F-F": ("root", 2), "RC5-F-F-RC16-C": ("root", 2), "RC5-F-RC17-C-F": ("root", 2),
               "RC5-F-F-C-RC21-C": ("RC5-F-F", 1)}


def _tok(code: str) -> str:
    return "-".join("R" if t.startswith("RC") else t for t in code.split("-"))


_EXTRA_TOK = {_tok(c): c for c in EXTRA_NODES}


def extra_decisions(h, hero: str) -> list:
    """Heros preflopbeslut i de extra lägena: [(index i ALL_NODES, handling 0/1/2, investerat före beslutet i bb,
    vilket av heros preflopbeslut i handen (0 = första))].
    Matchas på handlingsföljden (F/C/R, storlek ignoreras) från första spelaren; kräver 6 kort, 5 spelare, ingen straddle."""
    if getattr(h, "num_hole", 0) != 6 or len(getattr(h, "seats", {}) or {}) != 5:
        return []
    pre = [a for a in h.actions if a.street == "preflop"]
    if any(a.kind == "post_straddle" for a in pre):
        return []
    out, toks, inv, ordn = [], [], 0.0, 0
    for a in pre:
        if a.kind.startswith("post"):
            if a.player == hero:
                inv += a.added
            continue
        t = {"fold": "F", "call": "C", "raise": "R", "check": "X"}.get(a.kind)
        if t is None:
            return out
        if a.player == hero:
            code = _EXTRA_TOK.get("-".join(toks))
            if code is not None:
                act = {"fold": 0, "call": 1, "raise": 2, "check": 0}.get(a.kind)
                if code == "F-F-F-C" and a.kind == "call":
                    act = None
                if act is not None:
                    out.append((ALL_NODES.index(code), act, inv / h.bb if h.bb else 0.0, ordn))
            inv += a.added
            ordn += 1
        toks.append(t)
    return out


# 2.78.2: utförlig beskrivning av varje läge (visas i träningen): vem du är och vad som hänt före ditt beslut
NODE_DESC = {
    "root": "Du sitter UTG. Ingen har agerat. Öppna (höj pott) eller folda?",
    "F": "Du sitter på CO. UTG foldade. Öppna eller folda?",
    "F-F": "Du sitter på BTN. UTG och CO foldade. Öppna eller folda?",
    "F-F-F": "Du sitter i SB. Alla foldade till dig. Öppna, limpa eller folda?",
    "RC5": "Du sitter på CO. UTG öppnade (pott). Folda, syna eller 3-betta?",
    "RC5-F": "Du sitter på BTN. UTG öppnade, CO foldade. Folda, syna eller 3-betta?",
    "RC5-F-F": "Du sitter i SB. UTG öppnade, CO och BTN foldade. Folda, syna eller 3-betta?",
    "RC5-F-F-F": "Du sitter i BB. UTG öppnade, alla andra foldade. Folda, syna eller 3-betta?",
    "F-RC5": "Du sitter på BTN. UTG foldade, CO öppnade. Folda, syna eller 3-betta?",
    "F-RC5-F": "Du sitter i SB. CO öppnade, BTN foldade. Folda, syna eller 3-betta?",
    "F-RC5-F-F": "Du sitter i BB. CO öppnade, BTN och SB foldade. Folda, syna eller 3-betta?",
    "F-F-RC5": "Du sitter i SB. BTN öppnade. Folda, syna eller 3-betta?",
    "F-F-RC5-F": "Du sitter i BB. BTN öppnade, SB foldade. Folda, syna eller 3-betta?",
    "F-F-F-RC4": "Du sitter i BB. SB öppnade (alla andra foldade). Folda, syna eller 3-betta?",
    "F-F-RC5-F-RC15": "Du sitter på BTN och ÖPPNADE. SB foldade, BB 3-bettade. Ditt beslut: folda, syna eller 4-betta?",
    "F-F-RC5-RC16-F": "Du sitter på BTN och ÖPPNADE. SB 3-bettade, BB foldade. Ditt beslut: folda, syna eller 4-betta?",
    "F-RC5-RC17-F-F": "Du sitter på CO och ÖPPNADE. BTN 3-bettade, SB och BB foldade. Ditt beslut: folda, syna eller 4-betta?",
    "F-RC5-F-F-RC15": "Du sitter på CO och ÖPPNADE. BTN och SB foldade, BB 3-bettade. Ditt beslut: folda, syna eller 4-betta?",
    "RC5-F-RC17-F-F": "Du sitter UTG och ÖPPNADE. CO foldade, BTN 3-bettade, SB och BB foldade. Ditt beslut: folda, syna eller 4-betta?",
    "F-F-F-RC4-RC12": "Du sitter i SB och ÖPPNADE. BB 3-bettade. Ditt beslut: folda, syna eller 4-betta?",
    "F-F-RC5-RC16": "Du sitter i BB och har bara mörken i potten. BTN öppnade, SB 3-bettade. Kallsyna, folda eller 4-betta?",
    "F-RC5-C-F": "Du sitter i BB. CO öppnade, BTN synade, SB foldade. Folda, syna (multiway) eller squeeza?",
    "F-F-RC5-C": "Du sitter i BB. BTN öppnade, SB synade. Folda, syna (multiway) eller squeeza?",
    "F-F-F-C": "Du sitter i BB. Alla foldade till SB, som limpade (synade 1 bb). Checka eller höja?",
    "F-F-RC5-F-RC15-RC45": "Du sitter i BB. BTN öppnade, SB foldade, DU 3-bettade, BTN 4-bettade. Folda, syna eller all-in?",
    "F-RC5-RC17-F-F-RC51": "Du sitter på BTN. CO öppnade, DU 3-bettade, SB och BB foldade, CO 4-bettade. Folda, syna eller all-in?",
    "RC5-F-C-F": "Du sitter i BB. UTG öppnade, CO foldade, BTN synade, SB foldade. Folda, syna (multiway) eller squeeza?",
    "F-RC5-F-C": "Du sitter i BB. CO öppnade, BTN foldade, SB synade. Folda, syna (multiway) eller squeeza?",
    "F-RC5-C": "Du sitter i SB. CO öppnade, BTN synade. Folda, syna (ur position, multiway) eller squeeza?",
    "RC5-F-C": "Du sitter i SB. UTG öppnade, CO foldade, BTN synade. Folda, syna (ur position, multiway) eller squeeza?",
    "RC5-RC17": "Du sitter på BTN. UTG öppnade och CO 3-bettade. Folda, kallsyna 3-betten eller 4-betta?",
    "RC5-RC17-F": "Du sitter i SB. UTG öppnade, CO 3-bettade, BTN foldade. Folda, kallsyna 3-betten eller 4-betta?",
    "F-RC5-RC17": "Du sitter i SB. CO öppnade och BTN 3-bettade. Folda, kallsyna 3-betten eller 4-betta?",
    "RC5-C-C-F": "Du sitter i BB. UTG öppnade, CO och BTN synade, SB foldade. Folda, syna (multiway) eller squeeza?",
    "F-F-RC5-C-RC21": "Du sitter på BTN och ÖPPNADE. SB synade, BB squeezade. Ditt beslut: folda, syna eller 4-betta?",
    "F-RC5-F-C-RC21": "Du sitter på CO och ÖPPNADE. BTN foldade, SB synade, BB squeezade. Ditt beslut: folda, syna eller 4-betta?",
    "RC5-RC17-F-F-F": "Du sitter på UTG och ÖPPNADE. CO 3-bettade, resten foldade. Folda, syna eller 4-betta?",
    "RC5-F-F-RC16-F": "Du sitter på UTG och ÖPPNADE. SB 3-bettade, BB foldade. Folda, syna eller 4-betta?",
    "RC5-F-F-F-RC15": "Du sitter på UTG och ÖPPNADE. BB 3-bettade. Folda, syna eller 4-betta?",
    "F-RC5-F-RC16-F": "Du sitter på CO och ÖPPNADE. SB 3-bettade, BB foldade. Folda, syna eller 4-betta?",
    "RC5-C-C": "Du sitter i SB. UTG öppnade, CO och BTN synade. Folda, syna (multiway) eller squeeza?",
    "F-RC5-C-C-RC28": "Du sitter på CO och ÖPPNADE. BTN och SB synade, BB squeezade. Folda, syna eller 4-betta?",
    "RC5-C-C-F-RC29": "Du sitter på UTG och ÖPPNADE. CO och BTN synade, SB foldade, BB squeezade. Folda, syna eller 4-betta?",
    "RC5-F-F-C-RC21": "Du sitter på UTG och ÖPPNADE. SB synade, BB squeezade. Folda, syna eller 4-betta?",
    "RC5-RC17-RC58-F-F": "Du sitter på UTG och ÖPPNADE. CO 3-bettade, BTN 4-bettade, SB och BB foldade. Folda, syna eller all-in?",
    "RC5-F-F-C-RC21-C": "Du sitter i SB. UTG öppnade, DU synade, BB squeezade och UTG synade. Folda, syna eller 4-betta?",
    "RC5-F-F-RC16-C": "Du sitter på UTG och ÖPPNADE. SB 3-bettade, BB synade. Folda, syna eller 4-betta?",
    "RC5-C-RC24": "Du sitter i SB. UTG öppnade, CO synade, BTN squeezade. Folda, kallsyna eller 4-betta?",
    "RC5-RC17-C-F": "Du sitter i BB. UTG öppnade, CO 3-bettade, BTN synade, SB foldade. Folda, kallsyna eller 4-betta?",
    "RC5-F-C-C": "Du sitter i BB. UTG öppnade, CO foldade, BTN och SB synade. Folda, syna (multiway) eller squeeza?",
    "RC5-C-C-C": "Du sitter i BB. UTG öppnade, CO, BTN och SB synade. Folda, syna (multiway) eller squeeza?",
    "RC5-RC17-F-F": "Du sitter i BB. UTG öppnade, CO 3-bettade, BTN och SB foldade. Folda, kallsyna eller 4-betta?",
    "RC5-C-RC24-F": "Du sitter i BB. UTG öppnade, CO synade, BTN squeezade, SB foldade. Folda, kallsyna eller 4-betta?",
    "RC5-F-RC17-F": "Du sitter i BB. UTG öppnade, CO foldade, BTN 3-bettade, SB foldade. Folda, kallsyna eller 4-betta?",
    "RC5-F-RC17-C-F": "Du sitter på UTG och ÖPPNADE. BTN 3-bettade, SB synade, BB foldade. Folda, syna eller 4-betta?",
    "RC5-C-F-F": "Du sitter i BB. UTG öppnade, CO synade, BTN och SB foldade. Folda, syna (multiway) eller squeeza?",
}
