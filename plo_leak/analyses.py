"""Analysmodulerna och deras register.

Varje analys är en funktion som får ett sammanhang (urvalets statistik m.m.) och tidigare
analysers resultat, och lämnar ett resultat. Den vet ingenting om HTML. Rapporten, webben
och exportfilen visar bara resultaten.

Ny analys = en ny funktion med @analysis(...). Ändras en analys höjs dess version, så att
sparade resultat från den gamla versionen inte används.

Resultat sparas på disk per (data, urval, analys, version). Samma urval utan nya händer
visas då direkt nästa gång.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

REGISTRY: dict[str, dict] = {}
ORDER: list[str] = []


# ---------------------------------------------------------------- 2.79: cachenyckel per analys
# Nyckeln byggs av analysens egen version + ett fingeravtryck av analysfunktionens källkod och alla programfiler den
# (transitivt) importerar inom paketet, + FACTS_VERSION. En ny programversion som inte rör en analys (t.ex. bara
# webben, mallarna eller nattkörningen) behåller därför de sparade resultaten; ändras en fil analysen använder räknas
# just den analysen om. Saknas källkoden (t.ex. paketerat program) används programversionen som förut.
_PKG = Path(__file__).resolve().parent
_MOD_DEPS: dict = {}
_FP: dict = {}


def _mod_src(mod: str) -> bytes | None:
    f = _PKG / f"{mod}.py"
    try:
        return f.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return None


def _mod_deps(mod: str) -> set:
    """Moduler i paketet som modulen importerar (relativa importer, även inne i funktioner)."""
    if mod not in _MOD_DEPS:
        import ast
        out = set()
        src = _mod_src(mod)
        if src is not None:
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, ast.ImportFrom) and n.level == 1:
                    if n.module:
                        out.add(n.module.split(".")[0])
                    else:
                        out |= {a.name for a in n.names}
        _MOD_DEPS[mod] = {m for m in out if (_PKG / f"{m}.py").exists()}
    return _MOD_DEPS[mod]


def _closure(direct) -> list:
    seen, todo = set(), list(direct)
    while todo:
        m = todo.pop()
        if m not in seen:
            seen.add(m)
            todo.extend(_mod_deps(m))
    return sorted(seen)


def fingerprint(name: str) -> str:
    """Fingeravtryck för en registrerad analys (källkod + beroenden + FACTS_VERSION + beroende analyser)."""
    if name in _FP:
        return _FP[name]
    import inspect
    import re
    spec = REGISTRY[name]
    try:
        from .facts import FACTS_VERSION
        fn_src = inspect.getsource(spec["fn"])
        direct = set(re.findall(r"from \.(\w+) import", fn_src))
        h = hashlib.sha256()
        h.update(f"{name}|{spec['version']}|F{FACTS_VERSION}|".encode())
        h.update(" ".join(fn_src.split()).encode("utf-8"))
        for m in _closure(direct):
            src = _mod_src(m)
            if src is None:
                raise OSError(m)
            h.update(f"|{m}|".encode())
            h.update(src)
        for d in spec.get("after") or ():
            h.update(f"|after:{fingerprint(d)}".encode())
        fp = h.hexdigest()[:20]
    except (OSError, TypeError):
        fp = f"v{__version__}"
    _FP[name] = fp
    return fp


def module_fingerprint(*mods: str) -> str:
    """Samma sorts fingeravtryck för andra sparade resultat (t.ex. regeltestet i holdout.py)."""
    key = ("mods",) + tuple(sorted(mods))
    if key not in _FP:
        h = hashlib.sha256()
        try:
            from .facts import FACTS_VERSION
            h.update(f"F{FACTS_VERSION}".encode())
            for m in _closure(mods):
                src = _mod_src(m)
                if src is None:
                    raise OSError(m)
                h.update(f"|{m}|".encode())
                h.update(src)
            _FP[key] = h.hexdigest()[:20]
        except OSError:
            _FP[key] = f"v{__version__}"
    return _FP[key]


def analysis(name: str, version: int = 1, cache: bool = True, single_variant: bool = False, strict_only: bool = False,
             empty=None, label: str | None = None, model: bool = False, after: tuple = ()):
    """Registrera en analys. single_variant: körs inte när flera varianter analyseras tillsammans.
    model=True: analysen beskriver ditt spel (läckor, gränser, river-modellen …) och räknas på alla händer i
    varianten/bordet/nivån – inte på datumintervall eller "senaste N händer". Den räknas då om bara när nya
    händer kommer in, inte när du ändrar datum eller antal händer."""
    def deco(fn):
        REGISTRY[name] = {"fn": fn, "version": version, "cache": cache, "single": single_variant,
                          "strict_only": strict_only, "empty": empty, "label": label or name, "model": model,
                          "after": tuple(after)}
        ORDER.append(name)
        return fn
    return deco


@dataclass
class Ctx:
    st: object
    hero: str
    strict: bool = True
    mixed: bool = False
    pool: object = None
    river: object = None
    profile: str | None = None
    cache_key: str | None = None      # None = spara inte resultat (t.ex. händer utan databas)
    cache_dir: Path | None = None
    timings: dict = field(default_factory=dict)
    model_key: str | None = None      # nyckel för modellanalyserna (urvalet utan datum/senaste N); None = samma som cache_key
    model_st_fn: object = None        # ger statistiken för det urvalet (byggs bara om en modellanalys måste räknas)
    skip_models: bool = False         # 2.73.1: "Visa urvalet" utan sparad analys – modellanalyserna körs inte alls
    _model_st: object = None

    def model_st(self):
        if self.model_key is None or self.model_st_fn is None:
            return self.st
        if self._model_st is None:
            self._model_st = self.model_st_fn()
        return self._model_st


def _empty(spec):
    e = spec["empty"]
    return e() if callable(e) else e


def _cache_path(ctx: Ctx, name: str):
    spec = REGISTRY[name]
    use_model = spec.get("model") and ctx.model_key is not None
    key = ctx.model_key if use_model else ctx.cache_key
    if spec["cache"] and key and ctx.cache_dir:
        h = hashlib.sha1(f"{key}|{name}|{fingerprint(name)}".encode()).hexdigest()[:24]
        return ctx.cache_dir / f"{h}.pkl"
    return None


def _will_compute(ctx: Ctx, name: str) -> bool:
    spec = REGISTRY.get(name)
    if spec is None or (spec["single"] and ctx.mixed) or (spec["strict_only"] and not ctx.strict) \
            or (spec.get("model") and ctx.skip_models):
        return False
    p = _cache_path(ctx, name)
    return p is None or not p.exists()


_BG: dict = {}   # 2.79: analyser som räknas i en egen process (namn -> (executor, future))


def _bg_result(name: str):
    """Svaret från en analys som körts i en egen process, eller None (då räknas den här som förut)."""
    import threading
    item = _BG.pop((name, threading.get_ident()), None)
    if item is None:
        return None
    ex, fut = item
    try:
        return fut.result()
    except Exception:
        return None
    finally:
        ex.shutdown(wait=False)


def _warm(ctx: Ctx) -> None:
    """2.79: tunga radberäkningar startas i flera processer i bakgrunden medan analyserna körs i tur och ordning.
    Resultaten är desamma – raderna räknas per hand och läses sedan av analysen som vanligt."""
    if os.environ.get("PLO_PAR_ROWS", "1") == "0":
        return
    try:
        import multiprocessing as mp
        from .night import cpu_procs
        if mp.current_process().daemon or cpu_procs() < 2:
            return   # i en arbetsprocess (bakgrundskön) eller med en kärna: allt i tur och ordning som förut
    except Exception:
        return
    try:
        if _will_compute(ctx, "river_coach"):
            from concurrent.futures import ProcessPoolExecutor
            from .rivercoach import coach_worker, light_state
            st = ctx.model_st() if (REGISTRY["river_coach"].get("model") and ctx.model_key is not None) else ctx.st
            if getattr(st, "ft", None) is not None:
                ex = ProcessPoolExecutor(1, mp_context=mp.get_context("spawn"))
                _BG[("river_coach", __import__("threading").get_ident())] = (ex, ex.submit(coach_worker, (light_state(st), ctx.hero)))
    except Exception:
        _BG.pop(("river_coach", __import__("threading").get_ident()), None)
    try:
        if _will_compute(ctx, "pf_forward"):
            from .pfforward import warm_rows
            st = ctx.model_st() if (REGISTRY["pf_forward"].get("model") and ctx.model_key is not None) else ctx.st
            warm_rows(st, ctx.hero, ctx.cache_dir)
    except Exception:
        pass


def run(ctx: Ctx, progress=None) -> dict:
    R: dict = {}
    _warm(ctx)
    for name in ORDER:
        spec = REGISTRY[name]
        if (spec["single"] and ctx.mixed) or (spec["strict_only"] and not ctx.strict) or (spec.get("model") and ctx.skip_models):
            R[name] = _empty(spec)
            continue
        if progress:
            progress(f"Kör analyserna – {spec['label']}")
        t0 = time.time()
        path = None
        use_model = spec.get("model") and ctx.model_key is not None
        key = ctx.model_key if use_model else ctx.cache_key
        if spec["cache"] and key and ctx.cache_dir:
            h = hashlib.sha1(f"{key}|{name}|{fingerprint(name)}".encode()).hexdigest()[:24]
            path = ctx.cache_dir / f"{h}.pkl"
            if path.exists():
                try:
                    R[name] = __import__("plo_leak.signcache", fromlist=["x"]).loads(path.read_bytes())
                    ctx.timings[name] = ("sparat", round(time.time() - t0, 2))
                    continue
                except Exception:
                    pass
        if use_model:
            from dataclasses import replace as _replace
            R[name] = spec["fn"](_replace(ctx, st=ctx.model_st()), R)
        else:
            R[name] = spec["fn"](ctx, R)
        ctx.timings[name] = ("räknat", round(time.time() - t0, 2))
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")  # 2.79: unik per process
                tmp.write_bytes(__import__("plo_leak.signcache", fromlist=["x"]).dumps(R[name]))
                os.replace(tmp, path)
                _prune(ctx.cache_dir)
            except Exception:
                pass
    import threading
    for key in [k for k in _BG if k[1] == threading.get_ident()]:   # t.ex. analysen hoppades över – stäng processen
        _bg_result(key[0])
    return R


def _prune(d: Path, keep: int = 400) -> None:
    files = sorted(d.glob("*.pkl"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- analyserna
@analysis("leaks", label="läckor (upptäck och bekräfta)", version=1, empty=lambda: {"leaks": [], "tests": 0, "candidates": 0}, model=True)
def _leaks(ctx, R):
    from .leaks import find_leaks, find_proven
    st = ctx.st
    leaks = find_proven(st, ctx.river) if ctx.strict else find_leaks(st, ctx.profile, ctx.pool)
    return {"leaks": leaks, "tests": st.decisions.tests, "candidates": getattr(st.decisions, "candidates", None)}


@analysis("ranges", label="gränser för starthänder", version=3, single_variant=True, strict_only=True, empty=list, model=True)
def _ranges(ctx, R):
    from .ranges import analyze_ranges
    return analyze_ranges(ctx.st.decisions)


@analysis("guide", label="öppningsguide", version=1, single_variant=True, empty=list, model=True)
def _guide(ctx, R):
    from .ranges import opening_guide
    return opening_guide(ctx.st.decisions)


@analysis("river_tbl", label="river-syner", version=2, single_variant=True, empty=dict, model=True)
def _river(ctx, R):
    from .summary import river_call_table
    return river_call_table(ctx.st.decisions)


@analysis("river_bluff", label="river-bets och bluffar", version=3, single_variant=True, empty=dict, model=True)
def _river_bluff(ctx, R):
    from .summary import river_bluff_table
    return river_bluff_table(getattr(ctx.st, "ft", None), ctx.st.rows)


@analysis("river_guide", label="syna-gräns på river", version=2, single_variant=True, empty=dict, model=True)
def _river_guide(ctx, R):
    from .summary import river_call_guide
    return river_call_guide(getattr(ctx.st, "ft", None), ctx.st.rows)


@analysis("river_coach", label="river-coach (bästa beslut mot poolens ranges)", version=1, single_variant=True, empty=dict, model=True)
def _river_coach(ctx, R):
    from .rivercoach import coach
    got = _bg_result("river_coach")
    if got is not None:
        return got
    try:
        return coach(ctx.st, ctx.hero)
    except Exception as e:  # modellen får aldrig stoppa analysen
        return {"error": str(e)}


@analysis("turn_tbl", label="turn-syner", version=1, single_variant=True, empty=dict, model=True)
def _turn(ctx, R):
    from .summary import turn_call_table
    return turn_call_table(ctx.st.decisions)


@analysis("rundowns", label="rundowns", version=1, single_variant=True, strict_only=True, empty=dict, model=True)
def _rundowns(ctx, R):
    from .rundowns import rundown_table
    return rundown_table(ctx.st)


@analysis("nut_fold", label="starthänder jämfört med fold", version=1, single_variant=True, empty=dict, model=True)
def _nut_fold(ctx, R):
    from .nutfold import nut_fold_table
    return nut_fold_table(ctx.st)


@analysis("pos_leaks", label="positionsläckor", version=1, single_variant=True, empty=dict, model=True)
def _pos_leaks(ctx, R):
    from .positionleaks import position_leaks
    try:
        return position_leaks(ctx.st)
    except Exception as e:  # får aldrig stoppa analysen
        return {"error": str(e)}


@analysis("likely", label="trolig förbättring", version=2, single_variant=True, strict_only=True, empty=list, model=True,
          after=("ranges",))
def _likely(ctx, R):
    from .likely import likely_improvements
    return likely_improvements(ctx.st, R.get("ranges"))


@analysis("potsize", label="resultat efter pottstorlek", version=1, empty=dict)
def _potsize(ctx, R):
    from .potsize import pot_table
    return pot_table(ctx.st)


@analysis("hourly", label="timlön", version=2, empty=dict)
def _hourly(ctx, R):
    from .hourly import hourly_table
    return hourly_table(ctx.st)


@analysis("tested", label="översikt över testerna", version=1, empty=list)
def _tested(ctx, R):
    from .decisions import ACTION_VERB, SPOT_NAMES, tested_overview
    raw = tested_overview(ctx.st.decisions)
    out = []
    for r in raw:
        if r["bucket"] != "alla" and r["pos"] != "alla":
            continue
        verb = ACTION_VERB.get((r["spot"], r["action"]), r["action"])
        where = SPOT_NAMES.get(r["spot"], r["spot"])
        who = "" if r["bucket"] == "alla" else f" · {r['bucket']}"
        pos = "" if r["pos"] == "alla" else f" · {r['pos']}"
        out.append({"label": f"{verb.capitalize()} {where}{pos}{who}", "n": r["n"], "mean": r["mean"],
                    "z": r["z"], "mde": 3 * r["se"]})
    out.sort(key=lambda r: r["z"])
    return {"rows": out, "raw": raw}


@analysis("power", label="vad urvalet kan avgöra", version=1, empty=list)
def _power(ctx, R):
    from .decisions import ACTION_VERB, SPOT_NAMES, detectable_effect
    raw = detectable_effect(ctx.st.decisions)
    rows = sorted(({"label": f"{ACTION_VERB.get((r['spot'], r['action']), r['action']).capitalize()} "
                             f"{SPOT_NAMES.get(r['spot'], r['spot'])}", "n": r["n"], "mde": r["mde"]}
                   for r in raw), key=lambda r: -r["n"])[:14]
    return {"rows": rows, "raw": raw}


@analysis("pf_forward", label="framåttest av postflop-riktlinjer", version=2, single_variant=True, strict_only=True, empty=dict, model=True)
def _pf_forward(ctx, R):
    from .pfforward import forward_postflop
    try:
        return forward_postflop(ctx.st, ctx.hero, cache_dir=ctx.cache_dir)
    except Exception as e:  # får aldrig stoppa analysen
        return {"error": str(e)}


@analysis("hypotheses", label="nya framåthypoteser (2026-11-15)", version=1, single_variant=True, strict_only=True, empty=dict, model=True)
def _hypotheses(ctx, R):
    from .hypotheses import hypotheses_test
    try:
        return hypotheses_test(ctx.st)
    except Exception as e:  # får aldrig stoppa analysen
        return {"error": str(e)}


@analysis("betsize", label="betstorlek och polarisering", version=1, single_variant=True, empty=dict, model=True)
def _betsize(ctx, R):
    from .betsize import betsize_report
    try:
        return betsize_report(ctx.st)
    except Exception as e:
        return {"error": str(e)}
