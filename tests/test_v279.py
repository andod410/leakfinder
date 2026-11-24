"""2.79: utvecklingsläge – programmet får köras när GG är igång, men solverdata visas aldrig då."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_v276 import _client, _fake_raw  # noqa: E402


def test_dev_mode_allows_start_and_night_but_hides_solver(monkeypatch, tmp_path):
    from plo_leak import ggguard, night, solverref, web
    monkeypatch.setattr(ggguard, "dev_mode", lambda: True)
    assert ggguard.refuse_if_gg(lambda: "ja") is False
    monkeypatch.setattr(night, "gg_status", lambda: "ja")
    monkeypatch.setattr(night, "recent_hh", lambda db: False)
    assert night.blocked(None) == ""
    c, vid, db = _client(monkeypatch, tmp_path, "ja")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    tab, why = web.solver_gate()
    assert tab is None and why == "gg"
    assert "Utvecklingsläge" in c.get("/import").get_data(as_text=True)


def test_dev_mode_off_by_default(monkeypatch):
    from plo_leak import ggguard
    monkeypatch.setattr(ggguard, "dev_mode", lambda: False)
    monkeypatch.setattr(ggguard, "_interactive", lambda: False)
    assert ggguard.refuse_if_gg(lambda: "ja") is True
