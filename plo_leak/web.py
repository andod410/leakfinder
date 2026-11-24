"""Enkel webbsida: peka på din handhistorik och få läckrapporten direkt.

    python -m plo_leak.web            # öppna sedan http://localhost:8765
    python -m plo_leak.web --lan      # nå sidan från mobilen på samma wifi
"""
from __future__ import annotations

import sys

import argparse
from datetime import datetime
import os
import socket
import threading
import webbrowser
from collections import OrderedDict
from pathlib import Path

from flask import Flask, jsonify, request

from . import __version__
from .parser import dedupe, detect_hero, load_paths

app = Flask(__name__)


@app.before_request
def _positions_in():
    """2.74: sidorna visar UTG för den interna koden HJ – värden som kommer tillbaka översätts till HJ igen."""
    from werkzeug.datastructures import ImmutableMultiDict
    from .positions import from_ui
    # 2.81: formuläret tolkas inte här för uppladdningar eller stora anrop (skyddet i _guard ska gå först)
    big = (request.content_length or 0) > 1_000_000 or (request.mimetype or "").startswith("multipart/")
    for name in (("args",) if big else ("args", "form")):
        try:
            md = getattr(request, name)
        except Exception:
            continue
        if any("UTG" in v for _k, v in md.items(multi=True)):
            request.__dict__[name] = ImmutableMultiDict([(k, from_ui(v)) for k, v in md.items(multi=True)])


_FG = {"n": 0}  # 2.79: pågående sidvisningar – förvärmningen i bakgrunden väntar medan de körs
_FG_LOCK = threading.Lock()


@app.before_request
def _fg_in():
    from flask import g
    with _FG_LOCK:
        _FG["n"] += 1
    g._plo_fg = True


@app.teardown_request
def _fg_out(_exc=None):
    from flask import g
    if g.pop("_plo_fg", None):
        with _FG_LOCK:
            _FG["n"] -= 1


@app.after_request
def _gzip(resp):
    """2.79: stora HTML/JSON-svar skickas gzip-packade när webbläsaren klarar det (samma innehåll, färre byte –
    märks mest i nätverksläget mot mobilen). Körs sist, efter positionsbytet."""
    import gzip
    try:
        if (resp.direct_passthrough or resp.status_code != 200 or "Content-Encoding" in resp.headers
                or (resp.mimetype or "") not in ("text/html", "application/json")
                or "gzip" not in (request.headers.get("Accept-Encoding") or "").lower()):
            return resp
        body = resp.get_data()
        if len(body) < 20_000:
            return resp
        resp.set_data(gzip.compress(body, compresslevel=5, mtime=0))
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers.add("Vary", "Accept-Encoding")
    except Exception:
        pass
    return resp


@app.after_request
def _positions_out(resp):
    """2.74: byter HJ mot UTG i allt som visas (HTML och JSON). Nedladdade filer får namnet när de skrivs."""
    from .positions import to_ui
    ct = (resp.mimetype or "")
    if resp.direct_passthrough or not (ct == "text/html" or ct == "application/json"):
        return resp
    try:
        body = resp.get_data(as_text=True)
    except Exception:
        return resp
    new = to_ui(body)
    if new is not body and new != body:
        resp.set_data(new)
    return resp
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024

# ---------------------------------------------------------------- skydd
# * Bara adresser på den egna datorn accepteras (skyddar mot DNS-rebinding).
# * Formulär som ändrar något (POST) måste komma från programmets egen sida (skyddar mot att en
#   annan webbsida i webbläsaren tömmer databasen, startar analyser eller stänger programmet).
# * I nätverksläget (--lan) krävs en kod som visas i terminalfönstret.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
_LAN = {"token": None}


def _hostname(h: str) -> str:
    h = (h or "").lower()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.rsplit(":", 1)[0]


@app.before_request
def _guard():
    from urllib.parse import urlparse
    tok = _LAN["token"]
    if request.path in ("/version", "/avsluta") and request.remote_addr in ("127.0.0.1", "::1"):
        tok = None  # en nyare version på samma dator ska kunna hitta och stänga den här
        if _hostname(request.host) not in LOCAL_HOSTS:
            return "Okänd adress.", 403
    if tok is None:
        if _LAN["token"] is None and _hostname(request.host) not in LOCAL_HOSTS:
            return "Okänd adress. Öppna programmet via http://localhost.", 403
    elif request.args.get("kod") != tok and request.cookies.get("plo_kod") != tok:
        return ("Ange koden som visas i terminalfönstret: öppna adressen som står där "
                "(den slutar med ?kod=…)."), 403
    if tok is not None and request.method == "GET" and request.args.get("kod") == tok:
        # 2.81: koden byts mot en kaka och tas bort ur adressen (syns inte i historik eller bokmärken)
        from flask import redirect
        from urllib.parse import urlencode
        rest = [(k, v) for k, v in request.args.items(multi=True) if k != "kod"]
        resp = redirect(request.path + (("?" + urlencode(rest)) if rest else ""))
        resp.set_cookie("plo_kod", tok, httponly=True, samesite="Strict")
        return resp
    if request.method == "POST":
        src = request.headers.get("Origin") or request.headers.get("Referer")
        # 2.81: ett formulär utan Origin/Referer avvisas (webbläsare skickar alltid Origin vid POST). Undantag: en nyare
        # version på samma dator som stänger den här, och testerna (PLO_ALLOW_NO_ORIGIN).
        if not src and not (request.path == "/avsluta" and request.remote_addr in ("127.0.0.1", "::1")) \
                and os.environ.get("PLO_ALLOW_NO_ORIGIN") != "1":
            return "Formuläret saknar ursprung och avvisades.", 403
        if src and src != "null" and urlparse(src).netloc.lower() != (request.host or "").lower():
            return "Formuläret kom inte från läckfinnarens egen sida och avvisades.", 403
        if src == "null":
            return "Formuläret kom inte från läckfinnarens egen sida och avvisades.", 403
    return None


@app.after_request
def _no_framing(resp):
    """Sidan får inte visas inuti en annan webbsida (skydd mot klickkapning)."""
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.after_request
def _set_lan_cookie(resp):
    tok = _LAN["token"]
    if tok is not None and request.args.get("kod") == tok:
        resp.set_cookie("plo_kod", tok, httponly=True, samesite="Strict")
    return resp

_DB = None
_DB_LOCK = threading.Lock()


def get_db():
    global _DB
    if _DB is None:
        with _DB_LOCK:
            if _DB is None:
                from .db import HandDB
                _DB = HandDB()
    return _DB


def _path_ok(p: str) -> bool:
    try:
        return Path(p).expanduser().exists()
    except (RuntimeError, OSError, ValueError):
        return False


def _dir_ok(folder: str) -> bool:
    """Finns mappen? (Ogiltiga sökvägar som ~okänd/x ger False i stället för ett fel.)"""
    try:
        return Path(folder).expanduser().is_dir()
    except (RuntimeError, OSError, ValueError):
        return False


# ---------------------------------------------------------------- vyer (öppna analyser)
# En analys (ett urval) räknas en gång och sparas här; sidorna i menyn visar delar av den.
VIEWS: "OrderedDict[str, dict]" = OrderedDict()
VIEW_KEEP = 3
_VLOCK = threading.Lock()
_FT = {"key": None, "ft": None}   # senast inlästa faktatabell (delas av vyerna)
PAGES = {"oversikt": "Översikt", "resultat": "Resultat & graf", "hander": "Händer", "preflop": "Preflop",
         "postflop": "Turn & river", "betstorlek": "Betstorlek", "lackor": "Läckor", "folj": "Följ upp", "sessioner": "Sessioner", "utveckling": "Utveckling", "tider": "När du vinner", "rakeback": "Rakeback & leaderboard", "dela": "Dela som bild", "aggression": "Aggression", "detaljer": "Statistik & kontroll", "solver": "Solver (preflop)"}


def _add_view(C: dict, hero: str) -> str:
    import uuid
    vid = uuid.uuid4().hex[:10]
    with _VLOCK:
        VIEWS[vid] = {"C": C, "hero": hero, "cache": {}, "locks": {}, "t_add": __import__("time").monotonic()}
        while len(VIEWS) > VIEW_KEEP:
            VIEWS.popitem(last=False)
    _start_prefetch(vid)
    return vid


# ---------------------------------------------------------------- 2.79: cache per analys + förvärmning
# Allt som sidorna räknar fram ur en öppen analys (solverfacit, Topp 3, träningsrutan, Solver-sidan, sessionernas
# detaljer och sessionsfiler, rakeback-kurvan) räknas en gång per analys och sparas bredvid den (inte i C, som
# sparas på disk). Samma indata ger samma värden – bara snabbare andra gången. När en analys öppnas räknar en
# bakgrundstråd i förväg det som de vanligaste sidorna behöver, och väntar medan en sida håller på att visas.
_KLOCK = threading.Lock()


def _vstore(C):
    with _VLOCK:
        for V in VIEWS.values():
            if V.get("C") is C:
                return V.setdefault("cache", {}), V.setdefault("locks", {})
    return None, None


def _cached(C, key, fn):
    """fn() en gång per analys och nyckel. Räknas den redan (t.ex. i förvärmningen) väntar anropet på svaret."""
    cache, locks = _vstore(C)
    if cache is None:
        return fn()
    try:
        return cache[key]
    except KeyError:
        pass
    with _KLOCK:
        lk = locks.setdefault(key, threading.Lock())
    with lk:
        if key in cache:
            return cache[key]
        v = fn()
        cache[key] = v
        return v


_GG = {"fn": None, "t": 0.0, "v": None}
GG_TTL = 2.0


def _gg_status():
    """gg_status() (tasklist/ps, 0,01–0,3 s) högst en gång per GG_TTL sekunder – en sida frågar annars flera gånger."""
    import time as _t
    from . import night
    fn = night.gg_status
    now = _t.monotonic()
    with _KLOCK:
        if _GG["fn"] is fn and now - _GG["t"] < GG_TTL:
            return _GG["v"]
    v = fn()
    with _KLOCK:
        _GG.update(fn=fn, t=_t.monotonic(), v=v)
    return v


def _prefetch_wait(vid, limit: float = 20.0) -> bool:
    """Lägsta prioritet: vänta medan en sida visas. False om analysen inte är öppen längre."""
    import time as _t
    t_end = _t.monotonic() + limit
    while _FG["n"] > 0 and _t.monotonic() < t_end:
        _t.sleep(0.02)
    _t.sleep(0.001)
    return _view(vid) is not None


PREFETCH = {"on": True, "last": None}


def _prefetch(vid):
    V = _view(vid)
    if V is None:
        return
    C = V["C"]
    tasks = [lambda: _top3(C)]
    try:
        S = ((C.get("sessions") or {}).get("sessions") or [])[:3]
    except Exception:
        S = []
    tasks += [lambda: _solver_extra(C), lambda: _rb_extra(C), _warm_templates, lambda: V.__setitem__("warm", True)]
    for s0 in S:
        k = s0.get("key", "")
        tasks += [lambda k=k: _session_extra(V, k), lambda k=k: _session_text(V, [k])]
    tasks += [_warm_trainer]
    for t in tasks:
        if not _prefetch_wait(vid):
            return
        try:
            t()
        except Exception:
            pass
    V["warm"] = True
    PREFETCH["last"] = vid


WARM_MAX = 20.0


def _shown_vid():
    """Den analys sidorna ska byta till: den senaste, men först när förvärmningen av Översikt/Solver/Resultat är
    klar (högst WARM_MAX s) – då visas den gamla sidan tills den nya kan visas direkt."""
    import time as _t
    now = _t.monotonic()
    with _VLOCK:
        items = list(VIEWS.items())
    for vid, V in reversed(items):
        if V.get("warm") or not PREFETCH["on"] or now - V.get("t_add", 0) > WARM_MAX:
            return vid
    return items[-1][0] if items else None


def _warm_templates():
    from .report import _template
    env = _template("app.html").environment
    for name in env.list_templates(filter_func=lambda n: n.endswith(".html") or n.endswith(".js") or n.endswith(".css")):
        try:
            env.get_template(name)
        except Exception:
            pass


