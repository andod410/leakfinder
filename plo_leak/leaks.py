"""Läckdetektor: jämför dina siffror med riktvärden för vinnande PLO-spelare
och förklarar på svenska vad du gör fel och vad du ska göra istället.

Riktvärdena gäller 6-max PLO cashgame (ungefär NL25–NL500). De är medvetet
breda – målet är att hitta tydliga avvikelser, inte att jaga en exakt siffra.
Ändra dem i RULES om du spelar t.ex. full ring, PLO-5 eller högre stakes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .stats import HeroStats, Stat


@dataclass
class Leak:
    key: str
    title: str
    value: str
    target: str
    what: str
    why: str
    fix: list
    drill: str
    severity: float
    opps: int
    confidence: str
    examples: list = field(default_factory=list)  # (hand_id, net_bb)
    example_label: str = ""
    spot_note: str = ""
    category: str = ""
    source: str = ""  # varifrån riktvärdet kommer
    severity_low: float | None = None  # försiktig gräns (bb/100)

    @property
    def level(self) -> str:
        if self.confidence == "Säkerställd":  # severity = kostnad i bb/100
            return "Stor" if self.severity >= 2.0 else ("Medel" if self.severity >= 0.7 else "Liten")
        if self.severity >= 2.0:
            return "Stor"
        if self.severity >= 1.0:
            return "Medel"
        return "Liten"


def _confidence(opps: int, min_opps: int) -> tuple[str, float]:
    if opps >= min_opps * 4:
        return "Hög", 1.0
    if opps >= min_opps * 2:
        return "Medel", 0.85
    return "Låg", 0.65


# --------------------------------------------------------------------------- regler
# Varje regel: stat-nyckel, (min, max), minsta urval, vikt (hur dyr läckan
# typiskt är), och texter för för högt ("high") respektive för lågt ("low").
# I texterna ersätts {v} med ditt värde och {lo}/{hi} med riktvärdet.

RULES = [
    {
        "stat": "vpip", "range": (21, 32), "min": 300, "weight": 1.3, "cat": "Preflop",
        "name": "VPIP",
        "high": dict(
            title="Du spelar för många händer",
            what="Du går in i potten med {v:.0f}% av dina händer. Vinnande 6-max PLO-spelare ligger runt {lo}–{hi}%.",
            why="I PLO ligger ekvitet mellan händer nära varandra preflop, men pengarna vinns postflop av den som "
                "oftast har nöthänder och nötdrag. Svaga händer ({weak}) floppar "
                "andra-bästa-händer som förlorar stora pottar.",
            fix=["Följ en öppningsrange per position (t.ex. en PLO-preflopchart) – spela inte 'känsla'.",
                 "Släng {weak} från LJ/HJ, oavsett hur höga korten är.",
                 "Prioritera {good}."],
            drill="Gå igenom 50 händer du betalade/öppnade med från LJ/HJ och markera vilka som inte finns i din chart.",
        ),
        "low": dict(
            title="Du spelar för få händer",
            what="Du går bara in i {v:.0f}% av potterna (riktvärde {lo}–{hi}%).",
            why="I PLO är det sena positioner och blinds-strider som ger vinsten. För tight spel gör dig "
                "lätt att läsa och du missar många lönsamma steals och försvar.",
            fix=["Öppna bredare på CO och BTN (BTN ofta 45–55%).",
                 "Försvara BB oftare mot steals från CO/BTN – du får bra pottodds i pot limit.",
                 "Lägg till fler sammanhängande dubbelfärgade händer i dina ranges."],
            drill="Studera BTN- och BB-ranges i en PLO-solver/chart och jämför med dina faktiska händer.",
        ),
    },
    {
        "stat": "open_limp", "range": (0, 3), "min": 150, "weight": 1.2, "cat": "Preflop",
        "name": "Open-limp (ej SB)",
        "high": dict(
            title="Du open-limpar",
            what="När alla foldat till dig limpar du i {v:.0f}% av fallen (riktvärde: nästan aldrig).",
            why="En limp ger bort initiativet, bjuder in flera spelare och gör att du spelar multiway "
                "pottar ur position med en hand som inte var tillräckligt bra för att höja.",
            fix=["Raise-or-fold när det är foldat till dig: höj pot (eller nära pot) eller släng handen.",
                 "Om handen inte är bra nog att höja från din position – den är inte bra nog att limpa."],
            drill="Sätt en regel: inga limpar första in utanför SB under nästa 5 000 händer.",
        ),
    },
    {
        "stat": "3bet", "range": (5, 12), "min": 200, "weight": 1.0, "cat": "Preflop",
        "name": "3-bet",
        "high": dict(
            title="Du 3-bettar för mycket",
            what="Du 3-bettar {v:.1f}% när någon öppnat (riktvärde {lo}–{hi}%).",
            why="I PLO får öppnaren nästan alltid rätt odds att syna. Att 3-betta svaga händer bygger stora "
                "pottar där du ofta är dominerad och SPR blir lågt utan att du har en hand som klarar det.",
            fix=["3-betta främst {premium}.",
                 "Syna istället med spelbara händer i position."],
            drill="Lista dina 3-bets som förlorade mest och fråga: hade jag gärna fått in 100bb preflop med den här handen?",
        ),
        "low": dict(
            title="Du 3-bettar för lite",
            what="Du 3-bettar bara {v:.1f}% (riktvärde {lo}–{hi}%).",
            why="Utan 3-bets blir din synarrange väldigt stark och lätt att läsa, och du låter öppnaren se billiga "
                "flops med sina svagare händer. Särskilt från blinds mot sena öppningar tappar du värde.",
            fix=["3-betta {premium}.",
                 "Från blinds: 3-betta oftare mot BTN/CO istället för att bara syna ur position."],
            drill="Leta upp 20 händer där du synade en öppning med en premiumhand – 3-betta dem nästa gång.",
        ),
    },
    {
        "stat": "cold_call", "range": (5, 20), "min": 200, "weight": 0.7, "cat": "Preflop",
        "name": "Cold call (ej BB)",
        "high": dict(
            title="Du synar för många öppningar",
            what="Du cold-callar {v:.0f}% av öppningarna (riktvärde {lo}–{hi}%).",
            why="Varje cold call bjuder in blinds och skapar multiway-pottar där din hand oftast inte är "
                "nötig nog. Från SB är detta extra dyrt eftersom du sedan är ur position.",
            fix=["Antingen 3-betta eller folda – särskilt från SB (3-bet or fold).",
                 "Cold-calla främst i position (BTN/CO) med händer som spelar bra multiway."],
            drill="Gå igenom dina cold calls från SB och HJ – hur många var lönsamma?",
        ),
    },
    {
        "stat": "fold_to_3bet", "range": (32, 55), "min": 60, "weight": 1.1, "cat": "Preflop",
        "name": "Fold mot 3-bet",
        "high": dict(
            title="Du foldar för ofta mot 3-bets",
            what="När du öppnat och blir 3-bettad foldar du {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="I pot limit får du ofta runt 2:1 eller bättre på syn. Att folda för mycket gör att alla "
                "kan 3-betta dig med vad som helst och du förlorar din öppningsinsats gång på gång.",
            fix=["Syna mer i position – speciellt med sammanhängande, färgade händer.",
                 "Om du inte kan försvara mot 3-bets: öppna en tightare range från början."],
            drill="Räkna pottoddsen i dina senaste 20 fold mot 3-bet – hur många var klara synar?",
        ),
        "low": dict(
            title="Du försvarar för mycket mot 3-bets",
            what="Du foldar bara {v:.0f}% mot 3-bets (riktvärde {lo}–{hi}%).",
            why="3-bettade pottar har lågt SPR. Med svaga händer, särskilt ur position, hamnar du ofta "
                "all-in med andra-bästa hand eller drag mot nöten.",
            fix=["Folda {weak} mot 3-bets.",
                 "4-betta toppen av din range istället för att syna."],
            drill="Filtrera alla händer där du synade en 3-bet ur position och summera resultatet.",
        ),
    },
    {
        "stat": "call_3bet_oop", "range": (0, 40), "min": 40, "weight": 1.0, "cat": "Preflop",
        "name": "Syn av 3-bet ur position",
        "high": dict(
            title="Du synar 3-bets ur position för ofta",
            what="När du blir 3-bettad av någon som har position på dig synar du {v:.0f}% (riktvärde under {hi}%).",
            why="Ur position i en 3-bettad pott är du i nackdel på varje gata och kan sällan realisera din "
                "ekvitet. Hur mycket det kostar i PLO6 är inte känt i förväg – jämför dina resultat nedan med kostnaden för att folda.",
            fix=["4-betta toppen av din range, folda det mesta övriga ur position.",
                 "Syna bara med riktigt starka, dubbelfärgade och sammanhängande händer.",
                 "Öppna tightare från tidig position så du sällan hamnar här."],
            drill="Kolla dina resultat (bb) i de här händerna – rapporten visar summan nedan.",
        ),
    },
    {
        "stat": "cold_call_3bet", "range": (0, 6), "min": 60, "weight": 0.9, "cat": "Preflop",
        "name": "Cold call av 3-bet",
        "high": dict(
            title="Du cold-callar 3-bets",
            what="Du synar {v:.0f}% när det redan är öppnat och 3-bettat före dig (riktvärde under {hi}%).",
            why="Både öppnaren och 3-bettaren har starka ranges. Du riskerar att bli squeezad och hamnar "
                "i pottar med lågt SPR där din hand ofta är dominerad.",
            fix=["Folda nästan allt utom toppen av din range ({premium}).",
                 "Syna bara med händer som floppar nötdrag ofta och bara i position."],
            drill="Lägg upp en regel: cold call av 3-bet endast med {premium} i position.",
        ),
    },
    {
        "stat": "bb_fold_steal", "range": (30, 55), "min": 80, "weight": 1.0, "cat": "Blinds",
        "name": "BB fold mot steal",
        "high": dict(
            title="Du foldar för mycket i BB mot steals",
            what="Du foldar {v:.0f}% i big blind mot öppningar från CO/BTN/SB (riktvärde {lo}–{hi}%).",
            why="I BB har du redan 1bb i potten och får väldigt bra odds. PLO-händer ligger nära varandra i "
                "ekvitet, så att folda för ofta skänker bort pottar till stealers.",
            fix=["Försvara bredare mot BTN- och SB-öppningar: de flesta sammanhängande eller färgade händer är spelbara.",
                 "3-betta dina bästa händer för att inte alltid spela ur position passivt."],
            drill="Studera en BB-försvarsrange mot BTN i PLO och jämför med 30 händer du foldat.",
        ),
        "low": dict(
            title="Du försvarar BB för brett",
            what="Du foldar bara {v:.0f}% i BB mot steals (riktvärde {lo}–{hi}%).",
            why="Du spelar ur position resten av handen. Riktigt svaga händer ({weak}) "
                "förlorar mer än de 1bb du redan har i potten.",
            fix=["Folda {weak}.",
                 "Försvara med händer som kan flopa nötdrag."],
            drill="Kolla resultatet för dina BB-försvar med händer i de svagaste handtyperna (se tabellen Starthänder).",
        ),
    },
    {
        "stat": "sb_fold_steal", "range": (50, 80), "min": 60, "weight": 0.6, "cat": "Blinds",
        "name": "SB fold mot steal",
        "low": dict(
            title="Du spelar för många händer i SB mot steals",
            what="Du foldar bara {v:.0f}% i small blind mot steals (riktvärde {lo}–{hi}%).",
            why="SB är den sämsta positionen postflop. Att syna här bjuder in BB och du spelar ur position mot två spelare.",
            fix=["Spela 3-bet-or-fold från SB.", "Syna bara undantagsvis med väldigt spelbara händer."],
            drill="Summera resultatet för dina SB-syner mot öppningar.",
        ),
        "high": dict(
            title="Du foldar för mycket i SB",
            what="Du foldar {v:.0f}% i small blind mot steals (riktvärde {lo}–{hi}%).",
            why="Stealers kan öppna vad som helst om du nästan aldrig slår tillbaka.",
            fix=["3-betta mer från SB mot BTN-öppningar med starka och väl sammanhängande händer."],
            drill="Lägg till 3-bets från SB med dina topp ~10% händer.",
        ),
    },
    {
        "stat": "cbet_hu", "range": (45, 72), "min": 80, "weight": 0.9, "cat": "Flop",
        "name": "C-bet flop (heads up)",
        "high": dict(
            title="Du c-bettar för mycket",
            what="Du c-bettar {v:.0f}% heads up (riktvärde {lo}–{hi}%).",
            why="I PLO träffar synarens range ofta floppen hårt (sex hålkort i PLO6 = väldigt många kombinationer). "
                "Automatiska c-bets på våta eller låga bord bränner pengar och blir lätta att raisa.",
            fix=["Checka mer på bord som träffar synaren: låga, sammanhängande, tvåfärgade bord.",
                 "Betta med händer som har nötpotential eller blockers till nöten – inte bara 'för att jag höjde'."],
            drill="Gå igenom c-bets som blev check-raisade: vilka bordstyper var det?",
        ),
        "low": dict(
            title="Du c-bettar för lite",
            what="Du c-bettar bara {v:.0f}% heads up (riktvärde {lo}–{hi}%).",
            why="Du ger bort pottar på bord som gynnar din range (höga, torra bord) och dina "
                "värdehänder får för lite betalt.",
            fix=["C-betta oftare på höga, torra bord (t.ex. A/K-high utan färg).",
                 "Betta dina starka drag för att bygga potten när du har nötpotential."],
            drill="Markera 20 checkade floppar som preflop-höjare – vilka var bra c-bet-bord?",
        ),
    },
    {
        "stat": "cbet_mw", "range": (25, 55), "min": 50, "weight": 0.8, "cat": "Flop",
        "name": "C-bet flop (multiway)",
        "high": dict(
            title="Du c-bettar för mycket multiway",
            what="Du c-bettar {v:.0f}% mot två eller fler motståndare (riktvärde {lo}–{hi}%).",
            why="Multiway har någon nästan alltid träffat. Blufflika c-bets fungerar mycket sämre och du "
                "bygger pottar utan nötpotential.",
            fix=["Multiway: betta i princip bara med starka made hands och nötdrag.",
                 "Checka allt annat och var beredd att släppa."],
            drill="Kolla dina förlorade multiway-c-bets: hade du nötdrag eller toppset?",
        ),
    },
    {
        "stat": "turn_barrel", "range": (40, 65), "min": 50, "weight": 0.7, "cat": "Turn",
        "name": "Turn-barrel efter c-bet",
        "low": dict(
            title="Du ger upp för ofta på turn",
            what="Efter en c-bet som blivit synad bettar du turn bara {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Om du c-bettar men nästan aldrig följer upp blir din c-bet lätt att flyta (syna med vad som helst). "
                "Motståndare tar potten när du checkar.",
            fix=["Fortsätt på turn när kortet förbättrar dig eller din range (överkort, nya nötdrag).",
                 "Färre c-bets på floppen – men följ upp oftare när du väl bettar."],
            drill="Leta upp checkade turns efter c-bet där du hade bra blockers/drag.",
        ),
        "high": dict(
            title="Du barrelar turn för ofta",
            what="Du bettar turn {v:.0f}% efter c-bet (riktvärde {lo}–{hi}%).",
            why="Synarens range är stark efter flop-synen. Att bomba vidare utan ekvitet gör dyra bluffar.",
            fix=["Barrela med ekvitet (drag, blockers) – ge upp med helt luft på dåliga turnkort."],
            drill="Summera dina turn-barrels som förlorade utan showdown.",
        ),
    },
    {
        "stat": "fold_to_cbet", "range": (35, 58), "min": 60, "weight": 1.0, "cat": "Flop",
        "name": "Fold mot c-bet",
        "high": dict(
            title="Du foldar för mycket mot c-bets",
            what="Du foldar {v:.0f}% när preflop-höjaren c-bettar (riktvärde {lo}–{hi}%).",
            why="Bra spelare c-bettar brett. Om du foldar allt som inte träffat ger du dem gratis vinst varje gång.",
            fix=["Syna oftare med backdoor-drag + par, wraps och blockers till nöten.",
                 "Check-raisa ibland med nötdrag så att din range inte blir 'träff eller fold'."],
            drill="Gå igenom 20 fold mot c-bet: vilka hade 8+ outs eller nötblockers?",
        ),
        "low": dict(
            title="Du synar för många c-bets",
            what="Du foldar bara {v:.0f}% mot c-bets (riktvärde {lo}–{hi}%).",
            why="Att syna med svaga drag och andra-bästa-händer (t.ex. låga färgdrag, botten-två-par) leder till dyra turns och rivers.",
            fix=["Syna bara med drag som är nötiga eller händer som kan förbättras till nöten.",
                 "Släpp låga färgdrag och svaga par-med-dåligt-kicker."],
            drill="Summera vad dina syner mot c-bet kostat när du inte vann potten.",
        ),
    },
    {
        "stat": "flop_xr", "range": (6, 16), "min": 60, "weight": 0.6, "cat": "Flop",
        "name": "Check-raise flop",
        "low": dict(
            title="Du check-raisar sällan",
            what="När du checkat och mött en bet på floppen check-raisar du {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Utan check-raises kan motståndaren betta brett mot dig utan risk, och dina starka händer och nötdrag får för lite värde.",
            fix=["Check-raisa toppset, nötwraps och nötfärgdrag med extra outs.",
                 "Inkludera några semi-bluffar med starka drag och blockers."],
            drill="Leta upp händer där du checksynade floppen med set eller 13+ outs.",
        ),
        "high": dict(
            title="Du check-raisar för mycket",
            what="Du check-raisar {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Check-raises i PLO bygger enorma pottar snabbt. Med icke-nötiga händer blir du 3-bettad ut eller stackad av bättre.",
            fix=["Behåll check-raises för nöthänder och nötdrag med extra ekvitet."],
            drill="Gå igenom check-raises som förlorade stacken.",
        ),
    },
    {
        "stat": "fold_river_bet", "range": (38, 62), "min": 50, "weight": 1.0, "cat": "River",
        "name": "Fold mot river-bet",
        "low": dict(
            title="Du betalar av för mycket på river",
            what="Mot en river-bet foldar du bara {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Populationen bluffar för lite på river i PLO, framför allt på mikro- och lågstakes. "
                "Andra-bästa-händer är ofta slagna när någon bettar river.",
            fix=["Folda oftare med icke-nöthänder när en passiv spelare plötsligt bettar river.",
                 "Fråga: vilka bluffar finns faktiskt? Missade drag som kan ha nått river?"],
            drill="Lista alla river-syner som förlorade – vilka hade du kunnat folda?",
        ),
        "high": dict(
            title="Du foldar för mycket på river",
            what="Mot en river-bet foldar du {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Aggressiva spelare kan bluffa dig av potten varje gång du inte har nöten.",
            fix=["Syna oftare med bluff-catchers som blockerar värdehänder mot aggressiva spelare.",
                 "Använd pottodds: en pot-bet kräver bara att du vinner 33%."],
            drill="Kolla dina folds mot river-bluffar som visades.",
        ),
    },
    {
        "stat": "river_call_won", "range": (38, 100), "min": 25, "weight": 1.2, "cat": "River",
        "name": "Vunna river-syner",
        "low": dict(
            title="Dina river-syner förlorar för ofta",
            what="När du synar en river-bet vinner du bara {v:.0f}% av gångerna (riktvärde: minst {lo}%).",
            why="En pot-bet kräver att du vinner ~33%, en halvpott-bet ~25%. Ligger du under ~38% totalt "
                "synar du sannolikt för brett med händer som sällan är bäst.",
            fix=["Syna river framför allt med händer nära nöten eller med bra blockers.",
                 "Släpp andra-bästa färg/stege när brädet blir farligare."],
            drill="Rapporten listar dina dyraste förlorade river-syner – gå igenom dem en och en.",
        ),
    },
    {
        "stat": "wtsd", "range": (25, 34), "min": 200, "weight": 0.9, "cat": "Showdown",
        "name": "Went to showdown (WTSD)",
        "high": dict(
            title="Du går till showdown för ofta",
            what="Du når showdown i {v:.0f}% av händerna där du såg floppen (riktvärde {lo}–{hi}%).",
            why="Hög WTSD betyder oftast att du synar ner med händer som inte är tillräckligt starka – den klassiska 'calling station'-läckan.",
            fix=["Släpp fler medelstarka händer på turn och river när action visar styrka.",
                 "Var extra misstänksam när brädet parar sig eller fyller färg/stege."],
            drill="Jämför med din W$SD: om båda är låga respektive höga synar du för mycket.",
        ),
        "low": dict(
            title="Du går för sällan till showdown",
            what="Du når showdown bara {v:.0f}% (riktvärde {lo}–{hi}%).",
            why="Du foldar för ofta mot aggression och blir lätt att bluffa.",
            fix=["Syna oftare ner med bluff-catchers mot aggressiva spelare."],
            drill="Kolla händer där motståndaren visade bluff efter att du foldat.",
        ),
    },
    {
        "stat": "wsd", "range": (48, 60), "min": 100, "weight": 0.8, "cat": "Showdown",
        "name": "Won at showdown (W$SD)",
        "low": dict(
            title="Du förlorar för ofta vid showdown",
            what="Du vinner bara {v:.0f}% av dina showdowns (riktvärde {lo}–{hi}%).",
            why="Det betyder att du tar för svaga händer till showdown – oftast att du synar ner med andra-bästa hand.",
            fix=["Fokusera på nöthänder: i PLO är 'bra' inte bra nog i stora pottar.",
                 "Se avsnittet om andra-bästa-händer i den här rapporten."],
            drill="Gå igenom dina 20 största förlorade showdowns.",
        ),
    },
    {
        "stat": "ep_weak_open", "range": (0, 15), "min": 60, "weight": 1.1, "cat": "Preflop",
        "name": "Öppnar svaga händer från tidig position",
        "high": dict(
            title="Du öppnar svaga händer från tidig position",
            what="Med {weak} i LJ/HJ öppnar du {v:.0f}% (riktvärde under {hi}%).",
            why="Från tidig position har du flest spelare bakom dig och ofta ingen position postflop. "
                "Sådana händer saknar nötpotential och blir dominerade.",
            fix=["Från LJ/HJ: kräv {ep_req}.",
                 "Allt annat slängs – även om korten ser höga och fina ut."],
            drill="Se tabellen 'Starthänder' under Preflop: vilka handtyper förlorar mest för dig?",
        ),
    },
]


# --------------------------------------------------------------------------- profiler
# PLO6 spelas lösare än PLO4: ekviteterna ligger ännu närmare varandra preflop,
# fler spelar flop och nöten vinner ännu oftare. Riktvärdena är ungefärliga
# erfarenhetsvärden för vinnande 6-max-spelare – justera fritt.
PROFILES = {
    "PLO6": {
        "label": "PLO6 (6-korts Omaha), 6-max",
        "weak": "händer utan suited ess som inte hänger ihop, trips i handen eller 4+ kort i samma färg",
        "good": "händer med suited ess (nötfärgsdrag), rundowns med fem–sex sammanhängande kort och dubbel-/trippelfärgade händer",
        "premium": "suited ess + rundown och AA-händer med bra struktur",
        "ep_req": "suited ess eller en rundown med minst fyra sammanhängande kort – och inga trips eller 4+ kort i en färg",
        "ranges": {
            "vpip": (28, 42), "open_limp": (0, 3), "3bet": (6, 13), "cold_call": (8, 25),
            "fold_to_3bet": (25, 48), "call_3bet_oop": (0, 50), "cold_call_3bet": (0, 8),
            "bb_fold_steal": (20, 45), "sb_fold_steal": (45, 75), "cbet_hu": (40, 65),
            "cbet_mw": (20, 45), "turn_barrel": (40, 65), "fold_to_cbet": (35, 60),
            "flop_xr": (6, 16), "fold_river_bet": (40, 65), "river_call_won": (40, 100),
            "wtsd": (27, 37), "wsd": (48, 60), "ep_weak_open": (0, 15),
        },
        "rfi": {"LJ": (20, 30), "HJ": (24, 34), "CO": (32, 45), "BTN": (48, 65), "SB": (35, 55),
                "UTG": (16, 26), "UTG+1": (18, 28), "MP": (19, 29)},
        "pfr": (20, 32), "gap": 12,
    },
    "PLO4": {
        "label": "PLO (4-korts Omaha), 6-max",
        "weak": "regnbågshänder och händer med dangler",
        "good": "händer som är dubbelfärgade, sammanhängande och/eller innehåller suited ess",
        "premium": "AAxx och de bästa dubbelfärgade rundown-händerna",
        "ep_req": "minst enkelfärgad (gärna suited ess) och fyra sammanhängande kort",
        "ranges": {},
        "rfi": None,  # fylls med RFI_RANGES nedan
        "pfr": (15, 25), "gap": 10,
    },
}


def detect_profile(st: HeroStats) -> str:
    if not st.games:
        return "PLO6"
    game = max(st.games.items(), key=lambda kv: kv[1])[0]
    return "PLO6" if game == "PLO-6" else "PLO4"


def _fmt(text: str, **ctx) -> str:
    return text.format(**ctx)


# Hur handlingen ("hit") och motsatsen beskrivs i resultatjämförelsen.
ACTION_LABELS = {
    "fold_to_3bet": ("foldade", "fortsatte (syn eller 4-bet)"),
    "bb_fold_steal": ("foldade", "försvarade"),
    "sb_fold_steal": ("foldade", "försvarade"),
    "fold_to_cbet": ("foldade", "fortsatte"),
    "fold_river_bet": ("foldade", "synade/raisade"),
    "fold_turn_bet": ("foldade", "fortsatte"),
    "cold_call_3bet": ("cold-callade", "foldade/4-bettade"),
    "call_3bet_oop": ("synade ur position", "foldade/4-bettade"),
    "cold_call": ("cold-callade", "foldade/3-bettade"),
    "3bet": ("3-bettade", "inte 3-bettade"),
    "cbet_hu": ("c-bettade", "checkade"),
    "cbet_mw": ("c-bettade", "checkade"),
    "turn_barrel": ("bettade turn", "checkade turn"),
    "flop_xr": ("check-raisade", "inte check-raisade"),
    "open_limp": ("limpade", "höjde/foldade"),
    "vpip": ("spelade handen", "foldade preflop"),
}
# Stats där "hit" = fold. För dem kan resultaten visa om du borde folda oftare:
# om händerna du fortsatte med klart slog kostnaden för att folda, är det ingen läcka.
FOLD_STATS = {"fold_to_3bet", "bb_fold_steal", "sb_fold_steal", "fold_to_cbet", "fold_river_bet", "fold_turn_bet"}


def results_note(key: str, stat: Stat) -> str:
    if key not in ACTION_LABELS:  # t.ex. WTSD/W$SD: resultatet ÄR själva måttet, jämförelsen säger inget
        return ""
    hit_l, miss_l = ACTION_LABELS[key]
    parts = []
    mh, mm = stat.mean_hit(), stat.mean_miss()
    if mh is not None:
        se = stat.se_hit()
        parts.append(f"när du {hit_l}: {mh:+.2f} bb/hand ({stat.hits} ggr"
                     + (f", ±{1.96 * se:.2f}" if se else "") + ")")
    if mm is not None:
        se = stat.se_miss()
        parts.append(f"när du {miss_l}: {mm:+.2f} bb/hand ({stat.opps - stat.hits} ggr"
                     + (f", ±{1.96 * se:.2f}" if se else "") + ")")
    return ("Dina resultat i spotten – " + " · ".join(parts) + ".") if parts else ""


def apply_pool(prof: dict, pool) -> dict:
    """Ersätt de inbyggda uppskattningarna med riktvärden från vinnande spelare i databasen."""
    if not pool or not pool.usable:
        return prof
    prof = dict(prof)
    prof["ranges"] = dict(prof["ranges"])
    prof["sources"] = {}
    for k, b in pool.ranges.items():
        prof["ranges"][k] = (round(b.lo, 1), round(b.hi, 1))
        prof["sources"][k] = b
    if pool.rfi:
        prof["rfi"] = dict(prof["rfi"] or RFI_RANGES)
        for pos, b in pool.rfi.items():
            prof["rfi"][pos] = (round(b.lo, 1), round(b.hi, 1))
            prof["sources"][f"rfi_{pos}"] = b
    if "gap" in pool.extra:
        prof["gap"] = round(pool.extra["gap"].hi, 1)
        prof["sources"]["gap"] = pool.extra["gap"]
    if "agg" in pool.extra:
        prof["agg_lo"] = round(pool.extra["agg"].lo, 1)
        prof["sources"]["agg"] = pool.extra["agg"]
    prof["pool"] = pool
    return prof


def source_text(prof: dict, key: str) -> str:
    b = prof.get("sources", {}).get(key)
    if b:
        who = "vinnande regs" if b.group == "vinnare" else "regs"
        return f"{who} i din databas: mitten-80 % {b.lo:.0f}–{b.hi:.0f}%, median {b.median:.0f}% ({b.n} spelare)"
    return "inbyggd uppskattning (ingen pooldata)"


# Syn-stats där vi kan jämföra syn mot kostnaden för att folda i exakt samma spot.
CALL_VS_FOLD = {"call_3bet_oop": "fold_3bet_oop", "cold_call_3bet": "fold_vs_3bet_cold"}


def _call_vs_fold(stat: Stat, fold: Stat) -> tuple[str, bool | None]:
    """Jämför snittresultat när du synade med snittkostnaden när du foldade.
    Returnerar (text, belagt) där belagt=True om syn är klart sämre än fold,
    False om dina resultat inte visar det, None om data saknas."""
    cm, cse, fm = stat.mean_hit(), stat.se_hit(), fold.mean_hit() if fold else None
    if cm is None or fm is None or not cse or stat.hits < 50 or fold.hits < 20:
        return "", None
    txt = (f"Dina resultat: när du synade {cm:+.2f} bb/hand ({stat.hits} ggr, felmarginal ±{1.96 * cse:.2f}) "
           f"· att folda kostade {fm:+.2f} bb/hand ({fold.hits} ggr).")
    if cm + 1.96 * cse < fm:
        return txt + " Synarna har varit klart sämre än att folda – dina egna resultat stödjer läckan.", True
    return txt + (" Synarna har INTE varit klart sämre än att folda, så dina resultat belägger inte den här läckan. "
                  "Riktvärdet är en uppskattning, inte en bevisad sanning – se det som en hypotes att granska."), False


def _rule_leak(rule: dict, stat: Stat, prof: dict, allstats: dict | None = None) -> Leak | None:
    v = stat.pct
    if v is None or stat.opps < rule["min"]:
        return None
    lo, hi = prof["ranges"].get(rule["stat"], rule["range"])
    width = max(hi - lo, 5)
    if v > hi and "high" in rule:
        side, dev = "high", (v - hi) / width
    elif v < lo and "low" in rule:
        side, dev = "low", (lo - v) / width
    else:
        return None
    t = rule[side]
    conf_label, conf = _confidence(stat.opps, rule["min"])
    sev = min(dev, 3.0) * rule["weight"] * conf * 3
    # välj exempel: de dyraste händerna där läckan syns. För "för högt" är det
    # händerna där du gjorde handlingen, för "för lågt" där du inte gjorde den.
    use_hits = t.get("ex", "hit" if side == "high" else "miss") == "hit"
    examples = stat.worst_hits(4) if use_hits else stat.worst_misses(4)
    spot_note = results_note(rule["stat"], stat)
    if rule["stat"] in CALL_VS_FOLD and side == "high" and allstats is not None:
        txt, proven = _call_vs_fold(stat, allstats.get(CALL_VS_FOLD[rule["stat"]]))
        if txt:
            spot_note = txt
            if proven is False:
                sev *= 0.25
    # Säger dina egna resultat emot? (bara för fold-stats där du foldar "för lite")
    if rule["stat"] in FOLD_STATS and side == "low":
        mh, mm, se = stat.mean_hit(), stat.mean_miss(), stat.se_miss()
        if mh is not None and mm is not None and se and mm - 1.96 * se > mh:
            sev *= 0.25
            spot_note += (" Händerna du fortsatte med gav klart bättre resultat än att folda (även med felmarginal) "
                          "– så på dina nivåer är detta troligen INTE en läcka, trots att du avviker från riktvärdet.")
    ctx = dict(v=v, lo=f"{lo:g}", hi=f"{hi:g}", weak=prof["weak"], good=prof["good"],
               premium=prof["premium"], ep_req=prof["ep_req"])
    return Leak(
        key=f"{rule['stat']}_{side}",
        title=t["title"],
        value=f"{v:.1f}%",
        target=f"{lo:g}–{hi:g}%",
        source=source_text(prof, rule["stat"]),
        what=_fmt(t["what"], **ctx),
        why=_fmt(t["why"], **ctx),
        fix=[_fmt(x, **ctx) for x in t["fix"]],
        drill=_fmt(t["drill"], **ctx),
        severity=sev,
        opps=stat.opps,
        confidence=conf_label,
        examples=examples,
        example_label="Dyraste exemplen",
        spot_note=spot_note,
        category=rule["cat"],
    )


# Riktvärden för öppningsfrekvens per position (RFI), 6-max PLO.
RFI_RANGES = {"LJ": (14, 23), "HJ": (18, 28), "CO": (25, 37), "BTN": (40, 58), "SB": (25, 48),
              "UTG": (12, 20), "UTG+1": (13, 21), "MP": (14, 22)}


def _rfi_leaks(st: HeroStats, prof: dict) -> list[Leak]:
    out = []
    ranges = prof["rfi"] or RFI_RANGES
    for pos, stat in st.rfi_by_pos.items():
        if pos not in ranges or stat.opps < 60 or stat.pct is None:
            continue
        lo, hi = ranges[pos]
        v = stat.pct
        if lo <= v <= hi:
            continue
        conf_label, conf = _confidence(stat.opps, 60)
        dev = (v - hi) / (hi - lo) if v > hi else (lo - v) / (hi - lo)
        sev = min(dev, 3.0) * 0.8 * conf * 3
        if v > hi:
            title = f"Du öppnar för brett från {pos}"
            what = f"Från {pos} öppnar du {v:.0f}% när det är foldat till dig (riktvärde {lo:g}–{hi:g}%)."
            why = ("För breda öppningar ger fler spelare bakom dig chansen att 3-betta eller syna i position, "
                   "och du hamnar i svåra spots med medelmåttiga händer.")
            fix = [f"Stryk de svagaste händerna i din {pos}-range: {prof['weak']}.",
                   "Använd en chart för positionen och håll dig till den i några tusen händer."]
            ex = stat.worst_hits(4)
        else:
            title = f"Du öppnar för tight från {pos}"
            what = f"Från {pos} öppnar du bara {v:.0f}% (riktvärde {lo:g}–{hi:g}%)."
            why = "Särskilt i sen position är öppningar en av de största vinstkällorna – blinds och dött pengar."
            fix = [f"Lägg till fler spelbara händer från {pos}: sammanhängande färgade händer och suited ess."]
            ex = []
        out.append(Leak(
            key=f"rfi_{pos}", title=title, value=f"{v:.1f}%", target=f"{lo:g}–{hi:g}%",
            source=source_text(prof, f"rfi_{pos}"),
            what=what, why=why, fix=fix,
            drill=f"Gå igenom dina {pos}-öppningar i rapportens exempelhänder.",
            severity=sev, opps=stat.opps, confidence=conf_label, examples=ex,
            example_label="Dyraste öppningarna",
            spot_note=f"Resultat när du öppnade från {pos}: {stat.net_hit:+.1f} bb över {stat.hits} händer.",
            category="Preflop",
        ))
    return out


def _vpip_pfr_gap(st: HeroStats, prof: dict) -> Leak | None:
    v, p = st.s["vpip"], st.s["pfr"]
    if v.opps < 300 or v.pct is None:
        return None
    gap = v.pct - p.pct
    lim = prof["gap"]
    if gap <= lim:
        return None
    conf_label, conf = _confidence(v.opps, 300)
    sev = min((gap - lim) / 5, 3.0) * 1.0 * conf * 3
    return Leak(
        key="passive_pre", title="Du är för passiv preflop",
        value=f"VPIP {v.pct:.0f}% / PFR {p.pct:.0f}%", target=f"Skillnad högst ~{lim} procentenheter",
        what=f"Du går in i {v.pct:.0f}% av potterna men höjer bara {p.pct:.0f}%. Skillnaden ({gap:.0f} pe) betyder att du synar/limpar mycket.",
        why="Synar och limpar leder till pottar där du saknar initiativ och ofta är ur position eller multiway "
            "med en hand som inte är stark nog.",
        fix=["Höj eller folda som förstahandsval – syna bara med en tydlig plan (position + spelbar hand).",
             "Byt ut synar från SB mot 3-bet eller fold."],
        drill="Gå igenom dina syner preflop från SB och LJ/HJ.",
        source=source_text(prof, "gap"),
        severity=sev, opps=v.opps, confidence=conf_label, category="Preflop",
    )


def _agg_leak(st: HeroStats, prof: dict) -> Leak | None:
    af = st.agg_freq
    tot = st.agg_actions + st.pass_actions
    floor = prof.get("agg_lo", 33)
    if af is None or tot < 400 or af >= floor:
        return None
    conf_label, conf = _confidence(tot, 400)
    sev = min((floor - af) / 8, 3.0) * 0.9 * conf * 3
    return Leak(
        key="passive_post", title="Du är för passiv postflop",
        value=f"{af:.0f}%", target=f"Minst ~{floor:g}%", source=source_text(prof, "agg"),
        what=f"Bara {af:.0f}% av dina postflop-actions är bets eller raises.",
        why="Passivt spel låter motståndarna styra potten: de får gratis kort när du har starka händer "
            "och kan bluffa dig när du checkar.",
        fix=["Betta dina starka händer och nötdrag för värde – PLO-pottar ska byggas när du har nöten.",
             "Check-raisa mer med starka drag istället för att bara checksyna."],
        drill="Hitta 20 händer där du checksynade med set eller nötdrag och fundera på att betta/raisa.",
        severity=sev, opps=tot, confidence=conf_label, category="Postflop",
    )


def _reverse_dom_leak(st: HeroStats, prof: dict) -> Leak | None:
    allrd = st.reverse_dominated
    rd = [e for e in allrd if e["kind"] == "weak"]
    coolers = [e for e in allrd if e["kind"] == "cooler"]
    if len(rd) < 4 or st.hands < 500:
        return None
    lost = sum(e["net"] for e in rd)
    per100 = 100.0 * lost / st.hands
    if per100 > -2:
        return None
    conf_label = "Hög" if len(rd) >= 40 else ("Medel" if len(rd) >= 15 else "Låg")
    conf = {"Hög": 1.0, "Medel": 0.85, "Låg": 0.65}[conf_label]
    sev = min(-per100 / 4, 3.0) * 1.1 * conf * 3
    kinds = {}
    for e in rd:
        kinds[e["hero_hand"]] = kinds.get(e["hero_hand"], 0) + 1
    kinds_txt = ", ".join(f"{k} ({n})" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
    ex = sorted(((e["id"], e["net"]) for e in rd), key=lambda x: x[1])[:5]
    cool_lost = sum(e["net"] for e in coolers)
    return Leak(
        key="reverse_dom", title="Du betalar av stora pottar med slagbara händer",
        value=f"{lost:.0f} bb ({per100:.1f} bb/100)", target="Så nära 0 som möjligt",
        what=f"I {len(rd)} stora pottar förlorade du vid showdown med samma handtyp som vinnaren men en hand som "
             f"var klart slagbar ({kinds_txt}): minst 2 % av motståndarens möjliga kombinationer slog dig, vilket "
             f"med sex hålkort ofta betyder 25 % eller mer att en enskild motståndare har bättre.",
        why="När det blir stor action i PLO6 har motståndaren mycket ofta nöten eller nära. Icke-nötig färg, lägre kåk "
            "och lägre stege är bluff-catchers, inte värdehänder. Coolers – där du hade nöten eller nästan – är "
            f"redan bortfiltrerade ({len(coolers)} händer, {cool_lost:.0f} bb) och räknas inte som misstag.",
        fix=["Bygg inte stora pottar med icke-nötig färg, lägre kåk eller låg ända av stegen ('ignorant end').",
             "Fråga på varje gata: 'vad är nöten och hur många kombinationer slår mig?' – med sex kort har motståndaren 15 kombinationer.",
             "Med slagbar hand mot stor action (raise, check-raise, stor river-bet): syna en gång eller folda – inte re-raisa."],
        drill="Gå igenom händerna nedan: på vilken gata satte du in mest pengar, och var handen fortfarande bäst där?",
        severity=sev, opps=len(rd), confidence=conf_label, examples=ex,
        example_label="Dyraste förlusterna med slagbar hand", category="Postflop",
    )


def _tilt_leak(st: HeroStats, prof: dict) -> Leak | None:
    t = st.tilt
    if not t:
        return None
    after, normal = t["after"], t["normal"]
    if after.opps < 80 or normal.opps < 300:
        return None
    diff = after.pct - normal.pct
    if diff < 4:
        return None
    conf_label, conf = _confidence(after.opps, 80)
    sev = min(diff / 4, 3.0) * 1.0 * conf * 3
    return Leak(
        key="tilt", title="Du spelar lösare efter stora förluster (tilt)",
        value=f"VPIP {after.pct:.0f}% efter förlust vs {normal.pct:.0f}% normalt", target="Ingen skillnad",
        what=f"Under de {t['window']} händerna efter att du förlorat minst {t['threshold']:.0f} bb i en hand "
             f"spelar du {diff:.0f} procentenheter fler händer än annars ({t['triggers']} tillfällen).",
        why="PLO har enorm varians – stora förluster är normala. Att spela lösare efteråt förvandlar "
            "en kortsiktig förlust till en verklig läcka.",
        fix=["Inför en stoppregel: efter en förlust på 100bb+ – ta en 5-minuters paus.",
             "Ha en stop-loss per session (t.ex. 3 buy-ins).",
             "Spela färre bord när du har förlorat en stor pott."],
        drill="Logga hur du känner dig efter stora förluster under nästa vecka.",
        severity=sev, opps=after.opps, confidence=conf_label,
        spot_note=f"Resultat i händerna efter stora förluster: {after.net_all:+.1f} bb över {after.opps} händer "
                  f"({100 * after.net_all / after.opps:+.1f} bb/100 jämfört med {100 * normal.net_all / normal.opps:+.1f} bb/100 annars).",
        category="Mentalt",
    )


def find_leaks(st: HeroStats, profile: str | None = None, pool=None) -> list[Leak]:
    prof = apply_pool(PROFILES[profile or detect_profile(st)], pool)
    leaks: list[Leak] = []
    for rule in RULES:
        lk = _rule_leak(rule, st.s.get(rule["stat"], Stat()), prof, st.s)
        if lk:
            leaks.append(lk)
    leaks.extend(_rfi_leaks(st, prof))
    for fn in (_vpip_pfr_gap, _agg_leak, _reverse_dom_leak, _tilt_leak):
        lk = fn(st, prof)
        if lk:
            leaks.append(lk)
    leaks.sort(key=lambda l: l.severity, reverse=True)
    return leaks


def stat_table(st: HeroStats, profile: str | None = None, pool=None) -> list[dict]:
    """Alla regelstatistik med ditt värde, riktvärde och status – för översiktstabellen."""
    prof = apply_pool(PROFILES[profile or detect_profile(st)], pool)
    rows = []
    for rule in RULES:
        s = st.s.get(rule["stat"], Stat())
        v = s.pct
        lo, hi = prof["ranges"].get(rule["stat"], rule["range"])
        if v is None:
            status = "ingen data"
        elif s.opps < rule["min"]:
            status = "för litet urval"
        elif v > hi:
            status = "för högt"
        elif v < lo:
            status = "för lågt"
        else:
            status = "ok"
        b = prof.get("sources", {}).get(rule["stat"])
        rows.append({"name": rule["name"], "value": v, "lo": lo, "hi": hi, "opps": s.opps,
                     "min": rule["min"], "status": status, "cat": rule["cat"],
                     "median": b.median if b else None, "n": b.n if b else None,
                     "src": "pool" if b else "uppskattning", "note": results_note(rule["stat"], s)})
    vp = st.s.get("pfr", Stat())
    bp = prof.get("sources", {}).get("pfr")
    plo, phi = prof["ranges"].get("pfr", prof["pfr"])
    rows.insert(1, {"name": "PFR", "value": vp.pct, "lo": plo, "hi": phi, "opps": vp.opps, "min": 300,
                    "status": "info", "cat": "Preflop", "median": bp.median if bp else None,
                    "n": bp.n if bp else None, "src": "pool" if bp else "uppskattning", "note": ""})
    af = st.agg_freq
    ba = prof.get("sources", {}).get("agg")
    floor = prof.get("agg_lo", 33)
    rows.append({"name": "Aggression postflop", "value": af, "lo": ba.lo if ba else 35, "hi": ba.hi if ba else 50,
                 "opps": st.agg_actions + st.pass_actions, "min": 400,
                 "status": "info" if af is None else ("för lågt" if af < floor else "ok"), "cat": "Postflop",
                 "median": ba.median if ba else None, "n": ba.n if ba else None,
                 "src": "pool" if ba else "uppskattning", "note": ""})
    return rows


# =========================================================================== strikt läge
# Bara läckor som dina egna resultat bevisar (se decisions.py). Inga riktvärden,
# inga uppskattningar. Råder det tvivel säger programmet ingenting.
import math as _math

from .decisions import MIN_EFFECT_BB, MIN_N, SPOT_NAMES, ACTION_VERB, Z_REQUIRED, proven_leaks


def _odds_text(z: float) -> str:
    p = 0.5 * _math.erfc(abs(z) / _math.sqrt(2))
    if p <= 1e-6:
        return "mindre än 1 på en miljon"
    return f"mindre än 1 på {max(int(1 / p), 1):,}".replace(",", " ")


def _title(d: dict) -> str:
    verb = ACTION_VERB.get((d["spot"], d["action"]), d["action"])
    b, pos, spot = d["bucket"], d["pos"], d["spot"]
    if spot == "rfi":
        who = "händer" if b == "alla" else (f"händer med {b}" if b[:1].isdigit() else f"'{b}'-händer")
        where = "" if pos == "alla" else f" från {pos}"
        return f"Sluta {verb} {who}{where}"
    if spot == "river_mot_bet":
        return f"Sluta {verb} river-bets med {b}" if b != "alla" else f"Sluta {verb} river-bets så ofta"
    what = SPOT_NAMES.get(spot, spot)
    with_ = "" if b == "alla" else f" med '{b}'"
    where = "" if pos == "alla" else f" ({pos})"
    return f"Sluta {verb} {what}{with_}{where}"


def _p_text(p: float) -> str:
    if p <= 1e-6:
        return "mindre än 1 på en miljon"
    return f"ungefär 1 på {max(int(round(1 / p)), 1):,}".replace(",", " ")


def _proven_leak(d: dict) -> Leak:
    verb = ACTION_VERB.get((d["spot"], d["action"]), d["action"])
    ci = 1.96 * d["se"]
    cost100 = d["cost100"]
    fix = []
    if d["spot"] == "river_mot_bet":
        fix.append(f"Folda river-bets med {d['bucket']}.")
    elif d["spot"] == "rfi":
        fix.append("Folda de här händerna istället för att öppna dem"
                   + (f" från {d['pos']}" if d["pos"] != "alla" else "") + ".")
    else:
        fix.append(f"Folda istället för att {verb} i den här situationen"
                   + (f" med '{d['bucket']}'" if d["bucket"] != "alla" else "") + ".")
    fix.append("Ändra bara just detta – resultatet säger inget om andra situationer eller handtyper.")
    return Leak(
        key=f"proven:{d['spot']}:{d['pos']}:{d['bucket']}:{d['action']}",
        title=_title(d),
        value=f"{d['mean']:+.2f} bb per gång jämfört med fold",
        target="minst 0 (lika bra som att folda)",
        source=(f"dina egna resultat med all-in EV · {d['n']} tillfällen · hittad i halva A "
                f"({d['n_a']} st, {d['mean_a']:+.2f} bb/gång), bekräftad i halva B ({d['n_b']} st, {d['mean']:+.2f} bb/gång)"),
        what=(f"Du har valt att {verb} {d['n']} gånger här. I den halva av dina händer som användes för att bekräfta "
              f"läckan gav det i snitt {d['mean']:+.2f} bb per gång jämfört med att folda direkt (felmarginal ±{ci:.2f})."),
        why=(f"Det bygger enbart på dina egna händer, räknat med all-in EV så att tur i all-ins inte påverkar. "
             f"Läckan hittades i ena halvan av dina händer och bekräftades sedan i den andra halvan, som sökningen inte "
             f"hade sett. Risken att bekräftelsen beror på slump är {_p_text(d['p_b'])}. "
             f"Jämförelsen gäller hur du faktiskt spelat händerna vidare – det är din helhet med de här händerna som förlorar."),
        fix=fix,
        drill="Gå igenom exempelhänderna nedan och se var pengarna gick förlorade.",
        severity=cost100,
        severity_low=d.get("cost100_low"),
        opps=d["n"],
        confidence="Säkerställd",
        examples=d["examples"],
        example_label="Dyraste exemplen (jämfört med fold)",
        spot_note=(f"Hade du foldat de här händerna hade du vunnit ungefär {-d['total']:.0f} bb mer, "
                   f"{cost100:.2f} bb/100 på hela ditt urval (räknat på bekräftelsehalvan; försiktig gräns: minst "
                   f"{d['cost100_low']:.2f} bb/100). Skattningen är snarare för hög än för låg, eftersom bara läckor "
                   f"som syns tydligt klarar kraven. I samma situation foldade du {d['folds']} gånger."
                   + (f" {d['removed_later_street']} händer där en bekräftad läcka på en senare gata redan förklarar "
                      f"förlusten är borträknade." if d.get("removed_later_street") else "")),
        category=("River" if d["spot"].startswith("river") else
                  "Postflop" if d["spot"].startswith(("flop", "turn")) else "Preflop"),
    )


def find_proven(st: HeroStats, river=None) -> list[Leak]:
    """Säkerställda läckor: hittade i halva A av dina händer och bekräftade i halva B.

    River-modellen och tilt-testet ger inte längre "säkerställda" läckor: river-modellens
    slutsatser om folds och egna bets går inte att kontrollera mot verkliga utfall, och
    tilt-jämförelsen blandas ihop med bord, tid och motståndare."""
    leaks = [_proven_leak(d) for d in proven_leaks(st.decisions, st.hands)]
    leaks.sort(key=lambda l: l.severity, reverse=True)
    return leaks


STRICT_RULES_TEXT = (f"En läcka visas bara om den klarar två steg. 1) Upptäckt: dina händer delas i två fasta halvor, "
                     f"per spelpass (alla bord, nytt pass efter 30 minuters paus), så att händer från samma pass hamnar i samma halva. I halva A testas "
                     f"alla beslutsgrupper mot att folda, räknat med all-in EV, med en test som tar hänsyn till att "
                     f"pokerresultat är snedfördelade och Benjamini–Hochberg över alla tester. 2) Bekräftelse: varje "
                     f"kandidat testas igen i halva B, som sökningen inte sett, med kluster-bootstrap och "
                     f"Bonferroni-korrektion. Minst {MIN_N} tillfällen och minst 5 stora vinster i varje halva, och minst "
                     f"{MIN_EFFECT_BB} bb förlust per gång i båda. Läckor på senare gator bekräftas först, och de händerna "
                     f"räknas sedan bort från tidigare gator. Kostnaden räknas från halva B. Allt annat visas inte.")


# =========================================================================== topp 3 och troliga läckor
LIKELY_P = 0.95  # minst 95 % sannolikhet (efter krympning) att det är en förlust


def likely_leaks(st: HeroStats, proven: list[Leak], river=None) -> list[Leak]:
    """Borttaget i 1.3: "troliga" läckor var till stor del brus i tester på data utan läckor."""
    return []


def top_three(proven: list[Leak], likely: list[Leak] | None = None) -> list[Leak]:
    """De tre dyraste säkerställda läckorna. Färre än tre om färre är säkerställda."""
    return sorted(proven, key=lambda l: l.severity, reverse=True)[:3]
