"""2.79 (webb): cache per analys, förvärmning, gzip, sessionsfilens tidsstämpel, sidbyte först när varm."""
import gzip
import threading
import time


def test_cached_once_per_view_and_waits_for_running():
    import plo_leak.web as web
    C = {"x": 1}
    with web._VLOCK:
        web.VIEWS["t_cache"] = {"C": C, "hero": "h", "cache": {}, "locks": {}}
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.2)
        return {"v": 42}
    try:
        out = []
        ts = [threading.Thread(target=lambda: out.append(web._cached(C, ("k",), slow))) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert calls == [1] and all(o == {"v": 42} for o in out)
        assert web._cached({"y": 2}, ("k",), lambda: 7) == 7  # analys som inte är öppen: räknas direkt
    finally:
        with web._VLOCK:
            web.VIEWS.pop("t_cache", None)


def test_gzip_same_content():
    from flask import Response
    import plo_leak.web as web
    body = ("<html>" + "UTG abc " * 20000 + "</html>").encode()
    with web.app.test_request_context("/", headers={"Accept-Encoding": "gzip"}):
        r = web._gzip(Response(body, mimetype="text/html"))
        assert r.headers.get("Content-Encoding") == "gzip" and gzip.decompress(r.get_data()) == body
        small = web._gzip(Response(b"<p>x</p>", mimetype="text/html"))
        assert "Content-Encoding" not in small.headers
    with web.app.test_request_context("/"):
        r = web._gzip(Response(body, mimetype="text/html"))
        assert "Content-Encoding" not in r.headers and r.get_data() == body


def test_session_stamp_refreshed():
    import plo_leak.web as web
    t = "# Till Claude\nSkapad 2020-01-01 10:00 · PLO-läckfinnaren 2.78\n"
    new = web._STAMP_RX.sub(lambda _m: "Skapad X · PLO-läckfinnaren ", t)
    assert "Skapad X · PLO-läckfinnaren 2.78" in new and "2020-01-01" not in new


def test_gg_status_ttl_follows_monkeypatch(monkeypatch):
    import plo_leak.night as night
    import plo_leak.web as web
    monkeypatch.setattr(night, "gg_status", lambda: "ja")
    assert web._gg_status() == "ja"
    monkeypatch.setattr(night, "gg_status", lambda: "nej")
    assert web._gg_status() == "nej"  # ny funktion = ny kontroll, ingen gammal cache


def test_shown_vid_waits_for_warm():
    import plo_leak.web as web
    with web._VLOCK:
        saved = dict(web.VIEWS)
        web.VIEWS.clear()
        web.VIEWS["a"] = {"C": {}, "warm": True, "t_add": time.monotonic()}
        web.VIEWS["b"] = {"C": {}, "t_add": time.monotonic()}
    try:
        assert web._shown_vid() == "a"
        web.VIEWS["b"]["warm"] = True
        assert web._shown_vid() == "b"
    finally:
        with web._VLOCK:
            web.VIEWS.clear()
            web.VIEWS.update(saved)