def _warm_trainer():
    tab, inf = solver_gate()
    if tab is not None:
        from . import solverfacit
        solverfacit.open_freq(tab, (inf or {}).get("hash", ""))


def _start_prefetch(vid):
    if not PREFETCH["on"]:
        return
    threading.Thread(target=_prefetch, args=(vid,), daemon=True, name="förvärm-analys").start()


def _view(vid: str):
    with _VLOCK:
        return VIEWS.get(vid)


def _last_vid():
    with _VLOCK:
        return next(reversed(VIEWS), None)


def shell(page: str, title: str, vid: str | None = None, status: int = 200, **ctx):
    """En sida i programmets gränssnitt: sidomeny, urvalslist och innehåll."""
    from .report import _template
    base = {"app_version": __version__, "page": page, "page_title": title, "vid": vid}
    nav = vid or _last_vid()
    V = _view(nav) if nav else None
    if V is not None:
        C = V["C"]
        if vid:
            base.update(C)
        else:  # märkena i menyn (antal läckor, regelbrott) från den öppna analysen
            base.update(leaks=C["leaks"], fu=C["fu"], mixed=C["mixed"])
    base["nav_vid"] = nav if V is not None else None
    try:  # 2.89: vilka nyckeltalsrutor som är dolda (⚙ Anpassa rutor), sparas i programmets inställningar
        from . import watch as _wk
        base["kpi_hide"] = list(_wk.load_settings(get_db()).get("kpi_hide") or [])
    except Exception:
        base["kpi_hide"] = []
    if vid and base.get("focus_all"):
        from . import watch as _w
        from .focus import pick
        try:
            cfg = _w.load_settings(get_db())
        except Exception:
            cfg = {}
        locked = (cfg.get("focus") or {}).get(base.get("main_game") or "")
        f = pick(base["focus_all"], locked)
        if f and not locked:
            try:  # första fokus sparas, så att det inte byts av sig självt vid nästa analys
                _w.save_settings(get_db(), focus={**(cfg.get("focus") or {}), base.get("main_game") or "": f["id"]})
            except Exception:
                pass
        base["focus"] = f
        base["focus_next"] = next((x for x in base["focus_all"] if x is not f and not x["done"]), None)
    from . import watch
    with watch._LOCK:
        base["watch_new"] = watch.STATE["new_since_view"]
    base.update(ctx)
    return _template("app.html").render(**base), status


def page(error: str = "", folder: str = "", status: int = 200, info: str = ""):
    """Import- och databassidan (startsidan när ingen analys är öppen)."""
    db, db_error = None, ""
    try:
        from .db import quick_info
        db = quick_info(_DB.path if _DB is not None else None)
    except Exception as e:  # databasen får aldrig hindra sidan från att visas
        db_error = str(e)
    last = _last_vid()
    V = _view(last) if last else None
    carry = V["C"].get("filters") if V else None
    from . import watch
    try:
        ws = watch.load_settings(get_db())
    except Exception:
        ws = {}
    with watch._LOCK:
        wstate = dict(watch.STATE)
    import time as _t
    wstate["last_txt"] = _t.strftime("%H:%M", _t.localtime(wstate["last"])) if wstate.get("last") else None
    return shell("import", "Import & databas", error=error, info=info, folder=folder, db=db, db_error=db_error,
                 watch_cfg={"folder": watch.folder_of(ws), "auto": ws.get("auto", True),
                            "is_default": "watch" not in ws, "suggest": watch.default_folder(),
                            "every": watch.INTERVAL, "problem": watch.folder_problem(watch.folder_of(ws)),
                            "watch_dl": bool(ws.get("watch_dl")),
                            "mac": sys.platform == "darwin"},
                 watch_state=wstate,
                 last_vid=last if V else None, carry=carry if carry and carry.get("enabled") else None,
                 page_sub="Lägg till nya händer och se vad databasen innehåller", status=status)


_AUTO: dict = {"job": None}


def _auto_analysis(back: str = "oversikt"):
    """Ingen analys är öppen (t.ex. direkt efter start) men databasen har händer: analysera hela
    databasen automatiskt, så att menyn går att använda direkt. Startas bara en gång åt gången."""
    from .jobs import MANAGER
    j = MANAGER.get(_AUTO["job"]) if _AUTO["job"] else None
    if j is not None and j.status not in ("klar", "fel", "avbruten"):
        return j
    try:
        if get_db().count() == 0:
            return None
    except Exception:
        return None
    spec = {"hero": None, "game": None, "games": [], "folder": "", "use_db": True, "fran": None, "till": None,
            "table": "", "stake": "", "latest": None, "simulera": False, "upload_dir": None, "n_uploads": 0,
            "back": back if back in PAGES else "oversikt", "restore": True}
    j = MANAGER.start("Analys", _run_job, spec)
    _AUTO["job"] = j.id
    return j


LASTPAGE_NAME = "_senaste_sida.json"


def _lastpage_path():
    db = get_db()
    return db.path.parent / (db.path.stem + LASTPAGE_NAME)


_LASTPAGE = {"pg": None}


def _remember_page(pg: str) -> None:
    """2.79: sidan du senast tittade på öppnas igen när programmet startar om."""
    if _LASTPAGE["pg"] == pg:
        return
    _LASTPAGE["pg"] = pg
    try:
        import json
        _lastpage_path().write_text(json.dumps({"page": pg}), encoding="utf-8")
    except Exception:
        pass


def _saved_page() -> str:
    try:
        import json
        pg = json.loads(_lastpage_path().read_text(encoding="utf-8")).get("page")
        return pg if pg in PAGES else "oversikt"
    except Exception:
        return "oversikt"


@app.get("/")
def index():
    from flask import redirect
    back = request.args.get("till") or (_saved_page() if not _last_vid() else "oversikt")
    back = back if back in PAGES else "oversikt"
    last = _last_vid()
    if last:
        return redirect(f"/v/{last}/{back}")
    j = _auto_analysis(back)
    return redirect(f"/jobb/{j.id}") if j is not None else page()


# ---------------------------------------------------------------- senaste analysen på disk
# Öppna analyser finns bara i minnet. För att programmet ska starta snabbt sparas den senaste analysen
# av databasen på disk och öppnas direkt vid nästa start. Har nya händer kommit sedan dess visas de i
# rutan "nya händer" – analysen räknas om först när du uppdaterar.
SNAP_NAME = "_senaste_analys.pkl"


def _snap_path():
    db = get_db()
    return db.path.parent / (db.path.stem + SNAP_NAME)


def _save_snapshot(C: dict, hero: str, back: str, fkey=None) -> None:
    """Spara analysen till nästa start. Skrivs inte om när samma data och samma urval redan är sparat
    (filen kan vara stor). fkey = (databas, spelare, faktabutikens signatur)."""
    import json
    import os
    import pickle
    meta = {"version": __version__, "fkey": list(fkey) if fkey else None,
            "sel": repr(((C.get("filters") or {}).get("games_sel"), (C.get("filters") or {}).get("table"),
                         (C.get("filters") or {}).get("stake"), (C.get("filters") or {}).get("fran"),
                         (C.get("filters") or {}).get("till"), (C.get("filters") or {}).get("latest_on"),
                         (C.get("filters") or {}).get("latest"), (C.get("filters") or {}).get("model_sel")))}

    def run():
        try:
            db = get_db()
            path = _snap_path()
            mpath = path.with_suffix(".json")
            try:
                if fkey and path.exists() and json.loads(mpath.read_text(encoding="utf-8")) == meta:
                    return  # samma analys är redan sparad
            except Exception:
                pass
            data = __import__("plo_leak.signcache", fromlist=["x"]).sign(pickle.dumps(
                {"version": __version__, "hero": hero, "C": C, "back": back, "fkey": fkey,
                 "db_count": db.count()}, protocol=pickle.HIGHEST_PROTOCOL))   # 2.81: signerad
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            mpath.write_text(json.dumps(meta), encoding="utf-8")
        except Exception:
            pass  # bara en genväg vid start – får aldrig stoppa en analys
    threading.Thread(target=run, daemon=True, name="spara-analys").start()


def _load_snapshot():
    import pickle
    try:
        path = _snap_path()
        if not path.exists():
            return None
        d = __import__("plo_leak.signcache", fromlist=["x"]).loads(path.read_bytes())
        if d.get("version") != __version__:
            return None  # ny version: räkna om, mallarna kan behöva nya värden
        db = get_db()
        st = d["C"].get("st")
        hb = getattr(st, "hands_by_id", None)
        if hb is not None:
            hb._lookup = db.get_hand
        # samma faktadata som nu: låt nästa analys återanvända faktatabellen (ingen andra kopia i minnet)
        fk = d.get("fkey")
        try:
            if fk and getattr(st, "ft", None) is not None:
                cur = (str(db.path), fk[1], db.facts(fk[1]).signature())
                if tuple(fk) == cur:
                    _FT.update(key=cur, ft=st.ft)
        except Exception:
            pass
        return d
    except Exception:
        return None


@app.context_processor
def _dev_ctx():
    """2.79: utvecklingsläget syns överst på alla sidor."""
    try:
        from datetime import date
        from .ggguard import dev_mode
        on = dev_mode()
        return {"dev_on": on, "dev_late": date.today() >= date(2026, 12, 1)}
    except Exception:
        return {"dev_on": False, "dev_late": False}


@app.post("/utvecklingslage")
def dev_mode_toggle():
    from flask import redirect
    from . import watch
    import time as _t
    from .ggguard import DEV_MAX_H
    on = bool(request.form.get("on"))
    # 2.87 (R7-04): utvecklingsläget gäller högst ett dygn; ggguard.dev_mode_active stänger det helt från 2026-12-01
    watch.save_settings(get_db(), dev_mode=on, dev_mode_until=(_t.time() + DEV_MAX_H * 3600) if on else 0)
    return redirect("/import#utveckling")


@app.get("/import")
def import_page():
    from . import watch
    msg = watch.STATE.get("message", "") if request.args.get("klar") else ""
    return page(info=msg)


@app.get("/v/<vid>/<pg>")
def view_page(vid, pg):
    if pg not in PAGES:
        return page("Sidan finns inte.", status=404)
    if _view(vid) is None:
        return page("Den analysen är inte öppen längre (programmet har startats om eller fler analyser har "
                    "öppnats sedan dess). Öppna analysen igen.", status=404)
    extra = {}
    if _view(vid) is _view(_last_vid() or ""):
        _remember_page(pg)
    if pg == "sessioner" and request.args.get("s"):
        extra.update(_session_extra(_view(vid), request.args.get("s", "")))
    if pg == "sessioner" and request.args.getlist("m"):  # 2.77.6: graf och resultat för valda sessioner
        try:
            V_ = _view(vid)
            D_, inf_ = _facit(V_["C"])
            mk = ("multi", tuple(dict.fromkeys(request.args.getlist("m"))), (inf_ or {}).get("hash") if D_ is not None else None, _rbkey())
            extra["multi"] = _cached(V_["C"], mk, lambda: _multi_sessions(V_, request.args.getlist("m")))
        except Exception as e:
            extra["multi"] = {"error": f"{type(e).__name__}: {e}"}
    if pg in ("oversikt", "resultat"):
        try:
            extra.update(_rb_extra(_view(vid)["C"]))
        except Exception:
            pass
    if pg == "rakeback":
        try:
            from . import rbweek
            extra["rbweek"] = rbweek.table(_view(vid)["C"]["st"], get_db())
        except Exception as e:
            extra["rbweek"] = {"rows": [], "error": f"{type(e).__name__}: {e}"}
    if pg == "oversikt":
        try:
            extra["top3"] = _top3(_view(vid)["C"])
        except Exception as e:
            extra["top3"] = {"items": [], "error": f"{type(e).__name__}: {e}"}
        try:
            extra["prio_usd"] = _prio_usd(_view(vid)["C"])
        except Exception:
            extra["prio_usd"] = None
    if pg == "solver":
        extra.update(_solver_extra(_view(vid)["C"]))
    return shell(pg, PAGES[pg], vid, **extra)


def _session_extra(V, key: str) -> dict:
    """Sessionssidans detaljer för en session (en gång per analys, session och solverfil)."""
    try:
        D, inf = _facit(V["C"])
    except Exception:
        D, inf = None, None
    ck = ("sess", key, (inf or {}).get("hash") if D is not None else None, _rbkey())
    return dict(_cached(V["C"], ck, lambda: _session_calc(V, key, D)))


def _session_calc(V, key: str, D) -> dict:
    extra = {}
    from .sessions import session_detail
    extra["sess"] = session_detail(V["C"].get("sessions"), key, V["C"]["st"], V["hero"]
                                   if "hero" in V else "")
    if extra["sess"]:
        from .fatigue import session_hours
        fu = V["C"].get("fu") or {}
        extra["sess_hours"] = session_hours(V["C"]["st"], {"rules": fu.get("rules") or []},
                                            extra["sess"]["t0"], extra["sess"]["t1"])
        try:
            from .fatigue import session_stop
            extra["sess_stop"] = session_stop(V["C"]["st"], {"rules": fu.get("rules") or []},
                                              extra["sess"]["t0"], extra["sess"]["t1"])
        except Exception:
            extra["sess_stop"] = None
        try:  # 2.77: klara fel per 100 händer och 4 h-flaggan
            from . import solverfacit
            extra["sess_facit"] = solverfacit.session_errors(V["C"]["st"], D, int(extra["sess"]["t0"]), int(extra["sess"]["t1"])) if D is not None else None
            extra["sess_long"] = solverfacit.long_session_flag(V["C"]["st"], D, int(extra["sess"]["t0"]), int(extra["sess"]["t1"]))
        except Exception:
            extra["sess_facit"] = extra["sess_long"] = None
        from .sessionfile import session_hands
        try:
            extra["sess_hands"] = session_hands(V["C"]["st"], extra["sess"], {"rules": fu.get("rules") or []})
        except Exception:
            extra["sess_hands"] = []
        try:
            import numpy as np
            from .report import _chart
            from .sessionfile import session_rows
            Hh = V["C"]["st"].ft.H
            rr = session_rows(V["C"]["st"], extra["sess"])
            if len(rr) >= 2:
                cs = lambda k: np.cumsum(Hh[k][rr])
                from .rbcurve import current_cfg, rb_rows  # 2.86: all-in EV inkl. rakeback
                from .report import apply_rb
                cfg_ = current_cfg()
                rb, rb_m = rb_rows(V["C"]["st"].ft, rr, cfg_)
                on_ = bool(cfg_.get("on"))
                extra["sess_chart"] = apply_rb(_chart({"net": cs("net"), "ev": cs("ev"), "rake": cs("rake")}, ts=Hh["ts"][rr]),
                                               np.cumsum(Hh["net"][rr] + rb), np.cumsum(Hh["ev"][rr] + rb), on_)
                extra["sess_chart_money"] = apply_rb(_chart({"net": cs("money"), "ev": cs("ev_m"), "rake": cs("rake_m")}, money=True, ts=Hh["ts"][rr]),
                                                     np.cumsum(Hh["money"][rr] + rb_m), np.cumsum(Hh["ev_m"][rr] + rb_m), on_)
                extra["sess_rb"] = {"on": on_, "rb100": float(100 * rb.sum() / len(rr)),
                                    "ev100_rb": float(100 * (Hh["ev"][rr].sum() + rb.sum()) / len(rr)), "rb_m": float(rb_m.sum())}
        except Exception:
            extra["sess_chart"] = None
        from .aggr import session_stab
        try:
            extra["sess_stab"] = session_stab(V["C"]["st"], extra["sess"]["t0"], extra["sess"]["t1"],
                                              (V["C"].get("aggr") or {}).get("stab"))
        except Exception:
            extra["sess_stab"] = None
    return extra


def _multi_sessions(V, keys) -> dict:
    """Valfritt antal sessioner tillsammans: resultat, all-in EV, rake, klara fel och vinstkurva."""
    import numpy as np
    from .report import _chart
    from .sessionfile import session_rows
    from .sessions import session_detail
    C = V["C"]
    st = C["st"]
    S = [x for x in (session_detail(C.get("sessions"), k, st, V.get("hero", "")) for k in dict.fromkeys(keys)) if x]
    if not S:
        return {"error": "Inga av sessionerna finns i den här analysen."}
    S.sort(key=lambda x: x["t0"])
    H = st.ft.H
    r = np.concatenate([session_rows(st, x) for x in S])
    r = r[np.argsort(H["ts"][r], kind="stable")]
    cs = lambda k: np.cumsum(H[k][r])  # noqa: E731
    from .rbcurve import current_cfg, rb_rows  # 2.86
    from .report import apply_rb
    cfg_ = current_cfg()
    on_ = bool(cfg_.get("on"))
    rb, rb_m = rb_rows(st.ft, r, cfg_)
    n = len(r)
    out = {"n_sess": len(S), "hands": int(n), "minutes": int(sum(int(x.get("minutes") or 0) for x in S)),
           "net": float(H["net"][r].sum()), "ev": float(H["ev"][r].sum()), "money": float(H["money"][r].sum()),
           "ev_m": float(H["ev_m"][r].sum()), "rake_m": float(H["rake_m"][r].sum()),
           "first": S[0]["start"], "last": S[-1]["end"], "keys": [x["key"] for x in S],
           "chart": apply_rb(_chart({"net": cs("net"), "ev": cs("ev"), "rake": cs("rake")}, ts=H["ts"][r]),
                             np.cumsum(H["net"][r] + rb), np.cumsum(H["ev"][r] + rb), on_),
           "chart_money": apply_rb(_chart({"net": cs("money"), "ev": cs("ev_m"), "rake": cs("rake_m")}, money=True, ts=H["ts"][r]),
                                   np.cumsum(H["money"][r] + rb_m), np.cumsum(H["ev_m"][r] + rb_m), on_),
           "rb_on": on_, "rb100": float(100 * rb.sum() / n) if n else 0.0,
           "ev100_rb": float(100 * (H["ev"][r].sum() + rb.sum()) / n) if n else 0.0,
           "rb_m": float(rb_m.sum()), "ev_rb_m": float(H["ev_m"][r].sum() + rb_m.sum())}
    out["ev100"] = 100.0 * out["ev"] / n if n else 0.0
    # 2.80: samma aktiva speltid som Översikt/Timlön (luckor högst 5 min, sista handen = typisk handlängd),
    # så att samma händer alltid ger samma $/h. Väggklockan visas fortfarande som "Speltid".
    from .hourly import _active_seconds
    act_sec, _ns, _tail = _active_seconds(H["ts"][r], H["clu"][r])
    out["active_minutes"] = int(round(act_sec / 60.0))
    out["hourly_ev"] = out["ev_m"] / (act_sec / 3600.0) if act_sec > 0 else None
    D, _inf = _facit(C)
    if D is not None:
        from .solverfacit import session_errors
        fel = hands = 0
        for x in S:
            e = session_errors(st, D, int(x["t0"]), int(x["t1"]))
            fel += e["fel"]
            hands += e.get("hands", 0) or 0
        out["fel"] = fel
        out["fel100"] = 100.0 * fel / hands if hands else None
    return out


def _rb_extra(C: dict) -> dict:
    """2.76: rakeback i vinstkurvan (på/av) och nyckeltal med/utan rakeback."""
    import json as _json
    from .rbcurve import settings, summary
    cfg = settings(get_db())
    try:
        ck = ("rb", _json.dumps(cfg, sort_keys=True, default=str))
    except Exception:
        ck = None
    S = _cached(C, ck, lambda: summary(C["st"], cfg)) if ck else summary(C["st"], cfg)
    out = {"rbc": cfg, "rbs": S}
    if not S:
        return out
    from .report import apply_rb   # 2.88: lika med lika – båda linjerna med eller båda utan rakeback
    for key, nr, er in (("chart", "cum_net_rb", "cum_ev_rb"), ("chart_money", "cum_net_rb_m", "cum_ev_rb_m")):
        ch = C.get(key)
        if ch and ch.get("x"):
            out[key] = apply_rb(ch, S[nr], S[er], bool(cfg.get("on")))
    return out


def _rbkey() -> str:
    """2.87 (R2-02): rakeback-procentsatserna i cachenyckeln – sessionsvy, flerpassvy och sessionsfil räknas om när
    de ändras på Översikt."""
    import json as _j
    try:
        from .rbcurve import current_cfg
        return _j.dumps(current_cfg(), sort_keys=True)
    except Exception:
        return ""


def _gg_closed() -> bool:
    """2.87: True bara när GG-klienten säkert inte körs (färsk kontroll)."""
    from . import night
    try:
        return night.gg_status() == "nej"
    except Exception:
        return False


def solver_gate():
    """2.77: den enda vägen till solverdata. (tabell, info) bara när filen finns och GG-klienten säkert inte körs;
    annars (None, skäl). Säljversion: filen finns aldrig med i paketet (testat i test_v276)."""
    from . import night, solverref
    g = night.gg_status()  # 2.79: alltid färsk kontroll för solverdata (ingen 2 s-cache) – viktigt i utvecklingsläget
    if g != "nej":
        return None, ("gg" if g == "ja" else "okänd")
    tab, inf = solverref.load(get_db())
    if tab is None:
        return None, "ingen fil"
    return tab, inf


def _facit(C: dict):
    """Solverfacit (alla beslut med solverfrekvens) för analysen, cachat per solverfil."""
    tab, inf = solver_gate()
    if tab is None:
        return None, inf
    key = inf.get("hash")

    def build():
        from . import solverfacit
        try:
            return solverfacit.build(C["st"], tab)
        except Exception:
            return None
    if _vstore(C)[0] is not None:
        return _cached(C, ("facit", key), build), inf
    hit = C.get("_facit")  # analys som inte är öppen i menyn (t.ex. i testerna)
    if hit and hit[0] == key:
        return hit[1], inf
    D = build()
    C["_facit"] = (key, D)
    return D, inf


def _training(C: dict, D, key):
    """Träningsrutan (samma för Översikt och Solver-sidan), en gång per analys och solverfil."""
    from . import solverfacit
    return _cached(C, ("training", key), lambda: solverfacit.training(C["st"], None, D=D))


def _top3(C: dict) -> dict:
    """2.77: Översiktens enda lista – topp 3 just nu (Andreas: första sidan ska vara ren)."""
    D, inf = _facit(C)
    ck = ("top3", (inf or {}).get("hash") if D is not None else inf if isinstance(inf, str) else None)
    return _cached(C, ck, lambda: _top3_calc(C, D, inf))


