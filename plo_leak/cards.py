"""Kort, handutvärdering för Omaha och klassificering av starthänder."""
from __future__ import annotations

from collections import Counter
from itertools import combinations

RANKS = "23456789TJQKA"
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
SUITS = "cdhs"

CATEGORY_NAMES = {
    8: "färgstege",
    7: "fyrtal",
    6: "kåk",
    5: "färg",
    4: "stege",
    3: "triss",
    2: "två par",
    1: "par",
    0: "högt kort",
}


def parse_card(text: str) -> tuple[int, str]:
    text = text.strip()
    return RANK_VALUE[text[0].upper()], text[1].lower()


def parse_cards(text: str) -> list[tuple[int, str]]:
    return [parse_card(c) for c in text.split() if len(c) == 2]


def card_str(card: tuple[int, str]) -> str:
    return RANKS[card[0] - 2] + card[1]


def eval5(cards) -> tuple:
    """Utvärdera exakt fem kort. Större tupel = bättre hand."""
    ranks = sorted((c[0] for c in cards), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_high = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_high = 5
    if straight_high and flush:
        return (8, straight_high)
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [g[1] for g in groups]
    ordered = [g[0] for g in groups]
    if shape[0] == 4:
        return (7, *ordered)
    if shape == [3, 2]:
        return (6, *ordered)
    if flush:
        return (5, *ranks)
    if straight_high:
        return (4, straight_high)
    if shape[0] == 3:
        return (3, *ordered)
    if shape[:2] == [2, 2]:
        return (2, *ordered)
    if shape[0] == 2:
        return (1, *ordered)
    return (0, *ranks)


def best_omaha(hole, board) -> tuple:
    """Bästa hand med exakt två hålkort och tre bordskort."""
    best = None
    triples = list(combinations(board, 3))
    for pair in combinations(hole, 2):
        for t in triples:
            v = eval5(pair + t)
            if best is None or v > best:
                best = v
    return best


def nut_rank(hole, board) -> tuple[int, int]:
    """Hur många motståndarkombinationer (2 hålkort) slår handen på detta bord?

    Returnerar (antal kombos som slår oss, totalt antal kombos).
    0 = du hade nöten.
    """
    hero = best_omaha(hole, board)
    used = set(hole) | set(board)
    deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    triples = list(combinations(board, 3))
    beats = 0
    total = 0
    for pair in combinations(deck, 2):
        total += 1
        for t in triples:
            if eval5(pair + t) > hero:
                beats += 1
                break
    return beats, total


def beat_fraction(hole, board, samples: int = 300, seed: int = 0) -> float:
    """Andel av motståndarens möjliga 2-kortskombinationer som slår handen.

    Uppskattas med ett fast slumpurval (snabbt nog för tusentals händer);
    felmarginalen är runt ±1 procentenhet."""
    import random
    hero = best_omaha(hole, board)
    used = set(hole) | set(board)
    deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]
    pairs = list(combinations(deck, 2))
    if len(pairs) > samples:
        pairs = random.Random(seed).sample(pairs, samples)
    triples = list(combinations(board, 3))
    beats = 0
    for pair in pairs:
        for t in triples:
            if eval5(pair + t) > hero:
                beats += 1
                break
    return beats / len(pairs)


def hand_name(value: tuple) -> str:
    return CATEGORY_NAMES[value[0]]


# ---------------------------------------------------------------- starthänder

def _connectivity(ranks) -> int:
    """Max antal unika valörer inom ett fönster på fem valörer (ess räknas även som 1)."""
    uniq = set(ranks)
    if 14 in uniq:
        uniq.add(1)
    return max(sum(1 for r in uniq if low <= r <= low + 4) for low in range(1, 11))


def classify_start_plo6(hole) -> dict:
    """PLO6: nötpotential styrs av suited ess, sammanhängning och att korten
    inte 'blockerar sig själva' (trips eller 4+ kort i samma färg)."""
    suits = Counter(c[1] for c in hole)
    ranks = [c[0] for c in hole]
    rc = Counter(ranks)
    suited_ace = any(c[0] == 14 and suits[c[1]] >= 2 for c in hole)
    overloaded = max(suits.values()) >= 4
    trips = max(rc.values()) >= 3
    groups = sum(1 for n in suits.values() if n >= 2)
    conn = _connectivity(ranks)
    has_aa = rc.get(14, 0) >= 2
    if trips or overloaded:
        bucket = "Trips / 4+ i samma färg"
    elif suited_ace and conn >= 4:
        bucket = "Suited ess + rundown"
    elif suited_ace:
        bucket = "Suited ess"
    elif conn >= 4:
        bucket = "Rundown utan suited ess"
    else:
        bucket = "Svag struktur"
    weak = bucket in ("Trips / 4+ i samma färg", "Svag struktur") and not has_aa
    return {
        "suit": "TS" if groups >= 3 else ("DS" if groups == 2 else "SS"),
        "pairs": sorted((r for r, n in rc.items() if n >= 2), reverse=True),
        "dangler": False,
        "aa": has_aa,
        "suited_ace": suited_ace,
        "conn": conn,
        "bucket": bucket,
        "weak": weak,
    }


NUT_LABELS = {0: "0 nöt-egenskaper", 1: "1 nöt-egenskap", 2: "2 nöt-egenskaper", 3: "3 nöt-egenskaper"}


def nut_qualities(hole) -> tuple[bool, bool, bool]:
    key = tuple(hole)
    try:
        q = _NQ_MEMO.get(key)
    except TypeError:
        return _nut_qualities(hole)
    if q is None:
        if len(_NQ_MEMO) >= 256:
            _NQ_MEMO.clear()
        q = _NQ_MEMO[key] = _nut_qualities(hole)
    return q


def _nut_qualities(hole) -> tuple[bool, bool, bool]:
    """Grinders Vaults tre nöt-egenskaper för PLO6:
    högt par (knektar eller bättre, inte trips), suited ess (2–3 kort i essets färg)
    och rundown (fyra olika valörer från 5 och uppåt inom ett spann på högst fem valörer,
    alltså högst en lucka)."""
    suits = Counter(c[1] for c in hole)
    rc = Counter(c[0] for c in hole)
    high_pair = any(r >= 11 and n == 2 for r, n in rc.items())
    suited_ace = any(c[0] == 14 and 2 <= suits[c[1]] <= 3 for c in hole)
    rs = sorted(r for r in rc if r >= 5)
    rundown = any(rs[i + 3] - rs[i] <= 4 for i in range(len(rs) - 3))
    return high_pair, suited_ace, rundown


def nut_combo_label(q) -> str:
    names = [n for n, v in zip(("högt par", "suited ess", "rundown"), q) if v]
    return " + ".join(names) if names else "ingen"


_CS_MEMO: dict = {}
_NQ_MEMO: dict = {}


def classify_start(hole) -> dict:
    """Klassificering av starthanden. De senaste händerna minns (samma hand klassas flera gånger
    när fakta räknas fram); varje anrop får en egen kopia, så ingen anropare kan ändra en annans."""
    key = tuple(hole)
    try:
        d = _CS_MEMO.get(key)
    except TypeError:  # kort som listor (t.ex. från JSON) – räkna direkt
        return _classify_start(hole)
    if d is None:
        if len(_CS_MEMO) >= 64:
            _CS_MEMO.clear()
        d = _CS_MEMO[key] = _classify_start(hole)
    return {k: (list(v) if isinstance(v, list) else v) for k, v in d.items()}


def _classify_start(hole) -> dict:
    d = classify_start_plo6(hole) if len(hole) >= 6 else classify_start_plo4(hole)
    q = nut_qualities(hole)
    d["nut_q"] = q
    d["nut_n"] = sum(q)
    d["nut"] = NUT_LABELS[sum(q)]
    d["nut_combo"] = nut_combo_label(q)
    return d


def classify_start_plo4(hole) -> dict:
    """PLO4/PLO5-klassificering: färgstruktur, par, dangler."""
    suits = Counter(c[1] for c in hole)
    suited_groups = sorted((n for n in suits.values() if n >= 2), reverse=True)
    if len(suited_groups) >= 2:
        suit_cls = "DS"
    elif len(suited_groups) == 1 and suited_groups[0] <= 3:
        suit_cls = "SS"
    else:
        suit_cls = "R"  # regnbåge eller fyra i samma färg (lika dåligt)

    ranks = [c[0] for c in hole]
    rc = Counter(ranks)
    pairs = sorted((r for r, n in rc.items() if n >= 2), reverse=True)

    # Dangler: ett kort som inte hänger ihop (avstånd > 4) med något annat kort,
    # inte är parat och inte är ett suited ess.
    suited_aces = any(c[0] == 14 and suits[c[1]] >= 2 for c in hole)
    dangler = False
    for i, c in enumerate(hole):
        r = c[0]
        if rc[r] >= 2:
            continue
        if r == 14 and suited_aces:
            continue
        others = [o[0] for j, o in enumerate(hole) if j != i]
        dists = []
        for o in others:
            d = abs(r - o)
            if r == 14 or o == 14:
                low = 1 if r == 14 else r
                low_o = 1 if o == 14 else o
                d = min(d, abs(low - low_o))
            dists.append(d)
        if min(dists) > 4:
            dangler = True
            break

    has_aa = rc.get(14, 0) >= 2
    if has_aa:
        bucket = "AA"
    else:
        name = {"DS": "Dubbelfärgad", "SS": "Enkelfärgad", "R": "Regnbåge"}[suit_cls]
        bucket = name + (" + dangler" if dangler else "")
    weak = (suit_cls == "R" or dangler) and not has_aa and not (pairs and pairs[0] >= 12 and suit_cls != "R")
    return {
        "suit": suit_cls,
        "pairs": pairs,
        "dangler": dangler,
        "aa": has_aa,
        "bucket": bucket,
        "weak": weak,
    }
