"""Riktlinjer: råd som inte är statistiskt bekräftade regler.

Regler i programmet bygger på din egen data och är märkta bekräftad/trolig. Riktlinjer är strategiska råd
(från analyser med Claude) där datan pekar åt ett håll men inte kan bevisa det – t.ex. för att du själv valt
vilka händer du spelat på vilket sätt. De visas som råd (💡), räknas aldrig som regelbrott och påverkar inte
regelföljning eller fokuskö.
"""
from __future__ import annotations

from collections import Counter

from .cards import nut_qualities

DEEP_BB = 130  # djupare än så: i position kan du blanda in syner med AA så att handen inte blir face up

GUIDELINES = [
    {"id": "aa_sa_4bet", "area": "preflop", "rank": 9, "title": "Mot 3-bet: 4-betta AA med suited ess",
     "do": "AA där minst ett ess har ett kort till i samma färg: 4-betta vid ~100 bb, i och ur position. "
           f"Djupare än ~{DEEP_BB} bb: 4-betta ur position; i position kan du blanda in syner så att handen inte blir face up. "
           "AA utan färg: syna (djupt, ur position och svag resten av handen: fold är också okej).",
     "why": "I din data har 4-bet med högt par + suited ess gett ca +10–11 bb mot fold, syn ca +3,5–5,6 bb. "
            "Inte bevisat – du har själv valt vilka AA-händer du 4-bettat."},
    {"id": "hj_sa_low", "area": "preflop", "rank": 10, "level": "trolig", "gain": "~0,3–0,5 bb/100", "per100": 0.4,
     "title": "HJ: folda suited ess utan höga kort",
     "do": "I HJ (foldat till dig): folda händer vars enda styrka är ett suited ess med högst två kort T eller högre (inte AA/KK). "
           "I CO och senare är samma händer okej.",
     "why": "Nattanalysen 2026-11-08: −2,1 ± 0,5 bb per öppning i HJ, i båda halvorna av spelpassen. Ungefär hälften "
            "täcks redan av HJ-31 %-regeln."},
    {"id": "no_premium_fold", "area": "preflop", "rank": 11, "level": "trolig", "gain": "~0,4 bb/100",
     "per100": 0.4, "title": "Folda aldrig dina bästa händer när det är foldat till dig",
     "do": "Du foldar 5–7 % av dina topp-10 %-händer (även AA) när det är foldat till dig. Ta tiden, öppna alltid.",
     "why": "Nattanalysen 2026-11-08. Orsaken syns inte i datan (timeout, felklick eller för många bord)."},
    {"id": "bb_0nut_hu", "area": "preflop", "rank": 12, "level": "trolig", "gain": "~0,2 bb/100", "per100": 0.2,
     "title": "BB med 0 nöt-egenskaper: syna bara i två lägen",
     "do": "BB mot en öppning, inga andra i potten, hand utan nöt-egenskaper: syna bara när SB öppnat (högst ~3 bb) "
           "eller handen är dubbelsuited + suited kung. Folda resten – och alltid när någon annan redan synat.",
     "why": "Analys 2026-11-08 av 942 syner: övriga −1,8 ± 0,8 bb per syn mot fold (minus i båda halvorna av "
            "spelpassen); mot SB-öppning +0,8, dubbelsuited + suited kung +1,6 (inte bevisat plus). Med en extra "
            "synare i potten −1,4 bb per syn."},
    # 2026-11-12 (analys av 208 936 händer med Claude, se claude/analys-2026-11-12.md)
    {"id": "low_pairs_no_nut", "verified": True, "area": "preflop", "rank": 8, "level": "bekräftad", "gain": "~1,5–2,2 bb/100 (ingår i 0-nöt-reglerna)",
     "title": "Låga par och dubbelpar räknas inte: folda dem utan nöt-egenskaper",
     "do": "Folda preflop händer där enda paret/paren är under JJ och handen saknar nöt-egenskaper (suited ess, rundown) – "
           "utom trippelsuited och dubbelsuited + suited kung. Gäller även i BB.",
     "why": "Granskning 2026-11-12 (holdout): 5 340 spelade händer, −1,27 ± 0,28 bb per hand mot fold, negativ i alla fyra "
            "halvorna (udda/jämna pass, före/efter 24 sep). Undantagen +0,24. Värst i BB (−1,4) och BTN (−1,1); SB ~0. "
            "Räknas inte dubbelt i läcklistan – det är en del av 0-nöt-reglerna."},
    {"id": "aa_ip_3bet", "verified": True, "area": "preflop", "rank": 15, "level": "trolig", "gain": "~0,2 bb/100", "per100": 0.2,
     "title": "AA mot en öppning i position: 3-betta, syna inte",
     "do": "Har någon öppnat och du har AA (inte i blindarna): 3-betta i stället för att syna.",
     "why": "Granskning 2026-11-12: 3-bet minus syn +4,8 ± 2,1 bb per beslut, lika i båda halvorna. KK: inget stöd för "
            "någon ändring (4-bet/syn/fold mot 3-bet och 4-bet ungefär lika)."},
    # Postflop – omgång 2 (2026-11-08, export v2.62 med handstyrka på alla gator, all-in-flaggor och resultat per pott;
    # 4 agenter + 2 granskare, jämfört vid lika handstyrka). Ersätter nattanalysens postflop-lista: turn-barrel med
    # färdig färg, triss-höjning, c-bet ⅓ och turn-bluff ½ höll inte vid lika handstyrka. per100 = försiktig
    # uppskattning (bb/100). Bara level == "bekräftad" räknas i rutan "Om du tätar alla bekräftade läckor".
    # Se projektdokumentet claude/analys-omgang2-2026-11-08.md.
    {"id": "pf_river_bluff", "verified": True, "area": "postflop", "per100": 1.2, "rank": 1, "level": "bekräftad", "gain": "~1,0–1,3 bb/100",
     "title": "River, luft, ingen bet framför dig (heads-up): bluffa ca var tredje gång, pottstort",
     "do": "Med luft (minst 60 % av slumpade händer slår dig): betta ca 35–40 % av gångerna i stället för 19 %, pottstort "
           "(¾ går också, aldrig under 40 %). Bäst i position, på skrämselkort och med blockers.",
     "why": "+0,23 pott per bluff mot check (+0,17 justerat för vilka händer du väljer), i alla holdout-halvor och senaste "
            "30k. Poolen foldar 68 % mot pott och lika mycket där du sällan som där du ofta bluffar. Backa om folden mot "
            "dina bluffar sjunker under ca 55 %."},
    {"id": "pf_flop_raise_medium", "verified": True, "area": "postflop", "per100": 0.7, "rank": 2, "level": "bekräftad", "gain": "~0,7 bb/100",
     "title": "Flop heads-up, du möter en bet (inte all-in) med medelstark hand: höj i stället för att syna",
     "do": "När 10–35 % av slumpade händer slår dig (oftast två par) och du möter en flop-bet heads-up: höj oftare i stället "
           "för att syna. Gäller floppen, inte turn.",
     "why": "+0,65 pott (~7 bb) per höjning mot syn, även utan drag och mot alla spelartyper (störst mot tighta/passiva). "
            "Check-raise ur position ingår här."},
    {"id": "pf_pfa_oop_bet", "verified": True, "area": "postflop", "per100": 0.7, "rank": 3, "level": "bekräftad", "gain": "~0,7 bb/100",
     "title": "Du höjde preflop och agerar först på floppen med stark hand (inte nöten): betta",
     "do": "Ur position som preflop-höjare: betta när 3–25 % av slumpade händer slår dig i stället för att checka. "
           "Svagare händer: checka gärna.",
     "why": "+0,37 pott per beslut mot check. Övriga c-bets ur position ger inget säkert."},
    {"id": "pf_turn_after_check", "verified": True, "area": "postflop", "per100": 0.6, "rank": 4, "level": "bekräftad", "gain": "~0,6 bb/100",
     "title": "Turn efter checkad flop, du agerar först: betta oftare med svaga händer och luft",
     "do": "Betta turn oftare med svaga händer och luft (mer än 45 % slår dig) efter checkad flop. Medelstarka händer: checka.",
     "why": "+0,17–0,21 pott per bet mot check, i båda halvorna (svagare senaste 30k). Du bettar 39 % i dag."},
    {"id": "pf_allin_draw_call", "verified": True, "area": "postflop", "per100": 0.0, "rank": 5, "level": "bekräftad", "gain": "okänd",
     "title": "Möter all-in på flop/turn med drag och krav högst 34 %: fortsätt syna som i dag – granska dina folder",
     "do": "Drag mot all-in med krav högst ~34 %: fortsätt syna de drag du synar i dag. En fold här är inget fel i sig – granska den (krav, nöt-outs, heads-up eller flera).",
     "why": "2.73 (extern granskning + kontroll 2026-11-14): dina 873 syner hade 42 % faktisk equity mot krav 20 % (+24 till +41 bb per syn i "
            "alla nöt-outs-grupper). Dina 411 folder låg däremot nära kravet (skattat ~27 % mot 26,5 %), så en fold räknas inte som "
            "kostnad och ger inget syn-råd."},
    {"id": "pf_cbet_ip", "verified": True, "area": "postflop", "per100": 0.45, "rank": 6, "level": "bekräftad", "gain": "~0,45 bb/100",
     "title": "C-betta oftare som preflop-höjare: ~65–75 % i position, ~50–55 % ur position",
     "do": "C-betta oftare (i dag 46 %), även på låga och monotona bord och med par – poolen anpassar sig inte efter bordet. "
           "Storlek: se c-bet-storlek. Checka de svagaste händerna utan drag.",
     "why": "32 513 beslut, betta minus checka (inom handgrupp, HU/multiway, position): i position +0,31 ± 0,02 pott, ur position "
            "+0,25 ± 0,04; lågt sammanhängande +0,42, monotont +0,40, par utan drag +0,20 (alla fyra halvorna). "
            "Du väljer själv när du bettar – därför försiktigt räknat."},
    {"id": "pf_turn_barrel_weak", "area": "postflop", "per100": 0.35, "rank": 7, "level": "trolig", "gain": "~0,35 bb/100",
     "title": "Turn efter din flop-bet med svag hand eller drag: barrel oftare",
     "do": "Fortsätt betta turn oftare med svaga händer och drag (45–80 % slår dig). Färdig färg bettar du redan nog.",
     "why": "+0,12 pott per barrel; tecknet senaste 30k beror på metod, därför trolig."},
    {"id": "pf_river_mw_bluff", "verified": True, "area": "postflop", "per100": 0.25, "rank": 8, "level": "bekräftad", "gain": "~0,25 bb/100",
     "title": "River multiway med luft: bluffa oftare, ¾–pott",
     "do": "Multiway med luft och ingen bet framför dig: bluffa oftare (i dag 9,5 %), ¾–pott. Aldrig litet.",
     "why": "+0,31 pott per bluff (effekten bekräftad; hur mycket oftare är osäkert, ca 25 %)."},
    {"id": "pf_river_nuts_ip", "verified": True, "area": "postflop", "per100": 0.2, "rank": 9, "level": "bekräftad", "gain": "~0,2 bb/100",
     "title": "River i position med nöten eller nästan (högst 10 % slår dig) efter check: betta alltid",
     "do": "Checkas det till dig på river och högst 10 % slår dig: betta, alltid (i dag 92 %).",
     "why": "+0,24 pott per bet mot check."},
    {"id": "pf_river_value", "area": "postflop", "per100": 0.15, "rank": 10, "level": "trolig", "gain": "~0–0,3 bb/100",
     "title": "River heads-up, 10–20 % slår dig: värdebetta oftare (~80 %)",
     "do": "Betta ca 80 % av gångerna (i dag ~60 %) när 10–20 % slår dig och ingen bettat.",
     "why": "+0,12 pott per bet; trolig."},
    {"id": "pf_river_call_noflush", "area": "postflop", "per100": 0.15, "rank": 11, "level": "trolig", "gain": "~0,15 bb/100",
     "title": "River heads-up mot bet, färg inte möjlig, 10–30 % slår dig: syna oftare",
     "do": "Syna oftare när ingen färg är möjlig och 10–30 % slår dig. Är färg möjlig och 40–60 % slår dig: folda.",
     "why": "Trolig; synerna ger plus där, men urvalet drar uppåt."},
    # 2026-11-11 (analyser med Claude på hela databasen, se projektloggen): tre riktlinjer, inte bekräftade.
    {"id": "pf_river_cr_paired", "area": "postflop", "per100": 0.15, "rank": 12, "level": "trolig", "gain": "~0,15 bb/100",
     "title": "River, han check-raisar på parat bord och du har inte nöten: folda",
     "do": "Check-raise på river på parat bord betyder kåk i din pool. Folda allt utom fyrtal och nötkåken "
           "(syna bara en mycket stark kåk när priset är under ca 20 %).",
     "why": "198k händer: 25 syner, −13 bb per syn, du vann 16 % (krav 24 %). Han visade kåk eller bättre 23 av 25 "
            "gånger, aldrig en bluff. Få händer, därför inte bekräftad."},
    {"id": "pf_river_bigbet_call", "verified": True, "preregistered": {"date": "2026-11-14", "kåk_slår_dig_över": 0.16},
     "area": "postflop", "per100": 0.5, "rank": 13, "level": "trolig", "gain": "~0,5 bb/100",
     "title": "River mot stor bet (minst ⅔ pott): folda svaga kåkar, färg på parat bord och två par på oparat bord",
     "do": "Folda: kåk där fler än 16 % av slumpade händer slår dig, färg på parat bord och två par på oparat bord (särskilt "
           "mot pottbet). Syna: stege, set, två par på parat bord och starkare kåkar.",
     "why": "Granskning 2026-11-12 (holdout): fold-gruppen 291 syner, −7,4 ± 2,4 bb per syn, negativ i alla fyra halvorna. "
            "Kåk 12–16 % tjänar (+20) – gränsen flyttad från 12 till 16 % (själva gränsen inte holdout-testad). Stegar, set "
            "och två par på parat bord +12 till +23 bb per syn. Förregistrerad 2026-11-14: gränsen 16 % är låst och prövas bara framåt "
            "(oberoende granskning: kåk > 16 % −9,1 ± 4,5 ≈ 1,5σ, två par oparat −5,1 ± 3,5 ≈ 1σ – svagare än det såg ut)."},
    {"id": "pf_flop_draw_vs_cr", "area": "postflop", "per100": 0.3, "rank": 14, "level": "trolig", "gain": "~0,3 bb/100",
     "title": "Drag mot höjning på floppen (inte all-in): räkna nöt-outs",
     "do": "Räkna unika träffkort med överlapp borttaget. Nästa gatas nöthand är inte samma sak som equity till river. "
           "Jämför pris, beslutstidens pott, SPR och motståndarens range innan syn, höjning eller fold. "
           "Tidigare fasta 9/12/13-outsregler är indragna i 2.70.",
     "why": "Granskning 2026-11-12 (792 beslut, holdout): poolen foldar aldrig mot jam (0 av 81) – men jam/höjning är ändå "
            "minst lika bra som syn (+2,4 ± 4,0 bb, samma i båda halvorna). Under 9 outs −9,0 ± 4,6. Blank turn med 12–13 outs "
            "+5,0 ± 2,0 (413). Tidigare råd \"syna och planera turn i stället för att jamma\" är struket."},
    # 2026-11-12 (handexport med bordskort, 209 539 PLO6-händer, holdout i alla fyra halvorna – projektdokumenten
    # analys-set-cr-2026-11-12.md och projektloggen punkt 8 och 10)
    {"id": "set_cr", "area": "postflop", "per100": 1.0, "rank": 2, "level": "bekräftad", "gain": "~1–1,5 bb/100", "verified": True,
     "title": "Set på floppen, du checkade och möter en bet: check-raisa mellanset och toppset",
     "do": "Mellanset och toppset: check-raisa (särskilt på tvåfärgat bord eller med färgdrag/stegbackup). Bottenset: "
           "check-raisa bara när stege är möjlig på floppen eller du har stegbackup – annars syna.",
     "why": "CR minus syn: mellanset +19,4 ± 5,2 bb, toppset +11,4 ± 5,5, bottenset med stege möjlig +28 ± 8 (alla fyra "
            "halvorna). Torrt regnbågsbord: toppset/mellanset lika bra båda vägarna; bottenset syn bättre."},
    {"id": "cbet_size", "area": "postflop", "per100": 0.3, "rank": 7, "level": "bekräftad", "gain": "~0,3 bb/100", "verified": True,
     "title": "C-bet-storlek: 75 % med par + drag och på höga bord, annars 60 %",
     "do": "Par + drag (nötfärgdrag, färgdrag eller stegdrag): c-betta 75 %+. Höga bord (A/K/Q-högt) med par eller bättre: 75 %. "
           "Starka händer och par utan drag: storleken spelar ingen roll (60 %). Låga sammanhängande bord: aldrig större än 60 %.",
     "why": "15 002 c-bets, stor (≥70 %) minus liten (<55 %) inom samma bordtyp: par + drag +0,28 ± 0,08 pott, högt "
            "sammanhängande +0,27 ± 0,13, högt torrt +0,13 ± 0,07 (alla fyra halvorna). Lågt sammanhängande −0,09."},
]