def _top3_calc(C: dict, D, inf) -> dict:
    from . import solverfacit
    items = []
    st = C["st"]
    T = None
    if D is not None:
        try:
            T = _training(C, D, inf.get("hash"))
        except Exception:
            T = None
    # 1. senaste passet: 4 h-flaggan
    try:
        S = (C.get("sessions") or {}).get("sessions") or []
        if S:
            s0 = S[0]
            fl = solverfacit.long_session_flag(st, D, int(s0["t0"]), int(s0["t1"]))
            if fl and (fl["warn"] or fl.get("worse")):
                why = []
                if fl["warn"]:
                    why.append(f"all-in EV {fl['ev_bb']:+.0f} bb")
                if fl.get("worse"):
                    why.append(f"klara fel {fl['early']:.1f} → {fl['late']:.1f} per 100 händer efter 4 h")
                # 2.80: "sämre mot slutet" bara när det faktiskt mätts (fler klara fel efter 4 h än första 2 h)
                title = (f"Senaste passet var {fl['hours']:.1f} h och gick sämre mot slutet" if fl.get("worse")
                         else f"Senaste passet var {fl['hours']:.1f} h och slutade minus i all-in EV")
                items.append({"ic": "⏱", "title": title,
                              "text": " · ".join(why) + (". Sluta tidigare nästa gång passet ser ut så." if fl.get("worse")
                                                          else ". Passets total säger inget om när det gick sämre – se timme för timme."),
                              "link": f"sessioner?s={s0.get('key', '')}"})
    except Exception:
        pass
    # 2. preflop: de lägen som kostar mest i $/h senaste 7 dagarna (2.83; tidigare flest klara fel)
    if T and not T.get("empty"):
        for r in T["lagen"][:2]:
            rule = r["rules"][0]["text"] if r["rules"] else ""
            if r.get("usd_h") is not None:
                title = (f"{r['label']}: ≈ ${r['usd_h']:.1f}/h ({r['fel']} klara fel senaste 7 dagarna, "
                         f"{r['cost_bb']:.1f} bb per fel)")
            else:
                title = f"{r['label']}: {r['fel']} klara fel senaste 7 dagarna ({r['per100']:.1f} per 100 händer)"
            items.append({"ic": "🃏", "title": title, "text": rule or "Se Träna för exempel.", "link": "solver#trana"})
    elif inf in ("gg", "okänd"):
        items.append({"ic": "🃏", "title": "Preflop: solverfacit visas inte just nu",
                      "text": "GG-klienten körs eller kunde inte kontrolleras.", "link": None})
    # 3. största postflop-läckan som fortfarande är ett råd
    pl = [x for x in (C.get("postflop_leaks") or []) if x.get("per100", 0) >= 0.1]
    pl.sort(key=lambda x: -x["per100"])
    if pl:
        x = pl[0]
        items.append({"ic": "🎯", "title": x.get("do") or x.get("title"),
                      "text": (f"ca {x['per100']:.1f} bb/100 – tidigare uppskattning, inte mätt på ditt urval ({x.get('level')})"
                               if x.get("guide") else f"ca {x['per100']:.1f} bb/100 (mätt)"),
                      "link": x.get("link") or "postflop"})
    return {"items": items[:3], "training": T}


def _prio_usd(C: dict):
    """2.83: $/h för prio-listans preflop-rader (bara när solverfacit får visas)."""
    from . import solverfacit
    from .guidelines import PRIO_COST
    D, inf = _facit(C)
    if D is None:
        return None
    P = _cached(C, ("prio_usd", (inf or {}).get("hash")), lambda: solverfacit.prio_costs(C["st"], D))
    if not P:
        return None
    return {"rows": {i: P[k] for i, k in PRIO_COST.items()}, "days": P["days"], "hph": P["hph"]}


def _solver_extra(C: dict) -> dict:
    """2.76: Solver-sidan. Visas inte medan GG körs (realtidshjälp) eller när det inte går att kontrollera."""
    from . import night, solverref
    g = night.gg_status()  # 2.79: färsk kontroll
    if g != "nej":
        return {"solver_blocked": g}
    tab, inf = solverref.load(get_db())
    out = {"solver_info": inf}
    if tab is None:
        return out
    return _cached(C, ("solver", (inf or {}).get("hash")), lambda: _solver_calc(C, tab, inf, out))


def _solver_calc(C, tab, inf, out) -> dict:
    from . import solverref
    try:
        R = solverref.compare(C["st"], tab)
    except Exception as e:  # visa felet i stället för att sidan kraschar
        return {**out, "solver_error": f"{type(e).__name__}: {e}"}
    try:  # 2.77: träningsrutan
        D, _i = _facit(C)
        out["training"] = _training(C, D, inf.get("hash")) if D is not None else {"empty": True}
    except Exception as e:
        out["training"] = {"empty": True, "error": f"{type(e).__name__}: {e}"}
    import hashlib
    R["h4"]["hash"] = hashlib.sha256(f"{solverref.H4_TEXT}|{solverref.H4_START}|{inf['classifier']}|{inf['hash']}".encode()).hexdigest()[:16]
    return {**out, "solver": R}


@app.post("/solver/fil")
def solver_upload():
    from flask import redirect
    from .night import gg_status
    from . import solverref
    vid = request.form.get("vid") or ""
    back = f"/v/{vid}/solver" if _view(vid) else "/"
    if gg_status() != "nej":
        return page("Solverfilen kan bara läggas in när GG-klienten inte körs.", status=409)
    if request.form.get("ta_bort"):
        solverref.remove(get_db())
        return redirect(back)
    f = request.files.get("fil")
    if not f or not f.filename:
        return page("Ingen fil vald.", status=400)
    try:
        solverref.save_upload(get_db(), f.read(20_000_000))
    except ValueError as e:
        return page(f"Solverfilen lades inte in: {e}", status=400)
    return redirect(back)


@app.post("/rakeback-kurva")
def rakeback_curve():
    from flask import redirect
    from .rbcurve import save
    save(get_db(), request.form)
    vid = request.form.get("vid") or ""
    return redirect(f"/v/{vid}/oversikt" if _view(vid) else "/")


@app.post("/rakeback-vecka")
def rakeback_week():
    """2.77: veckomätning av rakeback (från 1 dec)."""
    from flask import redirect
    from . import rbweek
    rbweek.add(get_db(), request.form)
    vid = request.form.get("vid") or ""
    return redirect(f"/v/{vid}/rakeback#vecka" if _view(vid) else "/")


_STAMP_RX = __import__("re").compile(r"Skapad \d{4}-\d{2}-\d{2} \d{2}:\d{2} · PLO-läckfinnaren ")


def _session_text(V, keys):
    """Sessionsfilens text och filnamn (None om ingen av sessionerna finns). En gång per analys, urval av
    sessioner och solverfil – tidsstämpeln "Skapad" sätts när filen hämtas."""
    from . import __version__
    from .facts import dt_of
    from .fatigue import session_hours
    from .sessionfile import MAX_MULTI, build_multi
    from .sessions import session_detail
    C = V["C"]
    keys = list(dict.fromkeys(k for k in keys if k))[:MAX_MULTI]  # 2.77.6: upp till 500
    D_, inf = _facit(C)  # 2.77: solverfacit i sessionsfilen (bara när GG säkert inte körs)

    def calc():
        sess = [x for x in (session_detail(C.get("sessions"), k, C["st"], V.get("hero", "")) for k in keys) if x]
        if not sess:
            return None
        sess.sort(key=lambda x: x["t0"])
        fu = C.get("fu") or {}
        doc = {"rules": fu.get("rules") or []}
        hours = [session_hours(C["st"], doc, x["t0"], x["t1"]) for x in sess]
        text = build_multi(C["st"], sess, C.get("hero") or V.get("hero", "Hero"), doc, hours, __version__, C.get("river_coach"), D_)
        name = f"session_till_claude_{dt_of(sess[0]['t0']):%Y%m%d_%H%M}"
        if len(sess) > 1:
            name += f"_{len(sess)}st"
        return text, name + ".md"
    r = _cached(C, ("sfil", tuple(sorted(keys)), (inf or {}).get("hash") if D_ is not None else None, _rbkey()), calc)
    if r is None:
        return None
    text, name = r
    now = f"Skapad {datetime.now():%Y-%m-%d %H:%M} · PLO-läckfinnaren "
    return _STAMP_RX.sub(lambda _m: now, text), name


