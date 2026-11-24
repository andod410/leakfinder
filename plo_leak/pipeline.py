"""Analysvägen från fakta till rapport – gemensam för webben och kommandoraden.

    fakta (FactTable) + urval (Selection) -> HeroStats -> analyser -> rapport (HTML)
"""
from __future__ import annotations

from datetime import datetime

from collections import Counter
from dataclasses import replace

import numpy as np

from .aggregate import build_stats
from .facts import FactTable, dt_of
from .selection import Selection, game_table_ft


class EmptySelection(Exception):
    """Inga händer matchar urvalet. Meddelandet är skrivet för användaren."""


def available(ft: FactTable, sel: Selection, games: tuple) -> dict:
    """Valmöjligheter för urvalsrutan: varianter, nivåer och bordstyper som finns i datan."""
    pm = sel.period_mask(ft)
    H = ft.H
    nh_all = sorted({int(x) for x in np.unique(H["nh"][pm])}, reverse=True)
    gm = pm & np.isin(H["nh"], [int(g[-1]) for g in games])
    st = Counter(H["stake"][gm].tolist())
    span = (dt_of(H["ts"][0]).strftime("%Y-%m-%d"), dt_of(H["ts"][-1]).strftime("%Y-%m-%d")) if ft.n else ("", "")
    return {"games": [f"PLO{g}" for g in nh_all], "stakes": [ft.label("stake", k) for k, _ in st.most_common()],
            "has_rush": bool((H["ttype"][gm] == 1).any()), "span": list(span)}