# Prio-listan (2026-11-12, nivåraden 2.71 – mål: timlön) – visas överst i översikten och i sessionsfilen. Ordning efter värde och hur grundläggande det är.
PRIO = [
    # 2.83 (Andreas 2026-11-19): de tre preflopraderna överst – de enda med facit och uppmätt kostnad i $/h.
    # Ordning efter $/h senaste 30 dagarna (19 nov): syner ≈ $6,5, öppningar ≈ $5,9, 3-bets ≈ $2,6.
    ("🃏", "Syna mindre mot öppning utanför BB", "SB: syna nästan aldrig (3-bet eller fold). CO och BTN: syna hälften så ofta – "
           "folda par utan suited ess. BB försvarar som i dag."),
    ("🃏", "Öppna tightare från UTG och CO", "Par 99–22 och två par upp till 99 utan högt par (JJ+): folda – även med suited ess "
           "eller rundown, om handen inte är dubbelsuited och sammanhängande. BTN: öppna cirka 45–49 % (det solvern "
           "öppnar minst hälften av gångerna). SB-öppningen behöver inte ändras."),  # 2.87 (R3-07, BTN-analys 21 nov)
    ("🃏", "3-betta inte ett par med bara suited ess", "Ett par JJ–44 + suited ess mot öppning: folda oftast, syna ibland – "
           "inte 3-bet. KK/QQ + suited ess: syna mot UTG/CO. BB mot BTN: 3-betta lite oftare; SB mot BTN och BB mot SB: syna "
           "oftare. AA: 4-betta bara med sammanhängande/suitade sidokort – folda trasiga AA, AAA och AAAA mot 3-bet/squeeze."),  # 2.87 (R3-08, AA-analys 21 nov)
    ("🎯", "Check-raisa set på floppen", "Mellanset och toppset alltid (inte mot en spelare som redan är all-in); bottenset bara när stege är möjlig eller med stegbackup."),
    ("🛑", "River: folda mer", "Mot minst ⅔ pott (#11, förregistrerad 16 %): folda kåk där fler än 16 % slår dig, färg på parat "
           "bord och två par på oparat bord. Poolen bluffar bara ~8–15 % av sina river-bets."),
    ("🎲", "River-bluff-testet v2 (slump)", "Heads-up i position, checkat till dig, minst 75 % av slumpade händer slår dig, stack ≥ pott "
           "och rivern ändrar nöten: river ♥️/🔷 = betta ¾ pott, ♠️/☘️ = checka. Ny färg kräver ett kort i färgen."),
    ("⏸", "Paus efter stor förlust", "Förlorad pott > 175 bb: spela klart pågående händer, sitt ute från alla bord och gå från skärmen i 15 min (timer); kom tillbaka med hälften så många bord. −500 bb i ett pass: sluta (bankrulleskydd). Sluta efter 2 h – en försäkring, ingen bevisad EV-effekt (VPIP stiger med tiden). 2.87: en och samma tidsregel överallt. "
           "eller om dina klara fel per 100 händer ökat jämfört med passets början."),
]
# 2.83: vilka prio-rader som får ett uppmätt $/h (index -> kategori i solverfacit.prio_costs)
PRIO_COST = {0: "call", 1: "open", 2: "raise"}

