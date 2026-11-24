"""Parser för handhistorik i GGPoker-format (PLO / PLO-5 / PLO-6, cashgame).

Läser även PokerStars-liknande format och filer exporterade från DriveHUD 3
("Export All Hands" skapar filer som dh_exported_file_0 utan filändelse).
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .cards import parse_cards

AMT = r"[^\d\s(]?(\d[\d,]*(?:\.\d+)?)"

RE_HEADER = re.compile(
    r"Hand #(?P<id>[^\s:]+):\s*(?P<game>.+?)\s*\(" + r"[^\d]?(?P<sb>[\d,.]+)/[^\d]?(?P<bb>[\d,.]+)"
    + r"(?:[^)]*)\)\s*-\s*(?P<date>\d{4}/\d{2}/\d{2} \d{1,2}:\d{2}:\d{2})"
)
RE_TABLE = re.compile(r"Table '(?P<table>[^']*)'\s*(?P<max>\d+)-max\s*Seat #(?P<button>\d+) is the button")
RE_SEAT = re.compile(r"^Seat (?P<seat>\d+): (?P<name>.+?) \(" + AMT + r" in chips\)")
RE_DEALT = re.compile(r"^Dealt to (?P<name>.+?) \[(?P<cards>[^\]]+)\]")
RE_STREET = re.compile(r"^\*\*\* (?P<name>[A-Z ]+?) \*\*\*(?P<rest>.*)$")
RE_ACTION = re.compile(
    r"^(?P<name>.+?): (?P<act>folds|checks|calls|bets|raises|posts|straddle|shows|mucks)(?P<rest>.*)$"
)
RE_UNCALLED = re.compile(r"^Uncalled bet \(" + AMT + r"\) returned to (?P<name>.+)$")
RE_COLLECTED = re.compile(r"^(?P<name>.+?) collected " + AMT + r" from")
RE_CASHOUT = re.compile(r"^(?P<name>.+?): Receives Cashout \(" + AMT + r"\)")
RE_CASHOUT_FEE = re.compile(r"^(?P<name>.+?): Pays Cashout Risk \(" + AMT + r"\)")
RE_RAKE = re.compile(r"Total pot " + AMT + r".*?Rake " + AMT)
# 2.87 (R2-01): GG:s "received ($x) from time bank card," / "bought time bank card ($x)," före "showed" ingår inte i namnet
RE_SUMMARY_SHOWED = re.compile(r"^Seat \d+: (?P<name>.+?)(?: \([^)]*\))*"
                               r"(?: (?:received \([^)]*\) from time bank card|bought time bank card \([^)]*\)),?)? showed \[(?P<cards>[^\]]+)\]")

STREET_MAP = {
    "HOLE CARDS": "preflop",
    "FLOP": "flop",
    "TURN": "turn",
    "RIVER": "river",
    "FIRST FLOP": "flop",
    "FIRST TURN": "turn",
    "FIRST RIVER": "river",
    "SHOWDOWN": "showdown",
    "FIRST SHOWDOWN": "showdown",
    "SUMMARY": "summary",
}

POSTFLOP_ORDER = ["SB", "BB", "UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN"]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass(slots=True)
class Action:
    street: str
    player: str
    kind: str  # post_sb, post_bb, post_straddle, post_dead, fold, check, call, bet, raise
    added: float = 0.0  # pengar som lades in i potten av denna action
    to: float = 0.0  # spelarens totala insats på gatan efter actionen
    allin: bool = False
    inferred: bool = False  # fold som inte stod i historiken men som måste ha skett


@dataclass(slots=True)
class Hand:
    id: str
    game: str
    sb: float
    bb: float
    date: datetime
    table: str = ""
    max_seats: int = 6
    button_seat: int = 0
    seats: dict = field(default_factory=dict)  # namn -> sittplats
    stacks: dict = field(default_factory=dict)  # namn -> stack
    positions: dict = field(default_factory=dict)  # namn -> position
    hole: dict = field(default_factory=dict)  # namn -> kort
    actions: list = field(default_factory=list)
    board: list = field(default_factory=list)
    invested: dict = field(default_factory=dict)
    collected: dict = field(default_factory=dict)
    shown: dict = field(default_factory=dict)
    rake: float = 0.0
    total_pot: float = 0.0
    raw: str = ""
    run_twice: bool = False
    header_stakes: tuple = ()  # (sb, bb) enligt rubriken, för diagnostik
    corrupt: bool = False  # historiken hade inkonsekventa belopp som rättats
    inferred: list = field(default_factory=list)  # (spelare, gata) för härledda folds
    cashout_fee: dict = field(default_factory=dict)  # GG EV Cashout-premie (betalas utanför potten)
    cashout_recv: dict = field(default_factory=dict)  # GG EV Cashout-utbetalning (inte en vunnen pott)

    # --- hjälpfunktioner
    def net(self, name: str) -> float:
        return (self.collected.get(name, 0.0) + self.cashout_recv.get(name, 0.0)
                - self.invested.get(name, 0.0))

    def contrib(self, name: str) -> float:
        """Det spelaren lagt i själva potten (utan EV Cashout-premie)."""
        return self.invested.get(name, 0.0) - self.cashout_fee.get(name, 0.0)

    def pot_size(self) -> float:
        return sum(self.invested.values()) - sum(self.cashout_fee.values())

    def net_bb(self, name: str) -> float:
        return self.net(name) / self.bb if self.bb else 0.0

    def street_actions(self, street: str) -> list:
        return [a for a in self.actions if a.street == street]

    def folded_on(self, name: str):
        for a in self.actions:
            if a.player == name and a.kind == "fold":
                return a.street
        return None

    def remaining(self) -> list:
        folded = {a.player for a in self.actions if a.kind == "fold"}
        return [p for p in self.seats if p not in folded]

    def went_to_showdown(self) -> bool:
        return len(self.remaining()) >= 2

    def postflop_index(self, name: str) -> int:
        pos = self.positions.get(name, "")
        return POSTFLOP_ORDER.index(pos) if pos in POSTFLOP_ORDER else -1

    @property
    def num_hole(self) -> int:
        for cards in self.hole.values():
            return len(cards)
        return 4


NO_SB_LABEL = "SB-plats utan blind"


def _assign_positions(hand: Hand, sb_player, bb_player) -> None:
    seats_sorted = sorted(hand.seats.items(), key=lambda kv: kv[1])
    names = [n for n, _ in seats_sorted]
    n = len(names)
    if n == 0:
        return
    # börja vid knappen och gå medurs
    btn_idx = 0
    for i, (name, seat) in enumerate(seats_sorted):
        if seat == hand.button_seat:
            btn_idx = i
            break
    else:
        # knappen kan sitta på en tom plats: ta närmaste plats före
        cands = [i for i, (_, s) in enumerate(seats_sorted) if s < hand.button_seat]
        btn_idx = cands[-1] if cands else n - 1
    order = names[btn_idx:] + names[:btn_idx]  # BTN, SB, BB, ...
    if n == 2:
        hand.positions = {order[0]: "BTN", order[1]: "BB"}
        return
    pos = {order[0]: "BTN"}
    if sb_player is None and bb_player in order and bb_player != order[0]:
        # Ingen small blind postad (t.ex. död SB): ingen får etiketten SB (ingen blind är investerad).
        # En spelare på SB-platsen (mellan knappen och BB) agerar ändå först postflop – den får en
        # egen etikett i stället för en sen position (okänd etikett räknas som först att agera).
        bb = bb_player
        for p in order[1:order.index(bb)]:
            pos[p] = NO_SB_LABEL
    else:
        sb = sb_player if sb_player in order and sb_player != order[0] else order[1]
        pos[sb] = "SB"
        bb = bb_player if bb_player in order and bb_player not in pos else order[2]
    pos[bb] = "BB"
    start = order.index(bb) + 1
    rest = [p for p in order[start:] + order[:start] if p not in pos]
    labels = ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO"]
    for p, lab in zip(rest, labels[-len(rest):] if rest else []):
        pos[p] = lab
    hand.positions = pos


def fix_dead_sb_positions(hand: Hand) -> None:
    """Rättar positionerna i redan sparade händer utan postad small blind (så att databasen inte
    behöver parsas om): spelaren på SB-platsen får NO_SB_LABEL i stället för en sen position."""
    if any(a.kind == "post_sb" for a in hand.actions):
        return
    bb = next((a.player for a in hand.actions if a.kind == "post_bb"), None)
    _assign_positions(hand, None, bb)


def parse_hand(text: str) -> Hand | None:
    lines = [l.rstrip() for l in text.strip().splitlines()]
    if not lines:
        return None
    m = RE_HEADER.search(lines[0])
    if not m:
        return None
    game = m.group("game")
    if "Omaha" not in game and "PLO" not in game:
        return None
    hand = Hand(
        id=m.group("id"),
        game=game,
        sb=_num(m.group("sb")),
        bb=_num(m.group("bb")),
        date=datetime.strptime(m.group("date"), "%Y/%m/%d %H:%M:%S"),
        raw=text.strip(),
    )
    hand.header_stakes = (hand.sb, hand.bb)
    street = "preflop"
    contrib: dict[str, float] = {}
    sb_player = bb_player = None
    in_summary = False
    second_run = False
    closed: set = set()

    def close(st):
        if st not in closed and st in ("preflop", "flop", "turn", "river"):
            closed.add(st)
            _close_street(hand, st, contrib)

    for line in lines[1:]:
        if not line:
            continue
        if in_summary:
            ms = RE_SUMMARY_SHOWED.match(line)
            if ms and ms.group("name") not in hand.shown:
                hand.shown[ms.group("name")] = parse_cards(ms.group("cards"))
            mr = RE_RAKE.search(line)
            if mr:
                hand.total_pot = _num(mr.group(1))
                # Alla avgifter som dras från potten: rake + GG:s jackpot/bingo/fortune/tax
                hand.rake = sum(_num(x) for x in re.findall(
                    r"(?:Rake|Jackpot|Bingo|Fortune|Tax) [^\d\s]?(\d[\d,]*(?:\.\d+)?)", line))
            continue
        mt = RE_TABLE.search(line) if "Table '" in line else None
        if mt:
            hand.table = mt.group("table")
            hand.max_seats = int(mt.group("max"))
            hand.button_seat = int(mt.group("button"))
            continue
        ms = RE_SEAT.match(line) if line.startswith("Seat ") else None
        if ms and street == "preflop" and not hand.actions:
            name = ms.group("name")
            hand.seats[name] = int(ms.group("seat"))
            hand.stacks[name] = _num(ms.group(3))
            hand.invested[name] = 0.0
            continue
        mstreet = RE_STREET.match(line) if line.startswith("*** ") else None
        if mstreet:
            sname = mstreet.group("name").strip()
            if sname.startswith("SECOND") or sname.startswith("THIRD"):
                hand.run_twice = True
                second_run = True
                continue
            if sname.startswith("FIRST"):
                hand.run_twice = True
            new = STREET_MAP.get(sname)
            if new and new != street:
                close(street)
            if new == "summary":
                in_summary = True
                continue
            if new in ("flop", "turn", "river") and not second_run:
                cards = parse_cards(" ".join(re.findall(r"\[([^\]]+)\]", mstreet.group("rest"))))
                if cards:
                    hand.board = cards
            if new and new != street:
                street = new
                contrib = {}
            continue
        md = RE_DEALT.match(line) if line.startswith("Dealt to ") else None
        if md:
            hand.hole[md.group("name")] = parse_cards(md.group("cards"))
            continue
        mu = RE_UNCALLED.match(line) if line.startswith("Uncalled bet (") else None
        if mu:
            name = mu.group("name").strip()
            hand.invested[name] = hand.invested.get(name, 0.0) - _num(mu.group(1))
            continue
        mc = RE_COLLECTED.match(line) if " collected " in line else None
        if mc:
            name = mc.group("name")
            hand.collected[name] = hand.collected.get(name, 0.0) + _num(mc.group(2))
            continue
        mco = RE_CASHOUT.match(line) if ": Receives Cashout (" in line else None
        if mco:
            name = mco.group("name")
            hand.cashout_recv[name] = hand.cashout_recv.get(name, 0.0) + _num(mco.group(2))
            continue
        mcf = RE_CASHOUT_FEE.match(line) if ": Pays Cashout Risk (" in line else None
        if mcf:
            name = mcf.group("name")
            hand.invested[name] = hand.invested.get(name, 0.0) + _num(mcf.group(2))
            hand.cashout_fee[name] = hand.cashout_fee.get(name, 0.0) + _num(mcf.group(2))
            continue
        ma = RE_ACTION.match(line)
        if not ma:
            continue
        name, act, rest = ma.group("name"), ma.group("act"), ma.group("rest")
        if name not in hand.seats:
            continue
        allin = "all-in" in rest
        amounts = [_num(x) for x in re.findall(r"(\d[\d,]*(?:\.\d+)?)", rest)]
        if act == "shows":
            mcards = re.search(r"\[([^\]]+)\]", rest)
            if mcards:
                hand.shown[name] = parse_cards(mcards.group(1))
            continue
        if act == "mucks":
            continue
        cur = contrib.get(name, 0.0)
        if act == "straddle":
            # GG: "P1: straddle $2" – beloppet är spelarens totala insats (även vid re-straddle)
            to = amounts[-1] if amounts else 0.0
            added = max(to - cur, 0.0)
            contrib[name] = cur + added
            hand.invested[name] += added
            hand.actions.append(Action(street, name, "post_straddle", added, cur + added))
            continue
        if act == "posts":
            amt = amounts[-1] if amounts else 0.0
            low = rest.lower()
            if "small & big" in low or "small and big" in low:
                # PokerStars-format: död SB + BB i samma rad. BB-delen är levande, SB-delen död.
                hs_ = hand.header_stakes
                bb_part = hs_[1] if hs_ and 0 < hs_[1] < amt else amt / 1.5
                dead = max(amt - bb_part, 0.0)
                hand.invested[name] += dead
                hand.actions.append(Action(street, name, "post_dead", dead, cur))
                contrib[name] = cur + bb_part
                hand.invested[name] += bb_part
                hand.actions.append(Action(street, name, "post_bb", bb_part, cur + bb_part, allin))
                bb_player = bb_player or name
                continue
            if "small blind" in low:
                kind = "post_sb"
                sb_player = sb_player or name
            elif "big blind" in low:
                kind = "post_bb"
                bb_player = bb_player or name
                # Vissa GG/DriveHUD-händer har korrupt BB-belopp (t.ex. $6 på $0.5/$1).
                # (Inte om SB är all-in med en kort stack – då säger SB-beloppet inget.)
                sb_amt = next((a.added for a in hand.actions if a.kind == "post_sb" and not a.allin), None)
                hs_ = hand.header_stakes
                header_ok = bool(hs_ and hs_[1] > 0 and abs(amt - hs_[1]) < 1e-9
                                 and (sb_amt is None or abs(sb_amt - hs_[0]) < 1e-9))
                if sb_amt and not allin and not header_ok and amt > 2 * sb_amt * 1.01:
                    amt = 2 * sb_amt
                    hand.corrupt = True
            elif "straddle" in low:
                kind = "post_straddle"
            else:
                kind = "post_dead"
            if kind == "post_dead":
                hand.invested[name] += amt
                hand.actions.append(Action(street, name, kind, amt, cur))
            else:
                contrib[name] = cur + amt
                hand.invested[name] += amt
                hand.actions.append(Action(street, name, kind, amt, cur + amt, allin))
            continue
        if act in ("folds", "checks"):
            hand.actions.append(Action(street, name, act[:-1] if act == "folds" else "check", 0.0, cur))
            continue
        if act in ("calls", "bets"):
            amt = amounts[0] if amounts else 0.0
            if act == "calls" and not allin and contrib:
                # En syn matchar alltid högsta insatsen. Historikens belopp stämmer inte
                # alltid (sett i GG-exporter), så lita på matchningen.
                mx = max(contrib.values())
                if mx > cur and abs((cur + amt) - mx) > 1e-6:
                    amt = mx - cur
                    hand.corrupt = True
            contrib[name] = cur + amt
            hand.invested[name] += amt
            hand.actions.append(Action(street, name, act[:-1] if act == "calls" else "bet", amt, cur + amt, allin))
            continue
        if act == "raises":
            to = amounts[1] if len(amounts) > 1 else (amounts[0] if amounts else 0.0)
            added = to - cur
            contrib[name] = to
            hand.invested[name] += added
            hand.actions.append(Action(street, name, "raise", added, to, allin))
            continue

    close(street)
    # En härledd fold är fel om spelaren agerar senare i handen – ta bort den.
    if hand.inferred:
        keep_inf = []
        for p_, st_ in list(hand.inferred):
            idx = next(i for i, a in enumerate(hand.actions) if a.inferred and a.player == p_ and a.street == st_)
            if any(a.player == p_ and not a.inferred for a in hand.actions[idx + 1:]):
                hand.actions.pop(idx)
            else:
                keep_inf.append((p_, st_))
        hand.inferred = keep_inf
    # Blinds hämtas från de faktiskt postade beloppen – rubrikens format varierar.
    # All-in-postningar (kort stack) säger inget om nivån och hoppas över.
    sb_posts = [a.added for a in hand.actions if a.kind == "post_sb" and not a.allin]
    bb_posts = [a.added for a in hand.actions if a.kind == "post_bb" and not a.allin]
    hs = hand.header_stakes
    if sb_posts and sb_posts[0] > 0:
        hand.sb = sb_posts[0]
        hand.bb = 2 * sb_posts[0]  # GG: alltid 1:2
        if hs and hs[1] > 0 and abs(hs[0] - sb_posts[0]) < 1e-9 and any(abs(b - hs[1]) < 1e-9 for b in bb_posts):
            hand.bb = hs[1]  # t.ex. $0.10/$0.25: rubriken och postad BB stämmer överens
        elif hs and hs[1] > 0 and abs(hs[0] - sb_posts[0]) < 1e-9 and not bb_posts \
                and 2.0 - 1e-9 <= hs[1] / hs[0] <= 2.5 + 1e-9:
            hand.bb = hs[1]  # 2.81: BB postade kort (all-in) – rubriken stämmer med SB och är en giltig nivå
    elif bb_posts and max(bb_posts) > 0:
        hand.bb = max(bb_posts)
        hand.sb = hand.bb / 2
    elif hand.header_stakes and hand.header_stakes[1] > 0 and hand.header_stakes[0] > 0:
        hand.sb, hand.bb = hand.header_stakes
    else:
        # Alla blinds är all-in och rubriken är trasig: använd all-in-postningarna.
        sb_ai = [a.added for a in hand.actions if a.kind == "post_sb" and a.added > 0]
        bb_ai = [a.added for a in hand.actions if a.kind == "post_bb" and a.added > 0]
        hand.bb = max([2 * x for x in sb_ai] + bb_ai + [0.0])
        hand.sb = hand.bb / 2
    # En BB-postning som är större än rubrikens nivå när ingen normal SB finns att jämföra med
    # kan inte rättas säkert – handen hoppas över (mycket sällsynt).
    hs = hand.header_stakes
    if hs and hs[0] > 0 and abs(hs[1] - 2 * hs[0]) < 1e-9 and hand.bb > hs[1] * 1.01 \
            and not any(a.kind == "post_sb" and not a.allin for a in hand.actions):
        return None
    if hand.bb <= 0:
        return None
    if not _cards_ok(hand):
        return None  # trasig hand (okänd färg, fel antal kort, samma kort två gånger) – räknas som oläslig
    _assign_positions(hand, sb_player, bb_player)
    return hand


VALID_SUITS = set("cdhs")


def _cards_ok(hand) -> bool:
    seen = set()
    sizes = set()
    for cards in list(hand.hole.values()) + list(hand.shown.values()):
        if not cards:
            continue
        sizes.add(len(cards))
    # 2.80: ett fysiskt kort får bara finnas på ett ställe – hålkort, visade kort (andra spelare) och bordet.
    # Samma spelares utdelade och visade kort får vara desamma.
    per_player = {}
    for who, cards in list(hand.hole.items()) + list(hand.shown.items()):
        if not cards:
            continue
        cs = frozenset(cards)
        if len(cs) != len(cards):
            return False
        if who in per_player and per_player[who] != cs:
            return False
        per_player[who] = cs
    for cards in list(per_player.values()) + [hand.board]:
        for c in cards or []:
            if c[1] not in VALID_SUITS or not 2 <= c[0] <= 14 or c in seen:
                return False
            seen.add(c)
    if len(hand.board) > 5 or any(n not in (4, 5, 6) for n in sizes) or len(sizes) > 1:
        return False
    return True


def _close_street(hand: Hand, street: str, contrib: dict) -> None:
    """En spelare som inte matchat högsta insatsen när gatan tar slut (och inte är
    all-in) har foldat – även om fold-raden saknas i historiken."""
    folded = {a.player for a in hand.actions if a.kind == "fold"}
    mx = max(contrib.values(), default=0.0)
    if mx <= 0:
        return
    for p in hand.seats:
        if p in folded or contrib.get(p, 0.0) >= mx - 1e-6:
            continue
        if hand.stacks.get(p, 0.0) - hand.invested.get(p, 0.0) <= 1e-6:
            continue  # all-in
        hand.actions.append(Action(street, p, "fold", 0.0, contrib.get(p, 0.0), inferred=True))
        hand.inferred.append((p, street))


RE_HAND_START = re.compile(r"^(?:[A-Za-z]+ )*Hand #[^\s:]+:", re.M)


def split_hands(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    starts = [m.start() for m in RE_HAND_START.finditer(text)]
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def parse_text(text: str) -> list[Hand]:
    hands = []
    for chunk in split_hands(text):
        try:
            h = parse_hand(chunk)
        except Exception:  # en trasig hand ska inte stoppa hela analysen
            h = None
        if h:
            hands.append(h)
    return hands


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="ignore")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def looks_like_hh(head: bytes) -> bool:
    """Snabbkoll av filens början: innehåller den handhistorik?"""
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        head = head.decode("utf-16", errors="ignore").encode()
    return b"Hand #" in head


def parse_bytes(name: str, data: bytes, depth: int = 0, budget: dict | None = None) -> list[Hand]:
    if name.lower().endswith(".zip"):
        hands = []
        budget = budget if budget is not None else {"total": 0}   # 2.81: gemensam budget för alla nivåer
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zip_members(zf, budget):
                    data = zf.read(info)
                    if info.filename.lower().endswith(".zip"):
                        if depth < ZIP_MAX_DEPTH:
                            hands.extend(parse_bytes(info.filename, data, depth + 1, budget))
                    elif looks_like_hh(data[:4096]):
                        hands.extend(parse_text(_decode(data)))
        except ZIP_ERRORS:
            pass  # trasig eller krypterad zip hoppas över
        return hands
    return parse_text(_decode(data))


SKIP_SUFFIXES = {".db", ".sqlite", ".exe", ".dll", ".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".pdf", ".html",
                 ".xml", ".json", ".log", ".dmg", ".pkg", ".iso", ".mp4", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".m4a",
                 ".app", ".msi", ".7z", ".rar", ".gz", ".tar", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".key", ".numbers", ".pages", ".psd", ".ai", ".svg", ".ttf", ".otf", ".woff", ".crdownload", ".part"}
ZIP_MEMBER_MAX = 200 * 1024 * 1024  # zip-i-zip över den här storleken läses inte (måste rymmas i minnet)
ZIP_STREAM_FROM = 64 * 1024 * 1024  # textfiler över den här storleken läses i delar (2.73), inte i ett svep
ZIP_STREAM_PIECE = 32 * 1024 * 1024
ZIP_TOTAL_MAX = 2 * 1024 * 1024 * 1024  # högst så mycket uppackad text per zip-fil (skydd mot zip-bomber)
ZIP_MAX_MEMBERS = 20000
ZIP_MAX_DEPTH = 3
import zlib as _zlib
ZIP_ERRORS = (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError, ValueError,
              _zlib.error, KeyError)
MAX_BLOCK = 64 * 1024 * 1024   # 2.81: högsta textblock utan handstart vid strömmande läsning
ZIP_REJECTED: list = []  # (zip, fil i zip, skäl) – töms av den som läser in, visas efter inläsningen


def _reject(zf, name, why):
    row = (str(getattr(zf, "filename", None) or "zip i zip"), str(name), why)
    if row not in ZIP_REJECTED and len(ZIP_REJECTED) < 200:
        ZIP_REJECTED.append(row)


def zip_members(zf, budget: dict | None = None):
    """Filer i en zip som kan innehålla handhistorik (inga mappar, ingen Mac-metadata).
    Högst ZIP_MAX_MEMBERS filer och ZIP_TOTAL_MAX uppackade byte per zip. Det som avvisas för storlek
    antecknas i ZIP_REJECTED (2.73) – tidigare hoppades stora filer över utan besked."""
    # 2.81: budget delas av alla nivåer (zip i zip får ingen ny budget)
    if budget is None:
        budget = {"total": 0}
    for k, info in enumerate(zf.infolist()):
        if k >= ZIP_MAX_MEMBERS:
            _reject(zf, "…", f"fler än {ZIP_MAX_MEMBERS} filer i zip-filen – resten lästes inte")
            return
        name = info.filename
        base = name.rsplit("/", 1)[-1]
        if info.is_dir() or info.file_size == 0 or name.startswith("__MACOSX/") or base.startswith("."):
            continue
        suf = ("." + base.rsplit(".", 1)[-1].lower()) if "." in base else ""
        if suf in SKIP_SUFFIXES:
            continue
        if suf == ".zip" and info.file_size > ZIP_MEMBER_MAX:
            _reject(zf, name, f"zip i zip på {info.file_size / 1e6:.0f} MB (gräns {ZIP_MEMBER_MAX // 2**20} MB) – packa upp den och läs in mappen")
            continue
        budget["total"] = budget.get("total", 0) + info.file_size
        if budget["total"] > ZIP_TOTAL_MAX:
            _reject(zf, name, f"zip-filen innehåller mer än {ZIP_TOTAL_MAX // 2**30} GB uppackat – packa upp den och läs in mappen")
            return
        yield info


_RE_START_B = re.compile(rb"^(?:[A-Za-z]+ )*Hand #[^\s:]+:", re.M)


def zip_member_texts(zf, info):
    """Texten i en zip-medlem. Små filer i ett svep; stora (2.73) i delar som bryts vid en handstart,
    så att t.ex. en export på 300 MB i en enda textfil kan läsas utan att allt ligger i minnet två gånger."""
    with zf.open(info) as fh:
        head = fh.read(4096)
        if not looks_like_hh(head):
            return
        if info.file_size <= ZIP_STREAM_FROM or head[:2] in (b"\xff\xfe", b"\xfe\xff"):
            yield _decode(head + fh.read())
            return
        buf = head
        while True:
            piece = fh.read(ZIP_STREAM_PIECE)
            if not piece:
                break
            buf += piece
            last = None
            for m in _RE_START_B.finditer(buf, max(len(buf) - 4 * 1024 * 1024, 1)):
                last = m.start()
            if last:
                yield _decode(buf[:last])
                buf = buf[last:]
            elif len(buf) > MAX_BLOCK:   # 2.81: ingen handstart på länge – inte handhistorik, avbryt med orsak
                _reject(zf, info.filename, f"mer än {MAX_BLOCK // 2**20} MB text utan en ny hand – resten lästes inte")
                return
        if buf:
            yield _decode(buf)


def zip_has_hh(path, depth: int = 0) -> bool:
    """Snabbkoll: innehåller zip-filen handhistorik? Läser bara början av några filer."""
    try:
        with zipfile.ZipFile(path) as zf:
            # 2.81: textfiler först och fler kontroller – en handhistorik efter 50 informationsfiler hittades inte
            members = sorted(zip_members(zf), key=lambda i: not i.filename.lower().endswith((".txt", ".zip")))
            for k, info in enumerate(members):
                if k >= 500:
                    break
                if info.filename.lower().endswith(".zip"):
                    if depth < 2 and zip_has_hh(io.BytesIO(zf.read(info)), depth + 1):
                        return True
                    continue
                with zf.open(info) as fh:
                    if looks_like_hh(fh.read(4096)):
                        return True
    except ZIP_ERRORS:
        return False  # trasig, krypterad eller ofullständigt nedladdad zip
    return False


def _walk(root: Path, max_depth: int = 6):
    """Alla filer under en mapp. Dolda mappar och Mac-programpaket (.app) hoppas över."""
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_symlink() and e.is_dir():
                    continue  # länkar till mappar följs inte (kan ge oändliga slingor)
                if e.is_dir():
                    if depth < max_depth and e.suffix.lower() not in (".app", ".photoslibrary", ".bundle", ".download"):
                        stack.append((e, depth + 1))
                elif e.is_file():
                    yield e
            except OSError:
                continue


def find_files(paths) -> list[Path]:
    """Alla filer som ser ut att innehålla handhistorik (oavsett filändelse)."""
    out = []
    for p in paths:
        p = Path(p).expanduser()
        files = sorted(_walk(p)) if p.is_dir() else [p]
        for f in files:
            if not f.is_file() or f.name.startswith(".") or f.suffix.lower() in SKIP_SUFFIXES:
                continue
            if f.suffix.lower() == ".zip":
                if zip_has_hh(f):
                    out.append(f)
                continue
            try:
                with open(f, "rb") as fh:
                    if looks_like_hh(fh.read(4096)):
                        out.append(f)
            except (OSError, ValueError):
                continue
    return out


PARSER_VERSION = 10  # höj när parsningen ändras, så att gammal cache ignoreras


def _cache_dir():
    import os
    d = Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache"))
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        return None


def _cached_parse(f: Path, cache) -> list[Hand]:
    """Parsa en fil, eller läs den färdigparsade versionen från cachen om filen inte ändrats."""
    import hashlib
    import pickle
    if cache is None:
        return parse_bytes(f.name, f.read_bytes())
    st = f.stat()
    key = hashlib.sha1(f"{f.resolve()}|{st.st_size}|{st.st_mtime_ns}|{PARSER_VERSION}".encode()).hexdigest()
    cf = cache / f"{key}.pkl"
    if cf.exists():
        try:
            with open(cf, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass
    hands = parse_bytes(f.name, f.read_bytes())
    try:
        with open(cf, "wb") as fh:
            pickle.dump(hands, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass
    return hands


def load_paths(paths, progress=None, use_cache: bool = True) -> list[Hand]:
    hands: list[Hand] = []
    files = find_files(paths)
    cache = _cache_dir() if use_cache else None
    for i, f in enumerate(files, 1):
        hands.extend(_cached_parse(f, cache))
        if progress:
            progress(i, len(files), len(hands))
    return dedupe(hands)


def detect_hero(hands: list[Hand]) -> str | None:
    """Hero = spelaren vars hålkort syns i flest händer."""
    from collections import Counter
    c = Counter(name for h in hands for name, cards in h.hole.items() if cards)
    return c.most_common(1)[0][0] if c else None


def dedupe(hands: list[Hand]) -> list[Hand]:
    seen = set()
    out = []
    for h in sorted(hands, key=lambda h: (h.date, h.id)):
        if h.id in seen:
            continue
        seen.add(h.id)
        out.append(h)
    return out


def filter_variant(hands: list[Hand], game: str | None = None) -> tuple[list[Hand], str]:
    """Behåll bara en Omaha-variant (blandade varianter ger missvisande statistik).

    game: "PLO4", "PLO5", "PLO6", "alla" eller None (= den vanligaste)."""
    from collections import Counter
    if not hands or game == "alla":
        return hands, ""
    counts = Counter(h.num_hole for h in hands)
    want = int(game[-1]) if game else counts.most_common(1)[0][0]
    kept = [h for h in hands if h.num_hole == want]
    dropped = len(hands) - len(kept)
    note = ""
    if dropped:
        other = ", ".join(f"PLO{k}: {v}" for k, v in sorted(counts.items()) if k != want)
        note = f"Analyserar {len(kept)} PLO{want}-händer. Hoppade över {dropped} händer i andra varianter ({other})."
    return kept, note


def latest_hands(hands, hero: str, n: int | None):
    """De n senaste händerna där hero satt med, efter datum och tid (handnummer vid lika tid).
    Returnerar alla händer om n saknas eller är 0."""
    if not n or n <= 0:
        return hands
    mine = sorted((h for h in hands if hero in h.seats), key=lambda h: (h.date, h.id))
    return mine[-n:]
