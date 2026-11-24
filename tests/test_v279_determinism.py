"""2.79: faktatabellen ska bli identisk oavsett antal arbetsprocesser/klarordning."""
import os, shutil, sqlite3, tempfile
import numpy as np
from plo_leak import facts as F


def test_parts_sorted_before_concat():
    src = open(F.__file__, encoding="utf-8").read()
    i = src.index("parts.sort(key=lambda kv: kv[0])")
    j = src.index("new = FactTable.concat([ft for _, ft in parts])")
    assert i < j


def test_parallel_pf_rows_equal_serial(tmp_path, monkeypatch):
    """Raderna för framåttestet räknas i flera processer – exakt samma som en i taget via get_hand."""
    from pathlib import Path
    from plo_leak import night, pfforward as P
    from plo_leak.db import HandDB
    from plo_leak.postflop_rows import rows_for_hand
    db = HandDB(tmp_path / "p.db")
    db.add_paths([Path(__file__).parent / "real"])
    hero = db.detect_hero()
    ids = [r[0] for r in db.con.execute("SELECT id FROM hands")]
    items = [(i, 0.5) for i in ids]
    monkeypatch.setattr(night, "cpu_procs", lambda *a, **k: 2)
    monkeypatch.setattr(P, "PAR_MIN", 1)
    par = P._parallel_rows(str(db.path), hero, items)
    for hid in ids:
        h = db.get_hand(hid)
        try:
            xs = rows_for_hand(h, hero, 0.5, draws=False)
        except Exception:
            xs = None
        assert par[hid] == (0.5, xs)


def test_river_coach_light_state_has_what_coach_reads():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_v272 import _st
    from plo_leak.rivercoach import light_state
    st = _st()
    L = light_state(st)
    assert L.ft.n == st.ft.n and set(L.ft.H) == {"pot", "pot_fee", "bb"} and (L.rows == st.rows).all()
    assert len(L.ft.t["rsp"]["hidx"]) == len(st.ft.t["rsp"]["hidx"])