# 2.77 (agentgranskningen 2026-11-18): riktlinjer som motsäger solvern eller ersätts av den visas inte längre som råd
# (de finns kvar som underlag och mäts i de frysta testerna). Tre postflop-riktlinjer bygger på styrka mot slumpade händer
# och strider mot teori – de nedgraderas till "trolig" tills skuggmodell v3 (styrka mot range) har prövat dem.
HIDDEN_277 = {"hj_sa_low", "no_premium_fold", "bb_0nut_hu", "low_pairs_no_nut", "aa_ip_3bet", "pf_river_bluff"}
DOWNGRADE_277 = {"pf_flop_raise_medium", "pf_river_mw_bluff", "cbet_size"}
for _g in GUIDELINES:
    if _g["id"] in HIDDEN_277:
        _g.pop("verified", None)
        _g["hidden_277"] = True
    elif _g["id"] in DOWNGRADE_277:
        _g.pop("verified", None)
        _g["level"] = "trolig – strider mot teori"

VERIFIED = {g["id"] for g in GUIDELINES if g.get("verified")}
# Princip (Andreas 2026-11-12): bara riktlinjer som håller i alla holdout-halvor och ligger minst ~2 felmarginaler från noll
# visas (💡 i sessionsfilen och i läcklistan). Övriga finns kvar här som underlag men visas inte.
NOTE_ID = {"#1 ": "pf_river_bluff", "#2 ": "pf_flop_raise_medium", "#3 ": "pf_pfa_oop_bet", "#4 ": "pf_turn_after_check",
           "#5 ": "pf_allin_draw_call", "#6 ": "pf_cbet_ip", "#7 ": "pf_turn_barrel_weak", "#8 ": "pf_river_mw_bluff",
           "#9 ": "pf_river_nuts_ip", "#10 ": "pf_flop_draw_vs_cr", "#11 ": "pf_river_bigbet_call", "#12 ": "pf_river_cr_paired",
           "#13 ": "set_cr", "#14 ": "cbet_size"}


def visible(gid: str) -> bool:
    return gid in VERIFIED


def aa_suited_ace(hole) -> bool:
    """AA (exakt två ess) där minst ett ess har 1–2 kort till i samma färg."""
    if sum(1 for c in hole if c[0] == 14) != 2:
        return False
    suits = Counter(c[1] for c in hole)
    return any(c[0] == 14 and 2 <= suits[c[1]] <= 3 for c in hole)


def ds_suited_king(hole) -> bool:
    """Dubbelsuited (minst två färger med 2+ kort) och en kung med minst ett kort till i sin färg."""
    suits = Counter(c[1] for c in hole)
    return sum(1 for v in suits.values() if v >= 2) >= 2 and any(c[0] == 13 and suits[c[1]] >= 2 for c in hole)


def low_pairs_no_nut(hole) -> bool:
    """Handens enda par är under JJ, inga nöt-egenskaper, och den är varken trippelsuited eller dubbelsuited + suited kung."""
    if not hole:
        return False
    rc = Counter(c[0] for c in hole)
    pairs = [r for r, n in rc.items() if n >= 2]
    if not pairs or max(pairs) >= 11 or any(n >= 3 for n in rc.values()):
        return False
    if sum(nut_qualities(hole)) > 0:
        return False
    suits = Counter(c[1] for c in hole)
    if sorted(suits.values()) == [2, 2, 2] or ds_suited_king(hole):
        return False
    return True


def hj_sa_low(hole) -> bool:
    """Suited ess (ess med 1–2 kort till i färgen) med högst två kort T eller högre, inte AA/KK."""
    if not hole:
        return False
    ranks = [c[0] for c in hole]
    if ranks.count(14) >= 2 or ranks.count(13) >= 2:
        return False
    suits = Counter(c[1] for c in hole)
    if not any(c[0] == 14 and 2 <= suits[c[1]] <= 3 for c in hole):
        return False
    return sum(1 for r in ranks if r >= 10) <= 2


HYPOTHESES = {
    # 2.72 (Andreas ja 2026-11-14): visas som 🧪 hypotes, räknas aldrig som regelbrott, ska framåttestas
    "rundown_no_sa_call": "Rundown utan suited ess mot en öppning: syna, 3-betta inte (syn +0,76 ± 0,36, 3-bet −1,05 ± 1,19 bb mot fold; 1,5σ)",
    "low_pair_vs_4bet": "Mot 4-bet efter din 3-bet: folda lägre par (JJ–22) utan suited ess (−10,9 ± 3,3 bb mot fold; övriga händer: syna)",
}


def has_rundown_no_sa(hole) -> bool:
    if not hole:
        return False
    hp, sa, rd = nut_qualities(hole)
    return rd and not sa


