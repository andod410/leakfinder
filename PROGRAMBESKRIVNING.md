# Leakfinder – programbeskrivning för extern granskning

Version 2.81 · 2026-11-19 · skriven direkt från källkoden (paketet `plo_leak`/)

Det här dokumentet är till för en **extern granskare** (människa eller AI-agent). Det förklarar vad programmet gör,
hur data flödar och **exakt hur varje uträkning görs**, med formler, konstanter och var i koden de finns. Sist finns
kända begränsningar och en lista med frågor som granskaren uttryckligen ombeds pröva.

Om dokumentet och koden säger olika saker gäller koden. Konstantvärden är hämtade ur koden för version 2.73. Avsnitt 13 listar vad den externa granskningen av 2.72.2 ledde till.

---

## 0. Syfte och ramar

* **Spelaren:** PLO6 (sexkorts-Omaha) cashgame på GGPoker, nivåer upp till 2/5. Målet är **högsta möjliga timlön**,
  med en vinstnivå på 5–10 bb/100.
* **Vad programmet gör:** läser in spelarens handhistorik, räknar ut var pengarna förloras ("läckor") och gör om de
  säkraste slutsatserna till regler som följs upp session för session.
* **Hårda ramar:**
  1. **Ingen hjälp i realtid.** GG förbjuder det. Programmet är ett efterhandsverktyg. Det som programmet själv
     upprätthåller är smalare än så: **nattjobben** vägrar starta om GG-klienten är igång, om det inte går att
     kontrollera om den är igång (2.73), eller om en handhistorikfil har ändrats de senaste 10 minuterna. Webbsidorna
     går att öppna även när GG körs – det är spelarens uttryckliga val (2026-11-14) och hans ansvar att inte använda
     dem under spel.
  2. **Inga profiler per motståndare.** GG anonymiserar spelarna, så bara poolstatistik används.
  3. **Rakeback räknas inte.** All rake och alla avgifter dras från resultaten.
  4. **Regler bara med statistiskt stöd.** Statusen **"bekräftad"** kräver ett framåttest på händer spelade
     *efter* frysdatumet **2026-11-13** (`forward.FREEZE_DATE`). Från 2.73 sätts nivån på ett enda ställe
     (`report._forward_levels`): "bekräftad" bara när den frysta regeln har utfallet "håller" och dagens regel har exakt
     samma definition. Postflop-fokus (`pffocus`) är alltid "trolig" (hypotes med uppskattad kostnad). Råd som saknar sådant stöd är "riktlinjer" (💡)
     eller "hypoteser" (🧪) och räknas aldrig som regelbrott.
* **Grundprincip för slutsatser:** varje jämförelse görs **mot fold**, eftersom en fold har ett exakt känt utfall:
  den kostar det du redan lagt i potten. Det gör att effekten av ett beslut kan mätas utan att man vet hur poolen
  egentligen spelar.

---

## 1. Arkitektur

```
Handhistorik (GG .txt/.zip, DriveHUD-export)
      │  parser.py  (tolkning → Hand-objekt)
      ▼
SQLite-databas  ~/.plo_leak_cache/plo_leak.db   (db.py; en rad per hand, originaltext + per-hand-cache)
      │  facts.py  Builder: stats._analyze_hand körs EN gång per hand
      ▼
Faktatabeller i kolumnform (numpy, FactStore, FACTS_VERSION 13)
  hands · stat · grp · fold · pre · riv · trn · rsp · rvb · pfd · bsz · diag · samp · sd
      │  selection.py (urval: variant, nivå, datum, bordstyp)  →  aggregate.py (HeroStats)
      ▼
Analyser (analyses.py, @analysis-register, resultat cachas per data+urval+version)
      │
      ├── report.py + templates/  → HTML-rapport / webbsidor (web.py, Flask, port 8765)
      ├── export.py      → analysfil (JSON) för Claude
      ├── dataexport.py  → djupexport (CSV-zip) för Claude
      ├── sessionfile.py → sessionsfil (markdown)
      └── nightly.py     → nattkörning: backup, inläsning, night2, kvitto, morgonrapport
```

* **Bakgrundsjobb** (`jobs.py`): inläsning, djupanalys, export och nattberäkning körs i en egen tråd, ett jobb i
  taget. Ett nytt jobb med samma nyckel (`djup`, `natt`, `export`, `bevaka`) ger tillbaka det jobb som redan är
  aktivt. Förloppet hämtas via `/api/jobs` och visas överst på alla sidor.
* **Bevakad mapp** (`watch.py`): mappen kontrolleras var 10:e sekund. Zip-filer packas upp i minnet; textfiler över
  64 MB i en zip läses i delar som bryts vid en handstart (2.73). Det som avvisas (zip i zip över 200 MB, mer än 2 GB
  uppackat) visas med skäl efter inläsningen – inget hoppas över tyst. Filer som redan
  lästs in (samma storlek och ändringstid) hoppas över.
* **Urvalsraden (2.73.1):** "Visa urvalet" (`view=True` i `pipeline.build`) byter bara urvalet: statistik, resultat och
  per-urvals-analyser (pottstorlek, timlön m.m.) räknas för urvalet, medan modellanalyserna (`model=True`) och reglerna tas
  från den senast sparade fulla analysen av samma variant/bord/nivå, oavsett nya händer. Saknas en sparad analys körs
  modellanalyserna inte (`Ctx.skip_models`). "🔬 Analysera urvalet" räknar modellerna på urvalet (`model_on_selection`)
  när det är begränsat i tid, annars en full analys.
* **Cache:**
  * Tunga beräkningar per hand (all-in EV, handstyrka) sparas i `db.CalcCache` (`CALC_VERSION = 4`).
  * Analysresultat sparas på disk per (data, urval, analys, version).
* **Varianter:** PLO4, PLO5 och PLO6 tolkas alla, men flera analyser (`single_variant=True`) kräver en enda variant.
  `night2` använder bara huvudvarianten (`main_game`).

### Kodkarta (modul → ansvar)

| Område | Moduler |
|---|---|
| Inläsning | `parser.py`, `watch.py`, `db.py`, `facts.py`, `pipeline.py`, `selection.py`, `aggregate.py`, `stats.py` |
| Kort och equity | `cards.py`, `ev.py`, `fastev.py`, `board.py`, `replayer.py`, `sim.py` |
| Statistik | `statlib.py` (alla signifikanstester), `decisions.py` (bevismotor) |
| Preflop | `ranges.py`, `nutfold.py`, `rundowns.py`, `threebet.py`, `likely.py`, `subgroups.py` |
| Postflop | `aggr.py`, `river.py`, `rivercoach.py`, `summary.py`, `postflop_rows.py`, `betsize.py`, `pffocus.py` |
| Regler och uppföljning | `practice.py`, `holdout.py`, `forward.py`, `pfforward.py`, `riverbluff.py`, `guidelines.py`, `focus.py`, `sessions.py`, `blocks.py` |
| Tid och resultat | `hourly.py`, `fatigue.py`, `timeofday.py`, `stakecheck.py`, `potsize.py` |
| Jämförelsevärden | `leaks.py` (fasta riktvärden), `pool.py` (riktvärden från vinnande motståndare) |
| Natt | `night.py` (v1), `night2.py` (v2), `nightly.py` (schemaläggning) |
| Utdata | `report.py`, `web.py`, `export.py`, `dataexport.py`, `sessionfile.py`, `hhexport.py`, `hhwrite.py`, `share.py` |

---

## 2. Inläsning och grunddata

### 2.1 Tolkning (`parser.py`)
* GG-formatet och PokerStars-liknande format tolkas med reguljära uttryck. Raderna som läses är bord, platser och
  stackar, utdelade kort, gator, "Uncalled bet", "collected", cashout och avgifter.
* Positioner sätts från knappen. Vid dead SB rättas de av `fix_dead_sb_positions`.
* **Positionsnamn (2.74):** GG PLO6 är 5-max: UTG, CO, BTN, SB, BB. Tolkningen ger den första positionen efter BB
  koden `HJ` (etiketterna fylls bakifrån: …, HJ, CO). Koden behålls i databasen, faktatabellerna och de frysta reglerna
  (annars ändras framåttestets definitioner och fingeravtryck). `positions.py` byter HJ → UTG i allt som visas och
  exporteras (`web.after_request`, CSV/JSON-export, sessionsfil, morgonrapport) och UTG → HJ i värden som kommer
  tillbaka från sidorna (`web.before_request`).
* Hero hittas som den spelare som har "Dealt to"-kort i flest händer (`detect_hero`).
* Dubletter tas bort på handnummer. Databasen har handnumret som primärnyckel.

### 2.2 Spelpass = kluster
`FactTable._sessionize`: alla heros händer, från alla bord, sorteras i tidsordning. Ett nytt pass börjar efter en
paus på mer än **30 minuter** (`SESSION_GAP`). Passet är **klustret** i all statistik:
* standardfelen är klusterrobusta;
* bootstrap drar hela pass;
* halvdelningen A/B görs per pass med `half_of(c) = (c >> 7) & 1`, där c är ett crc32-hashat pass-id.

### 2.3 Resultat och rake
* **Nettoresultat** per hand = det som vanns minus det som satsades (bb och pengar).
* **Rake som hero betalar** (`stats.py`), i potter hero vinner:
  `rake_bb = rake × hero_collected / (total_pot − rake) / bb`.
  Rake fördelas alltså proportionellt mot heros andel av potten.
* Resultaten visas både efter rake (huvudmåttet) och före rake (som information).

### 2.4 All-in EV (`ev.py: allin_ev`)
Används överallt i stället för faktiskt resultat, så att tur i all-ins rensas bort.
* **Villkor:** alla levande spelares kort måste vara kända (heros egna och visade kort), och varje pott där hero är
  med måste vara låst av en all-in före river. Om någon foldar efter låsningen används det faktiska resultatet.
* **Beräkning** per sidopott:
  * Equity räknas fram med kort som syns hos andra spelare borträknade.
  * Flop och turn räknas exakt; preflop med Monte Carlo (1 500 dragningar, minst 6 000 när potten är 100 bb eller mer).
  * EV för en pott = `equity × pottbelopp × (1 − fee_rate)`, där `fee_rate = rake / total insats` (begränsad till 0–0,5).
  * En pott med bara hero berättigad räknas som `belopp × (1 − fee_rate)`.
* **Hand-EV:** summan över potterna minus heros insats.

### 2.5 Handutvärdering
* `cards.eval5` och `best_omaha` är exakta. Omaha kräver exakt 2 hålkort + 3 bordskort.
* `fastev.best_values` är den vektoriserade motorn:
  * primtalsprodukt för valörer och tabeller för färg respektive icke-färg;
  * alla 2-av-n hålkort × 3-av-bord kombineras.
* `board.BoardTable` (river): för ett färdigt bord utvärderas alla 1 081 tvåkortskombinationer en gång. Ur det fås
  `beat_frac` = andelen kombinationer som slår handen, med korrekt kortborttagning. 0 betyder nöten.
* **Handstyrka "slår dig"** = andelen slumpade motståndarhänder (lika många kort, kända kort borttagna) som slår
  handen på bordet. Måttet är jämförbart mellan bord och används för att slå ihop situationer.
* **Luft** = minst 60 % av slumpade händer slår dig.

### 2.6 Starthandsklassificering (`cards.py`)
* Nöt-egenskaper ("Grinders Vault", PLO6):
  * **högt par**: JJ eller bättre, exakt två kort, inte trips;
  * **suited ess**: esset har 2–3 kort i sin färg;
  * **rundown**: fyra olika valörer ≥ 5 inom ett spann på högst 5 valörer.
* Antalet egenskaper (0–3) och deras kombination ("högt par + suited ess" och så vidare) är huvudindelningen preflop.
* Därutöver finns färgstruktur (trippel-, dubbel-, enkelsuited, rainbow), par, sammanhängning och låga kort.

---

## 3. Statistikbiblioteket (`statlib.py`)

Alla moduler som drar slutsatser använder de här funktionerna.

| Funktion | Vad den gör |
|---|---|
| `cluster_se(x, c)` | Klusterrobust standardfel. Klustersummor S_k, antal n_k, medel m = ΣS/Σn. var = Σ(S_k − m·n_k)² / N² · K/(K−1). |
| `johnson_p(x)` | Ensidigt test av H₁: medel < 0 med Johnsons (1978) skevhetskorrigering: t = (m + μ₃/(6s²n) + μ₃/(3s⁴)·m²) / (s/√n). Används vid **upptäckt**. |
| `bootstrap_t_p(x, c)` | Kluster-bootstrap-t: hela pass dras med återläggning, t* = (m* − m)/se*, p = (#{t* ≤ t_obs} + 1)/(B + 1). Ger p = 1 om antalet kluster är under 20. B = 4 000 som standard. Används vid **bekräftelse**. |
| `bh_cutoff(p, q)` | Benjamini–Hochberg: största p_(i) med p_(i) ≤ i/m · q. |
| `ci_cell(...)` | Medel ± 1,96·cluster_se. När intervallet ligger under noll men svansvakten stoppar blir domen "osäkert (svansvakt)" (2.73). Domen "lönsamt"/"förlorar" kräver tre saker: intervallet på ena sidan om noll, **svansvakt** (minst 5 utfall över +10 bb om det gäller en förlust) och ensidig bootstrap-t på nivån α/(2m) (Bonferroni över m celler). Antalet dragningar anpassas så att p-värdet kan nå nivån (minst 30/need). |
| `ci_cells` | `ci_cell` för en hel tabell, med m = antalet celler som har minst min_n. |

Konstanter: `BOOT_REPS = 4000`, `RULE_MIN_N = 100`, `MIN_BIG_WINS = 5`, `BIG_WIN_BB = 10`, `RULE_FAMILIES = 3`.

---

## 4. Bevismotorn (`decisions.py`)

**Grundmått** för varje beslut där hero fortsätter (syn eller höjning) i stället för att folda:

```
delta = handens all-in EV-resultat (bb) + det hero investerat före beslutet (bb)
```

En fold hade gett −investerat, så delta är "resultat jämfört med fold". Beslut grupperas på
(situation, position, betstorleksgrupp, handling).

**Upptäck och bekräfta:**
1. **Halva A (upptäckt):**
   * Varje grupp med n ≥ `MIN_N = 100` testas med `johnson_p`.
   * Benjamini–Hochberg körs över alla tester med q = `DISCOVERY_Q = 0.10`.
   * Effekten måste vara minst `MIN_EFFECT_BB = 0.3` bb per beslut.
2. **Halva B (bekräftelse):**
   * Kandidaterna testas med `bootstrap_t_p`.
   * Bonferroni över kandidaterna ger α = `CONFIRM_ALPHA = 0.05`.
   * Svansvakten (minst 5 utfall över +10 bb) måste klara sig i varje halva.
3. **Kostnaden** räknas bara på halva B, så att den inte blåses upp av urvalet.
4. Av överlappande grupper (t.ex. "alla positioner" och "HJ") rapporteras bara en.

**Begränsning, angiven i koden:** metoden kan bara bevisa att något är *sämre än fold*. Den kan aldrig bevisa att
du borde syna oftare, eftersom utfallet av foldade händer är okänt.

`detectable_effect` och analysen `power` visar vilken effektstorlek urvalet kan upptäcka.

---

## 5. Preflop

### 5.1 Range-gränser (`ranges.py`)
1. **Handpoäng:** en linjär poäng av handens egenskaper. Vikterna lärs från delta mot fold och korsvalideras: händer
   i halva A får sin poäng från vikter som lärts på halva B, och tvärtom.
2. I varje situation (t.ex. öppning från HJ) rangordnas de utdelade händerna till en percentil, där 0 % är bäst.
3. **Isoton regression** (fallande kurva) av delta över percentilen, i `N_BINS = 20` grupper.
4. **Gränsen** är där kurvan korsar noll. Osäkerheten fås genom att dra om hela pass `BOOT = 300` gånger.
5. Gränsen tas bara fram om det finns minst `MIN_PLAYED = 300` spelade händer.

Förbehåll, angivet i koden: kurvan bygger på de händer spelaren själv valt att spela. Inom ett percentilband spelas
troligen de bättre händerna, så händer under gränsen kan vara sämre än kurvan säger.

**Winrate-kurva per öppningsgräns (2.75, `ranges._winrate_curve`):** för varje öppningsposition ("rfi") räknas
förväntat resultat mot fold om spelaren öppnar exakt topp X % (X = 0–100):
* De utdelade händerna delas i 5 %-band efter den korsvaliderade percentilen. Varje band får medlet av de spelade
  händernas delta, gånger bandets andel av alla utdelade händer (som om alla händer i bandet spelats). Kurvan är
  summan upp till X, i bb per 100 händer i situationen; linjär inom ett band. Felmarginal: ±1,96·√(Σ andel²·var/n).
* Ett band räknas bara med minst 30 spelade händer; första bandet utan det avslutar kurvan ("ingen data").
* **Urvalsskydd:** ett band där spelaren öppnat under hälften av händerna är "osäkert" (de valda händerna är bättre än
  bandet). Från det första sådana bandet räknas inget som säkert, och **toppen söks bara i det säkra området**.
  Tränaren visar inga värden där, bara "troligen sämre än vid X %".
* Toppen, en platå (inom 2 bb/100 av toppen) och nuläget sparas i regelfilen (`wr_curves`). Bandens medel är mätta på
  samma händer som toppen väljs i, så toppen är något optimistisk.

**Träningens reglage (2.75, `practice.trainer_hand_pct`):** "📏 öppna topp X %" för UTG, CO, BTN och SB. Facit = handens
percentil mot 20 000 slumpade händer (seed 7) med regelfilens handvikter (`hand_weights`, samma för alla situationer;
standardvikter om ingen analys sparats) ≤ X. Spelarens regler visas bara som information. Hälften av händerna väljs
inom 8 procentenheter från gränsen.

### 5.2 Öppningsguide och nöt-egenskaper (`ranges.opening_guide`, `nutfold.py`)
* Celler är position × kombination av nöt-egenskaper. Måttet är delta för första beslutet preflop mot fold
  (exakt: 0 utanför blindarna, blinden i SB och BB).
* Domen kommer från `ci_cells` med Bonferroni över tabellens celler, `MIN_N = 100`.

### 5.3 Rundowns (`rundowns.py`)
* Handens högsta rundown är fyra olika valörer inom fem steg, högst en lucka; esset räknas både högt och som 1.
* Händerna grupperas efter rundownens lägsta kort: A–3, 4, … 9, T+.
* Huvudtabellen gäller **rena** rundowns, utan suited ess och utan högt par.
* Tabellen visar delta mot fold, pottens storlek när stegen vann och hur ofta stegen förlorade vid showdown.
* `sim.py` simulerar enbart kort (ingen satsning) för samma frågor. Motståndarna är "spelbara" händer med minst en
  nöt-egenskap.

### 5.3b Positionsläckor (`positionleaks.py`, 2.75)
* Första beslutet preflop per hand delas i grupper position × situation × handling × nöt-egenskaper (folds är facit
  och ingen grupp). Delta mot fold som i 5.2.
* Grupper med minst 30 spelade bedöms. "Säkert minus" = 95 %-intervallet (kluster per pass) under noll. "Bekräftad
  förlust" = `ci_cell` med Bonferroni över alla grupper och svansvakten.
* bb/100 totalt = gruppens summa / alla händer i urvalet × 100; bb/100 i positionen = / positionens beslut × 100.
  Positionerna sorteras efter vad de säkra minusgrupperna kostar.

### 5.4 3-bets (`threebet.py`)
* **"3-betta inte utan suited ess":** delta mot fold för 3-bets utan suited ess i lägena mot_hojning, bb_mot_hojning
  och sb_mot_hojning. Regeln gäller om delta är negativt med 95 % säkerhet (klusterrobust) och negativt i båda halvorna.
  `MIN_N = 200`.
  * Rundowns har särskild text: "syna i stället".
* **"3-betta högt par + suited ess i stället för att syna":** jämför två handlingar. Den markeras som **trolig**
  eftersom urvalet kan styra resultatet; kostnaden är den nedre gränsen för skillnaden.
* `vs3bet_nut_rule` hanterar beslut mot 3-bet.

### 5.5 Undantag inom regler (`subgroups.py`)
* Varje starthandsregel delas i förutbestämda strukturgrupper: trippelsuited, ds + sammanhängande, ds + suited kung,
  ds övriga, sammanhängande, övriga.
* Gruppens delta krymps mot regelns snitt med **empirisk Bayes**; mellangruppsvariansen τ² skattas med
  **DerSimonian–Laird**.
* En undergrupp vars krympta skattning är ≥ 0 blir **undantag** och räknas inte som regelbrott. Regelns kostnad räknas
  då om utan den.

### 5.6 Trolig förbättring (`likely.py`)
* Kandidaterna är bestämda i förväg: nöt-egenskaper × position, rundowns efter lägsta kort, öppningsguidens celler
  och range-gränser som inte klarat det strikta testet.
* Varje kandidat väljs i en halva av passen och mäts i den andra, i båda riktningarna.
* Benjamini–Hochberg med `Q_FDR = 0.20` och minst `N_MIN = 150`.
* "Säkerhet" = 1 − q. Den väntade vinsten räknas på den halva som inte valde kandidaten.

### 5.7 Solverjämförelse (2.76: `solvergroups.py`, `solverref.py`)
* **Läge:** `solvergroups.node_of` tar heros första preflopbeslut i 6-kortshänder utan straddle. Ingen höjning och ingen
  syn före = öppning (HJ/UTG, CO, BTN, SB); exakt en höjning och ingen syn/limp före = försvar mot öppning (10 par av
  position × öppnare). Allt annat (limp före, synare efter öppningen, 3-bet före, check) ingår inte. Sparas i faktatabellen
  `spn` (nod, handling 0/1/2, delta = handens resultat mot fold som i `pre`), FACTS_VERSION 15.
* **Handgrupp:** `classify` delar in i solverns tre nivåer. Nivå 0: antal par (0–3) × färger med minst två kort (3 =
  triple, 2 = double, 1 = single). Nivå 1: parvalör för högsta paret (AA, KK, QQ, JJ–TT, 99–88 …) eller för händer utan
  par 6/5/4-korts rundown (n valörer inom n + 2 steg, ess både högt och lågt), annars 3 klädda (minst tre olika T+) eller
  osammanhängande. Nivå 2: färgfördelning (Pure 2-2, Trip 3-x, Quad 4-x / Quad+ i single suited) och för AA antal
  nötfärger, annars suited ess / ess utan färg / 2+ klädda kort (räknat utanför paren) / övrigt. Trips/quads saknas i
  solvern och utesluts. Uppslaget går till nivå 2, annars nivå 1, annars nivå 0. Kontrollerad mot analysskriptet
  2026-11-16 (0 avvikelser på 20 000 slumpade händer).
* **Solverfilen** (`solverref.normalize`): djupet räknas från nodens första rad (en nod kan börja på djup 1), rader
  utanför nivå 0–2 eller som inte summerar till 100 ± 1 hoppas över, noder med bara fold/höj får syn = 0. Alla 14 noder
  krävs. Fingeravtryck = sha256 av den normaliserade tabellen (16 tecken). Filen sparas i `<databas>_solver/` och läses
  aldrig från programmappen; inget i export, delning, djupanalys eller sessionsfiler läser den (test).
* **Jämförelse** (`compare`): frekvenser per läge (din andel mot solverns medel över dina händer); "avvikande spel" =
  syn/höj där solvern gör samma handling < 10 % i gruppen, mot "huvudlinje" ≥ 50 %; medel av delta med klustrat SE per
  spelpass, ≈ bb/100 = summa delta / urvalets händer × 100; dyraste läge × handling (≥ 20 beslut) och grupper (≥ 30);
  fold där solverns fold ≤ 30 %; trend per månad.
* **H4:** avvikande spel från 2026-11-17 (handtid). "Håller" om 95 %-intervallet ligger under noll med minst 100 beslut och
  20 pass. Fingeravtryck = sha256(text | startdatum | klassificerarversion | solverfilens fingeravtryck).
* **Visning:** sidan renderas bara när `night.gg_status()` är "nej"; "ja" och "okänd" visar att sidan är dold (RTA).
* **Begränsningar:** gruppfrekvens ≠ handfrekvens; delta mäter hela handen och är observationellt; sortering efter förlust
  överskattar (regression mot medel); bara 14 lägen; 100bb och öppning 3,5x antas (BB mot SB jämförs mot SB:s 3x-öppning
  i solvern).

---

### 5.8 Rakeback i vinstkurvan (2.76: `rbcurve.py`)
* Rakeback per hand = `rake × (ocean + leaderboard[spelform] + agent) / 100`. Spelform: PLO6 0.5/1, PLO6 1/2, PLO4 Rush &
  Cash (ttype = 1), övrigt. Standard: ocean 13,6, leaderboard 10,6 / 13 / 34,7 / 0, agent 0 (mätning 11 sep–14 nov 2026).
* Sparas i inställningsfilen (`rakeback_curve`); på/av lägger linjen "All-in EV inkl. rakeback" (kumulativ EV + rakeback)
  i vinstkurvan på Översikt och Resultat och visar EV/100 med och utan. Påverkar inga andra uträkningar.

---

### 5.9 Solvern är facit preflop (2.77: `solverfacit.py`)
* Gäller de 14 lägena i solverfilen. Nivåer per beslut: **klart fel** = solvern gör handlingen < 1 %, **tveksamt** = 1–10 %,
  ok = ≥ 10 %. Grunden: hela den mätbara förlusten mot fold ligger under 1 % (−1,58 ± 0,30 bb, n 5 777); 1–10 % ≈ 0.
* All solvervisning går genom `web.solver_gate()`: filen finns och `gg_status() == "nej"`. Annars visas inga frekvenser.
* **Topp 3** på Översikt (en enda lista): 4 h-flaggan för senaste passet, de två lägen som kostar mest i $/h senaste 7 dagarna,
  och största postflop-rådet. Allt annat ligger under "Mer".
* **$/h (2.83)** = spelade klara fel per 100 händer i fönstret × kostnad per fel i bb × händer per aktiv timme i fönstret
  (luckor > 5 min räknas som 5 min, som Timlön) × snitt-bb i $ i fönstret. Kostnad per fel = −(resultat mot fold), all-in EV
  efter rake, över hela urvalet per läge, krympt mot snittet över alla lägen: (summa + 100 × snitt) / (n + 100); negativ
  kostnad räknas som 0. Felfoldar (solvern spelar, du foldade) har okänd kostnad och ingår inte. Prio-listans tre preflop-
  rader visar samma mått för senaste 30 dagarna (2.84: 36 solverlägen, 14 grund + 22 extra): syn mot öppning utanför BB (även kallsyn av 3-bet), UTG/CO/BTN-öppning,
  höjning mot höjning (3-bet/squeeze/4-bet). SB-öppning och BB-försvar ingår inte.
* **Träningsrutan** (Solver & träning): tre lägen som kostar mest i $/h senaste 7 dagarna (minst 150 beslut; utan timtakt: flest klara fel per 100 händer),
  2–3 tumregler som testas mot filen (solvern ≤ 10 % eller ≥ 80 % och du avviker ≥ 10 pe, minst 30 beslut), 4 egna
  exempelhänder i fyrfärg, felfrekvens vecka för vecka och överkorrigeringsvarning (öppning > 3 pe under solvern).
  Framsteg mäts på veckorna efter urvalet mot de fyra veckorna före – aldrig mot urvalsveckan (regression mot medel).
* **Träna starthänder**: 🧮-lägen med solvern som facit (≥ 10 % räknas rätt, < 10 % fel); hälften av händerna ur
  blandade grupper.
* **Sessioner**: omdömet = klara fel per 100 händer. 4 h-flaggan: pass > 4 h varnas bara om passet ligger minus i
  all-in EV eller om klara fel per 100 händer efter 4 h är fler än under de första 2 h. Stoppregeln 2 h är inte längre en läcka.
* **Sessionsfilen**: solverns frekvens per preflopbeslut och klara fel per pass (Andreas tillät delning med Claude
  2026-11-18). Aldrig i export, delning eller säljversion. Återkommande misstag (`misstag.py`) markeras per pott.
* Riktlinjer som motsäger solvern döljs som råd (`guidelines.HIDDEN_277`); tre postflop-riktlinjer som bygger på styrka
  mot slumpade händer nedgraderas till "trolig – strider mot teori" (`DOWNGRADE_277`). De frysta testerna är oförändrade.

### 5.10 GG-stopp (2.77: `ggguard.py`)
GG förbjuder från 15 okt 2026 all pokermjukvara som körs samtidigt som klienten och varnar från 1 dec. Programmet och
nattkörningen vägrar starta när GG körs, och en vakt avslutar processen inom 5 s om GG startar.

### 5.11 River-bluff-test v2 och rakeback per vecka (2.77)
* `riverbluff.bluff_test_v2`: förregistrerat 2026-11-18, start 2026-11-19. Läge: river HU i position, checkat till dig,
  ≥ 75 % slår dig, effektiv stack ≥ pott. Lager S1 = rivern ändrar nöten (ny färg/stege/parat), S2 = blank (redovisas).
  Slump: river ♥/♦ = betta ¾ pott, ♠/♣ = checka. Veto: ny färg som enda ändring utan kort i färgen. Intention-to-treat.
  Avläsning vid 100 och 200 S1-lägen; stopp om hela 95 %-intervallet för fold < 51 %. v1 visas inte (ogiltigt).
* River-coachens rader visas inte när modellen inte klarar kontrollen (i praktiken alla, tills v3 prövats).
* `rbweek.py`: veckoformulär på Rakeback-sidan (GEMs, Tide Points, värde i $) mot programmets rake samma vecka.

### 5.12 Extra solverlägen (2.78: `solvergroups.extra_decisions`, faktatabell `spx`)
* 12 lägen utöver de 14: öppnaren mot 3-bet (6), BB kallsyn mot öppning + 3-bet, BB överkall (2), BB mot SB-limp,
  3-bettaren mot 4-bet (2). Hämtade 2026-11-18, nivå 0–2, i `privat/solver_extra.json` (aldrig i kodpaketet).
* Matchning: handlingsföljden preflop från första spelaren som F/C/R (storlek ignoreras) ska vara exakt solverlägets;
  kräver 6 kort, 5 spelare och ingen straddle. Heros beslut kan vara det andra i handen.
* Resultat mot fold för ett senare beslut = handens all-in EV + det hero investerat före beslutet (bb).
* Träning: kandidathänder accepteras med sannolikheten att de tagit sig till läget (solverns frekvens för handlingen före).

### 5.13 Hastighet, förberäkning och utvecklingsläge (2.79)
- **Cache per analys**: nyckeln är analysens version plus ett källkodsavtryck av funktionen och alla moduler den importerar, plus FACTS_VERSION. En ny programversion räknar bara om analyser vars kod ändrats.
- **Radcache** för pf_forward (`pfrows_*.pkl`): bara nya händer räknas.
- **Urvalscache och kö** (`precompute.py`): en färdig sida sparas på disk per urval. Nyckeln innehåller data, urval, läge, regel- och frysfiler, modellsignatur, sessionsgräns och hela källkoden. Den används bara när inga regler sparas.
  - Efter en analys räknar en pool med kärnor−1 processer på lägsta prioritet de vanligaste urvalen: alla spel, varje variant, varje nivå, bord/Rush och senaste 15 000.
  - Kön avbryts när ett jobb startar.
  - Av/på för test: `PLO_CTX_CACHE`, `PLO_PRECOMPUTE`.
- **Webben**: cache per analys i VIEWS, förvärmningstråd (Topp 3, Solver, Resultat, mallar, tre senaste passen med sessionsfil, Träna), gzip och GG-status med 2 s TTL. Solverspärren använder däremot alltid färsk GG-status.
- **Bevakning**: mappen kontrolleras var 4:e s (`watch.INTERVAL`). Väntande nya händer försöks igen. Sidan pollar var 3:e s och byter först när den nya analysen är förvärmd.
- **Fakta**: calc-förhämtning (`rb6`, `bf6`, `bfs`), memo i BoardTable, snabbare `fastev.equities`, bitmask-`straight_outs`, regex-förfilter i parsern, SQLite-index. Satserna slås ihop i satsordning, så att resultaten inte beror på antal kärnor (FACTS_VERSION 17).
- **Natt**: `fastev_delat.py` ger samma värden som `best_values` vid delat bord eller fast hand. night3:s egenskaper, anpassning och prognoser är effektiviserade med samma summeringsordning. Poolen återanvänds.
- **Utvecklingsläge** (`ggguard.dev_mode()`, inställningen `dev_mode`, route `/utvecklingslage`): programmet körs trots att GG är igång. `solver_gate` döljer ändå solverfrekvenser när GG körs (RTA). Bannern är röd från 2026-12-01, när GG förbjuder tredjepartsprogram.

### 5.14 Rättningar 2.80
Se ANDRINGAR_2.80.md: riverförsökets behörighet före river och protokoll v2.1 (fasta prefix), ofullständiga händer, EV före rake (`evr`, FACTS_VERSION 18), facing_size_pct vid aggressorns handling, nivåval i USD/h, aktiv tid i multipass, rakeback på hela kontot, unika jobbnycklar, v2-avläsning kräver full täckning.

### 5.15 Rättningar 2.81
Se ANDRINGAR_2.81.md: fasta avläsningar (seqtest.py, 20/40/80 pass), order_hash och samma täckning för "bekräftad", beat_strict/tie_frac, protokoll v2.1 (högsta stege), showdownrisk på hela händer (FACTS_VERSION 19), kvot-SE för timlön, λ per rad i v2, fryst v1-bank, uppspelning med döda kort och återbetalning, signerade cachefiler (signcache.py), CSRF utan Origin, GG-spärr i CLI.

## 6. Postflop

### 6.1 Frekvenser och riktvärden (`stats.py`, `leaks.py`, `pool.py`, `aggr.py`)
* Heros frekvenser jämförs med fasta intervall för vinnande 6-max PLO (`leaks.RULES`). Exempel: VPIP 21–32,
  3-bet 5–12, fold mot 3-bet 32–55, c-bet heads-up 45–72, check-raise på flop 6–16, fold mot river-bet 38–62,
  WTSD 25–34, W$SD 48–60.
  * Ett intervall jämförs bara när det finns minst `min` tillfällen.
  * En avvikelse är "trolig" när sannolikheten är minst `LIKELY_P = 0.95`.
* `pool.py` tar fram riktvärden från motståndare i databasen som har vunnit: minst 30 tillfällen per statistik och
  minst 8 spelare. Vinstmåttet är brusigt, eftersom det bara bygger på händer där hero satt med.
* Aggressionsmått i `aggr.py`:
  * AF = (bet + höjning) / syn;
  * AFq = (bet + höjning) / alla beslut;
  * c-bet, check-raise och stab-andel.
  * Jämförelsen bet mot check per handgrupp är **observationell** och visas bara som riktning.

### 6.2 River-modellen (`river.py`, `rivercoach.py`)
* **Idé:** GG visar alla händer vid showdown. Bettarens hand när en river-bet synas är därför ett opartiskt
  stickprov av vad poolen bettar med, eftersom synaren inte vet vad bettaren har. Detsamma gäller synarens hand, och
  OOP-handen när river checkas igenom.
* **Ranges** byggs per nivå: roll × betstorlek × linje × brädtyp × SPR. Grövre nivåer används när underlaget är
  under `MIN_SAMPLES = 120`.
* **Vinstchans:**
  * w av n händer i rangen slår inte hero (räknat med beat_frac);
  * osäkerheten är `Beta(k + 0,5, n − k + 0,5)`, med `DRAWS = 400` dragningar;
  * resultatet kalibreras mot heros faktiska utfall i händer modellen inte lärt sig av (`HeroCal`).
* **Rake på river** (`FeeModel`): medianen av rake/bb per slutpottsintervall, intervallgränser
  [0, 4, 8, 15, 30, 60, 120, ∞] bb, per nivå. Minst 20 händer per intervall krävs, och preflop-händer räknas inte.
* **Mot en bet** (syn eller fold):
  ```
  vinst_om_syn = pott + bet − rake(pott + 2·bet)
  EV(syn) = p · vinst_om_syn − (1 − p) · bet        (fold = 0)
  krav    = bet / (vinst_om_syn + bet)
  ```
* **I position efter check:**
  * EV(check) = p_sd · (pott − rake);
  * EV(bet b) räknas med poolens fold-, syn- och höjningsfrekvens mot storlek b, plus vinstchansen mot synrangen;
  * storlekarna är liten, medel, pott och överbet.
* **Domen** kräver att 2,5 %-kvantilen av vinsten (`Q_LOW`) talar för samma sak. Delar av modellen som inte klarar
  kalibreringen (`component_ok`) visas bara som "osäkert".
* Endast heads-up på river. Poolen behandlas som en helhet.

### 6.3 Syn-tabeller (`summary.py`)
* Turn- och river-syner grupperas efter betstorlek (under 40 %, 40–60 %, 60–85 %, pott+) och efter "slår dig"
  (`CALL_BINS`).
* Cellerna kräver minst `MIN_CELL = 30`. "Det viktigaste" överst i rapporten väljs av `key_points`.

### 6.4 Betstorlek och polarisering (`betsize.py`, nytt i 2.72)
* **Händelser:** första bet per gata och hand, av vem som helst.
  * Storleken räknas i andel av potten före betten, på **effektivt** belopp (högst vad den största motståndaren kan syna).
  * `who`: 0 = pool mot pool, 1 = hero bettar, 2 = poolen bettar mot hero.
  * `out`: 0 = alla foldade, 1 = syn, 2 = höjning.
* **Break-even för ren bluff med rake:**
  ```
  r  = min(0,05, tak / pott)                  tak = nivåns 99:e percentil av pot_fee (minst 50 händer, annars 3,0)
  be = b / (b + 1 − r)                        b = bet / pott
  ```
  Tabellen jämför poolens faktiska foldfrekvens per storlek med be. Celler kräver `MIN_N = 30`.
  Gränsen gäller en **ren bluff** (0 equity vid syn, checkens värde 0, ingen fortsatt action). Har checken värdet C
  krävs fold > (B + C)/(P − F + B). Poolens foldfrekvens mot alla bets är inte foldfrekvensen mot just heros bluffar.
* **Polariseringsmatris:** heros bets per handgrupp × storlek. Andelen "extrema" storlekar (under 45 % eller över
  85 %) jämförs med poolens egen fördelning. **Ingen solver:** jämförelsen görs mot poolen, inte mot GTO.

### 6.5 Postflop-riktlinjer och fokus (`guidelines.py`, `pffocus.py`)
* Riktlinjerna är strategiska råd från tidigare analyser. De visas med 💡 och räknas aldrig som regelbrott.
* `verified=True` betyder att riktningen höll i en senare oberoende omgång, inte att effekten är kausalt bevisad.
* Aktuella postflop-riktlinjer (id → innehåll):
  * pf_river_bluff: river, luft, ingen bet framför, heads-up → bluffa ca var tredje gång, pottstort.
  * pf_flop_raise_medium: flop heads-up mot en bet (inte all-in) med medelstark hand → höj i stället för att syna.
  * pf_pfa_oop_bet: preflop-höjaren agerar först på floppen med stark hand (inte nöten) → betta.
  * pf_turn_after_check: turn efter checkad flop, du agerar först → betta oftare med svaga händer och luft.
  * pf_allin_draw_call: mot all-in på flop eller turn med drag och krav högst 34 % → fortsätt syna som i dag. En
    **fold** markeras bara för granskning (🔎), utan syn-råd och utan bokförd kostnad (2.73: synerna hade 42 % faktisk
    equity mot krav 20 %, men folderna låg nära kravet).
  * pf_cbet_ip: c-betta som preflop-höjare ca 65–75 % i position och 50–55 % ur position.
  * pf_river_mw_bluff: river multiway med luft → bluffa oftare, ¾ pott.
  * pf_river_nuts_ip: river i position med nöten eller nästan (högst 10 % slår dig) efter check → betta alltid.
  * pf_river_bigbet_call: mot en river-bet på minst ⅔ pott → folda svaga kåkar, färg på parat bord och två par på
    oparat bord.
  * set_cr: set på floppen, du checkade och möter en bet → check-raisa mellanset och toppset.
  * cbet_size: c-bet 75 % med par + drag och på höga bord, annars 60 %.
  * Ytterligare råd utan `verified`: turn-barrel, värdebet på river, river-syn utan möjlig färg, check-raise på parat
    bord, drag mot höjning.
* Preflop-riktlinjer:
  * med `verified`: låga par och dubbelpar utan nöt-egenskaper → folda; AA mot en öppning i position → 3-betta;
  * utan `verified`: AA med suited ess → 4-betta; HJ med suited ess utan höga kort → folda; folda aldrig de bästa
    händerna när det är foldat till dig; BB med 0 nöt-egenskaper heads-up.
* **Hypoteser (🧪):** rundown-3-bets utan suited ess, och lägre par mot 4-bet.
* **Fokuskostnad i `pffocus`** = (mål − din frekvens) × hur ofta situationen uppstår × vinst per ändrat beslut.
  Vinsten per beslut (EFF) är satt försiktigt till ca ⅓ av den uppmätta effekten. Det är en uppskattning från äldre
  händer – posten har nivån "trolig" och mål och kostnadsmål är samma (35 %) från 2.73.

---

## 7. Regler, kostnad och uppföljning

### 7.1 Regler (`practice.py`, `RULES_VERSION = 10`)
* Regler byggs bara av bekräftade eller troliga resultat:
  * "för brett" i range-gränser;
  * "folda" i öppningsguiden;
  * rundowns som förlorar klart;
  * 3-bet-regler (typen `action`, där ett brott är en viss handling och inte att handen spelades).
* Reglerna tas fram på hela databasen och sparas i en fil, så att uppföljningen fungerar även när bara de senaste
  händerna analyseras.

### 7.2 Försiktig kostnad per brott (`practice.careful_costs`)
1. Utgångsvärde: den **minst negativa** av två siffror, regelns kostnad i den halva som inte valde ut regeln och
   snittet för alla brott i urvalet.
2. **Krympning mot noll:** faktor = max(0, 1 − 1/z²), där z = snitt / klusterrobust standardfel.
   z = −1 ger 0, z = −2 ger 75 %, z = −3 ger 89 %.
3. Regler av typen `action` behåller sin redan försiktiga kostnad.

### 7.3 Validering
* **Holdout (`holdout.py`):**
  * De äldsta ⅔ av händerna används för att hitta regler; de nyaste ⅓ för att mäta dem.
  * Kräver minst `MIN_TOTAL = 90 000` händer och minst `MIN_NEW = 100` brott.
  * Utfall: "håller" (identisk fryst regel, minst 20 pass, korrigerat 95 %-intervall under noll och bootstrap),
    "osäkert", "håller inte" (regeln tas bort), "inte oberoende" eller "för få".
  * Svaghet: holdout-händerna ligger i samma databas som reglerna formades på, och analysvalen har gjorts med
    hela databasen synlig. Därför kom framåttestet till.
* **Framåttest (`forward.py`, sedan 2.71):**
  * Regler hittas en gång på händer före 2026-11-13 (minst 20 000), fryses och mäts sedan bara på nya händer.
  * Frysgränsen räknas i **handtid** (`facts.ts_of`), samma på alla datorer (2.73; tidigare datorns lokala tid).
  * De frysta definitionerna får ett fingeravtryck (`forward.rules_hash`, sha256 av definitionerna utan kostnader och
    texter). Det visas i översikten, morgonrapporten och nattkvittot, och nattkörningen varnar om det ändras.
  * Kriterierna är samma som för holdout. Det är **det enda test som kan ge statusen "bekräftad"**. Jämförelser mellan
    två handlingar märks "inte oberoende".
* **Framåttest av postflop-riktlinjer (`pfforward.py`):**
  * 11 riktlinjer är omskrivna till situation → rekommenderad handling. Definitionerna är låsta 2026-11-14
    (`SPECS_FROZEN_HASH`); ändras källtexten visas en varning.
  * Testet mäter efterlevnaden och skillnaden i `from_here_pot` mellan att följa och inte följa.
  * Standardfelen är klustrade, med Bonferroni över riktlinjerna, `MIN_ARM = 30` (räknat på beslut med känt utfall,
    2.73) och `MIN_CLUSTERS = 20`.
  * Jämförelsen är observationell, så den kan som mest ge "håller framåt" och aldrig "bekräftad".
* **Nya hypoteser (`hypotheses.py`, frysta 2026-11-15, fingeravtryck `HYP_HASH = e4e93fbb9face71d`):** mäts bara på
  händer efter 2026-11-15 (handtid), räknas aldrig som regelbrott och rör inte de frysta reglerna.
  H1 BTN-öppningar sämre än topp 30 % (frysta handvikter, percentil mot slumpade händer) mot fold; H2 syn i SB/BB mot
  en öppning med 0 nöt-egenskaper mot fold; H3 3-bet med rundown utan suited ess mot fold (syn med samma händer visas
  bara beskrivande). Minst 100 händer och 20 pass, Bonferroni över tre, bootstrap.
* **Randomiserat river-bluff-test (`riverbluff.py`, start 2026-11-14 i handtid):**
  * Situation: river, heads-up, i position, det checkas till dig, du har luft.
  * Spelaren slumpar själv vid bordet: jämn sekund på sekundvisaren = betta pott, udda = checka.
  * Armarna är **pott-bet** (effektiv storlek ≥ 85 % av potten, faktakolumnen `esz`) och **check**. Mindre bets räknas
    som protokollavvikelser.
  * Fold-andelen räknas bara på pott-bets med känt svar (Wilson-intervall). Utfallet är pott-bet minus check i andel
    av potten, klustrat per pass.
  * Avläsning bara vid **300 och 500 lägen**; däremellan visas inga fold- eller utfallssiffror.
  * Grönt slutbesked kräver: ≥ 60 lägen per arm med känt utfall, ≥ 60 pott-bets med känt svar, bet-andel 35–65 %,
    högst 20 % för små bets, ≥ 20 pass och en skattad skillnad. Ett protokollbrott kan inte skrivas över.
  * **Stopp** om fold-andelen är under 62 % vid en avläsning, eller när som helst om hela 95 %-intervallet ligger
    under 51 % (ren break-even med rake – säkerhetsstopp).
  * Ett grönt besked är underlag för en hypotes, inte en bekräftad riktlinje.

### 7.4 Sessioner, fokus och utveckling
* **Sessioner (`sessions.py`):**
  * Per pass räknas tillfällen, brott, regelföljning och väntad kostnad (brott × försiktig kostnad).
  * Vila före passet: `gap_h`, `rested` (minst `REST_H = 8` timmar sedan förra passet), `morning` (start kl. 06–12).
* **Fokus (`focus.py`):**
  * Kostnad nu = brott i de senaste `RECENT = 20 000` händerna × kostnad per brott, i bb/100.
  * Varje hand räknas bara mot den mest specifika regeln.
  * En läcka är under kontroll när de senaste 2 veckorna har minst 100 tillfällen och högst 5 % brott.
* **Block (`blocks.py`):**
  * Händerna delas i block om 5 000.
  * Varningar jämför de senaste 10 000 händerna med allt före, med kravet z > 3.
* **Trötthet (`fatigue.py`):**
  * Mäts per timme i passet, som VPIP-avvikelse i samma läge (position, antal spelare, nivå, bordstyp) och
    regelbrott per 100 händer. Felmarginal per pass.
  * **Stoppregel** (förregistrerad):
    * sluta efter **2 timmar**;
    * eller vid **−500 bb** i passet;
    * eller ta paus efter en förlust på **175 bb** i en hand.
* **Tid på dygnet (`timeofday.py`):** fyra block. "Tydligt" kräver z > 2,5 (Bonferroni över 4 block).
* **Nivåer (`stakecheck.py`):** den bästa nivån (minst 10 000 händer) jämförs med de andra. Den nedre gränsen för
  skillnaden används som kostnad.
* **Timlön (`hourly.py`):**
  * Speltid = summan av luckorna mellan händer i passet, där varje lucka högst räknas som 300 s.
  * Den sista handen i passet får medianluckan.
  * Timlön = resultat / speltid, med intervall från variationen mellan passen. Vid flera bord blir det fler händer
    per timme.
* **Pottstorlek (`potsize.py`):** resultat per slutpott i steg om 10 bb, och vägen in i potten.

---

## 8. Nattberäkningar

### 8.1 v1 (`night.py`)
* Per postflop-beslut räknas tre slags outs:
  * `nut_outs`: kort som ger nöten utan att para bordet;
  * `nut2_outs`: kort som ger näst bästa hand;
  * `pair_outs`: kort som parar bordet.
* `eq_pool` är equity mot **visade** händer i samma situation (bank med högst 60 000 händer, 40 motståndare ×
  50 utfall).
* Visade händer är starkare än den verkliga rangen på samma gata (bluffar som får fold visas aldrig). Det gör inte
  eq_pool till en försiktig skattning i alla lägen: när hero **möter all-in med drag** låg eq_pool ca 9 procentenheter
  **över** faktisk all-in-equity (51,7 % mot 42,3 %, 820 händer, r = 0,49; kontroll 2026-11-14). Den som går all-in har
  en starkare range än gatans visade händer i snitt.

### 8.2 v2 (`night2.py`, modellversion 3 från 2.73) – status: **HYPOTES** tills acceptanstestet är klart
1. **Linjefrekvenser:**
   * För varje motståndarbeslut efter floppen, i händer före frysdatumet, räknas frekvenserna per
     gata × vad han mötte (ingen bet / storlek 40, 60, 85, 110 %) × IP/OOP × nivå.
   * Läget slås ihop när det har färre än `MIN_LINE = 300` beslut: först utan nivå, sedan utan position, sedan utan
     storlek.
2. **Percentilband** (`band`), där 0 är starkast:
   * utan bet framför: bet → [0, f_bet] och check → [f_bet, 1], med f_bet begränsad till 0,02–0,98;
   * mot bet: höjning → [0, f_r] och syn → [f_r, f_r + f_c], med f_r ≤ 0,9.
   * Fold avslutar handen.
3. **Kedjning** (`_survivors`):
   * 6 000 slumpade motståndarhänder dras ur kortleken (kända kort borttagna).
   * För varje tidigare beslut rangordnas de händer som är kvar efter styrka på det bordet, och de utanför bandet
     filtreras bort.
   * Aggressiva band blandas med bluffar: en andel λ av händerna behålls i stället från botten av fördelningen, med
     samma bredd som bandet.
   * Preflop antas slumpade händer (förenkling).
4. **λ-ankaret** (`fit_lambda`):
   * För alla all-ins *före* frysdatumet förutsägs heros equity med varje λ i {0, 0,1, 0,2, 0,3, 0,4, 0,5} (2.73;
     i 2.72 slutade rutnätet vid 0,3, som också blev valt – ett randvärde). λ är en modellparameter, inte poolens
     uppmätta bluffandel.
   * Det λ som ger lägst medelkvadratfel mot den faktiska all-in-equityn väljs, och det krävs minst 50 all-ins per λ.
   * Värdet låses därefter (`night2_meta.lam`). Utan värde används 0,2.
5. **Konvergensstyrd Monte Carlo** (`eq_range`):
   * Satser om `BATCH = 3000` körs tills medelfelet är högst `SE_TARGET = 0,005`, med taket `MAX_SAMPLES = 24 000`.
   * Medelfelet sparas per beslut.
   * Om färre än `MIN_SURV = 40` händer överlever blir rangen "tom" och inget värde räknas.
6. **Turjustering per hand (förenklad AIVAT):**
   * Gäller heads-up-potter, före all-in-låsning.
   * Vid turn- och river-kortet: `luck += pott × (equity efter kortet − equity före)`, med samma motståndarhänder.
   * Det justerade resultatet = all-in EV − luck.
7. **Acceptanstest** (`acceptance`, plan `2.73/2026-11-14`), bara på händer efter frysdatumet. Planen ersätter 2.72:s
   efter den externa granskningen; två pass efter frysdatum hade då setts.
   * **Avläsning** bara när 20, 40 och 80 spelpass finns efter frysdatumet (de första K passen används). Före 20 pass
     visas inga siffror. Kritiskt värde z ≈ 2,13 (ensidigt 5 % delat på tre avläsningar).
   * **Kalibrering:** lägre MSE än v1 (diff − z·se > 0) **och** absolut avvikelse prognos − faktisk all-in-equity
     visad inom ±5 pe (|bias| + z·se < 0,05). Minst 100 all-ins och 20 kluster.
   * **Fold-prognos:** lägre Brier än poolens totala fold-andel **och** prognos − faktisk inom ±10 pe. Minst 100
     river-bets. Delen prövar linjefrekvenserna, inte hela rangemodellen.
   * **Tur:** ekvivalenstest – medel visat inom ±0,05 bb/hand – **och** minst 20 % lägre varians än all-in EV. Minst
     2 000 händer och 20 kluster. (2 pass gav ca 10 % lägre varians; då tillför justeringen lite.)
   * En del är underkänd när intervallet ligger helt på fel sida (eller variansvinsten är under 10 %).
   * Status: "väntar", "godkänd", "underkänd" eller "inte avgjord" (efter 80 pass). Första avgörandet sparas
     (`acceptance_final`) och är slutligt för modellversionen. Först vid "godkänd" visas det turjusterade resultatet,
     och då som experimentellt mått bredvid all-in EV.
8. Körning: flera processer (spawn) med låg prioritet. Den kan pausas och fortsätter där den slutade.

### 8.3 Schemalagd nattkörning (`nightly.py`)
1. GG-vakt (processnamnen ggnet, ggpoker, ggpcom, plus ny handhistorik de senaste 10 minuterna). Går processlistan
   inte att läsa är statusen "okänd" och körningen startar inte (2.73).
2. SQLite online-backup; de 3 senaste sparas.
3. Inläsning av nya händer.
4. night2 körs till stopptiden (standard 03:30 → 07:00).
5. Kvitto (JSON: version, tider, databasens fingeravtryck, vad som gjordes) och en morgonrapport i markdown.

Schemaläggning: `schtasks` via en .bat-fil på Windows, launchd-plist (`se.leakfinder.natt`) på Mac.

**Egen kö (2.75, `jobs.JobManager.lanes`):** nattberäkningen som startas från webben körs i kön "natt" med en egen
SQLite-anslutning (WAL, `timeout=30`). Huvudkön (analys, visning, export, bevakning) väntar inte på den. Natten håller
huvudköns lås bara under backup, inläsning och fakta (`run_night(prep_lock=…)`), de steg som skriver i samma filer.

---

### 8.4 Skuggmodell v3 (`night3.py`, 2.77.6) – status: förregistrerad, ger inga råd
* Kandidater: 200 slumpade 6-kortshänder (bord och dina kort borttagna). Egenskaper per gata: percentil bland kandidaterna,
  percentil², chans att bli topp 15 % på nästa kort, nöt (< 3 %).
* Linjemodell: motståndarens handlingar som val mellan tre (check/liten/stor bet, eller fold/syn/höj), logistisk per
  gata × bet framför × position × föregående aggressor × storlek han möter (72 grupper × 2 × 5 parametrar, L2 0,05).
* Preflop: log(solverfrekvens för hans första preflophandling) × β; β skattas (β < 1 = poolen bredare än solvern).
* Anpassning: betingad likelihood för visade händer givet linjen (sann hand + 199 slumpade). Kalibrering: Platt på dina
  river-beslut, korsanpassad i två halvor per hand-id.
* Utveckling 2026-11-18 (träning t.o.m. 5 nov, test 6–12 nov): log-likelihood −5,19 mot slump −5,70; solverprior β ≈ 0,47.
  Korsanpassad kalibrering före 6 nov: prognos 46,4 % mot faktiskt 45,5 %. Test 6–12 nov: check bakom 45 % mot 39 %
  (v2 i agentens mätning 67 mot 42), syn 43 mot 36 (v2 59 mot 42). Rangordningen är bra; nivån överskattar i testveckan.
* Förregistrerat test (`acceptance`): se modulens docstring. Före 20 pass visas inga siffror.

## 9. Utdata

* **Rapport och webb:** sidorna översikt, preflop, postflop, river, betstorlek, sessioner, fokus/träning, timlön,
  export och natt. Den största läckan visas alltid överst.
* **Analysfil (JSON, `export.py`):** sammanställningar plus upp till 4 000 anonymiserade exempelhänder.
* **Djupexport (CSV-zip, `dataexport.py`):** hands, preflop-beslut, postflop-beslut, turn-syner, river-beslut,
  sessioner, regler, nattberäkning v1/v2 och acceptans, plus filen METOD. Inga spelarnamn ingår, bara GG:s hand-id.
  Varje del är högst 20 MB.
* **Sessionsfil (markdown):** de 10 största potterna med fakta per beslut. Kortfärger: ♠️ ♥️ 🔷 ☘️.
* **Handexport:** originaltexten för DriveHUD och HoldemManager. Saknas originalet återskapas handen i GG-format.

---

## 10. Tester

* `tests/`: 180 tester (`test_core`, `test_v270`, `test_v272`, `test_v273`, `test_v2731`, `test_v274`, `test_v275`). `test_v273` innehåller den externa
  granskarens motexempel som negativa kontroller. Körs med `python -m pytest tests`.
* Testerna täcker tolkning, all-in EV, statistikfunktionerna, regler, nattberäkning v2 (i samma process), jobbhantering
  och webbsidorna.
* **Inte testat:** körning på spelarens riktiga databas, och schemaläggningen på en riktig Mac eller Windows-dator.

---

## 11. Kända begränsningar och antaganden

1. **Urvalsbias i jämförelser mellan handlingar.** Spelaren väljer själv när han synar, höjer eller bettar.
   Jämförelser bet mot check och syn mot 3-bet är därför observationella. Bara jämförelser mot fold är exakta.
2. **Bevismotorn kan inte se vinster av att spela fler händer**, bara förluster mot fold.
3. **Visade händer är starkare än rangen** (påverkar v1 och delar av river-modellen). River-modellen motiverar sitt
   urval med att synaren inte vet bettarens hand; kontrollen av det sker genom kalibrering.
4. **night2 antar slumpade händer preflop** och rangordnar efter nuvarande handstyrka. Drag behandlas därför som
   svaga i banden, och λ är en enda global parameter.
5. **Turjusteringen** täcker bara heads-up före all-in och ignorerar framtida satsningar. Den är inte en fullständig
   AIVAT.
6. **Rake:** schablonen 5 % med ett tak som skattas ur datan (99:e percentilen). River-modellen använder medianen per
   intervall. GG:s jackpot- och avgiftsfördelning skrivs som rake.
7. **Poolen behandlas som en helhet.** Ingen anpassning till enskilda motståndare (avsiktligt).
8. **Kluster = spelpass med 30 minuters paus.** Pass som ligger tätt kan vara beroende av varandra, så standardfelen
   kan vara något för små.
9. **Många tester totalt.** Korrektion görs inom varje familj (BH eller Bonferroni), inte över hela programmet.
   Framåttestet är skyddet mot detta.
10. **Riktvärden i `leaks.RULES`** är breda erfarenhetsvärden, inte uppmätta för PLO6 på GG.

---

## 12. Granskningar hittills

* 2.69 → extern agent (2.70, LF-01–LF-10).
* 2.72.2 → extern agent 2026-11-14: `claude/granskning-extern-2.72.2-slutrapport-2026-11-14.md` i projektet, med
  svar på tolv metodfrågor. Jämförelse och egen kontroll: `claude/jamforelse-extern-slutrapport-2026-11-14.md` och
  `claude/granskning-egen-2026-11-14.md`.

## 13. Vad granskningen av 2.72.2 ledde till i 2.73

| Fynd | Åtgärd i 2.73 |
|---|---|
| Zip med fil över 200 MB gav tyst 0 händer | Strömmande läsning; avvisade filer visas med skäl |
| River-bluff-testet kunde bli "klart" på små bets utan checkar | Effektiv storlek, två armar, protokollkrav, fasta avläsningar |
| "Bekräftad" kunde sättas utanför framåttestet | En funktion sätter nivån; pffocus är "trolig" |
| #5 gav syn-råd på en fold utan equitykontroll | Granskningsmarkering, ingen kostnad |
| Acceptanstestet för v2 godkände felkalibrering, bias och ökad varians | Ny plan (avsnitt 8.2) |
| Frysgräns i datorns tidszon | Handtid; fingeravtryck av frysta definitioner |
| Minimiantal i pfforward räknat före bortfall | Räknas på beslut med känt utfall |
| GG-kontroll som misslyckas räknades som "körs inte" | "Okänd" blockerar nattkörningen |
| `uncalled_return_bb` är inte faktisk återbetalning | Nya kolumner `unmatched_bb`, `hand_returned_bb`, `hand_returned_to_hero` |
| River: bet värderas som bet/fold | Utskrivet i coachen och metodfilen |
| Svansvakten syns inte | Domen "osäkert (svansvakt)" |

**Kvar som kända begränsningar (inte åtgärdade):**

1. River-modellen saknar gren för syn eller återhöjning mot check-raise.
2. `careful_costs` är en tumregel (max(0, 1 − 1/z²)), inte en hierarkisk modell; den styr bara ordningen i fokuslistan.
3. Bootstrapen i `ranges` håller de lärda poängen fasta – osäkerheten i viktlärande och gränsval ingår inte.
4. `proven_leaks` tar bort händer från tidigare gators grupper efter bekräftelser i halva B. Riktningen är försiktig
   (färre bekräftelser), men gruppen är inte bestämd helt oberoende av B, och kostnaden mäts i samma halva.
5. Upptäcktssteget (Johnson) ignorerar klustring; bekräftelsen gör det inte.
6. Rake per sidopott fördelas proportionellt (`fee_rate`); ingen verifierad avgiftstabell per pottlager.
7. All-in EV kräver kända kort för alla kvarvarande spelare – täckningen redovisas inte per nivå och gata.
8. Speltiden är en uppskattning från handstarter (tak 300 s); intervallet för timlönen håller tiden fast.
9. Rangemodellen i v2 använder hårda percentilband på nuvarande handstyrka; drag, blockers och preflop-urval saknas.
10. Webbsidorna är inte spärrade när GG körs (spelarens val).
