"""2.87: rättningar efter granskningen av 2.86 (GG-spärr, utvecklingsläge, tidsregel, stoppregel per pass,
pauskontroll, regeltexter, Windows-utdata, inställningsfil, time bank card, rakeback-cache)."""
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent


def test_dev_mode_expires_and_hard_stop():
    from plo_leak.ggguard import dev_mode_active
    now = time.mktime((2026, 11, 22, 12, 0, 0, 0, 0, -1))
    assert dev_mode_active({"dev_mode": True, "dev_mode_until": now + 3600}, now)
    assert not dev_mode_active({"dev_mode": True, "dev_mode_until": now - 1}, now)        # gått ut
    assert not dev_mode_active({"dev_mode": True}, now)                                    # gammal fil utan tid
    dec2 = time.mktime((2026, 12, 2, 12, 0, 0, 0, 0, -1))
    assert not dev_mode_active({"dev_mode": True, "dev_mode_until": dec2 + 3600}, dec2)    # aldrig efter 1 dec


def test_tasklist_decoding():
    from plo_leak.night import _decode_oem
    raw = '"Systemprocess","4","Tjänster","0","8 kB"\r\n"ggnet.exe","123","Console","1","90 000 kB"'.encode("cp850")
    out = _decode_oem(raw)
    assert "ggnet.exe" in out.lower() and _decode_oem(b"") == ""


def test_downloads_need_gg_closed(monkeypatch, tmp_path):
    """2.87.3: GG igång → bekräftelsesida med valet "Ladda ner ändå" (?ok=1), ingen spärr."""
    import plo_leak.web as web
    from plo_leak import night, hhexport
    monkeypatch.setattr(night, "gg_status", lambda: "ja")
    monkeypatch.setattr(hhexport, "export_dir", lambda db: tmp_path)
    monkeypatch.setattr(web, "get_db", lambda: None)
    names = ("plo_djupanalys_till_claude_20261121_100414_87721e.zip", "PLO_export_20261121_113031_599119_250121h.zip")
    for n in names:
        (tmp_path / n).write_bytes(b"PK\x05\x06" + b"\0" * 18)
    c = web.app.test_client()
    for url in ("/djupanalys/fil/" + names[0], "/exportera/fil/" + names[1]):
        r = c.get(url)
        assert r.status_code == 200 and "Ladda ner ändå" in r.get_data(as_text=True), (url, r.status_code, r.get_data(as_text=True)[:200])
        r2 = c.get(url + "?ok=1")
        assert r2.status_code == 200 and r2.headers.get("Content-Type", "").startswith("application/zip")
    monkeypatch.setattr(night, "gg_status", lambda: "okänd")
    assert web._gg_closed() is False


def test_overview_has_solver_marker_and_js_hides_on_server_loss():
    ov = (ROOT / "plo_leak" / "templates" / "pages" / "oversikt.html").read_text(encoding="utf-8")
    app = (ROOT / "plo_leak" / "templates" / "app.html").read_text(encoding="utf-8")
    assert "data-solver-page" in ov
    assert "miss>=2" in app and "Sidan är dold" in app


def test_pause_check_multitable():
    from plo_leak.fatigue import _pause_check, HAND_SEC
    # förlust vid 0; en hand på ett annat bord startar 30 s senare (pågick redan) – pausen hålls ändå
    H = {"net": np.array([-200.0, 1.0, 2.0])}
    ts = np.array([0, 30, 1100])
    assert _pause_check(H, np.arange(3), ts)["pauses_taken"] == 1
    # ny hand efter 5 min = bruten paus
    ts2 = np.array([0, 30, 300])
    assert _pause_check(H, np.arange(3), ts2)["pauses_taken"] == 0
    assert HAND_SEC == 60


def test_time_bank_card_line_parses():
    from plo_leak.parser import RE_SUMMARY_SHOWED, PARSER_VERSION
    m = RE_SUMMARY_SHOWED.match("Seat 1: Hero (small blind) received ($0.5) from time bank card, showed [Ac Kd Qh Js Tc 9d] and won ($10)")
    assert m and m.group("name") == "Hero"
    m = RE_SUMMARY_SHOWED.match("Seat 4: x1 (big blind) bought time bank card ($1), showed [Ac Kd Qh Js Tc 9d] and lost")
    assert m and m.group("name") == "x1"
    assert PARSER_VERSION >= 10


def test_settings_atomic_and_backup(tmp_path):
    from types import SimpleNamespace
    from plo_leak import watch
    db = SimpleNamespace(path=tmp_path / "plo_leak.db")
    watch.save_settings(db, a=1)
    watch.save_settings(db, b=2)
    p = watch.settings_path(db)
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    p.write_text("", encoding="utf-8")            # avbrott/krock tömde filen
    assert watch.load_settings(db).get("a") == 1   # .bak räddar


def test_nightly_utf8_and_bat(monkeypatch, tmp_path):
    from plo_leak import nightly
    src = (ROOT / "plo_leak" / "nightly.py").read_text(encoding="utf-8")
    assert "chcp 65001" in src and "PYTHONIOENCODING=utf-8" in src and "_utf8_streams()" in src


def test_texts_one_time_rule_and_rule_titles():
    from plo_leak.guidelines import PRIO
    t7 = PRIO[6][2]
    assert "Sluta efter 2 h" in t7 and "4 h varnas" not in t7
    ses = (ROOT / "plo_leak" / "templates" / "pages" / "sessioner.html").read_text(encoding="utf-8")
    assert "Ta 2 minuter" not in ses and "sluta efter 4 h" not in ses
    sf = (ROOT / "plo_leak" / "sessionfile.py").read_text(encoding="utf-8")
    assert "bara information" not in sf
    lk = (ROOT / "plo_leak" / "likely.py").read_text(encoding="utf-8")
    assert "är enda styrkan" in lk
    t2, t3 = PRIO[1][2], PRIO[2][2]
    assert "även med suited ess" in t2 and "45–49 %" in t2
    assert "BB mot BTN: 3-betta lite oftare" in t3 and "AAAA" in t3


def test_rakeback_in_cache_keys():
    src = (ROOT / "plo_leak" / "web.py").read_text(encoding="utf-8")
    assert src.count("_rbkey()") >= 3


def test_session_stop_counts_per_pass():
    """Två pass på 1,5 h var: inget av dem når 2 h – tidigare blev det 'gränsen nådd' över urvalet."""
    from types import SimpleNamespace
    from plo_leak import fatigue
    n = 40
    ts = np.concatenate([np.arange(20) * 270, 100000 + np.arange(20) * 270]).astype(np.int64)  # 0–1,5 h och nytt pass
    H = {"ts": ts, "net": np.zeros(n), "ev": np.zeros(n), "vpip": np.zeros(n), "pos": np.zeros(n, np.int16),
         "nplay": np.full(n, 5), "stake": np.zeros(n, np.int16), "ttype": np.zeros(n, np.int8), "bb": np.ones(n)}
    st = SimpleNamespace(ft=SimpleNamespace(H=H), rows=np.arange(n))
    orig = (fatigue.hand_session_info, fatigue._vpip_dev, fatigue._breaks)
    fatigue.hand_session_info = lambda s: (np.arange(n), np.repeat([0, 1], 20), None)
    fatigue._vpip_dev = lambda H_, r: np.zeros(len(r))
    fatigue._breaks = lambda s, d, r: (np.zeros(len(r)), np.zeros(len(r)))
    try:
        S = fatigue.session_stop(st, {}, 0, int(ts[-1]))
    finally:
        fatigue.hand_session_info, fatigue._vpip_dev, fatigue._breaks = orig
    assert S["kept"] is True


HH_SIDEPOT_LATE_FOLD = """Poker Hand #OM117809443: PLO-6 ($0.5/$1) - 2026/11/22 09:55:41
Table 'PLO-6Bronze5' 5-max Seat #3 is the button
Seat 1: 5670026 ($20 in chips)
Seat 2: bab9bab8 ($259.01 in chips)
Seat 3: d604bd1b ($100 in chips)
Seat 4: d0e94fa3 ($229.89 in chips)
Seat 5: Hero ($102.28 in chips)
d0e94fa3: posts small blind $0.5
Hero: posts big blind $1
d0e94fa3: straddle $2
5670026: straddle $4
*** HOLE CARDS ***
Dealt to 5670026 
Dealt to bab9bab8 
Dealt to d604bd1b 
Dealt to d0e94fa3 
Dealt to Hero [6h 7s As 6s Td 4s]
bab9bab8: calls $4
d604bd1b: folds
d0e94fa3: calls $2
Hero: calls $3
5670026: raises $16 to $20 and is all-in
bab9bab8: calls $16
d0e94fa3: calls $16
Hero: calls $16
*** FLOP *** [4d 6c 9s]
d0e94fa3: checks
Hero: bets $80
bab9bab8: raises $159.01 to $239.01 and is all-in
d0e94fa3: folds
Hero: calls $2.28 and is all-in
Uncalled bet ($156.73) returned to bab9bab8
bab9bab8: shows [4c 7d 5s Jh 8c Kh] (a pair of Fours)
Hero: shows [6h 7s As 6s Td 4s] (three of a kind, Sixes)
5670026: shows [Qd Ah Jd Jc 3c 4h] (a pair of Jacks)
*** TURN *** [4d 6c 9s] [Ac]
*** RIVER *** [4d 6c 9s Ac] [Qc]
*** SHOWDOWN ***
5670026 collected $79.03 from pot
bab9bab8 collected $162.54 from pot
*** SUMMARY ***
Total pot $244.56 | Rake $1.99 | Jackpot $1 | Bingo $0 | Fortune $0 | Tax $0
Board [4d 6c 9s Ac Qc]
Seat 1: 5670026 showed [Qd Ah Jd Jc 3c 4h] and won ($79.03) with a flush Ace high
Seat 2: bab9bab8 showed [4c 7d 5s Jh 8c Kh] and won ($162.54) with a flush Ace high
Seat 3: d604bd1b (button) folded before Flop (didn't bet)
Seat 4: d0e94fa3 (small blind) folded on the Flop
Seat 5: Hero (big blind) showed [6h 7s As 6s Td 4s] and lost with three of a kind, Sixes
"""


def test_allin_ev_pot_locked_preflop_with_later_fold():
    """2.87: kort all-in preflop, SB foldar på floppen, du all-in på floppen – EV ska räknas (ej faktiskt resultat)."""
    from plo_leak.parser import parse_text
    from plo_leak.ev import allin_ev
    h = parse_text(HH_SIDEPOT_LATE_FOLD)[0]
    r = allin_ev(h, "Hero", samples=2000)
    assert r is not None and r[2] == "flop"
    assert 25 < r[0] < 38   # exakt uppräkning: +31,49 $


HH_DEAD_BLIND = """Poker Hand #OM92968554: PLO-6 ($0.5/$1) - 2026/06/21 07:43:19
Table 'PLO-6Bronze4' 5-max Seat #2 is the button
Seat 1: cc733a5c ($100 in chips)
Seat 2: Hero ($616.81 in chips)
Seat 3: 3ba42d96 ($95.41 in chips)
Seat 4: 35ffbe95 ($100 in chips)
Seat 5: 4b0c9ebe ($133.51 in chips)
3ba42d96: posts small blind $0.5
35ffbe95: posts big blind $1
cc733a5c: posts dead $0.5
4b0c9ebe: posts straddle $2
*** HOLE CARDS ***
Dealt to cc733a5c
Dealt to Hero [Th As Ac 9d 9c 3s]
Dealt to 3ba42d96
Dealt to 35ffbe95
Dealt to 4b0c9ebe
cc733a5c: calls $2
Hero: raises $8 to $10
3ba42d96: folds
35ffbe95: raises $25 to $35
4b0c9ebe: calls $33
cc733a5c: folds
Hero: raises $108 to $143
35ffbe95: calls $65 and is all-in
4b0c9ebe: calls $98.51 and is all-in
Uncalled bet ($9.49) returned to Hero
*** FLOP *** [6s Ks 6h]
*** TURN *** [6s Ks 6h] [6d]
*** RIVER *** [6s Ks 6h 6d] [Jd]
*** SHOWDOWN ***
Hero: shows [Th As Ac 9d 9c 3s]
35ffbe95: shows [Qs Jh 7s Tc 8d 9h]
4b0c9ebe: shows [4h Ts Ah 4c 5d 3c]
Hero collected $367.03 from pot
*** SUMMARY ***
Total pot $370.02 | Rake $2.99 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Board [6s Ks 6h 6d Jd]
Seat 1: cc733a5c folded before Flop
Seat 2: Hero (button) showed [Th As Ac 9d 9c 3s] and won ($367.03)
Seat 3: 3ba42d96 (small blind) folded before Flop
Seat 4: 35ffbe95 (big blind) showed [Qs Jh 7s Tc 8d 9h] and lost
Seat 5: 4b0c9ebe showed [4h Ts Ah 4c 5d 3c] and lost
"""


def test_allin_ev_dead_blind_goes_to_main_pot():
    """2.87: död blind bestämmer ingen all-in-nivå – pengarna ligger i huvudpotten (oberoende granskning: +$7,86)."""
    from plo_leak.parser import parse_text
    from plo_leak.ev import allin_ev
    r = allin_ev(parse_text(HH_DEAD_BLIND)[0], "Hero")
    assert r is not None and r[2] == "preflop" and abs(r[0] - 7.86) < 0.05


def test_allin_ev_river_fold_after_hero_allin():
    """2.87: någon foldar först på river efter din all-in före river → EV vid din all-in (inte faktiskt resultat)."""
    from plo_leak.parser import parse_text
    from plo_leak.ev import allin_ev
    import re
    t = HH_SIDEPOT_LATE_FOLD
    r = allin_ev(parse_text(t)[0], "Hero")
    assert r is not None


def test_ev_recomputed_after_upgrade():
    """2.87: fakta och sparade EV-beräkningar byggs om så att hela databasen får rättad all-in EV."""
    from plo_leak.facts import FACTS_VERSION
    from plo_leak.db import CALC_VERSION
    import inspect, plo_leak.stats as st, plo_leak.facts as fa
    assert FACTS_VERSION >= 25 and CALC_VERSION >= 5
    assert 'ev3|' in inspect.getsource(st) and '"ev3"' in inspect.getsource(fa)


def test_multi_view_has_session_zip_button():
    """2.87.2: vyn för flera valda sessioner har en egen zip för just de sessionerna (inte hela databasen)."""
    from pathlib import Path
    import plo_leak
    root = Path(plo_leak.__file__).parent / "templates"
    s = (root / "pages" / "sessioner.html").read_text(encoding="utf-8")
    assert 'id="m-zip"' in s and "sessionzip?{% for k in M['keys'] %}s={{ k|urlencode }}" in s
    a = (root / "app.html").read_text(encoding="utf-8")
    assert "Djupanalys hela urvalet (zip)" in a


def test_session_zip_job_keeps_only_selected_keys():
    import inspect
    from plo_leak import web
    src = inspect.getsource(web.session_zip)
    assert '"keys": keys' in src and 'if not keys' in src