def low_pair_no_sa(hole) -> bool:
    """Handens högsta par är JJ–22 (inget QQ+), inget suited ess."""
    if not hole:
        return False
    rc = Counter(c[0] for c in hole)
    pairs = [r for r, n in rc.items() if n >= 2]
    if not pairs or max(pairs) >= 12:
        return False
    return not nut_qualities(hole)[1]


def hypothesis_note(spot: str, kind: str, hole) -> str:
    if spot in ("mot_hojning", "bb_mot_hojning", "sb_mot_hojning") and kind == "raise" and has_rundown_no_sa(hole):
        return "🧪 hypotes: rundown utan suited ess – syna i stället för att 3-betta"
    if spot == "mot_4bet" and kind in ("call", "raise") and low_pair_no_sa(hole):
        return "🧪 hypotes: lägre par utan suited ess mot 4-bet – folda"
    return ""


def preflop_note(spot: str, kind: str, hole, depth_bb: float | None, pos: str = "", stake: str = "") -> str:
    """Kort råd till ett preflop-beslut – verifierade riktlinjer först, annars en märkt hypotes (🧪)."""
    t = _preflop_note(spot, kind, hole, depth_bb, pos, stake)[1]
    return t or hypothesis_note(spot, kind, hole)


def _preflop_note(spot: str, kind: str, hole, depth_bb: float | None, pos: str = "", stake: str = ""):
    """(riktlinje-id, text) för det första förslaget som är verifierat, annars (None, "")."""
    c = []
    if kind in ("call", "raise") and hole and low_pairs_no_nut(hole):
        c.append(("low_pairs_no_nut", "💡 bekräftat: lågt par/dubbelpar utan nöt-egenskaper – folda (utom trippelsuited, "
                                      "dubbelsuited + suited kung)"))
    if spot == "mot_hojning" and kind == "call" and hole and sum(1 for x in hole if x[0] == 14) == 2:
        c.append(("aa_ip_3bet", "💡 AA mot en öppning i position – 3-betta, syna inte"))
    if spot in ("mot_3bet_oop", "mot_3bet_ip") and kind == "call" and aa_suited_ace(hole):
        deep = depth_bb is not None and depth_bb > DEEP_BB
        if spot == "mot_3bet_oop" or not deep:
            c.append(("aa_sa_4bet", "💡 4-betta AA med suited ess"))
    if spot == "bb_mot_hojning" and kind == "call" and hole and sum(nut_qualities(hole)) == 0 and not ds_suited_king(hole):
        c.append(("bb_0nut_hu", "💡 BB med 0 nöt-egenskaper – syna bara mot SB-öppning (heads-up), annars folda"))
    if spot == "rfi" and pos == "HJ" and kind == "raise" and hj_sa_low(hole):
        c.append(("hj_sa_low", "💡 HJ – folda suited ess utan höga kort"))
    for gid, t in c:
        if visible(gid):
            return gid, t
    return None, ""

WEAK = ("högt kort", "par")


def postflop_note(r: dict) -> str:
    """Kort råd till ett postflop-beslut – bara från verifierade riktlinjer."""
    t = _postflop_note(r)
    for k, gid in NOTE_ID.items():
        if t.startswith("💡 " + k):
            return t if visible(gid) else ""
    return t


def _postflop_note(r: dict) -> str:
    """Kort råd till ett postflop-beslut (en rad från postflop_rows som dict), eller tom sträng."""
    try:
        st, act, fac = r.get("street"), r.get("action"), r.get("facing")
        hu = int(r.get("players") or 0) == 2
        hand = r.get("hand") or ""
        bf = r.get("beat_frac")
        bf = float(bf) if bf not in ("", None) else None
        size = float(r["size_pct"]) if r.get("size_pct") not in ("", None) else None
        outs = int(r["straight_outs"]) if r.get("straight_outs") not in ("", None) else 0
        fd = r.get("flush_draw") or ""
        mf = r.get("made_frac")
        mf = float(mf) if mf not in ("", None) else None
        fa = r.get("facing_allin")
        fp = float(r["facing_pct"]) if r.get("facing_pct") not in ("", None) else None
        need = fp / (100 + fp) if fp is not None else None
        ip = int(r.get("ip") or 0) == 1
        pfa = int(r.get("pfa") or 0) == 1
        if st == "river" and fac == "ingen" and hu and bf is not None and bf > 0.6 and act == "check":
            return "💡 #1 luft på river heads-up: bluffa ca var tredje gång, pottstort"
        if st == "river" and fac == "ingen" and bf is not None and bf > 0.6 and act == "bet" and size is not None and size < 40:
            return "💡 #1 bluffa inte under 40 % av potten på river"
        if st == "flop" and fac == "bet" and hu and fa in (0, "0", 0.0) and act == "call" and mf is not None and 0.10 <= mf <= 0.35:
            return "💡 #2 medelstark hand mot flop-bet heads-up: höj hellre än syna"
        if st == "flop" and fac == "ingen" and pfa and not ip and act == "check" and mf is not None and 0.03 <= mf <= 0.25:
            return "💡 #3 stark hand som preflop-höjare ur position: betta floppen"
        if st == "turn" and fac == "ingen" and r.get("prev_aggressor") == "ingen" and act == "check" and mf is not None and mf > 0.45:
            return "💡 #4 turn efter checkad flop med svag hand/luft: betta oftare (ca hälften)"
        if st in ("flop", "turn") and fac != "ingen" and fa in (1, "1", 1.0) and act == "fold" and (fd or outs >= 8) \
                and need is not None and need <= 0.34:
            no = r.get("nut_outs")
            return (f"🔎 #5 fold med drag mot all-in, krav {100 * need:.0f} %"
                    + (f", {int(float(no))} nöt-outs" if no not in ("", None) else "")
                    + ": granska handen (inget facit – dina syner i samma läge har gått plus, men dina folder ligger nära gränsen)")
        if st == "flop" and fac == "ingen" and pfa and act == "check" and hu:
            return "💡 #6 c-betta oftare (~65–75 % i position, ~50–55 % ur position)"
        if st == "turn" and fac == "ingen" and r.get("prev_aggressor") == "hero" and act == "check" and mf is not None and 0.45 <= mf <= 0.8:
            return "💡 #7 svag hand/drag efter din flop-bet: barrel oftare (trolig)"
        if st == "river" and fac == "ingen" and not hu and act == "check" and bf is not None and bf > 0.6:
            return "💡 #8 luft multiway på river: bluffa ibland, ¾–pott"
        if st == "river" and fac == "ingen" and ip and act == "check" and bf is not None and bf == 0.0:
            return "💡 #9 ingen slumpad hand slog din: granska värdebet (stickprovet bevisar inte nöten)"
        paired = str(r.get("board_paired") or "0") in ("1", "1.0", "True")
        fsize = float(r["facing_size_pct"]) if r.get("facing_size_pct") not in ("", None) else None
        if st == "river" and fac == "raise" and ip and paired and act == "call" and mf is not None and mf > 0 \
                and hand != "fyrtal":
            return "💡 #12 check-raise på river på parat bord = kåk: folda om du inte har nöten"
        if st == "river" and fac in ("bet", "raise") and act == "call" and fsize is not None and fsize >= 66 and mf is not None \
                and ((hand == "kåk" and mf > 0.16) or (hand == "färg" and paired) or (hand == "två par" and not paired)):
            return "💡 #11 stor river-bet: folda svag kåk, färg på parat bord och två par på oparat bord"
        raw_nut = r.get("nut_outs")
        nut_outs = int(raw_nut) if raw_nut not in ("", None) else None
        eff = float(r["eff_stack_bb"]) if r.get("eff_stack_bb") not in ("", None) else None
        pot = float(r["pot_bb"]) if r.get("pot_bb") not in ("", None) else None
        tc = float(r["to_call_bb"]) if r.get("to_call_bb") not in ("", None) else 0.0
        spr_raw = r.get("spr_after_call")
        spr_after = float(spr_raw) if spr_raw not in ("", None) else None
        if st in ("flop", "turn") and fac in ("raise", "bet") and act in ("call", "fold") and hand in WEAK and (fd or outs >= 4):
            return ("💡 #10 drag: " + (f"{nut_outs} unika kort ger nöten på nästa gata; " if nut_outs is not None else "nöt-outs inte beräknade; ")
                    + "granska equity mot hans range, pris och SPR. Ingen automatisk jam-/foldregel.")
        sr = r.get("set_rank") or ""
        bt = r.get("board_type") or ""
        allin_vs = str(r.get("facing_allin") or "0") in ("1", "1.0", "True")
        # 2.80: mot en motståndare som redan är all-in finns ingen check-raise – bara syn eller fold
        if st == "flop" and fac == "bet" and int(r.get("order") or 1) >= 2 and sr and not allin_vs:
            conn = bt in ("lågt sammanhängande", "högt sammanhängande") or outs >= 4
            if act == "call" and sr in ("topp", "mellan"):
                return f"💡 #13 {sr}set mot bet efter din check: check-raisa"
            if act == "call" and sr == "botten" and conn:
                return "💡 #13 bottenset med stege möjlig/stegbackup: check-raisa"
            if act == "raise" and sr == "botten" and not conn:
                return "💡 #13 bottenset utan stegbackup på torrt bord: syna hellre"
        if st == "flop" and fac == "ingen" and pfa and act == "bet" and size is not None and size < 55 \
                and (hand == "par" and (fd or outs >= 8) or (bt.startswith("högt") and hand not in ("högt kort",))):
            return "💡 #14 c-bet: 75 % med par + drag eller på högt bord"
    except Exception:
        return ""
    return ""


# Fixed historical heuristics are not recomputed or independently validated for a new selection.
for _guide in GUIDELINES:
    _guide["historical_level"] = _guide.get("level")
    _guide["level"] = "trolig"
    _guide["source"] = "historisk riktlinje; fryst 2026-11-13, framåttest på nya händer från 2.71"
    _guide["why"] = "Historisk riktlinje, inte aktuell oberoende validering. " + _guide.get("why", "")
