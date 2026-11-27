"""2.89.1: automatisk uppdatering högst en gång per minut – både i programmet och på alla sidor."""
from pathlib import Path

T = Path(__file__).resolve().parents[1] / "plo_leak" / "templates"


def _fake(monkeypatch, tmp_path):
    from plo_leak import watch, web
    import plo_leak.jobs as jobs
    started = []

    class FakeJob:
        id = "j1"; status = "klar"; stage = ""

    class FakeMgr:
        run_lock = __import__("threading").Lock()
        def get(self, jid): return FakeJob() if jid else None
        def start(self, title, fn, spec):
            started.append(spec); return FakeJob()

    class FakeDB:
        path = tmp_path / "x.db"
    monkeypatch.setattr(jobs, "MANAGER", FakeMgr())
    monkeypatch.setattr(web, "get_db", lambda: FakeDB())
    monkeypatch.setattr(web, "_last_vid", lambda: "abc")
    watch.save_settings(FakeDB(), auto_update=True, last_spec={"stake": "0.5/1"})
    return web, started


def test_auto_update_at_most_once_per_minute(monkeypatch, tmp_path):
    web, started = _fake(monkeypatch, tmp_path)
    now = [1_000_000.0]
    monkeypatch.setattr(web.time, "time", lambda: now[0])
    web._AUTO["job"] = None; web._AUTO["started"] = 0.0
    web._auto_update()
    assert len(started) == 1                      # första startar direkt
    now[0] += 30
    web._auto_update(); web._auto_update(retry=True)
    assert len(started) == 1                      # inom minuten: ingen ny uppdatering
    now[0] += 31
    web._auto_update(retry=True)
    assert len(started) == 2                      # efter en minut tas de nya händerna med (via retry)
    web._AUTO["job"] = None; web._AUTO["started"] = 0.0


def test_pages_reload_at_most_once_per_minute():
    a = (T / "app.html").read_text(encoding="utf-8")
    assert "MIN_GAP=60000" in a and "Date.now()-loaded" in a
    # den enda automatiska omladdningen av analyssidorna går genom reload(), som har minutspärren
    assert a.count("location.replace(location.pathname.replace('/v/'") == 1


def test_version():
    import plo_leak
    assert plo_leak.__version__ == "2.89.1"
