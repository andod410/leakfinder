import threading, time
from plo_leak import ggguard


def test_refuse_when_gg_running(capsys, monkeypatch):
    monkeypatch.setattr(ggguard, "dev_mode", lambda: False)
    monkeypatch.setattr(ggguard, "_interactive", lambda: False)
    assert ggguard.refuse_if_gg(lambda: "ja") is True
    assert "GG-klienten körs" in capsys.readouterr().out
    assert ggguard.refuse_if_gg(lambda: "nej") is False
    assert ggguard.refuse_if_gg(lambda: "okänd") is False


def test_guard_exits_when_gg_starts(monkeypatch):
    monkeypatch.setattr(ggguard, "dev_mode", lambda: False)
    ggguard.reset_for_tests()
    seq = iter(["nej", "nej", "ja"])
    hit = threading.Event()
    ggguard.start(status_fn=lambda: next(seq, "ja"), exit_fn=hit.set, interval=0.01)
    assert hit.wait(2)
    ggguard.reset_for_tests()


def test_guard_ignores_unknown():
    ggguard.reset_for_tests()
    hit = threading.Event()
    ggguard.start(status_fn=lambda: "okänd", exit_fn=hit.set, interval=0.01)
    time.sleep(0.1)
    assert not hit.is_set()
    ggguard.reset_for_tests()


def test_web_and_nightly_call_guard():
    import inspect
    from plo_leak import web, nightly
    assert "ggguard.refuse_if_gg" in inspect.getsource(web.main)
    assert "ggguard.start(" in inspect.getsource(web.main)
    assert "ggguard.refuse_if_gg" in inspect.getsource(nightly.main)


def test_start_question_when_gg_runs(monkeypatch):
    """2.87.1: GG körs vid start → fråga j/n i kommandofönstret."""
    monkeypatch.setattr(ggguard, "dev_mode", lambda: False)
    ggguard.reset_for_tests()
    assert ggguard.refuse_if_gg(lambda: "ja", ask_fn=lambda q: "j") is False and ggguard.STATE["override"]
    ggguard.reset_for_tests()
    assert ggguard.refuse_if_gg(lambda: "ja", ask_fn=lambda q: "n") is True
    assert ggguard.refuse_if_gg(lambda: "ja", ask_fn=lambda q: "") is True
    monkeypatch.setattr(ggguard, "_interactive", lambda: False)
    assert ggguard.refuse_if_gg(lambda: "ja") is True    # nattkörningen: ingen som kan svara
    ggguard.reset_for_tests()


def test_web_guard_does_not_close_when_gg_starts(monkeypatch):
    monkeypatch.setattr(ggguard, "dev_mode", lambda: False)
    ggguard.reset_for_tests()
    hit = threading.Event()
    ggguard.start(status_fn=lambda: "ja", exit_fn=hit.set, interval=0.01, kill=False)
    time.sleep(0.1)
    assert not hit.is_set()
    ggguard.reset_for_tests()


def test_solver_still_hidden_when_gg_runs():
    import inspect
    from plo_leak import web
    assert 'g != "nej"' in inspect.getsource(web.solver_gate)