def _session_files(vid, keys):
    """Sessionsfil (en eller flera sessioner, högst 5) som nedladdning."""
    from flask import Response
    from . import watch as _w
    V = _view(vid)
    if V is None:
        return page("Den analysen är inte öppen längre. Öppna analysen igen.", status=404)
    r = _session_text(V, keys)
    if r is None:
        return page("Sessionen finns inte i den här analysen.", status=404)
    text, name = r
    data = text.encode("utf-8")
    folder = _w.load_settings(get_db()).get("export_dir")
    if folder:
        try:
            pth = Path(folder).expanduser()
            pth.mkdir(parents=True, exist_ok=True)
            (pth / name).write_bytes(data)
        except OSError:
            pass
    return Response(data, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _job_key(kind: str, *parts) -> str:
    """2.80: jobbnyckel = sort + hela beställningen. Två olika beställningar får aldrig samma jobb (och fil)."""
    import hashlib
    import json as _json
    return kind + "|" + hashlib.sha1(_json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


@app.get("/v/<vid>/sessionsfil")
def session_file(vid):
    """En eller flera sessioner (?s=…&s=…, högst 5) som textfil till Claude: sammanfattning + de största
    potterna med fakta per beslut."""
    return _session_files(vid, request.args.getlist("s"))


@app.get("/v/<vid>/sessionzip")
def session_zip(vid):
    """Djupanalysens zip för bara de valda sessionerna (?s=…&s=…, högst 5) – med sessionsfilen och alla
    handhistoriker – så att Claude kan svara på följdfrågor om just de händerna."""
    from flask import redirect
    from .jobs import MANAGER
    if _view(vid) is None:
        return page("Den analysen är inte öppen längre – öppna den igen.", status=404)
    keys = [k for k in request.args.getlist("s") if k]
    if not keys:
        return page("Välj minst en session.", status=400)
    if len(keys) > 60:   # 2.80: inget tyst avklipp – för många pass ger ett tydligt besked
        return page(f"Du valde {len(keys)} pass – högst 60 i en zip. Välj färre.", status=400)
    job = MANAGER.start("Sessionens händer till Claude", _deep_job, {"vid": vid, "keys": keys}, key=_job_key("djup", vid, keys))
    return redirect(f"/jobb/{job.id}")


@app.post("/sessgrans")
def session_limit():
    """Välj efter hur många timmar du ska ta paus (tomt = rekommenderad gräns)."""
    from flask import redirect
    from . import watch as _w
    from .fatigue import fatigue_table
    from .report import add_session_focus
    vid = request.form.get("vid", "")
    v = (request.form.get("h") or "").strip()
    try:
        h = float(v) if v else None
        if h is not None and not 0.5 <= h <= 12:
            h = None
    except ValueError:
        h = None
    _w.save_settings(get_db(), sess_limit_h=h)
    V = _view(vid)
    if V is not None:
        C = V["C"]
        fu = C.get("fu") or {}
        doc = {"rules": fu.get("rules") or []}
        C["fatigue"] = fatigue_table(C["st"], doc, h)
        if C.get("focus_all") is not None and not C.get("mixed"):
            C["focus_all"] = add_session_focus(C["focus_all"], C["st"], doc, C["fatigue"], C.get("stake_check"))
        return redirect(f"/v/{vid}/sessioner#tid")
    return redirect("/")


@app.get("/v/<vid>/export")
def view_export(vid):
    import base64
    from flask import Response
    V = _view(vid)
    if V is None:
        return page("Den analysen är inte öppen längre – öppna den igen.", status=404)
    C = V["C"]
    return Response(base64.b64decode(C["export_b64"]), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{C["export_name"]}"'})


@app.get("/v/<vid>/djupanalys")
def view_deep_export(vid):
    """Zip med tabellerna bakom analysen (CSV), för djupanalys tillsammans med Claude (som ett jobb)."""
    from flask import redirect
    from .jobs import MANAGER
    if _view(vid) is None:
        return page("Den analysen är inte öppen längre – öppna den igen.", status=404)
    job = MANAGER.start("Djupanalys till Claude", _deep_job, {"vid": vid}, key=_job_key("djup", vid))
    return redirect(f"/jobb/{job.id}")


def _deep_job(job, spec) -> str:
    from .dataexport import build_zip, stakes_csv
    from .hhexport import export_dir
    from .jobs import UserError
    from .practice import load_rules
    from . import watch as _w
    V = _view(spec["vid"])
    if V is None:
        raise UserError("Analysen är inte öppen längre – öppna den igen och exportera.")
    C = V["C"]
    st = C["st"]
    variant = max(st.games.items(), key=lambda kv: kv[1])[0].replace("-", "") if st.games else None
    f = C.get("filters") or {}
    sel = " + ".join(f.get("games_sel") or []) or (C.get("main_game") or "")
    db = get_db() if C.get("db_info") is not None else None
    extra = {}
    if spec.get("keys"):
        # bara de valda sessionerna: samma tabeller, men på sessionernas händer + sessionsfil och handhistorik
        import numpy as _np
        from .aggregate import build_stats
        from .fatigue import session_hours
        from .sessionfile import build_multi, session_rows
        from .sessions import session_detail
        sess = [x for x in (session_detail(C.get("sessions"), k, st, V.get("hero", "")) for k in spec["keys"]) if x]
        if not sess:
            raise UserError("Sessionen finns inte i den här analysen.")
        sess.sort(key=lambda x: x["t0"])
        rows = _np.unique(_np.concatenate([session_rows(st, x) for x in sess]))
        mask = _np.zeros(st.ft.n, bool)
        mask[rows] = True
        job.set("Räknar sessionens händer")
        lookup = db.get_hand if db is not None else st.hands_by_id.get
        fu = C.get("fu") or {}
        doc = {"rules": fu.get("rules") or []}
        hours = [session_hours(st, doc, x["t0"], x["t1"]) for x in sess]
        extra["session.md"] = build_multi(st, sess, C.get("hero") or V.get("hero", "Hero"), doc, hours, __version__,
                                          C.get("river_coach"), _facit(C)[0]).encode("utf-8")
        texts = []
        for hid in st.ft.H["id"][rows]:
            h = lookup(str(hid))
            if h is not None and getattr(h, "raw", ""):
                texts.append(h.raw.strip())
        extra["handhistorik.txt"] = ("\n\n\n".join(texts) + "\n").encode("utf-8")
        st = build_stats(st.ft, mask, V.get("hero", ""), lookup)
        sel += f" · {len(sess)} session(er) {sess[0]['start']} – {sess[-1]['end']}"
    if st.first_date and st.last_date:
        sel += f" · {st.first_date:%Y-%m-%d} – {st.last_date:%Y-%m-%d} · {st.hands} händer"
    job.set("Skriver tabellerna")
    rules = load_rules(variant) or ((C.get("fu") or {}).get("rules") and {"rules": C["fu"]["rules"]})
    data = build_zip(st, rules, sel, __version__, db=db, hero=V.get("hero"),
                     progress=lambda d, t: job.set("Läser postflop-besluten", d, t),
                     extra_files={"stakes.csv": stakes_csv(C.get("stake_check")), **extra})
    name = f"plo_djupanalys_till_claude_{datetime.now():%Y%m%d_%H%M%S}_{(getattr(job, "id", None) or __import__("uuid").uuid4().hex)[:6]}.zip"   # 2.80: unik per jobb
    out = export_dir(get_db()) / name
    out.write_bytes(data)
    saved = ""
    folder = _w.load_settings(get_db()).get("export_dir")
    if folder:
        try:
            pth = Path(folder).expanduser()
            pth.mkdir(parents=True, exist_ok=True)
            (pth / name).write_bytes(data)
            saved = str(pth / name)
        except OSError:
            saved = ""
    DEEP[name] = {"name": name, "size_mb": round(len(data) / 1e6, 1), "saved": saved}
    return f"/djupanalys/klar/{name}"


DEEP: dict = {}
DEEP_OK = __import__("re").compile(r"^plo_djupanalys_till_claude_\d{8}_\d{6}(_[0-9a-f]{6})?\.zip$")


@app.get("/djupanalys/klar/<name>")
def deep_done(name):
    d = DEEP.get(name)
    if d is None or not DEEP_OK.match(name):
        return page("Filen finns inte längre – skapa djupanalysen igen.", status=404)
    msg = (f"Djupanalysen är klar ({d['size_mb']} MB)." + (f" Sparad i {d['saved']}." if d["saved"] else ""))
    return shell("exportera", "Djupanalys till Claude", deep=d, page_sub=msg)


def _gg_confirm_page(name: str):
    """2.87.3 (Andreas 23 nov): när GG körs får du alltid välja – en bekräftelse i stället för spärr."""
    from markupsafe import escape
    n = escape(name)
    html = f"""<!doctype html><meta charset="utf-8"><title>GG körs</title>
<body style="font-family:system-ui,sans-serif;background:#111418;color:#e6e6e6;max-width:640px;margin:60px auto;line-height:1.5">
<h2>GG-klienten körs</h2>
<p>Filen <b>{n}</b> kan innehålla rader från solvern (i sessionsfilen). Enligt din egen regel ska solverdata inte
synas medan du spelar, och från 1 dec 2026 förbjuder GG tredjepartsprogram som körs samtidigt som klienten.</p>
<p>Du väljer själv:</p>
<p><a href="?ok=1" style="background:#3b82f6;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none">Ladda ner ändå</a>
&nbsp; <a href="javascript:history.back()" style="color:#9aa">Avbryt</a></p></body>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/djupanalys/fil/<name>")
def deep_file(name):
    from flask import abort, send_file
    from .hhexport import export_dir
    if not DEEP_OK.match(name):
        abort(404)
    p = export_dir(get_db()) / name
    if not p.is_file():
        abort(404)
    if not _gg_closed() and request.args.get("ok") != "1":   # 2.87.3: fråga i stället för spärr
        return _gg_confirm_page(name)
    if not p.is_file():
        abort(404)
    return send_file(p, as_attachment=True, download_name=name, mimetype="application/zip")


def hand_filter(C: dict, args):
    """Urvalets händer filtrerade som i handlistan (rader i faktatabellen, i tidsordning)."""
    import numpy as np
    st = C["st"]
    ft, rows = st.ft, st.rows
    H = ft.H
    r = np.asarray(rows)
    q = args.get("q", "forlust")
    pos = args.get("pos", "")
    if pos:
        code = ft.codes("pos").get(pos)
        r = r[H["pos"][r] == code] if code is not None else r[:0]
    if q == "forlust":
        r = r[H["net"][r] < 0]
    elif q == "vinst":
        r = r[H["net"][r] > 0]
    elif q == "allin":
        r = r[H["ai_st"][r] >= 0]
    elif q == "sd":
        r = r[H["sd"][r]]
    fu = C.get("fu") or {}
    dev = fu.get("dev_rows")
    dev = np.asarray(dev if dev is not None else [], dtype=np.int64)
    if q == "brott":
        r = r[np.isin(r, dev)]
    if q == "fokus":
        rid = args.get("regel", "")
        f = next((x for x in (C.get("focus_all") or []) if x["id"] == rid), None)
        r = r[np.isin(r, f["dev_rows"])] if f is not None else r[:0]
    if q in ("session", "sessbrott"):
        try:
            a_, b_ = int(args.get("fran_ts", "")), int(args.get("till_ts", ""))
        except ValueError:
            a_, b_ = 0, -1
        r = r[(H["ts"][r] >= a_) & (H["ts"][r] <= b_)]
        if q == "sessbrott":
            r = r[np.isin(r, dev)]
    if q not in ("session", "sessbrott") and args.get("fran_ts") and args.get("till_ts"):
        # en session (från sessionslistan) kombinerad med vilket filter som helst
        try:
            a_, b_ = int(args["fran_ts"]), int(args["till_ts"])
            r = r[(H["ts"][r] >= a_) & (H["ts"][r] <= b_)]
        except ValueError:
            pass
    hid = (args.get("id") or "").strip()
    if hid:
        r = r[np.char.find(H["id"][r].astype(str), hid) >= 0]
    return r, dev


def hand_rows(C: dict, args) -> dict:
    """Handlistan: filtrera, sortera och bläddra bland urvalets händer (direkt i faktatabellen)."""
    import numpy as np
    from .facts import STREET_CODE, decode_cards, dt_of
    st = C["st"]
    ft = st.ft
    H = ft.H
    r, dev = hand_filter(C, args)
    # pott-nummer som i sessionsfilen (de 10 största potterna i sessionen), när en session är vald
    nr = {}
    if args.get("fran_ts") and args.get("till_ts"):
        try:
            from .sessionfile import top_pots
            a_, b_ = int(args["fran_ts"]), int(args["till_ts"])
            allr = np.asarray(st.rows)
            sr = allr[(H["ts"][allr] >= a_) & (H["ts"][allr] <= b_)]
            nr = {int(x): i for i, x in enumerate(top_pots(H, sr), 1)}
        except ValueError:
            nr = {}
    if args.get("q") == "top":
        r = r[np.isin(r, np.array(list(nr), dtype=np.int64))]
    sort = args.get("sort", "net")
    if sort == "nr":
        key = np.array([nr.get(int(x), 999) for x in r], dtype=np.int64)
        o = np.argsort(key, kind="stable")
    else:
        col = {"date": "ts", "pot": "pot", "net": "net", "ev": "ev", "money": "money", "luck": None}.get(sort, "net")
        o = np.argsort(H["net"][r] - H["ev"][r] if col is None else H[col][r], kind="stable")
    if args.get("dir") == "desc":
        o = o[::-1]
    try:
        size = min(max(int(args.get("size", 50)), 1), 200)
        pg = max(int(args.get("page", 0)), 0)
    except ValueError:
        size, pg = 50, 0
    pick = r[o[pg * size:(pg + 1) * size]]
    street = {v: k for k, v in STREET_CODE.items()}
    devset = set(dev.tolist())
    out = []
    for j in pick.tolist():
        out.append({"id": str(H["id"][j]), "date": dt_of(H["ts"][j]).strftime("%Y-%m-%d %H:%M"),
                    "game": f"PLO{int(H['nh'][j])}", "stake": ft.label("stake", int(H["stake"][j])),
                    "pos": ft.label("pos", int(H["pos"][j])),
                    "hole": sorted(decode_cards(H["hole"][j]), key=lambda c: (-c[0], c[1])),
                    "pot": float(H["pot"][j]), "net": float(H["net"][j]), "ev": float(H["ev"][j]),
                    "money": float(H["money"][j]), "allin": street.get(int(H["ai_st"][j]), ""),
                    "sd": bool(H["sd"][j]), "dev": j in devset, "nr": nr.get(int(j)),
                    "time": dt_of(H["ts"][j]).strftime("%H:%M")})
    return {"total": int(len(r)), "rows": out}


@app.post("/fokus")
def set_focus():
    """Välj vilken läcka du jobbar med (sparas per variant)."""
    from flask import redirect
    from . import watch
    f = request.form
    game = (f.get("game") or "")[:8]
    rid = (f.get("id") or "")[:200]
    cfg = watch.load_settings(get_db())
    fm = dict(cfg.get("focus") or {})
    if rid:
        fm[game] = rid
    else:
        fm.pop(game, None)
    watch.save_settings(get_db(), focus=fm)
    vid = f.get("vid") or ""
    return redirect(f"/v/{vid}/oversikt" if _view(vid) else "/")


@app.get("/api/status")
def status_api():
    """För sidorna: har den bevakade mappen läst in nya händer, pågår ett jobb, och vilken analys är den senaste?
    Sidan laddar om sig själv till den senaste analysen när programmet uppdaterat den automatiskt."""
    from . import watch
    from .jobs import MANAGER
    with watch._LOCK:
        n = watch.STATE["new_since_view"]
    try:
        auto = bool(watch.load_settings(get_db()).get("auto_update", True))
    except Exception:
        auto = True
    j = MANAGER.get(_AUTO["job"]) if _AUTO.get("job") else None
    return {"watch_new": n, "job_running": MANAGER.run_lock.locked(), "latest_vid": _shown_vid(),
            "auto_update": auto, "auto_running": bool(j is not None and j.status in ("väntar", "kör")),
            "auto_stage": (j.stage if j is not None and j.status in ("väntar", "kör") else "")}


@app.get("/api/gg")
def api_gg():
    """2.80: färsk GG-status för öppna flikar med solverdata – de laddas om (och döljs) när GG startar."""
    from . import night
    try:
        st = night.gg_status()
    except Exception:
        st = "okänd"
    return jsonify({"gg": st})


@app.get("/api/jobs")
def jobs_api():
    """Pågående och köade jobb – jobbraden överst på varje sida visar dem med förlopp, så att ett jobb syns även när
    du bytt sida (och samma jobb inte startas två gånger)."""
    from .jobs import MANAGER
    return {"jobs": [{**j.as_dict(), "title": j.title} for j in MANAGER.active()]}


KPI_KEYS = ("real", "rb100", "ev_rb_m", "net_rb_m", "hands", "net_bb", "bb100", "ev100", "ev100_pre", "bb100_pre",
            "rake100", "money", "ev_m", "hourly", "ev_hourly", "ev_hourly_rb", "leaks")


@app.post("/api/kpi")
def kpi_api():
    """2.89: spara vilka nyckeltalsrutor som ska döljas (gäller efter omstart och i alla flikar)."""
    import json as _j
    from . import watch
    try:
        hide = _j.loads(request.form.get("hide") or "[]")
    except ValueError:
        return {"ok": False}, 400
    hide = [k for k in hide if k in KPI_KEYS] if isinstance(hide, list) else []
    watch.save_settings(get_db(), kpi_hide=hide)
    return {"ok": True, "hide": hide}


@app.post("/api/auto")
def auto_api():
    """Slå på/av automatisk uppdatering av analysen när nya händer lästs in (sparas i programmets inställningar)."""
    from . import watch
    on = request.form.get("on") == "1"
    watch.save_settings(get_db(), auto_update=on)
    if on:
        with watch._LOCK:
            pending = watch.STATE["new_since_view"]
        if pending:
            _auto_update()
    return {"auto_update": on}


_AUTO = {"job": None}
_SPEC_KEEP = ("hero", "game", "games", "fran", "till", "table", "stake", "latest", "model_sel", "back")


def _default_spec() -> dict:
    return {"hero": None, "game": None, "games": [], "folder": "", "use_db": True, "fran": None, "till": None,
            "table": "", "stake": "", "latest": None, "simulera": False, "upload_dir": None, "n_uploads": 0,
            "model_sel": False, "quick": True, "back": "oversikt"}


def _auto_update(retry: bool = False) -> None:
    """Den bevakade mappen hittade nya händer: gör en snabb uppdatering (samma urval som senaste analysen) direkt i
    programmet – oberoende av om webbsidan är öppen eller ligger i en bakgrundsflik. Sidan laddar sedan om sig själv."""
    from . import watch
    from .jobs import MANAGER
    try:
        ws = watch.load_settings(get_db())
        if not ws.get("auto_update", True) or _last_vid() is None:
            return
        j = MANAGER.get(_AUTO["job"]) if _AUTO.get("job") else None
        if (j is not None and j.status in ("väntar", "kör")) or MANAGER.run_lock.locked():
            return  # ett jobb pågår – nästa kontroll (retry) tar med de nya händerna
        if retry and j is not None and j.status == "fel":
            return  # förra automatiska uppdateringen misslyckades – vänta på nya filer i stället för att loopa
        spec = _default_spec()
        spec.update({k: v for k, v in (ws.get("last_spec") or {}).items() if k in _SPEC_KEEP})
        spec.update(quick=True, folder="", upload_dir=None, n_uploads=0, use_db=True, simulera=False)
        _AUTO["job"] = MANAGER.start("Analys", _run_job, spec).id
    except Exception:
        pass  # automatiken får aldrig stoppa programmet


@app.get("/api/hander/<vid>")
def hands_api(vid):
    V = _view(vid)
    if V is None:
        return {"error": "Analysen är inte öppen längre – ladda om sidan."}, 404
    return hand_rows(V["C"], request.args)


@app.get("/api/dela/<vid>")
def share_api(vid):
    """Siffrorna till delningsbilden (ritas i webbläsaren)."""
    from .share import share_data
    V = _view(vid)
    if V is None:
        return {"error": "Analysen är inte öppen längre – ladda om sidan."}, 404
    fran = (request.args.get("fran") or "").strip()
    return share_data(V["C"], fran if fran and _valid_date(fran) else None)


@app.get("/api/replay/<vid>/<hid>")
def replay_api(vid, hid):
    from .practice import get_replays
    V = _view(vid)
    if V is None:
        return {"error": "Analysen är inte öppen längre"}, 404
    st = V["C"]["st"]
    rp = get_replays(st, [hid], V["hero"]).get(hid)
    if rp:
        ce = ((V["C"].get("river_coach") or {}).get("decisions") or {}).get(hid)
        if ce:
            from .rivercoach import line_text
            rp = {**rp, "coach": line_text(ce).replace("**", ""), "coach_ok": bool(ce.get("ok"))}
    return (rp, 200) if rp else ({"error": "Handen finns inte i urvalet"}, 404)


@app.get("/version")
def version():
    return {"app": "plo-leak-finder", "version": __version__}


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # som webbservern själv
        try:
            sk.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _who_is_on(port: int) -> str:
    """Beskriv vad som redan kör på porten (en äldre läckfinnare?)."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/version", timeout=1.5) as r:
            return f"PLO-läckfinnare version {json.loads(r.read()).get('version', '?')}"
    except Exception:
        pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1.5) as r:
            if "PLO-läckfinnare" in r.read().decode("utf-8", "ignore"):
                return "en äldre PLO-läckfinnare (version 0.3 eller tidigare)"
    except Exception:
        pass
    return "ett annat program"


@app.get("/trana")
def trainer_page():
    from .practice import load_rules, rule_variants, trainer_scenarios
    variants = [v for v in rule_variants() if v]
    spel = request.args.get("spel")
    if spel not in ("PLO4", "PLO5", "PLO6"):
        spel = "PLO6" if "PLO6" in variants else (variants[0] if variants else None)
    doc = load_rules(spel)
    sc = trainer_scenarios(doc)
    tab, inf = solver_gate()
    sdef = dict(__import__("plo_leak.practice", fromlist=["x"]).SLIDER_DEFAULT)
    pre = request.args.get("s", "")
    solver_note = {"gg": "GG-klienten körs", "okänd": "det gick inte att kontrollera om GG körs",
                   "ingen fil": "ingen solverfil är inlagd (Solver & träning)"}.get(inf) if tab is None else None
    if tab is not None and (spel or "PLO6") == "PLO6":  # 2.77: solvern är facit – dess lägen först
        from . import solverfacit
        sc = solverfacit.trainer_scenarios(tab) + sc
        try:  # 2.77.1: reglaget startar på solverns öppningsfrekvens
            sdef.update(solverfacit.open_freq(tab, (inf or {}).get("hash", "")))
        except Exception:
            pass
        pre = pre or sc[0]["key"]
    return shell("trana", "Träna starthänder", variants=variants, spel=spel, scenarios=sc,
                 preselect=pre, solver_note=solver_note, solver_on=tab is not None,
                 rules_created=str((doc or {}).get("created")), rules_hands=(doc or {}).get("hands"),
                 slider_default=sdef,
                 wr_curves=(doc or {}).get("wr_curves") or {},
                 page_sub="Spela, folda eller 3-betta – facit från solvern (🧮), dina egna regler eller reglaget")


@app.get("/trana/hand")
def trainer_hand_api():
    from .practice import load_rules, trainer_hand
    spel = request.args.get("spel")
    doc = load_rules(spel if spel in ("PLO4", "PLO5", "PLO6") else None)
    spot, _, pos = (request.args.get("s") or "rfi|" + request.args.get("pos", "")).partition("|")
    if spot == "sol":  # 2.77: solverns facit, bara när GG säkert inte körs
        from . import solverfacit
        tab, _inf = solver_gate()
        h = solverfacit.trainer_hand(tab, pos) if tab is not None else None
        return (h, 200) if h else ({"error": "solverfacit visas inte (GG körs, okänd status eller ingen fil)"}, 404)
    if spot == "pct":  # 2.75: reglaget bestämmer facit – fungerar även utan sparade regler
        try:
            cut = float(request.args.get("cut", ""))
        except ValueError:
            cut = None
        h = trainer_hand(doc, pos, spot=spot, cut=cut)
    else:
        h = trainer_hand(doc, pos, spot=spot) if doc else None
    return (h, 200) if h else ({"error": "ingen regel"}, 404)


@app.post("/avsluta")
def shutdown():
    """Låter en nyare version stänga denna, så den gamla inte ligger kvar på porten."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return {"ok": False}, 403
    import threading
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return {"ok": True}


# ---------------------------------------------------------------- exportera händer
def _facts(job, hero: str | None = None):
    """Faktatabellen för databasen (räknar fakta för nya händer först). Delas med analyserna."""
    from .db import set_active
    db = get_db()
    hero = hero or db.detect_hero()
    if not hero:
        from .jobs import UserError
        raise UserError("Databasen är tom eller saknar ditt spelarnamn.")
    store = db.facts(hero)
    set_active(None)
    store.sync(db, lambda d, t, el: job.set("Räknar fram fakta för nya händer", d, t))
    fkey = (str(db.path), hero, store.signature())
    if _FT["key"] != fkey:
        _FT.update(key=fkey, ft=store.load())
    return _FT["ft"], hero


EXPORTS: dict = {}  # senaste exporterna: namn -> statistik


def _export_job(job, spec) -> str:
    import numpy as np
    from .hhexport import write_export
    from .jobs import UserError
    from .selection import Selection
    if spec.get("vid"):
        V = _view(spec["vid"])
        if V is None:
            raise UserError("Analysen är inte öppen längre – öppna den igen och exportera.")
        C = V["C"]
        ft = C["st"].ft
        r, _ = hand_filter(C, spec["args"])
        H = ft.H
        col = {"date": "ts", "pot": "pot", "net": "net", "ev": "ev", "money": "money"}.get(spec["args"].get("sort"), "net")
        o = np.argsort(H[col][r], kind="stable")
        if spec["args"].get("dir") == "desc":
            o = o[::-1]
        rows = r[o]
    else:
        job.set("Hämtar fakta")
        ft, _ = _facts(job)
        games = tuple(spec["games"]) or tuple(f"PLO{int(x)}" for x in np.unique(ft.H["nh"]))
        sel = Selection(games=games, table=spec["table"], stake=spec["stake"],
                        date_from=spec["fran"], date_to=spec["till"], latest=None)
        rows = np.flatnonzero(sel.mask(ft))
        if spec["latest"]:
            rows = rows[-spec["latest"]:]
    if spec.get("limit"):
        rows = rows[:spec["limit"]]
    if not len(rows):
        raise UserError("Inga händer matchar valen. Ändra valen och försök igen.")
    job.set("Skriver händerna", 0, len(rows))
    folder, fmt = spec.get("folder"), spec.get("fmt") or "zip"
    if spec.get("vid") and folder is None:  # "Exportera listan": samma mapp och format som senast
        from . import watch as _w
        cfg = _w.load_settings(get_db())
        folder, fmt = cfg.get("export_dir") or None, cfg.get("export_fmt") or "zip"
    try:
        st = write_export(get_db(), ft, rows, split=spec["split"], folder=folder, fmt=fmt,
                          progress=lambda d, t: job.set("Skriver händerna", d, t))
    except OSError as e:
        raise UserError(f"Kunde inte skriva i mappen {folder}: {e.strerror or e}. Välj en annan mapp.")
    if not st["hands"]:
        raise UserError("Händerna kunde inte skrivas ut. Läs in dem igen från dina filer.")
    key = st["name"] if st["fmt"] == "zip" else f"mapp{int(st['time'] * 1000)}"
    EXPORTS[key] = st
    return f"/exportera?klar={key}"


def _export_form_spec(f) -> dict | str:
    fran = (f.get("fran") or "").strip() or None
    till = (f.get("till") or "").strip() or None
    for d in (fran, till):
        if d and not _valid_date(d):
            return f"Datum ska skrivas ÅÅÅÅ-MM-DD (fick {d})."
    def num(k):
        v = (f.get(k) or "").strip()
        if not v:
            return None
        if not v.isdigit() or int(v) <= 0:
            raise ValueError
        return int(v)
    try:
        latest, limit = num("latest"), num("limit")
    except ValueError:
        return "Antalet händer måste vara ett positivt heltal."
    folder = (f.get("mapp") or "").strip().strip('"').replace("\0", "") or None
    fmt = "txt" if f.get("fmt") == "txt" else "zip"
    if folder:
        try:
            p = Path(folder).expanduser()
            anc = next((a for a in [p, *p.parents] if a.exists()), None)
            ok = p.is_absolute() and anc is not None and anc.is_dir() and (p == anc or not p.exists())
        except (RuntimeError, OSError, ValueError):
            ok = False
        if not ok:
            return f"Hittar inte mappen: {folder}. Skriv hela sökvägen, t.ex. ~/Documents/PLO-export."
    return {"games": [g for g in f.getlist("games") if g in ("PLO4", "PLO5", "PLO6")],
            "table": f.get("table") if f.get("table") in ("vanliga", "rush") else "",
            "stake": (f.get("stake") or "").strip(), "fran": fran, "till": till,
            "latest": latest, "limit": limit, "split": "en" if f.get("split") == "en" else "dag",
            "folder": folder, "fmt": fmt if folder else "zip"}


def _night_status(db):
    try:
        from . import night2, nightly
        st = night2.status(db)
        from .jobs import MANAGER
        st["running"] = any(j.title == "Nattberäkning" and j.status in ("väntar", "kör") for j in MANAGER.jobs.values())
        from .night import cpu_procs
        st["procs"] = cpu_procs()
        st["acceptance"] = night2.meta_get(db.con, "acceptance")
        try:  # 2.77.6: skuggmodell v3
            from . import night3
            st["v3"] = night3.acceptance(db, night3.v2_river_eq(db))
        except Exception as e:
            st["v3"] = {"status": f"fel: {type(e).__name__}"}
        st["lam_info"] = night2.meta_get(db.con, "lam_info")
        st["lines_info"] = night2.meta_get(db.con, "lines_info")
        st["schedule"] = nightly.schedule_status()
        st["receipt"] = nightly.last_receipt(db)
        try:
            files = sorted(nightly.reports_dir(db).glob("morgonrapport_*.md"))
            st["report"] = files[-1].name if files else None
        except Exception:
            st["report"] = None
        return st
    except Exception:
        return None


@app.get("/exportera")
def export_page(error=None, status=200):
    from . import watch as _w
    from .hhexport import export_dir
    last = _last_vid()
    V = _view(last) if last else None
    carry = V["C"].get("filters") if V else None
    done = EXPORTS.get(request.args.get("klar", ""))
    db = get_db()
    cfg = _w.load_settings(db)
    try:
        missing = db.missing_raw_count()
    except Exception:
        missing = 0
    return shell("exportera", "Exportera händer", carry=carry if carry and carry.get("enabled") else None,
                 done=done, error=error, status=status, exp_dir=cfg.get("export_dir") or "",
                 exp_fmt=cfg.get("export_fmt") or "zip", own_dir=str(export_dir(db)), missing_raw=missing,
                 night=_night_status(db), night_msg=request.args.get("natt", ""),
                 page_sub="Spara händer i originalformatet för DriveHUD eller HoldemManager")


@app.post("/exportera")
def export_start():
    from flask import redirect
    from .jobs import MANAGER
    spec = _export_form_spec(request.form)
    if isinstance(spec, str):
        return export_page(error=spec, status=400)
    from . import watch as _w
    _w.save_settings(get_db(), export_dir=spec["folder"] or "", export_fmt=spec["fmt"])  # kom ihåg till nästa gång
    job = MANAGER.start("Exportera händer", _export_job, spec, key=_job_key("export", spec))
    return redirect(f"/jobb/{job.id}")


@app.post("/natt")
def night_start():
    """🌙 Nattkörning nu: backup, nya händer, nattberäkning v2, acceptanstest och morgonrapport. Kan pausas."""
    from flask import redirect
    from .jobs import MANAGER
    from .night import blocked, force_for
    if request.form.get("direkt"):  # 2.78.1: GG stängt – starta utan att vänta 10 min på ny handhistorik
        force_for()
    why = blocked(get_db())
    if why:
        return export_page(error="🌙 " + why, status=400)
    try:
        procs = int(request.form.get("procs") or 0) or None
    except ValueError:
        procs = None
    from urllib.parse import quote

    def work(j):
        from .db import HandDB
        from .nightly import run_night
        with MANAGER.run_lock:  # 2.75: bara de skrivande stegen väntar på huvudkön
            _facts(j)
        r = run_night(None, procs, lambda m: j.set(m), db=HandDB(get_db().path), prep_lock=MANAGER.run_lock)
        return "/exportera?natt=" + quote(str(r.get("night2") or r.get("reason") or r.get("status"))[:300])
    job = MANAGER.start("Nattberäkning", work, key="natt", lane="natt")
    return redirect(f"/jobb/{job.id}")


@app.post("/natt/stopp")
def night_stop():
    from flask import redirect
    from . import night
    night.STOP["flag"] = True
    from urllib.parse import quote
    return redirect("/exportera?natt=" + quote("⏸ Pausar efter pågående omgång – den fortsätter där den slutade nästa gång."))


@app.post("/natt/schema")
def night_schedule():
    from flask import redirect
    from urllib.parse import quote
    from . import nightly
    try:
        if request.form.get("off"):
            msg = nightly.remove_schedule()
        else:
            msg = nightly.install_schedule((request.form.get("at") or nightly.DEFAULT_TIME).strip(),
                                           (request.form.get("stop") or nightly.DEFAULT_STOP).strip())
    except ValueError:
        msg = "Skriv tiden som HH:MM, t.ex. 03:30."
    return redirect("/exportera?natt=" + quote(msg[:300]))


@app.get("/natt/rapport")
def night_report():
    from flask import abort, send_file
    from . import nightly
    files = sorted(nightly.reports_dir(get_db()).glob("morgonrapport_*.md"))
    if not files:
        abort(404)
    return send_file(files[-1], as_attachment=True, download_name=files[-1].name, mimetype="text/markdown")


@app.post("/exportera/allt")
def export_all():
    """Genväg: hela databasen (alla varianter, hela perioden) som en zip i programmets exportmapp."""
    from flask import redirect
    from .jobs import MANAGER
    spec = {"games": [], "table": "", "stake": "", "fran": None, "till": None, "latest": None, "limit": None,
            "split": "en", "folder": "", "fmt": "zip"}
    job = MANAGER.start("Exportera händer", _export_job, spec, key=_job_key("export", spec))
    return redirect(f"/jobb/{job.id}")


@app.post("/v/<vid>/exportera-lista")
def export_list(vid):
    from flask import redirect
    from .jobs import MANAGER
    f = request.form
    lim = (f.get("limit") or "").strip()
    try:
        lim_n = int(lim) if lim else None
    except ValueError:
        lim_n = None
    spec = {"vid": vid, "split": "dag", "limit": lim_n if lim_n and lim_n > 0 else None,
            "args": {k: f.get(k, "") for k in ("q", "regel", "pos", "id", "sort", "dir", "fran_ts", "till_ts")}}
    job = MANAGER.start("Exportera händer", _export_job, spec, key=_job_key("export", spec))
    return redirect(f"/jobb/{job.id}")


@app.get("/exportera/fil/<name>")
def export_file(name):
    from flask import abort, send_file
    from .hhexport import NAME_OK, export_dir
    if not NAME_OK.match(name):
        abort(404)
    p = export_dir(get_db()) / name
    if not p.is_file():
        abort(404)
    if not _gg_closed() and request.args.get("ok") != "1":   # 2.87.3: fråga i stället för spärr
        return _gg_confirm_page(name)
    if not p.is_file():
        abort(404)
    return send_file(p, as_attachment=True, download_name=name, mimetype="application/zip")


@app.post("/bevaka")
def watch_settings():
    """Spara den bevakade mappen och läs in den direkt (som ett jobb med förlopp)."""
    from flask import redirect
    from . import watch
    from .jobs import MANAGER
    f = request.form
    folder = "" if f.get("off") else watch.normalize(f.get("watch") or "")
    if folder and not _dir_ok(folder):
        return page(f"Hittar inte mappen: {folder}", status=400)
    prob = watch.folder_problem(folder)
    if prob:
        return page(prob, status=400)
    watch.save_settings(get_db(), watch=folder or None, auto=f.get("auto") == "1", watch_dl=f.get("watch_dl") == "1")
    if not folder:
        return page(info="Bevakningen är avstängd.")
    job = MANAGER.start("Bevakad mapp", _watch_job, folder, key="bevaka")
    return redirect(f"/jobb/{job.id}")


def _watch_job(job, folder) -> str:
    import time
    from . import watch
    job.set(f"Läser in nya filer från {folder}")
    r = get_db().add_paths([Path(folder).expanduser()],
                           lambda i, n, new: job.set(f"Läser in nya filer ({new} nya händer hittills)", i, n))
    nf = r["files"] - r["files_skipped"]
    with watch._LOCK:
        watch.STATE.update(last=time.time(), new=r["hands_new"], files=nf, error=None)
        watch.STATE["new_since_view"] += r["hands_new"]
        watch.STATE["message"] = (f"Mappen bevakas. {r['hands_new']} nya händer lästes in"
                                  + ((" från 1 ny fil." if nf == 1 else f" från {nf} nya filer.") if nf else " – inga nya filer sedan förra gången.")
                                  + (f" ⚠ {len(r['rejected'])} fil(er) i zip lästes inte – se Import." if r.get("rejected") else ""))
    return "/import?klar=1"


@app.post("/rensa")
def clear_db():
    from .jobs import MANAGER
    with MANAGER.run_lock:  # vänta tills ett pågående jobb är klart
        get_db().clear()
        try:
            _snap_path().unlink(missing_ok=True)
            _snap_path().with_suffix(".json").unlink(missing_ok=True)
        except OSError:
            pass
        with _VLOCK:
            VIEWS.clear()
        _FT.update(key=None, ft=None)
    return page(info="Databasen är tömd.")


def _valid_date(d: str) -> bool:
    """ÅÅÅÅ-MM-DD och ett datum som finns (2026-13-45 avvisas)."""
    from datetime import datetime
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return len(d) == 10
    except ValueError:
        return False


def _why_empty(use_db, folder, uploads, fran, till, imports) -> str:
    """Säg exakt varför det inte fanns några händer att analysera."""
    if not use_db:
        if not folder and not uploads:
            return "Ange en mapp eller filer, eller kryssa ur \"Använd inte databasen\"."
        return "Hittade inga Omaha-händer i mappen/filerna." + (" Kontrollera också perioden." if fran or till else "")
    db = get_db()
    total = db.count()
    stale = db.stale_count()
    if total == 0:
        msg = f"Databasen är tom ({db.path}). "
        if stale:
            msg += (f"Den innehåller {stale} händer från en äldre version som måste läsas in igen – "
                    "ange mappen med dina händer en gång.")
        elif imports:
            msg += "Inga läsbara Omaha-händer hittades i det du angav."
        else:
            msg += "Ange mappen med dina händer (t.ex. DriveHUD-exporten) – de sparas då i databasen."
        return msg
    return (f"Databasen har {total} händer, men ingen inom perioden {fran or 'början'} – {till or 'slutet'}. "
            "Töm periodfälten eller ändra datumen.")


@app.post("/analyze")
def analyze_upload():
    """Tar emot formuläret, sparar uppladdade filer och startar ett bakgrundsjobb."""
    import tempfile
    from flask import redirect
    from .jobs import MANAGER
    f = request.form
    folder = (f.get("folder") or "").strip().strip('"')
    uploads = [x for x in request.files.getlist("files") if x.filename]
    spec = {"hero": (f.get("hero") or "").strip() or None, "game": f.get("game") or None,
            "games": [g for g in f.getlist("games") if g in ("PLO4", "PLO5", "PLO6")],
            "folder": folder, "use_db": not (f.get("no_db") == "1" and (folder or uploads)),
            "fran": (f.get("fran") or "").strip() or None, "till": (f.get("till") or "").strip() or None,
            "table": f.get("table") or "", "stake": f.get("stake") or "", "latest": None,
            "simulera": f.get("simulera") == "1", "upload_dir": None, "n_uploads": len(uploads),
            "model_sel": f.get("model_sel") == "1", "quick": f.get("quick") == "1",
            "view": f.get("mode") == "visa" and f.get("quick") != "1",
            "back": f.get("back") if f.get("back") in PAGES else "oversikt"}
    for d in (spec["fran"], spec["till"]):
        if d and not _valid_date(d):
            return page(f"Datum ska skrivas ÅÅÅÅ-MM-DD (fick {d}).", folder, status=400)
    if f.get("latest_on") == "1":
        try:
            spec["latest"] = int(f.get("latest") or 15000)
        except ValueError:
            return page("Antalet senaste händer måste vara ett heltal.", folder, status=400)
    if f.get("mode") == "analys":
        # 2.73.1: "🔬 Analysera urvalet" – läckor och modeller räknas på just urvalet om det är begränsat i tid,
        # annars en full analys av hela varianten (som tidigare "Uppdatera")
        spec["model_sel"] = bool(spec["latest"] or spec["fran"] or spec["till"])
    if folder and not _dir_ok(folder) and not _path_ok(folder):
        return page(f"Hittar inte mappen: {folder}", folder, status=400)
    if uploads:
        import re as _re
        import shutil as _sh
        td = tempfile.mkdtemp(prefix="plo_upp_")
        try:
            for i, x in enumerate(uploads):
                name = _re.sub(r"[^\w.\- ]+", "_", Path(x.filename.replace("\0", "")).name)[:120] or "fil"
                x.save(Path(td) / f"{i}_{name}")
        except (OSError, ValueError):
            _sh.rmtree(td, ignore_errors=True)
            return page("En av filerna kunde inte sparas. Försök igen.", folder, status=400)
        spec["upload_dir"] = td
    _user_selection_submitted(spec)
    job = MANAGER.start("Analys", _run_job, spec)
    return redirect(f"/jobb/{job.id}")


def _user_selection_submitted(spec: dict) -> None:
    """2.89: ditt urval gäller direkt när du trycker – även om en automatisk uppdatering råkar vara igång.
    1) Urvalet sparas som "senaste urval" redan nu (förut först när jobbet var klart), så att en automatisk
       uppdatering som startar under tiden använder ditt nya urval och inte det gamla.
    2) En automatisk uppdatering som väntar eller kör med det gamla urvalet avbryts; ditt jobb tar dess plats.
       (Den automatiska uppdateringen läser in nya händer – ditt jobb ser dem också, och nästa kontroll tar resten.)"""
    from . import watch
    from .jobs import MANAGER
    if spec.get("use_db") and not spec.get("upload_dir") and not spec.get("folder"):
        try:
            watch.save_settings(get_db(), last_spec={k: spec.get(k) for k in _SPEC_KEEP})
        except Exception:
            pass
    j = MANAGER.get(_AUTO["job"]) if _AUTO.get("job") else None
    if j is not None and j.status in ("väntar", "kör"):
        try:
            MANAGER.cancel(j.id)
        except Exception:
            pass


def _run_job(job, spec) -> str:
    if spec.get("restore"):
        job.set("Öppnar den senaste analysen")
        d = _load_snapshot()
        if d is not None:
            from . import watch
            vid = _add_view(d["C"], d["hero"])
            try:
                new = max(0, get_db().count() - int(d.get("db_count") or 0))
            except Exception:
                new = 0
            with watch._LOCK:
                watch.STATE["new_since_view"] = new
            return vid, spec.get("back") or d.get("back") or "oversikt"
    return _run_job_full(job, spec)


def _run_job_full(job, spec) -> str:
    import shutil
    from .db import set_active
    from .jobs import UserError
    from .pipeline import EmptySelection, build
    from .selection import Selection
    imports = []
    db_info = None
    hero = spec["hero"]
    from . import precompute
    precompute.cancel()  # 2.79: bakgrundskön släpper alla kärnor när du startar en analys
    try:
        if spec["use_db"]:
            db = get_db()
            if spec.get("quick"):
                job.set("Läser in nya händer från den bevakade mappen")
                try:
                    from . import watch as _wt
                    _wt.scan_now(db)
                except Exception:
                    pass
            for label, path in ((f"Mappen {spec['folder']}", spec["folder"]),
                                (f"{spec['n_uploads']} uppladdade filer", spec["upload_dir"])):
                if not path:
                    continue
                job.set(f"Läser in filer – {label}")
                r = db.add_paths([Path(path).expanduser()],
                                 lambda i, n, new: job.set(f"Läser in filer ({new} nya händer hittills)", i, n),
                                 fill_raw=True)
                imports.append((label, r))
            if db.count() == 0:
                raise UserError(_why_empty(True, spec["folder"], spec["n_uploads"], spec["fran"], spec["till"], imports))
            job.set("Letar upp ditt spelarnamn")
            hero = hero or db.detect_hero()
            if not hero:
                raise UserError("Hittade inget spelarnamn med hålkort i databasen. Ange ditt namn under \"Ditt spelarnamn\".")
            store = db.facts(hero)
            set_active(None)  # arbetsprocesserna läser själva de sparade beräkningar de behöver
            store.sync(db, lambda d, t, el: job.set("Räknar fram fakta för nya händer (görs bara en gång per hand)", d, t))
            job.set("Hämtar fakta")
            fkey = (str(db.path), hero, store.signature())
            if _FT["key"] == fkey:
                ft = _FT["ft"]  # samma data som förra analysen – ingen ny inläsning
            else:
                ft = store.load()
                _FT.update(key=fkey, ft=ft)
            data_sig, cache_dir = store.signature(), db.path.parent / (db.path.stem + "_resultat")
            lookup = db.get_hand
            a_, b_ = db.span()
            db_info = {"count": db.count(), "first": a_, "last": b_}
        else:
            from .facts import extract
            set_active(None)
            hands = []
            job.set("Läser in filer")
            for path in (spec["folder"], spec["upload_dir"]):
                if path:
                    hands.extend(load_paths([Path(path).expanduser()]))
            hands = dedupe(hands)
            if not hands:
                raise UserError(_why_empty(False, spec["folder"], spec["n_uploads"], spec["fran"], spec["till"], imports))
            hero = hero or detect_hero(hands)
            if not hero:
                raise UserError("Hittade inget spelarnamn med hålkort i filerna. Ange ditt namn under \"Ditt spelarnamn\".")
            ft = extract(hands, hero, lambda k: job.set("Räknar fram fakta", k, len(hands)))
            by_id = {h.id: h for h in hands}
            lookup = by_id.get
            data_sig = cache_dir = None
        if not ft.n:
            raise UserError(f'Ingen spelare som heter "{hero}" hittades.')
        games = tuple(spec["games"]) or ((spec["game"],) if spec["game"] else ())
        sel = Selection(games=games, table=spec["table"], stake=spec["stake"], date_from=spec["fran"],
                        date_to=spec["till"], latest=spec["latest"])
        sim = None
        if spec["simulera"]:
            from .sim import run_simulation
            job.set("Kör simuleringen av rundowns")
            sim = run_simulation()
        try:
            C = build(ft, hero, lookup, sel, use_db=spec["use_db"], hero_given=bool(spec["hero"]), sim=sim,
                      imports=imports, db_info=db_info, progress=job.set, data_sig=data_sig, cache_dir=cache_dir,
                      as_context=True, model_on_selection=bool(spec.get("model_sel")), quick=bool(spec.get("quick")),
                      view=bool(spec.get("view")))
        except EmptySelection as e:
            raise UserError(str(e))
        if spec["use_db"]:
            get_db().save_calc()
        job.set("Öppnar analysen")
        from . import watch
        watch.view_opened()
        vid = _add_view(C, hero)
        if spec["use_db"]:
            _save_snapshot(C, hero, spec.get("back") or "oversikt", _FT.get("key"))
            if os.environ.get("PLO_PRECOMPUTE", "1") != "0":
                precompute.schedule(get_db().path, hero, bool(spec["hero"]))  # 2.79: förbered vanliga urval
            try:  # samma urval används när programmet uppdaterar automatiskt
                watch.save_settings(get_db(), last_spec={k: spec.get(k) for k in _SPEC_KEEP})
            except Exception:
                pass
        return vid, spec.get("back") or "oversikt"
    finally:
        if spec["upload_dir"]:
            shutil.rmtree(spec["upload_dir"], ignore_errors=True)


@app.get("/jobb/<jid>")
def job_page(jid):
    from .jobs import MANAGER
    j = MANAGER.get(jid)
    title = {"Analys": "Analyserar", "Exportera händer": "Exporterar händer", "Bevakad mapp": "Läser in nya händer"}.get(
        j.title if j else "", "Arbetar")
    return shell("jobb", title, job_id=jid, page_sub="Sidan uppdateras av sig själv")


@app.post("/jobb/<jid>/avbryt")
def job_cancel(jid):
    """2.88: avbryt ett tungt jobb (analys, djupanalys, zip, nattberäkning)."""
    from flask import redirect
    from .jobs import MANAGER
    MANAGER.cancel(jid)
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True}
    return redirect(request.referrer or f"/jobb/{jid}")


@app.get("/jobb/<jid>/status")
def job_status(jid):
    from .jobs import MANAGER
    j = MANAGER.get(jid)
    return j.as_dict() if j else {"status": "saknas"}


@app.get("/jobb/<jid>/rapport")
def job_report(jid):
    from .jobs import MANAGER
    j = MANAGER.get(jid)
    if j is None:
        return page("Rapporten finns inte längre – kör analysen igen.", status=404)
    if j.status != "klar":
        return job_page(jid)
    from flask import redirect
    if isinstance(j.result, str) and j.result.startswith("/"):
        return redirect(j.result)
    vid, back = j.result
    if _view(vid) is None:
        return page("Analysen är inte öppen längre – kör den igen.", status=404)
    return redirect(f"/v/{vid}/{back if back in PAGES else 'oversikt'}")


@app.get("/jobb/<jid>/fel")
def job_error(jid):
    from .jobs import MANAGER
    j = MANAGER.get(jid)
    msg = (j.error if j and j.error else "Analysen finns inte längre – kör den igen.")
    return page(msg, status=400)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="Lyssna på hela nätverket (för att nå sidan från mobilen)")
    ap.add_argument("--open", action="store_true", help="Öppna webbläsaren automatiskt")
    a = ap.parse_args()
    from . import ggguard
    if ggguard.refuse_if_gg():
        sys.exit(2)
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    port = a.port
    if not _port_free(port) and "PLO-läckfinnare" in _who_is_on(port):
        import time
        import urllib.request
        try:  # be den gamla versionen stänga sig (fungerar från version 1.23)
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/avsluta", data=b"", method="POST"),
                                   timeout=2)
            for _ in range(20):
                time.sleep(0.25)
                if _port_free(port):
                    print("En äldre version av läckfinnaren stängdes.")
                    break
        except Exception:
            pass
    if not _port_free(port):
        who = _who_is_on(port)
        print("=" * 70)
        print(f"OBS: Port {port} används redan av {who}.")
        print("Det är troligen ett gammalt terminalfönster som fortfarande är öppet.")
        print("Stäng det fönstret (eller avsluta Terminal helt) så du inte råkar använda den gamla versionen.")
        print("=" * 70)
        for cand in range(port + 1, port + 50):
            if _port_free(cand):
                port = cand
                break
    a.port = port
    url = f"http://localhost:{a.port}"
    if a.lan:
        import secrets
        _LAN["token"] = secrets.token_urlsafe(8)
        url = f"{url}/?kod={_LAN['token']}"
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"På mobilen (samma wifi): http://{ip}:{a.port}/?kod={_LAN['token']}")
            print("Koden behövs – utan den kommer ingen annan på nätverket åt dina händer.")
        except OSError:
            pass
    from . import watch
    from .jobs import MANAGER
    watch.ON_NEW = _auto_update
    watch.start(get_db, MANAGER.run_lock)
    ggguard.start(kill=False)   # 2.87.1: webbprogrammet stängs inte när GG startas
    print(f"PLO-läckfinnaren version {__version__} körs på {url}  (stäng fönstret för att avsluta)")
    if a.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