def build(ft: FactTable, hero: str, lookup, sel: Selection, *, use_db: bool = True, hero_given: bool = False,
          sim=None, imports=None, db_info=None, progress=None, data_sig: str | None = None, cache_dir=None,
          strict: bool = True, pool=None, river=None, profile: str | None = None, collect: dict | None = None, as_context: bool = False,
          model_on_selection: bool = False, quick: bool = False, view: bool = False):
    """data_sig: faktabutikens signatur – då sparas analysresultaten per urval och återanvänds.
    as_context=True: returnera mallvariablerna (för programmets sidor) i stället för en färdig HTML-sida.
    view=True (2.73.1, "Visa urvalet"): bara urvalet byts. Läckor, regler och modeller tas från den senaste fulla
    analysen av samma variant/bord/nivå – även om nya händer kommit in sedan dess – och räknas aldrig om. Finns ingen
    sparad analys för den kombinationen visas urvalet utan dem."""
    from .leaks import detect_profile
    from .report import build_context, build_report
    pm = sel.period_mask(ft)
    if not pm.any():
        raise EmptySelection(f"Inga händer inom perioden {sel.date_from or 'början'} – {sel.date_to or 'slutet'}. "
                             "Ändra eller töm periodfälten.")
    games = sel.resolve_games(ft, pm)
    sel2 = replace(sel, games=games)
    mask = sel2.mask(ft)
    if not mask.any():
        raise EmptySelection("Inga händer matchar urvalet (variant, bordstyp, nivå och period). Ändra urvalet och försök igen.")
    key = f"{data_sig}|{sel2.key()}|{hero}" if data_sig else None
    if pool is not None or river is not None or not strict:
        key = None  # gamla lägen med riktvärden/river-modell sparas inte
    base = replace(sel2, date_from=None, date_to=None, latest=None)
    bkey = f"{base.key()}|{hero}"
    stored = _model_sig_get(cache_dir, bkey) if key else None
    # 2.79: färdiga urval på disk (se precompute.py). Bara lägen som inte sparar regler; nyckeln täcker allt som
    # påverkar sidan, så en träff är samma sida som en ny beräkning.
    ckey = None
    import os
    if (as_context and key and cache_dir and os.environ.get("PLO_CTX_CACHE", "1") != "0" and sim is None and not imports and profile is None and collect is None):
        nb0 = int(base.mask(ft).sum())
        uq = bool((quick or view) and stored and not model_on_selection and (view or 0 <= nb0 - stored["n"] <= QUICK_MAX))
        sk = bool(view and not stored and not model_on_selection)
        rmode = "save" if (use_db and sel.full and strict and not uq and not sk) else "load"
        if rmode == "load":
            from . import precompute
            flags = {"view": bool(view), "quick": bool(quick), "use_quick": uq, "skip": sk, "msel": bool(model_on_selection),
                     "hero_given": bool(hero_given), "use_db": bool(use_db), "full": bool(sel.full), "nb": nb0 if quick else None}
            ckey = precompute.context_key(data_sig=data_sig, sel_key=(sel.key(), sel2.key()), hero=hero,
                                          variants=games, cache_dir=cache_dir, flags=flags,
                                          stored=stored if (quick or view) else None, db_info=db_info)
            C = precompute.load_context(cache_dir, ckey, ft, lookup)
            if C is not None:
                if progress:
                    progress("Öppnar det sparade urvalet")
                if not uq and not model_on_selection and not sk:
                    _model_sig_put(cache_dir, bkey, {"sig": data_sig, "n": nb0, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
                C["generated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                C["export_name"] = f"plo_analys_till_claude_{datetime.now():%Y%m%d_%H%M}.json"
                return C
    if progress:
        progress("Summerar händerna i urvalet")
    st = build_stats(ft, mask, hero, lookup)
    game_rows = game_table_ft(ft, pm)
    av = available(ft, sel, games)
    filters = {"enabled": True, "game": games[0], "games_sel": list(games), "hero": hero if hero_given else "",
               "games": av["games"], "table": sel.table, "has_rush": av["has_rush"], "stake": sel.stake,
               "stakes": av["stakes"], "latest_on": bool(sel.latest), "latest": str(sel.latest or 15000),
               "fran": sel.date_from or "", "till": sel.date_to or "", "full": use_db and sel.full, "span": av["span"],
               "model_sel": bool(model_on_selection),
               # 2.89: hur många händer som fanns före "senaste N" – urvalsraden visar "N av M händer"
               "n_all": int(replace(sel2, latest=None).mask(ft).sum()) if sel.latest else None}
    if progress:
        progress("Kör analyserna")
    fn = build_context if as_context else build_report
    extra = {"live": True} if as_context else {}
    # Modellanalyserna (läckor, gränser, river-modellen …) räknas på alla händer i variant/bord/nivå och
    # sparas – byter du bara datum eller "senaste N händer" återanvänds de, och räknas om först när nya
    # händer kommer in.
    # Snabb uppdatering (nya händer från den bevakade mappen): läckor, regler och modeller från senaste fulla
    # analysen återanvänds – bara resultat, sessioner, grafer och timlön räknas om med de nya händerna. Efter
    # QUICK_MAX nya händer sedan den fulla analysen görs en full analys ändå.
    bmask = base.mask(ft) if key else None
    nb = int(bmask.sum()) if bmask is not None else 0
    use_quick = bool((quick or view) and key and stored and not model_on_selection
                     and (view or 0 <= nb - stored["n"] <= QUICK_MAX))
    skip_models = bool(view and key and not stored and not model_on_selection)
    if skip_models:
        extra["skip_models"] = True
    model_sig = stored["sig"] if use_quick else data_sig
    if key and not model_on_selection and (base.key() != sel2.key() or use_quick):
        extra["model_key"] = f"{model_sig}|{base.key()}|{hero}"
        extra["model_st_fn"] = lambda: build_stats(ft, bmask, hero, lookup)
    if as_context:
        extra["quick_info"] = ({"since": max(nb - stored["n"], 0), "date": stored.get("date", ""), "max": QUICK_MAX,
                                "view": bool(view)} if use_quick else
                               {"skipped": True, "view": True} if skip_models else None)
    out = fn(None, hero, profile or detect_profile(st), st, pool, strict=strict, river=river, sim=sim,
             game_rows=game_rows, filters=filters, mixed=sel2.mixed, imports=imports, db_info=db_info,
             rules_mode="save" if (use_db and sel.full and strict and not use_quick and not skip_models) else "load",
             cache_key=key, cache_dir=cache_dir, progress=progress, collect=collect, **extra)
    if key and not use_quick and not model_on_selection and not skip_models:
        _model_sig_put(cache_dir, bkey, {"sig": data_sig, "n": nb, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    if ckey is not None:
        precompute.save_context(cache_dir, ckey, out, ft)
    return out


def warm_full(ft: FactTable, hero: str, lookup, sel: Selection, *, data_sig: str, cache_dir) -> None:
    """2.79 (förberäkningen): räkna och spara analysresultaten för en full analys av urvalet – exakt samma
    sammanhang som build() ger analyserna – utan att skriva regler eller modellsignatur."""
    from .analyses import Ctx, run
    from .leaks import detect_profile
    pm = sel.period_mask(ft)
    if not pm.any():
        return
    sel2 = replace(sel, games=sel.resolve_games(ft, pm))
    mask = sel2.mask(ft)
    if not mask.any() or not data_sig or not cache_dir:
        return
    base = replace(sel2, date_from=None, date_to=None, latest=None)
    if base.key() != sel2.key():
        return  # bara hela varianten (då räknas modellanalyserna på samma urval)
    st = build_stats(ft, mask, hero, lookup)
    run(Ctx(st=st, hero=hero, strict=True, mixed=sel2.mixed, profile=detect_profile(st),
            cache_key=f"{data_sig}|{sel2.key()}|{hero}", cache_dir=cache_dir))


QUICK_MAX = 10000


def _model_sig_file(cache_dir):
    from pathlib import Path
    return Path(cache_dir) / "model_sig.json" if cache_dir else None


def _model_sig_get(cache_dir, bkey):
    import json
    f = _model_sig_file(cache_dir)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get(bkey) if f and f.exists() else None
    except (OSError, ValueError):
        return None


def _model_sig_put(cache_dir, bkey, val):
    import json
    f = _model_sig_file(cache_dir)
    if not f:
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        d = {}
    d[bkey] = val
    try:
        import os
        import uuid
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{uuid.uuid4().hex[:8]}.tmp")  # 2.79: atomiskt (förberäkningen läser samtidigt)
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass
