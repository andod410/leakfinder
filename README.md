# PLO-läckfinnare 2.86

> **Granskning:** `PROGRAMBESKRIVNING.md` beskriver alla delar av programmet och exakt hur varje uträkning görs.

## Version 2.89.1 – automatisk uppdatering högst en gång per minut

- Programmet och alla sidor uppdateras automatiskt högst en gång per minut. Se ANDRINGAR_2.89.1.md.

## Version 2.89 – urvalet håller, alla grafer i Dela som bild, valbara rutor

- **Urvalet gäller alltid:** nivå, datum och senaste N kombineras. Sidan tappar aldrig ett ändrat urval när nya händer kommer in, och urvalsraden visar exakt vad som visas.
- **Dela som bild:** välj vilka linjer som ska synas (samma som på Översikt, även med rakeback), och rutor med eller utan rakeback.
- **Nya rutor:** all-in EV och resultat inkl. rakeback i pengar, och EV-timlön inkl. rakeback. **⚙ Anpassa rutor** med snabbvalen Enkel och Allt.

## Version 2.88 – avbryt-knapp, verklig winrate och rättvisa vinstkurvor

- **⏹ Avbryt** på alla tunga jobb (i jobbraden och på förloppssidan).
- **Verklig winrate** (all-in EV inkl. rakeback, bb/100 med intervall) och **Rakeback bb/100** som egna nyckeltal överst – även per nivå, i sessionerna och i sessionsfilen.
- **Vinstkurvorna jämför lika med lika:** ny linje "Faktiskt resultat inkl. rakeback", en knapp för rakeback i alla linjer och raden "Tur i all-ins" under varje graf.

## Version 2.87.3 – export när GG körs

- Zip-filer kan alltid hämtas; när GG körs får du en fråga och väljer "Ladda ner ändå".

## Version 2.87.2 – zip för valda sessioner

- "Graf och resultat" för flera sessioner har en egen zip med bara de sessionernas händer. Toppknappen heter "Djupanalys hela urvalet (zip)".

## Version 2.87.1 – starta trots att GG körs

- Körs GG vid start frågar kommandofönstret om du vill starta ändå (skriv j). Programmet stängs inte när GG startas. Solver, Träna och Översikt är fortfarande dolda medan GG körs.

## Version 2.87 – rättad all-in EV och granskningen av 2.86

- **All-in EV räknas nu rätt i alla lägen.** Det gäller potter som låsts av en tidig kort all-in och sedan följs av en fold, fold först på river efter din all-in, och döda blinds. Preflop räknas exakt. Första analysen räknar om hela databasen, vilket tar cirka 20 minuter extra en gång. Kontrollerat mot en oberoende granskning: 325 + 73 händer stämmer inom en halv cent.
- GG-spärrar, utvecklingsläget högst 24 h, en enda tidsregel (2 h / −500 bb / 15 min), rättade regeltexter med AA-regeln och BTN 45–49 %, stoppregeln per pass, time bank-händer tolkas, och säkrare inställningar och nattkörning. Se ANDRINGAR_2.87.md.

## Version 2.86 – 56 solverlägen, rakeback i sessionsgrafen, paus 15 min
Tolv nya solverlägen (56 totalt). Sessionsgraferna och sessionsfilen visar all-in EV inkl. rakeback. Pausen efter en förlorad pott över 175 bb är nu 15 min. Se ANDRINGAR_2.86.md.

## Version 2.82 – 5 nya solverlägen

Öppning + synare i SB/BB och kall 4-bet på BTN. Se `ANDRINGAR_2.82.md`.

## Version 2.81 – resten av granskningen

Fasta avläsningar i framåttest och hypoteser, "slår dig" uppdelat i bättre/delar, rätt uppspelning, λ per hand, signerade cachefiler och säkrare formulär. Se `ANDRINGAR_2.81.md`. Fakta byggs om en gång.

## Version 2.80 – rättningar efter oberoende granskning

Riverförsöket räknar folds rätt, ofärdiga händer låser inte längre fel resultat, EV före rake, nivåval i $/h, samma timlön överallt och unika exportjobb. Se `ANDRINGAR_2.80.md`. Fakta byggs om en gång.

## Version 2.79 – snabbare överallt

Sidor öppnas på hundradelar av en sekund. Vanliga urval räknas färdigt i bakgrunden, nya händer läses in automatiskt och sidan uppdaterar sig själv. Nytt utvecklingsläge låter programmet köras medan GG är igång (solvern är ändå dold). Se `ANDRINGAR_2.79.md`. Fakta byggs om en gång vid första analysen.

## Version 2.78 – 12 nya solverlägen

Mot 3-bet, kallsyn, överkall, limp och 4-bet ingår nu i solverns facit. Se `ANDRINGAR_2.78.md`. Fakta byggs om vid första analysen.

## Version 2.77 – solvern som facit, GG-stopp, Topp 3

Stäng GG innan du startar Leakfinder (programmet vägrar annars starta och stänger sig om GG startas). Se `ANDRINGAR_2.77.md`.
Ingen ny analys krävs – faktatabellerna är oförändrade.

## Version 2.75 – reglage med winrate, positionsläckor, egen nattkö
Träna öppningar med ett reglage (topp X %) som är facit och visar förväntad winrate för varje %, ny flik Positionsläckor,
nattberäkningen blockerar inte längre analys/export, tre nya framåthypoteser frysta 2026-11-15, och rundown förklaras i texterna.
Se `historik/ANDRINGAR_2.75.md`. Kör en full analys av hela databasen efter installationen.

## Version 2.74 – UTG i stället för HJ
Positionen efter big blind heter UTG överallt (5-max: UTG, CO, BTN, SB, BB). Internt och i de frysta reglerna är koden
oförändrad. Se `historik/ANDRINGAR_2.74.md`.

## Version 2.73.2 – Översikten börjar med resultatet
Nyckeltal, vinstkurva och Det viktigaste ligger överst på Översikt; prio-listan kommer efter.

## Version 2.73.1 – "Visa urvalet"
I urvalsraden byter **Visa urvalet** bara urvalet (resultat, EV-graf, dollar, sessioner, timlön) utan att köra om analysen;
**🔬 Analysera urvalet** kör analysen. Se `historik/ANDRINGAR_2.73.md`.

## Version 2.73 – rättningar efter extern granskning
Stora zip-filer läses in, river-bluff-testet kräver pott-bets och checkar och läses av vid 300/500 lägen, "bekräftad" sätts bara av
framåttestet, #5 är en granskningsmarkering, nytt acceptanstest för nattberäkning v2 (λ 0–0,5), frysdatum i handtid med
fingeravtryck, GG-vakt som blockerar vid okänd status, tydligare pengafält i exporten. Se `historik/ANDRINGAR_2.73.md`.

## Version 2.72 – nattberäkning v2, betstorlek, river-bluff-test och schemalagd nattkörning
Nattberäkning v2 (range från poolens frekvenser per linje, konvergensstyrd Monte Carlo, turjusterat EV – används bara om
den klarar acceptanstestet på händer efter 13 nov), ny sida Betstorlek (polarisering och poolens svar per storlek med rake),
randomiserat river-bluff-test, framåttest av postflop-riktlinjerna, ny stoppregel (2 h / −500 bb / paus efter förlust
> 175 bb), schemalagd nattkörning med backup, kvitto och morgonrapport, samt fyrfärg och vila/morgon i sessionerna.
Se `historik/ANDRINGAR_2.72.md`.

## Version 2.71 – mätning, timlön och sammanslagning
Bygger på den externt granskade 2.70 (rättningar LF-01–LF-10) plus Claudes 2.70 (🌙 nattberäkning, prio-lista,
set-check-raise/c-bet-riktlinjer, brädtyp i exporten, exportera hela databasen). Se `historik/ANDRINGAR_2.71.md`.
Äldre ändringsrapporter ligger i mappen `historik/`.


## Version 2.70 – rättningar efter granskning

Den här versionen bygger på 2.69. Se `historik/ANDRINGAR_2.70.md` för rättningar, tester och kända begränsningar.

- Databasens originalhänder behålls. Första starten räknar om fakta och analyser eftersom EV, blockerhantering och beslutsfält har ändrats. Det kan ta några minuter.
- Gamla snapshots och regler återanvänds inte som bekräftade resultat. Kör en full analys av PLO6 innan du följer upp eller tränar regler.
- River-coachen och fasta historiska riktlinjer visar hypoteser. Deras förslag är inte bevisat optimala pokerbeslut.
- Fasta 9/12/13-outsregler för jam/syn/fold har dragits tillbaka. Exporten ger i stället unika träffkort och tydligt definierade beslutstidsfält.
- Rakebackkalkylatorn tar underlag från en enskild nivå; blandade nivåer visar sitt faktiska dollarresultat separat. Äldre kalkylatorvärden återläses inte automatiskt.
- Testa: `python tools/run_tests.py` (inga extra testberoenden). Med pytest installerat fungerar även `python -m pytest -q`.


Analyserar din handhistorik i PLO6 (även PLO4/PLO5), sammanställer resultat och identifierar möjliga läckor med tydliga evidensnivåer, med exempelhänder ur ditt eget spel. Allt körs lokalt på din dator.

## Starta (Mac och Windows)

1. **Windows:** inget behöver installeras i förväg – startfilen installerar Python själv om det saknas.
   **Mac:** installera **Python 3.10 eller nyare** från https://www.python.org/downloads/ (en gång).
2. Packa upp zip-filen.
3. Dubbelklicka på:
   - **Mac:** `Starta (Mac).command`. Första gången kan macOS säga att filen kommer från en okänd utvecklare. Högerklicka då på filen, välj **Öppna** och sedan **Öppna** igen.
   - **Windows:** `Starta (Windows).bat`. Om SmartScreen varnar, klicka på **Mer info** och sedan **Kör ändå**.
4. Webbläsaren öppnas på http://localhost:8765. Första starten tar någon minut eftersom programmet installerar det det behöver.

Låt terminalfönstret vara öppet medan du använder programmet. Stäng det när du är klar.

## Analysera hela din DriveHUD 3-databas

1. I DriveHUD 3: gå till **Cash**-vyn, högerklicka i rapporttabellen och välj **Export All Hands**.
2. Välj gärna **Omaha** under spelformer (eller exportera allt, programmet hoppar själv över andra spel). Klicka på **Export** och välj en **tom mapp**, t.ex. `Dokument/PLO-export`.
3. DriveHUD skriver filer som heter `dh_exported_file_0`, `dh_exported_file_1` och så vidare, med upp till 1 000 händer per fil. Programmet läser dem trots att de saknar filändelse.
4. I läckfinnaren: gå till **Import & databas**, klistra in sökvägen till mappen och klicka på **Läs in och analysera**.

Händerna sparas i en databas (`~/.plo_leak_cache`). Nästa gång läses bara nya händer in, och fakta räknas bara för dem.

Programmet analyserar automatiskt den Omaha-variant du spelat mest (PLO6). Blandade varianter ger missvisande statistik. Ditt spelarnamn hittas automatiskt. Om du spelat på flera konton eller sajter kan du ange namnet själv.

## Kommandorad (valfritt)

```bash
python -m plo_leak ~/Dokument/PLO-export --out rapport.html
python -m plo_leak ~/Dokument/PLO-export --hero MittNamn --game PLO6
```

## Version 2.66 – zip med en sessions händer

- På **Sessioner**: knappen **📦 Zip med händerna** (per session, och för 1–5 kryssade sessioner). Zip-filen har samma tabeller som djupanalysen men bara för de valda sessionerna, plus sessionsfilen (`session.md`) och alla handhistoriker (`handhistorik.txt`). Ladda upp den i chatten för följdfrågor om just de händerna.
- Sessionsfilen är som förut (sammanfattning + de 10 största potterna) – liten och lätt att läsa.

## Version 2.65 – knappen "⚡ Nya händer"

- Ny knapp **⚡ Nya händer** i urvalsraden och **⚡ Läs in nya händer** överst på Sessioner: läser in nya händer från den bevakade mappen direkt och gör en snabb uppdatering (resultat, sessioner, grafer, timlön). Läckor och regler behålls från senaste fulla analysen.
- **Uppdatera** gör som förut en full analys.
- Första gången efter uppdateringen till 2.64/2.65 görs en full analys (då sparas grunden för de snabba uppdateringarna).

## Version 2.64 – snabb uppdatering med nya händer

- När nya händer läses in (rutan "N nya händer" eller "Uppdatera automatiskt") görs en **snabb uppdatering**: resultat, winrate, nettovinst, sessioner, grafer och timlön räknas om med alla händer, men läckor, regler och modeller återanvänds från den senaste fulla analysen. Det går mycket fortare.
- Översikt visar "⚡ Snabbt uppdaterad" med datum för den fulla analysen och antal nya händer sedan dess.
- **Full analys:** tryck "Uppdatera analysen" i urvalet. Görs också automatiskt efter 10 000 nya händer sedan den senaste fulla analysen.

## Version 2.63 – postflop-läckorna omprövade vid lika handstyrka (omgång 2)

Fyra nya agenter och två granskare analyserade djupexporten från 2.62, nu med handstyrka på alla gator, all-in-flaggor och resultat per pott. Postflop-riktlinjerna är ersatta med det som höll:

**Bekräftade** (räknas i rutan "Om du tätar alla bekräftade läckor"):
1. River heads-up, luft, ingen bet framför: bluffa ca var tredje gång (35–40 %), pottstort – ~1,2 bb/100 (fokuspunkten har nu målet minst 35 %)
2. Flop heads-up, möter bet (inte all-in) med medelstark hand (10–35 % slår dig): höj i stället för att syna – ~0,7
3. Preflop-höjare ur position med stark hand (3–25 % slår dig): betta floppen – ~0,7
4. Turn efter checkad flop: betta oftare med svaga händer och luft – ~0,6
5. Drag mot all-in på flop/turn: syna när kravet är högst 34 % – ~0,5
6. C-bet i position oftare, 60–85 % av potten – ~0,45
7. River multiway med luft: bluffa oftare, ¾–pott – ~0,25
8. River i position med nöten efter check: betta alltid – ~0,2

**Troliga:** turn-barrel med svag hand/drag, river-value när 10–20 % slår dig, syna river-bet utan möjlig färg.

**Borttagna (höll inte vid lika handstyrka):** turn-barrel med färdig färg, höj triss mot flop-bet, c-bet ⅓ pott, turn-bluff ½ pott.

Sessionsfilen markerar de nya lägena.

## Version 2.62 – rikare underlag till Claude

**Djupanalysen (zip):**
- `postflop.csv` har fem nya kolumner: `facing_allin` (betten du möter är all-in – du kan bara syna eller folda), `hero_allin`, `eff_stack_bb` (effektiv stack just före beslutet), `made_frac` (handstyrka just nu på flop, turn och river: andel slumpade händer som slår dig – finare än handkategorin) och `from_here_pot` (resultatet från beslutet delat med potten, för att jämföra potter av olika storlek).
- `hands.csv` har `hands_per_hour_now` (dina händer per timme runt handen – hur många bord du spelade).
- LÄS_MIG beskriver kolumnerna. Första djupexporten tar längre tid (handstyrkan på flop och turn räknas en gång och sparas).

**Sessionsfilen:**
- Ny del **Fokuspunkterna i passet**: regelbrotten tillsammans och river-bluffen (hur ofta du bettade luft heads-up mot målet 45 %).
- BB-beslut visar om bara öppnaren var i potten eller hur många som synat före dig.
- Tabellen visar "krav" (equity du behöver för att syna) i stället för det missvisande "pottodds", markerar all-in-bets, och "Slår dig" visas på alla gator.

## Version 2.61 – riktlinje för BB med 0 nöt-egenskaper

- Ny 💡-riktlinje: **BB mot en öppning med en hand utan nöt-egenskaper – syna bara när SB öppnat (högst ~3 bb, inga andra i potten) eller handen är dubbelsuited + suited kung; folda resten**, och alltid när någon annan redan synat. I din data har övriga syner gett −1,8 bb per syn mot fold.
- Visas på Preflop, i läcklistan på Översikt och i sessionsfilen vid sådana syner.
- **Ny ruta på Översikt: 🚀 Om du tätar alla bekräftade läckor.** Visar din winrate nu, winraten med alla bekräftade läckor tätade, och hur mycket mer det ger i timlön på din nivå och på $2/$5. Bara statistiskt bekräftade läckor räknas – troliga läckor och råd ingår inte.

## Version 2.60 – Python installeras automatiskt på Windows

- `Starta (Windows).bat` installerar Python 3.12 själv med Windows inbyggda installerare (winget) om Python saknas – inget besök på python.org och ingen ruta att kryssa i. Svara Ja om Windows frågar om lov.
- Startfilen hittar en nyss installerad Python även innan Windows uppdaterat PATH.
- Saknas winget (mycket gamla Windows-installationer) öppnas python.org som förut.

## Version 2.59 – enklare läcklista

- **Alla läckor** visar preflop-reglerna som en enda läcka, "Följ dina preflop-regler", placerad efter sin summa. Tryck på raden för att se reglerna och välja en i taget som fokus.
- Bara de 5 största läckorna visas direkt, resten under "Visa mindre läckor".
- Fokusrutan: är fokus en regel visas att den ingår i preflop-läckan (summan). "Byt fokus" föreslås bara när en annan läcka är större än hela preflop-läckan; är preflop-läckan störst föreslås dess dyraste regel.

## Version 2.58 – efter nattanalysen (7 agenter, korsgranskad)

- **Borttaget:** fokuspunkten och riktlinjen "flop: din bet blir höjd – syna, 3-betta inte" (höll inte: synerna mot all-in-höjningar, där 3-bet var omöjlig, hade jämförts med 3-bets). Även "syna medelhand mot river-bet" och "två par mot flop-raise: syna" (urvalseffekter).
- **River-bluffen** (fokuspunkt #1) räknas om: ~1,3 bb/100 i stället för ~3 (effekten räknad per pott), storlek ½–pott, aldrig under 40 %.
- **Nya riktlinjer** i rangordning: turn-barrel med färdig färg, turn efter checkad flop, turn-barrel med två par/stege, triss: höj mot flop-bet, river-value med starka icke-nöt-händer, c-bet ⅓, river multiway-bluff, turn-bluffstorlek. Preflop: HJ – folda suited ess utan höga kort; folda aldrig dina bästa händer när det är foldat till dig.
- **Översikt:** överst i "Alla läckor" visas summan av alla preflop-regler – tillsammans din största läcka. Preflop-riktlinjerna finns med i listan.
- Sessionsfilen markerar HJ-öppningar med suited ess utan höga kort och de nya postflop-lägena.
- LÄS_MIG i djupexporten: rättad beskrivning av facing_pct (syn/(pott + bet); krav 33 % mot pottstor bet).

## Version 2.57 – postflop-läcka #1 och #2 följs som fokuspunkter

- **#1 River-bluff** (luft heads-up, ingen bet framför dig; mål: betta minst 45 %) och **#2 Flop-bet höjd** (mål: högst 5 % 3-bet) räknas nu på dina senaste 20 000 händer, med kostnad i bb/100, frekvens vecka för vecka och knappen Fokus – precis som reglerna.
- Kostnaden räknas försiktigt (se pffocus.py): på hela databasen ger den samma ~3,0 och ~2,6 bb/100 som postflop-analysen.
- Fokusrutan visar "Det finns en större läcka … Byt fokus" när en annan läcka kostar mer än fokusläckan.
- Faktatabellen har två nya kolumner (river-styrka och betstorlek per postflop-beslut), så första analysen efter uppdateringen bygger om fakta och tar längre tid.

## Version 2.56 – postflop-läckorna syns på Översikt

- **Alla läckor – störst först** på Översikt visar nu även de 8 riktlinjerna från postflop-analysen (💡 #1–#8) med uppskattad vinst i bb/100, sorterade tillsammans med reglerna. Märkta bekräftad/trolig, länk till Postflop.
- Fokusrutan säger till när en postflop-riktlinje är större än fokusläckan.
- Den äldre river-bluff-mätningen visas inte separat längre (den ingår i #1).

## Version 2.55 – riktlinjer postflop från en oberoende analys

En oberoende analys av 197k händer (felmarginal per spelpass, kontroll i två halvor av spelpassen, korrigering för
många tester) hittade åtta postflop-läckor. De finns nu som 💡-riktlinjer, störst vinst först, överst på sidan
**Turn & river**, och i sessionsfilen markeras de beslut där en riktlinje gäller:

1. River, luft, ingen bet framför dig (heads-up): bluffa oftare, ¾–pott (~3 bb/100, bekräftad)
2. Flop: din bet blir höjd – syna, 3-betta inte (~2,6 bb/100, bekräftad)
3. Turn efter checkad flop: betta starka drag och två par (~2,8 bb/100, delvis bekräftad)
4. C-bet flop i position, enkelhöjd pott, heads-up: oftare, ⅓ pott (~1–2 bb/100, trolig)
5. River, möter bet heads-up med medelhand: syna oftare (~0,8 bb/100, bekräftad)
6. Flop, höjd med två par utan drag: syna oftare (~0,8 bb/100, överskattad)
7. Turn: bluffa ½ pott, betta värde stort (~0,5–1 bb/100, trolig)
8. Turn med färdig färg efter din flop-bet: betta alltid (~0,7 bb/100, bekräftad)

Hela analysen finns i projektet som claude/postflop-analys-2026-11-08.md.

## Version 2.54 – rättelser efter en oberoende granskning

En ny agent utan kännedom om koden granskade 2.53. Rättat:

* **Regeln mot 3-bet ("folda 0 nöt-egenskaper") är nu korsvaliderad.** Undantagen väljs i ena halvan av
  spelpassen och regeln mäts i den andra (båda hållen). Tidigare valdes undantagen och testades på samma händer,
  vilket på slumpdata gav "bekräftad" i ca 19 % av fallen; nu ca 2 %. Kostnaden som visas är den korsvaliderade.
* **Brusfiltret:** regler där brotten faktiskt gått plus mot fold tas nu bort (tidigare behölls de).
* **Regeljämförelser tar hänsyn till situationen:** en regel mot 3-bet blandas inte ihop med öppningsregler, varken
  i testet på nya händer eller när troliga förbättringar döljs.
* **Testet på nya händer** mäter nu regeln som den hittades i de äldre händerna (dess gränser och undantag), så de
  nya händerna inte har använts för att välja ut den.
* **Filtrerade vyer** (datum, senaste N, nivå) visar de sparade reglerna från hela databasen – inga bekräftade
  regler listas längre som "borttagna" bara för att urvalet är litet.
* **Nivåjämförelsen** korrigerar för att den jämför flera nivåer med den bästa (Bonferroni).
* **Snabbare full analys:** sökningen i de äldre händerna (för testet på nya händer) sparas och görs om bara när
  nya händer kommer in. En upprepad full analys utan nya händer gick i test från 82 s till under 2 s.
* Mindre: den sparade analysen skrivs inte om i onödan och delar faktatabell med nästa analys efter start;
  träningen skapar inte längre öppningsövningar från regeln mot 3-bet; "Dela som bild" räknar regelföljning på
  alla sessioner.

Reglerna räknas om vid nästa analys av hela databasen.

## Version 2.53 – riktlinjer, och färre undantag på brus

* **Riktlinjer (💡)**: råd som inte är bekräftade regler visas för sig och räknas aldrig som regelbrott. Den första:
  *mot 3-bet, 4-betta AA med suited ess* (vid ~100 bb, och ur position även djupt; i position djupt kan du blanda in
  syner; AA utan färg: syna). Riktlinjerna står överst på sidan Preflop, och i sessionsfilen markeras händer där
  du synade en 3-bet med en sådan hand.
* Regeln "mot 3-bet: folda 0 nöt-egenskaper" undantar nu en undergrupp först när den har minst 100 spelade händer
  och går plus – färre undantag som bara är brus.

## Version 2.52 – ny regel: mot 3-bet, folda händer utan nöt-egenskaper

Programmet prövar en ny regel på dina händer: **mot 3-bet efter din öppning (i och ur position) – folda händer med
0 nöt-egenskaper** (inget högt par, inget suited ess, ingen rundown). Undergrupper som inte förlorar mot fold i din
data undantas automatiskt (t.ex. dubbelsuited + suited kung). Regeln blir "bekräftad" när syner med resten har gett
minus mot fold även med felmarginalen, "trolig" när den bara är minus. Den syns i sessionsfilerna, under Följ upp
och i fokuskön. Reglerna räknas om vid nästa analys av hela databasen.

## Version 2.51 – välj själv om läckor ska räknas på urvalet

Ny ruta i filterraden: **Läckor & modeller → Analysera på urvalet**.
* Av (standard): grafer, resultat, sessioner m.m. följer urvalet (t.ex. senaste 25k händer); läckor, gränser och
  river-modellen bygger på alla händer i varianten och räknas om bara när nya händer kommer in.
* På: även läckor och modeller räknas på just urvalet. Tar längre tid första gången, sparas sedan.

## Version 2.50 – ingen ny analys när du bara byter datum eller antal händer

Läckor, gränser för starthänder, öppningsguiden, river- och turn-tabellerna, river-coachen, rundowns och
"trolig förbättring" beskriver ditt spel och räknas nu på alla händer i varianten (och vald nivå/bordstyp).
De sparas och räknas om **bara när nya händer kommer in**. Byter du datumintervall eller "senaste N händer"
uppdateras bara resultat, grafer, sessioner, timlön och liknande – det går på någon sekund.

## Version 2.49 – EV i dollar i sessionslistan

Sessionslistan har en ny kolumn **EV $** (all-in EV i dollar) bredvid Dollar. Den går att sortera.

## Version 2.48 – bb eller dollar även på Översikt och Sessioner

Vinstkurvan på **Översikt** har samma knapp för bb eller dollar. På **Sessioner** finns nu en kurva för
den valda sessionen (faktiskt resultat, all-in EV och betald rake hand för hand), också med bb eller dollar.
Valet är gemensamt för alla sidor och sparas.

## Version 2.47 – bb eller dollar i graferna och all-in-tabellen

Under Resultat & graf finns nu en flik **Graf** med en knapp för **bb** eller **Dollar** (förut två flikar).
Fliken **All-in EV** har samma knapp och visar faktiskt resultat, EV och tur/otur per gata i bb eller dollar,
plus en totalrad för alla händer. Valet gäller båda och sparas till nästa gång.

## Version 2.46 – dela som bild

Ny sida under Analys: **Dela som bild**. Gör en snygg bild av din utveckling att skicka till en vän –
i mobilformat (1080 × 1920) eller desktopformat (1920 × 1080), i dollar eller i bb.

* Överst: resultat, all-in EV och EV per 100 händer.
* Kurva: resultat och all-in EV hand för hand.
* Utan startdatum: all-in EV per månad (per vecka vid kortare period), grönt = plus, rött = minus.
* Med startdatum (t.ex. när du började med ett nytt upplägg): före, efter och de senaste 7 dagarna –
  all-in EV, VPIP och regelföljning.
* Egen rubrik. Bilden ritas i programmet och laddas ner som PNG. Inga spelarnamn finns med.

## Version 2.45 – flera sessioner i en sessionsfil

På sidan Sessioner kan du kryssa i 1–5 sessioner och ladda ner dem som en enda fil till Claude
("📤 Sessionsfil för valda"). "Välj senaste dagen" kryssar i dagens sessioner med ett klick. Filen
börjar med en sammanställning av alla valda sessioner (händer, resultat, EV, rake, VPIP, regelföljning)
och har sedan varje session med sina största potter, numrerade "Session 1, 2 …".

## Version 2.44 – snabbare start

Den senaste analysen sparas nu på disk (bredvid databasen) och öppnas direkt när programmet startar,
i stället för att hela databasen analyseras om. Har nya händer lästs in sedan dess visas de i rutan
"nya händer" – tryck Uppdatera (eller låt "Uppdatera automatiskt" vara ikryssad) för att räkna om.
Efter en uppdatering av programmet räknas analysen om en gång.

## Version 2.43 – Rakeback & leaderboard

Ny sida under Analys: **Rakeback & leaderboard**. Räkna ut vilken winrate du behöver när rakeback och
leaderboard-priser (t.ex. Rush & Cash) räknas in.

* Fyll i automatiskt från dina händer: hela urvalet eller de senaste 1, 5 eller 10 spelpassen (händer per
  timme, rake i bb/100, din EV-winrate). Välj Rush & Cash och nivå i urvalet för att få rätt siffror.
* Ändra rakeback %, timmar i happy hour och övriga timmar, poäng per timme, happy hour-multiplikator och
  leaderboardens poänggränser och priser. Poäng per timme kan räknas ut från en dag du spelat.
* Visar poäng per dag och trolig placering, timmar som krävs för plats 1 och plats 10, rake, rakeback och
  leaderboard per timme, break-even-winrate och vad du tjänar per timme och månad vid olika winrate.
* Inställningarna sparas i webbläsaren.

## Version 2.34 – Aggression

* **Ny sida: Aggression** (under Spel). Den visar:
  * AF och AFq per gata, c-bet på flop i och ur position, check-raise och din stab-andel (hur ofta du bettar när det checkats till dig i position heads-up)
  * **Vinner du mer när du är aggressiv?** Dina sessioner delade i fyra lika stora grupper efter stab-andel, med resultat utan showdown och all-in EV för varje grupp
  * **Stab-andel över tid** i block om 5 000 händer, med resultat utan showdown. En röd stapel betyder en passiv period.
  * **Betta eller checka när det checkats till dig i position:** vad bet och check gav i andel av potten, per handgrupp. Grönt betyder att det alternativet gett mer.
* **Sessioner:** analysen av en session säger till när sessionen var passiv (minst 6 procentenheter under din normala stab-andel) eller tydligt aggressiv.
* Fakta byggs om första gången, eftersom dina postflop-beslut nu sparas i faktatabellen.

## Version 2.33 – När du vinner, och sessionsfil till Claude

* **Ny sida: När du vinner** (under Analys).
  * En färgkarta visar resultatet per tid på dygnet (00–06, 06–12, 12–18, 18–24) och nivå, plus hur mycket varje ruta bidrar till din totala bb/100.
  * Överst finns tre korta rader: bästa läget, dyraste läget och vilken tid du helst ska spela.
  * Är en tid tydligt bättre (z > 2,5, eftersom fyra tider jämförs) kommer den med i läckkartan på Översikt, med ett försiktigt värde.
* **Sessioner:** analysen av en session varnar när sessionen startade utanför din bästa tid.
* **📤 Sessionsfil till Claude** (knapp i analysen av en session). Den ger en liten textfil som du laddar upp i chatten. Filen innehåller:
  * en sammanfattning: händer, resultat, all-in EV, rake, VPIP och regelföljning
  * timme för timme och regelbrott per regel
  * de 10 potterna där mest stod på spel för dig
  * för varje pott: dina kort, bordet, vad motståndarna visade och preflop-beslutet med eventuellt regelbrott
  * en tabell per beslut med pott, SPR, vad du mötte (storlek och pottodds), vad du gjorde, handstyrka, färgdrag, stegouts och resultatet räknat från beslutet
  * hela handhistoriken
  * en instruktion till Claude om att gå igenom sessionen ur ett GTO-perspektiv
  * Filen sparas också i din exportmapp om du valt en.

## Version 2.32 – reglerna testas på nya händer, och en rikare djupanalys

* **Test på nya händer.** När hela databasen analyseras letar programmet också regler bara i de äldsta två tredjedelarna av händerna. Varje regel mäts sedan på den nyaste tredjedelen.
  * En regel som går åt fel håll där, med minst en felmarginal, tas bort.
  * Kostnaden per brott blir den försiktigaste av den gamla och den nya mätningen.
  * En regel som inte hittades i de äldre händerna kan bara vara "trolig".
  * Under Läckor → "Test på nya händer" står resultatet per regel. Läckkartan på Översikt visar ✓ testad, ? osäker eller ? få händer.
  * Testet körs bara när databasen har minst 90 000 händer, och då tar analysen ungefär dubbelt så lång tid.
* **3-bet med högt par + suited ess jämförs i liknande lägen:** samma position, AA eller inte, och samma struktur. Skillnaden blir mindre och mer ärlig.
* **Djupanalysen (zip) har två nya filer och fler kolumner:**
  * `preflop_context.csv`: vem som öppnade (position och anonymt id), öppningsstorlek, limpers, syner före dig, vem som 3-bettade, antal spelare till flop och typ av pott.
  * `opponents.csv`: en rad per motståndare och hand med anonymt id, VPIP, PFR, till flop och om motståndaren visade kort. Samma spelare får samma id i alla dina exporter, men namnet går inte att få fram. Med filen kan Claude se hur du går mot tighta och lösa spelare.
  * `postflop.csv` har nya kolumnerna `straight_outs` (antal kort som ger dig stege på flop och turn), `pot_type` och `hero_pos`.

## Version 2.31 – träna 3-bet-beslut

* **Träna starthänder** har en ny situation överst: 🎯 "BB / SB / BTN / CO mot en öppning: 3-betta, syna eller folda?". Du svarar med tre knappar: 3-betta, Syna eller Folda.
* Facit följer dina regler:
  * **Högt par + suited ess:** 3-betta.
  * **Utan suited ess:** syna eller folda räknas som rätt. 3-bet är fel.
  * **Suited ess utan högt par:** 3-betta eller syna räknas som rätt.
  * **En foldregel går före,** till exempel rundowns A–4 eller 0 nöt-egenskaper.
* Händerna blandas: en tredjedel högt par + suited ess, en tredjedel utan suited ess och en tredjedel suited ess utan högt par.
* Tangenter: ← / 3 = 3-betta, ↓ / S = syna, → / F = folda.
* "Träna den här" på 3-bet-läckorna i fokuskortet öppnar den nya träningen.

## Version 2.30 – tydligare läckor och syna-gräns på river

* **Översikt → "Alla läckor – störst först".** Varje läcka tar en rad:
  * en färgprick
  * en kort instruktion
  * vad läckan kostar nu i bb/100
  * en stapel per vecka för de senaste veckorna, grön när du höll regeln
  * en knapp för att göra den till din fokusläcka
  * River-läckorna (bluffar och syner) finns med i samma lista.
* **Fokuskortet** är kortare. Förklaringen ligger bakom "Varför?".
* **Turn & river → "River: syna eller folda mot en bet?"** är ny.
  * Överst står en rad per betstorlek, till exempel "syna om högst 4 % av hans händer slår dig".
  * Under den finns en färgkarta. Grön betyder att syn har gått plus, röd att den gått minus. Siffran i rutan visar hur ofta du foldat.
  * Längst ner listas de senaste folds du borde ha synat, med uppspelning.
* **River: bluffa mer?** har fått kortare text och en uppskattning av värdet i bb/100.
* Kortare texter under Utveckling och Läckor.
* Fakta byggs om första gången (river-handens exakta styrka sparas nu).

## Version 2.29 – rättelser efter en oberoende granskning

En oberoende granskning av programmet hittade fel som gjorde siffrorna för optimistiska. Rättelserna:

**Regler**
* **Brusregler tas bort.** En regel vars brott på alla dina händer inte ens kostat en felmarginal mer än fold sparas inte längre. De borttagna reglerna visas under Läckor → "Regler som tagits bort".
* **Försiktiga kostnader krymps efter hur säkra de är.** Faktorn är max(0, 1 − 1/z²), så en regel med många brott men osäker kostnad hamnar inte längre överst i fokuskön. Kostnaden räknas på alla händer och sparas med regeln.
* **Gränsregler ("spela bara topp X %")**
  * Lönsamma kombinationer undantas. En kombination av nöt-egenskaper som gått bättre än fold även med felmarginalen räknas inte som regelbrott. Exempel: högt par + suited ess i BB.
  * Gränsens läge prövas. Även händerna närmast gränsen måste ha förlorat, annars sitter gränsen för snävt och blir ingen regel.
* **"Trolig förbättring"**
  * Ingen förhandsgallring på hela urvalet.
  * Alla prövade kandidater räknas med i falskupptäcktskontrollen.
  * Snittet räknas inte längre bara på det bästa hållet.
* **3-bet-reglerna** använder samma halvor av spelpassen som resten av programmet. Regeln om högt par + suited ess kräver nu att 3-bet är bättre i båda halvorna.

**Överlapp mellan läckor**
* **Nivåer** jämförs med dina regelbrott borträknade. En nivå räknas inte som sämre bara för att du bröt mot reglerna oftare där.
* **Pausen** i fokuskön är samma pengar som regelbrotten efter gränsen. Det står nu i texten, så lägg inte ihop dem.

**Ny analys**
* **River: möjlig överfoldning** (Turn & river). Visar rutor där dina syner gått klart bättre än fold men där du ändå foldar minst var femte gång.
* **River: dina bets.** Visar hur ofta motståndarna foldat mot dina river-bets per storlek, jämfört med hur ofta en bluff behöver lyckas. Visar också hur ofta du bettar i position när det checkats till dig, per handstyrka.
* **Syna eller 3-betta per situation** (Läckor → 3-bets mot en öppning). Visar vad syn och 3-bet gett mot fold i varje position.

**Djupanalysen och data**
* `postflop.csv` har två nya kolumner:
  * `facing_size_pct`: betten du mötte i procent av potten före den.
  * `beat_frac`: river-handens styrka.
* `facing_pct` är pottodds (en pottstor bet = 50). Beskrivningen är rättad.
* BB:s höjning över limpers räknas nu som ett beslut.
* Utvecklingens varningar har felmarginal per spelpass.
* Fakta och regler byggs om första gången. Analysera hela databasen en gång – det tar längre tid än vanligt.

## Version 2.28 – utveckling över tid och 3-bet-regler

* **Ny flik: Utveckling** (under Förbättra). Alla händer i urvalet delas i block om 5 000 händer i tidsordning. För varje block ser du läckkostnaden i bb/100, alltså dina regelbrott gånger vad ett brott kostar. Du ser också en färgkarta med en rad per regel, där grön betyder att du följer regeln och röd att du bryter ofta, samt VPIP och resultat. Resultatet per block visas bara som information, eftersom felmarginalen på 5 000 händer är ±25–35 bb/100. Därför finns också ett rullande resultat över 25 000 händer.
* **Nya läckor:** dina senaste 10 000 händer jämförs med alla tidigare. Du får en varning när du bryter mot en regel klart oftare än förut, spelar klart fler eller färre händer från en position, eller 3-bettar klart oftare eller mer sällan mot en öppning. "Klart" betyder mer än tre felmarginaler.
* **Två nya regler om 3-bets mot en öppning** prövas på dina händer:
  * "3-betta inte utan suited ess" blir en bekräftad regel när dina 3-bets utan suited ess förlorar mot fold även med felmarginalen och i båda halvorna av spelpassen.
  * "3-betta högt par + suited ess, syna inte" blir en trolig regel när 3-bet är bättre än syn även med felmarginalen. Kostnaden per syn räknas försiktigt, som den nedre gränsen för skillnaden.
  * Ett brott är här fel handling, inte att du spelade handen. Båda reglerna följs upp under Följ upp, Sessioner, Utveckling och i fokuskön. Siffrorna visas under Läckor → 3-bets mot en öppning.
* Reglerna har fått en ny version. Analysera hela databasen en gång så sparas de nya reglerna.

## Version 2.27 – motståndarnas händer vid showdown

* `postflop.csv` har två nya kolumner. `villain_hand` är den bästa hand en motståndare visade vid showdown, på hela bordet. `villain_better` är 1 om den slog din hand och 0 om du hade bäst. Då kan Claude se vad motståndarna faktiskt hade när det gick check–check, och hur ofta en bet hade mött en bättre eller en sämre hand.

## Version 2.26 – postflop-besluten går att värdera exakt

* `postflop.csv` i Djupanalys (zip) har tre nya kolumner. `hero_in_bb` är det du lagt i potten före beslutet, `to_call_bb` är vad det kostar att syna, och `from_here_bb` är handens resultat räknat från beslutet (all-in EV plus det du redan lagt i). Att folda ger 0 härifrån, så mot en bet är `from_here_bb` exakt skillnaden mot fold, på flop, turn och river. Då kan Claude värdera varje postflop-beslut, inte bara se hur ofta du gör det.

## Version 2.25 – postflop i djupanalysen och kontroll av nivåer

* **Djupanalys (zip)** har en ny tabell, `postflop.csv`, med en rad per beslut du tagit på flop, turn och river. Den innehåller antal spelare, position, vem som höjde preflop, pott, SPR, vad du mötte och hur stort, vad du gjorde och med vilken storlek, din hand just då, färgdrag och bordets struktur. Med den kan Claude leta läckor i c-bets, fortsatta bets och syner följda av fold. Djupanalysen körs nu som ett jobb med förlopp och sparas även i din exportmapp om du valt en.
* **Nivåer:** programmet jämför all-in EV per nivå med felmarginal. Går du tydligt sämre på en nivå visas det under "Det viktigaste" och i tabellen Per nivå på Översikt, och det blir en läcka i fokuskön ("Spela på $X – inte på $Y"). Kostnaden räknas försiktigt, efter den nedre gränsen för skillnaden.
* Analysfilen till Claude innehåller "stake_check", och djupanalysen har `stakes.csv`.

## Version 2.24 – försiktigare rangordning av läckorna

* Fokuskön och Tid i sessionen räknar nu varje regelbrott **försiktigt**. Kostnaden är det minst negativa av regelns kostnad och vad dina brott mot regeln faktiskt har kostat i hela urvalet. En regel vars brott i praktiken varit billiga, till exempel "HJ: öppna inte händer med suited ess" (−0,19 bb i praktiken mot −1,40 bb enligt regeln), hamnar då inte högt i kön. Fokuskortet visar när den försiktiga kostnaden används.
* Rättat: "efter 1 timme" i stället för "efter 1 timmar".

## Version 2.23 – långa sessioner

* **Tid i sessionen** (överst under Sessioner) visar timme för timme hur mycket fler händer du spelar än du brukar i samma läge (position, antal spelare, nivå och bordstyp), hur ofta du bryter mot dina regler, vad brotten kostar och all-in EV med felmarginal.
* En timme räknas som **tydligt sämre** när den är lösare än din första timme även med felmarginalen. Den första sådana timmen blir den **rekommenderade pausgränsen**. Tabellen "Vad en paus är värd" visar den väntade vinsten i bb/100 för en paus efter 1, 1,5, 2, 2,5 eller 3 timmar. Du kan välja en egen gräns.
* Gränsen blir en läcka i **fokuskön**: "Ta minst 30 minuters paus efter X timmar". Om den är din dyraste läcka blir den din fokusläcka, med andelen händer efter gränsen vecka för vecka.
* **Sessionsanalysen** varnar när en session har gått över gränsen och visar timme för timme hur du spelade.
* "Det viktigaste" på Översikt nämner långa sessioner när det är en tydlig läcka.
* Analysfilen till Claude innehåller "time_in_session". Långa sessioner visar bara de 60 dyraste regelbrotten.

## Version 2.22 – djupanalysen delas upp

* Tabeller i Djupanalys (zip) som är större än 20 MB delas upp i delar, till exempel `hands_del1.csv` och `hands_del2.csv`. Varje del har samma rubrikrad. Då går varje fil att ladda upp i chatten, där gränsen är 30 MB per fil.

## Version 2.21 – bättre underlag till Claude

* **Exportera till Claude** (analysfilen) innehåller nu också sessionerna (de senaste 60 med regel för regel) och hela fokuskön med vecka för vecka.
* Ny knapp **Djupanalys (zip)** bredvid. Den ger en zip med tabellerna bakom analysen. Ladda upp den i chatten med Claude för egna, djupare frågor.
  * `hands.csv`: en rad per hand (tid, session, position, kort, nöt-egenskaper, struktur, resultat, all-in EV, rake, pott, showdown med mera).
  * `preflop.csv`: varje preflop-beslut, med resultat mot fold och vilken regel det bröt mot.
  * `turn_calls.csv`, `river.csv`: syner mot turn-bet och beslut mot river-bet.
  * `sessions.csv`, `rules.json` och `LÄS_MIG.txt` som beskriver kolumnerna.
* Filerna innehåller inga spelarnamn, bara GG:s hand-id så att en hand går att hitta igen.

## Version 2.20 – Sessioner

* Ny flik **Sessioner** under Förbättra. En ny session börjar när det gått mer än 30 minuter mellan två händer, så en session kan vara 10 minuter eller 4 timmar.
* För varje session visas **regelföljning** (andel tillfällen du följde dina regler, bekräftade och troliga), regelbrott, väntad kostnad av brotten i bb och bb/100, och resultatet (bara som information). Allt jämförs med ditt snitt i alla tidigare sessioner, i färg från rött till grönt.
* **Analysera** på en session visar regel för regel jämfört med ditt snitt (fokusläckan markeras med 🎯) och händerna där du bröt mot en regel, med uppspelning. Länken "Alla händer i sessionen" öppnar handlistan för just den sessionen.
* Översikten visar den senaste sessionen överst, med en knapp för att analysera den.
* Stapeldiagrammet visar regelföljningen i de senaste 30 sessionerna. Målet är jämnt grönt.

## Version 2.19 – alla händer går att exportera, till valfri mapp

* **Alla händer kommer med.** Händer som lästes in av en äldre version saknar originaltext i databasen. De återskapas nu i GG:s format från den tolkade handen, med samma platser, stackar, kort, handlingar, belopp, vinster och rake. Kontrollerat på 40 000 händer: att läsa in den återskapade texten igen ger exakt samma hand. Det enda som saknas är handbeskrivningar som "two pair", och jackpot räknas in i rake.
* **Få tillbaka exakt originaltext:** läs in dina GG-filer eller DriveHUD-exporten igen under Import & databas. Händer som redan finns får då tillbaka sin originaltext, och det syns i importrutan.
* **Välj mapp:** på Exportera händer kan du skriva in en mapp (den skapas om den inte finns) och välja format, en zip-fil eller vanliga textfiler. Programmet kommer ihåg mappen, och "Exportera listan" på sidan Händer använder samma mapp. Lämnar du rutan tom laddas filen ner i webbläsaren som förut.

## Version 2.18 – menyn fungerar direkt efter start

* När programmet startar och databasen har händer analyseras hela databasen automatiskt. Du ser förloppet och hamnar sedan på Översikt.
* Menyflikarna är aldrig gråa. Trycker du på en flik innan någon analys är öppen startas analysen, och du hamnar på den fliken när den är klar.

## Version 2.17 – snabbare träning

* **Nästa hand automatiskt:** efter rätt svar efter 1 s, efter fel efter 4 s (går att ändra, eller "vänta på mig"). En stapel visar när nästa hand kommer. Tangenter: ← / Ö = öppna, → / F = folda, mellanslag = nästa.
* **Dina händer** listas i en smal kolumn till höger: grön = rätt, röd = fel, grå = ditt val. Tryck på en hand för att se facit igen. Listan sparas i webbläsaren.
* **Träna om felsvar:** knappen tar alla händer du svarat fel på i slumpad ordning. Svarar du rätt räknas handen som klar.
* **Ditt val:** när ingen av dina regler säger något om handen (och det inte finns någon "topp X %"-gräns) visas "Ditt val" i stället för "Fel". Båda svaren räknas som rätt, eftersom datan inte visar att handen förlorar mot fold – men det betyder inte heller att den är lönsam.

## Version 2.16 – bra händer räknas inte som läckor

* Regler om starthandsklasser ("folda händer med 0 nöt-egenskaper", rena rundowns, öppningsguidens rutor) delas nu upp efter handens struktur: trippelsuited, dubbelsuited + sammanhängande, dubbelsuited + suited kung, dubbelsuited övriga, sammanhängande (enkelsuited/rainbow) och övriga.
* Varje del prövas för sig mot fold. Med få händer dras skattningen mot regelns snitt, med många talar delen för sig själv (empirisk Bayes). En del som inte är sämre än fold blir ett **undantag**: de händerna räknas inte som regelbrott i fokusläckan, uppföljningen, handlistan eller tränaren.
* Regelns kostnad räknas om utan undantagen. Ny ruta under Läckor: "Undantag – bra händer räknas inte som läckor", med röd–grön stapel per del.
* Tränaren visar "undantag" när en hand slipper en regel. Reglerna sparas om vid nästa analys av hela databasen.

## Version 2.15 – byta version utan att stänga något

* Starta bara den nya versionen – den stänger den gamla själv. På Windows stängs nu även den gamla versionens fönster automatiskt (förut stod det kvar med "Tryck på valfri tangent"). Bara om programmet avslutas av ett fel står fönstret kvar, så att felet går att läsa.

## Version 2.14 – en fokusläcka åt gången

* Överst på **Översikten**: **Din fokusläcka – jobba bara med den här**. Programmet väljer den regel (bekräftad eller trolig) som kostar dig mest *just nu*: hur ofta du bröt mot den i dina senaste 20 000 händer gånger vad ett brott kostar, i bb/100. Samma hand räknas bara på en regel.
* Rutan visar vad det kostar, hur ofta du bryter mot regeln, och **regelbrott vecka för vecka** (rött → grönt) för de senaste 8 veckorna.
* **▶ Träna den här** öppnar tränaren i den situation där du bryter mot regeln oftast. **Se händerna** öppnar handlistan med just de händerna.
* Fokus **står kvar** tills du byter – det hoppar inte runt mellan analyserna. När du har följt regeln två veckor i rad (högst 5 % brott, minst 100 tillfällen) står det **Under kontroll** och programmet föreslår nästa läcka. Under "Övriga läckor i kön" kan du välja en annan själv.

## Version 2.13 – bredare träning, rensa datum, automatisk uppdatering

* **Träna starthänder** (tidigare Träna öppningar) tränar nu varje situation där du har en regel: öppningar per position, **BB och SB mot en öppning**, cold call/3-bet och händer **utan nöt-egenskaper**, rundowns och kombinationer. Hälften av händerna bryter mot en regel och hälften gör det inte; finns en gräns ligger hälften nära gränsen.
* Facit märker varje skäl som **bekräftad** eller **trolig**.
* **✕ Rensa datum** i urvalet överst (och på exportsidan) tömmer från- och till-datum med ett klick.
* **Automatisk uppdatering:** när den bevakade mappen läser in nya händer visas rutan "N nya händer" direkt på sidan du har öppen (programmet kollar var 20:e sekund), och analysen uppdateras automatiskt efter 15 sekunder med samma urval och sida. Kryssa ur "Uppdatera automatiskt" om du hellre trycker själv.

## Version 2.12 – timlön

* Ny flik **Timlön** under Resultat & graf, och två nya rutor överst: Timlön och EV-timlön.
* Speltiden räknas ur tidsstämplarna i handhistoriken, för alla bord tillsammans (flera bord = fler händer per timme). Ett nytt spelpass börjar efter 30 minuters paus, och inom ett pass räknas en lucka på mer än 5 minuter som paus.
* Visar speltid, händer per timme, antal spelpass, timlön faktiskt och med all-in EV (med 95 %-intervall), EV-timlön före rake, rake per timme och bb per timme.
* **Vecka för vecka** som stapeldiagram från rött till grönt, **per nivå** och **de senaste spelpassen**. Veckor och nivåer med mindre än en timmes spel visas inte.
* Rakeback ingår inte.

## Version 2.11 – oberoende granskning, rättningar

Två oberoende granskare (säkerhet respektive poker/statistik) gick igenom programmet. Allt de hittade och kunde visa är rättat:

**Säkerhet och stabilitet**
* En trasig hand (okänd färg, för många kort, samma kort två gånger) kunde stoppa alla analyser tills databasen tömdes. Nu hoppas sådana händer över, och en hand som inte går att räkna på stoppar aldrig resten.
* En trasig zip-fil i den bevakade mappen kunde stoppa all inläsning varje minut. Nu hoppas den över, liksom filer som försvinner mitt i inläsningen.
* Skydd mot zip-bomber (högst 2 GB uppackat per zip, högst 200 MB per fil, högst 3 nivåer zip i zip) och mot mappslingor via genvägar.
* Den bevakade mappen läser bara zip- och textfiler, och när databasen redan har dina händer bara händer där du själv fick kort – en fil som hamnat i Hämtade filer av misstag kan inte blanda in andras händer.
* Sidan kan inte längre visas inuti en annan webbsida (skydd mot klickkapning), och programmet kan inte stängas via en främmande adress i nätverksläget.
* Mindre fel: felaktiga antal och sökvägar gav serverfel, ett uppladdat filnamn med ogiltiga tecken lämnade kvar tillfälliga filer, länken "Standard:" fungerade inte.

**Poker och statistik**
* **Trolig förbättring** var för generös: utan några verkliga förluster visades ändå rader. Nu väljs varje rad ut i ena halvan av spelpassen och mäts i den andra, och listan hålls till högst ca 20 % felaktiga rader (Benjamini–Hochberg). Kontrollerat med 40 slumpkörningar utan verkliga förluster: rader visades i 20 % av körningarna (förut 100 %).
* **Bekräftat** var 2–4 gånger för generöst: nöt-egenskaper, öppningsguiden och rundowns korrigeras nu tillsammans, och en ruta kräver minst 100 händer. Kontrollerat med 200 slumpkörningar: en falsk regel i 5 % av körningarna, som utlovat (förut 12 %).
* Nivåer som $0.10/$0.25 (2,5:1) räknades som $0.10/$0.20. Rättat.
* "Small & big blinds" (död SB + BB i PokerStars-format) räknas rätt, och den riktiga small blinden får positionen SB.
* "Dina pengar in genom syn" och "Du synade sist" räknade osynade bets som insatta pengar och satsningar efter att du redan var all-in. Rättat (fakta byggs om automatiskt en gång).
* Stora preflop-all-ins (pott över 100 bb) räknas med 6 000 slumpade bord i stället för 1 500 – mindre brus i all-in EV.
* Positionstabellen visar tydligt att bb/100 där är all-in EV.

## Version 2.10 – resultat efter pottstorlek

* Ny flik **Pottstorlek** under Resultat & graf. Alla händer i urvalet delas upp efter hela pottens storlek när handen var slut: 0–10, 10–20 … 190–200 och 200+ bb.
* **Diagram från rött till grönt:** en stapel per pottstorlek, djupt röd där du förlorar mest, grå runt noll och djupt grön där du vinner mest. Välj all-in EV eller faktiskt resultat, och totalt bb, bb per hand, bb/100 eller dollar.
* **Tabell** med samma färger: antal händer, andel, all-in EV, EV per hand med 95 %-intervall, faktiskt resultat, bidrag till bb/100, dollar, hur ofta du gick till showdown och vann där.
* **Pottar på 150 bb och mer** sammanfattas i en egen ruta, och under Det viktigaste visas var du förlorar och vinner mest.
* **Vägen in i potten:** för pottar 0–50, 50–100, 100–150, 150–200 och 200+ bb visas om du satsade sist, synade sist, foldade eller om ingen satsade – med resultat och färg. Det är det som visar om du är för lös i stora pottar (stora röda rutor under "Du synade sist"). Dessutom hur stor del av dina pengar i potten som kom in genom syner.
* Fakta byggs om en gång efter uppdateringen (för att räkna vägen in i potten). Det sker automatiskt första gången du kör analysen.

## Version 2.9 – exportera händer till DriveHUD och HoldemManager

* **Exportera händer** (ny sida i menyn under Data): välj variant, bord, nivå, period och antal (de senaste N händerna). Händerna sparas i en zip-fil som DriveHUD (Import → Import File) och HoldemManager 3 (Import → Import Files) kan läsa direkt.
* **Samma format som originalet:** varje hand har exakt den text den hade i filen du läste in, t.ex. GG:s zip-fil, och händerna skrivs i tidsordning. Det är kontrollerat i ett test att den exporterade texten är identisk med originalet tecken för tecken.
* Välj mellan **en fil per dag och nivå** (ungefär som GG:s egna filer) eller **alla händer i en fil**.
* **Exportera listan** på sidan Händer: tar med just de händer listan visar, t.ex. dina 50 största förluster eller alla regelbrott, för att gå igenom dem i DriveHUD eller HoldemManager.
* De fem senaste exportfilerna sparas bredvid databasen (mappen `plo_leak_export`), äldre tas bort.

## Version 2.8 – standardmapp som kollas varje minut

* **Standardmapp:** utan att du ställer in något bevakas mappen Hämtade filer (Downloads). Du byter mapp under Import & databas – skriv in den nya mappen och tryck "Spara och läs in nu". Där kan du också stänga av bevakningen.
* **Kollas en gång i minuten** medan programmet är öppet, och när det startar. Bara nya eller ändrade filer öppnas, så en kontroll utan nya filer tar några hundradelar av en sekund även i en full mapp.
* En fil som ändrats de senaste 20 sekunderna väntar till nästa kontroll, så att en zip som fortfarande laddas ner inte läses halvfärdig.

## Version 2.7 – bevakad mapp och zip-filer

* **Bevakad mapp** (under Import & databas): peka ut mappen där GG:s zip-filer hamnar, t.ex. Hämtade filer. Programmet läser in nya händer automatiskt när det startar och regelbundet medan det är öppet (en gång i minuten från version 2.8). Du kan också trycka "Spara och läs in nu".
* **Inget behöver packas upp.** Zip-filer (även zip i zip) läses direkt i minnet, och originalfilerna lämnas orörda. Zip-filer utan handhistorik, ofullständigt nedladdade filer, Mac-metadata (`__MACOSX`) och vanliga filtyper som bilder och filmer hoppas över.
* Filer som redan lästs in hoppas över, och händer som redan finns sparas inte igen.
* När nya händer har lästs in medan en analys är öppen visas **"N nya händer har lästs in" med knappen Uppdatera analysen** högst upp. Analysen körs då om med samma urval.
* Zip-filerna kan också laddas upp som de är under "Ladda upp filer".
* På Mac kan macOS fråga om Terminal får komma åt mappen Hämtade filer första gången. Svara OK.

## Version 2.6 – trolig förbättring

Målet är högsta möjliga bb/100. "Bekräftat" är lika strängt som förut, men programmet visar nu också det som **troligast** höjer din bb/100, även när det inte är bevisat:

* **Trolig förbättring** (under Läckor och på Översikten): starthandsbeslut som har gått sämre än fold, med
  * sannolikheten att fold verkligen är bättre (minst 90 % för att visas),
  * väntad vinst i bb/100 om du foldar händerna,
  * sorterat efter väntad vinst.
* Kandidaterna är bestämda i förväg: antal nöt-egenskaper per position och för "utanför blindarna" respektive "blindarna", rena rundowns efter lägsta kort, öppningsguidens rutor och range-gränser som inte bekräftats strikt.
* Det som redan är bekräftat visas inte en gång till, och en grupp av positioner ersätter sina egna positioner.
* Raderna sparas som regler med nivån **trolig** under Följ upp (när hela databasen för en variant analyseras), så att du kan följa att du ändrar spelet.
* Analysfilen till Claude innehåller listan (`likely_improvements`).

## Version 2.5 – starthänder jämfört med fold

* **Nöt-egenskaper jämförs nu med att folda direkt.** Tidigare visades "netto när spelad", där blinden du redan lagt i SB och BB räknas som en förlust – fast den är förlorad även om du foldar. Nu visas för varje antal nöt-egenskaper (0–3), och per position:
  * resultatet per spelad hand jämfört med fold, med 95 %-intervall,
  * **totalt mot fold** – vad det har gett att spela händerna i stället för att folda dem,
  * en bedömning ("förlorar"/"lönsamt") bara när den klarar bootstrap-testet med korrigering för alla rutor i tabellen.
* **Det viktigaste** ger inte längre råd som inte är bevisade. Tumregeln "minst två nöt-egenskaper" (PLO6-teori) visas som bakgrund, inte som slutsats, och syns inte längre som råd för PLO4.
* **Nya regler:** en säkerställd förlust för t.ex. "0 nöt-egenskaper från CO" blir en egen regel som följs upp under Följ upp.
* **Läckor** visar nu överst allt som är bekräftat i tabellerna (rundowns, öppningsguiden, nöt-egenskaper per position, range-gränser), inte bara bevismotorns läckor.
* Analysfilen till Claude innehåller den nya tabellen (`starting_hands_vs_fold`).

## Version 2.4 – vinstkurvan

* **Två nya linjer:** vinst *med showdown* och vinst *utan showdown* (händer som avgjordes innan river-showdown – du foldade eller alla andra foldade). Tillsammans blir de ditt faktiska resultat.
* **Slå av och på linjer** genom att trycka på dem ovanför grafen: faktiskt resultat, all-in EV, med showdown, utan showdown och betald rake. Axlarna anpassas efter det som visas, och valet sparas till nästa gång.
* **Rutnät** i både höjd- och sidled. Intervallet på händer-axeln anpassas efter antalet händer, t.ex. 20, 1 000 eller 10 000 händer mellan strecken.
* Håll muspekaren (eller fingret) över grafen för att se alla synliga linjers värden vid just den handen.

## Version 2.3 – equity bara mellan kända händer

* I uppspelningen räknas equity nu **bara mellan händerna vars kort syns** (dina och de som visades). Spelare med okända kort räknas inte med alls, så andelarna blir tillsammans 100 %. Tidigare räknades okända motståndare som slumpade händer, och deras andel visades som "Okända händer".
* Equity visas när minst två händer med kända kort är kvar i handen. Den ändras inte när en spelare med okända kort foldar.
* Flop räknas nu exakt (alla turn- och river-kombinationer), precis som turn. Preflop räknas med 20 000 slumpade bord, vilket ger en felmarginal på några tiondels procentenheter.

## Version 2.2 – nytt gränssnitt

Programmet är byggt om till ett riktigt analysverktyg i samma stil som HoldemManager och DriveHUD, i stället för en enda lång sida:

* **Meny till vänster** med egna sidor: Översikt, Resultat & graf, Händer, Preflop, Turn & river, Läckor, Följ upp, Träna öppningar, Statistik & kontroll samt Import & databas. Menyn visar antal läckor och hur ofta du brutit mot dina regler.
* **Urvalet ligger alltid överst**: variant (en eller flera), bord, nivå, senaste händerna och period. Ändra och tryck Uppdatera – du hamnar på samma sida igen.
* **Flikar inom varje sida** i stället för scrollning, t.ex. Preflop: Öppningsguide, Nöt-egenskaper, Rundowns, Range-gränser, Per position och Starthänder.
* **Översikten** samlar nyckeltal, vinstkurvan, det viktigaste, dina läckor, uppföljningen och resultat per nivå och position.
* **Handlistan (Händer)** omfattar alla händer i urvalet. Den går att sortera och filtrera (största förluster/vinster/pottar, senaste, all-in, showdown, regelbrott, position, handnummer). Tryck på en hand så spelas den upp i panelen bredvid; på mobilen öppnas den i helskärm.
* **Mörkt tema** som standard, med ljust tema ett klick bort (nere till vänster).
* **Mobilen**: menyn fälls ut med ☰, och urvalet visas med knappen Urval.
* Exportfilen till Claude laddas ner med knappen **Exportera till Claude** uppe till höger.

Samma analys och samma siffror som tidigare. Rapporten från kommandoraden (`--out rapport.html`) är kvar som en enda sida att spara eller skicka.

## Version 2.1

* **Händer att spela upp.** Ny del i rapporten: dina 10 största förluster och 10 största vinster i urvalet, med handuppspelning. Du når den via länken "Händer" i menyn. Uppspelningen fanns redan i 2.0 men bara under Följ upp, för händer som bröt mot en regel.
* **Equity kontrollerad** mot en helt oberoende handutvärderare:
  * exakt samma värden på flop och turn när korten är kända,
  * samma värden inom felmarginalen mot motståndare med okända kort.

## Version 2.0 – ny kärna för miljontals händer

Kärnan är omskriven så att programmet klarar miljontals händer och kan byggas ut utan att bli långsamt. Rapporten ser ut som förut. Siffrorna är kontrollerade mot version 1.28 och är desamma.

**Det här märker du**

* Analysen körs i bakgrunden och visar hur långt den kommit. Sidan låser sig inte längre.
* Första starten efter uppdateringen räknar fram fakta för alla händer i databasen. Med 190 000 händer tar det några minuter, och det görs bara en gång. Efter det räknas bara nya händer.
* Att byta urval i rapporten går på sekunder. Samma urval utan nya händer visas nästan direkt.
* Stora inläsningar delas upp på alla processorkärnor.

**Så fungerar kärnan** (för den som vill bygga vidare)

| Del | Fil | Uppgift |
|---|---|---|
| Rådata | `db.py` | Varje hand sparas en gång (SQLite) med originaltexten. Bara nya händer läses in, parallellt. |
| Fakta | `facts.py` | Allt analysen behöver om en hand räknas en gång och sparas i kolumnfiler (numpy): en rad per hand, per beslut och per statistik. Har en version; ändras en beräkning byggs fakta om automatiskt. |
| Urval | `selection.py` | Variant, bord, nivå, period och senaste N, beskrivet på ett ställe och använt överallt. |
| Summering | `aggregate.py` | Gör om fakta för ett urval till statistik med numpy, utan att läsa några hela händer. |
| Analyser | `analyses.py` | Varje analys är en modul i ett register med eget versionsnummer. Resultaten sparas per data och urval. |
| Statistik | `statlib.py` | Alla tester som avgör om något är säkerställt, samlade på ett ställe. |
| Motor | `fastev.py` | Vektoriserad handutvärdering. Ger samma värden som tidigare men 5–10 gånger snabbare. Används för all-in EV, uppspelning och simuleringar. |
| Jobb | `jobs.py` | Inläsning och analys i bakgrunden, med förlopp. |
| Rapport | `report.py`, `templates/` | Visar bara modulernas resultat. |

Prestandatest: `python tools/benchmark.py <mapp> --db /tmp/test.db`.

**Striktare och säkrare** (efter en oberoende granskning av koden)

* **Spelpass i stället för klockblock.** Statistiken behandlar händer från samma spelpass som en enhet. Ett spelpass är alla dina bord tills du pausar i mer än 30 minuter. Hela passet hamnar alltid i samma halva när en läcka först hittas i ena halvan och sedan bekräftas i den andra. Tidigare kunde ett pass delas vid klockslag.
* **Inga fler falska "Folda"/"förlorar".** I öppningsguiden, rundown-tabellen och turn/river-tabellerna sattes bedömningen tidigare bara utifrån 95 %-intervallet. I en simulering med 64 rutor och ingen verklig skillnad gav det i snitt 9 falska utslag. Nu krävs ett test som tål sneda pokerresultat (bootstrap över hela spelpass) och som tar hänsyn till att alla rutor testas samtidigt. I samma simulering blev det under 0,1 falska utslag. Bara det som klarar testet blir en regel.
* **Range-gränserna** testas nu helt utan information från testhalvan.
* **Kort all-in.** När den enda höjningen är en kort all-in räknas nästa spelares beslut som "mot en höjning", inte som "foldat till dig".
* **River-folds** räknas nu per handstyrka.
* **Säkerhet:**
  * Andra webbsidor i webbläsaren kan inte längre tömma databasen, starta analyser eller stänga programmet.
  * Bara adresser på den egna datorn accepteras.
  * Nätverksläget (`--lan`) kräver en kod som visas i terminalfönstret.
* **Robusthet:**
  * Ogiltiga datum ger ett tydligt meddelande.
  * Händer från andra konton läses inte om varje gång.
  * Byts databasen ut byggs fakta om automatiskt.
  * Beräkningar från arbetsprocesserna sparas i databasen.

## Flera varianter tillsammans (version 1.28)

* Under "Urval" kan du nu kryssa i flera varianter samtidigt, till exempel PLO4 och PLO6. Kombinera med "Senaste händerna" för att se de senaste 20 000 händerna över båda varianterna.
* Med flera varianter visas resultatdelen: vinst, all-in EV, rake, nivåer och kurvor. Läckor, öppningsguide, range-gränser och uppföljning visas bara när en enda variant är vald.

## Ändra urval direkt i rapporten (version 1.27)

* Överst i rapporten finns rutan "Urval", där du väljer variant, bordstyp (vanliga eller Rush & Cash), nivå, antal senaste händer och period. Tryck sedan Uppdatera analysen.
* Händerna ligger kvar i minnet mellan analyserna, så att byta urval går betydligt snabbare än den första inläsningen.
* Dina regler sparas nu per variant (PLO4, PLO5, PLO6). Träningssidan låter dig välja variant om du har regler för flera.

## Resultat per speltyp (version 1.26)

* Ny tabell överst i rapporten: resultat för alla inlästa händer, uppdelat på PLO4, PLO5 och PLO6, och på vanliga bord och Rush & Cash. Tabellen har också en rad för alla speltyper tillsammans.
* Varje rad visar händer, vinst, bb/100, all-in EV, rake och resultat före rake.
* Läckor, öppningsguide och range-gränser räknas fortfarande för en variant i taget, den du valt eller den du spelat mest.

## Handuppspelning (version 1.25)

* Händerna under "Gå igenom de här händerna" spelas upp vid ett bord med riktiga spelkort, stackar, insatser och pott.
* Du kan stega framåt och bakåt, hoppa till början eller slutet, dra i reglaget eller använda piltangenterna.
* Equity för dig och motståndarna visas i varje läge och räknas om när en ny gata delas ut eller någon foldar. Motståndare som visat sina kort räknas med de riktiga korten. Den som aldrig visade räknas som en slumpad hand, och det står vid bordet när det gäller.

## Följ upp och träna (version 1.24)

* **Dina regler.** När hela databasen analyseras gör programmet om de säkra slutsatserna till regler och sparar dem: range-gränser som bekräftats "för brett", "Folda" i öppningsguiden och rundowns som förlorar klart.
* **Följ upp.** En ny första del i rapporten visar, per regel och vecka, hur ofta du brutit mot reglerna och vad det förväntas kosta. Det fungerar även när du bara analyserar de senaste händerna.
* **Gå igenom händerna.** De tio dyraste och de tio senaste regelbrotten visas med hela handen uppspelad.
* **Träna.** På sidan "Träna dina öppningar" visas slumpade händer, och du väljer öppna eller folda. Facit kommer från dina egna regler. Hälften av händerna ligger nära gränsen.

## Databasen används alltid (version 1.22)

* Rutan "Analysera alla händer i databasen" är ersatt av "Använd inte databasen", som inte är ikryssad från början.
* Utan mapp eller filer analyseras alltid databasen, oavsett vad som är ikryssat.

## Tydligare när inga händer hittas (version 1.21)

* Startsidan visar var databasfilen ligger.
* Felmeddelandet säger exakt vad som är fel: databasen är tom, perioden innehåller inga händer, eller rutan för databasen är avmarkerad.
* Händer som sparats av en äldre version döljs inte längre utan förklaring. Programmet säger hur många det är och läser in dem igen när du anger mappen en gång.
* Från och med nu sparas originaltexten för varje hand, så framtida uppdateringar läser om databasen automatiskt.

## Inläsningen syns (version 1.20)

Överst i rapporten (och på kommandoraden) står vad som hände vid inläsningen: antal filer, händer som hittades, hur många som var nya och sparades, hur många som redan fanns, andra spel som hoppades över, händer som inte kunde läsas (med exempel) och den nyaste nya handen. Därunder står hur många händer databasen innehåller och vilka datum de täcker.

## Bara de senaste händerna (version 1.19)

Kryssa i "Analysera bara de senaste händerna" på startsidan och ange antal (standard 15 000). Programmet väljer de senaste händerna där du satt med, sorterade efter datum och tid. På kommandoraden: `--senaste` (15 000) eller `--senaste 30000`. Kan kombineras med perioden Från/Till.

## Simulering av rundowns (version 1.18)

1,1 miljon simulerade utdelningar (125 000 per grupp): en ren rundown mot två motståndare med spelbara händer (minst en nöt-egenskap), hela vägen till river utan satsning. Visar per lägsta kort: equity, hur ofta handen gör stege, hur ofta stegen är nötstegen, hur ofta den ändå förlorar, och hur ofta motståndaren har set eller bättre när du vinner. Ett färdigt resultat följer med programmet; `--simulera` (eller kryssrutan på startsidan) kör om det. Antagandet om motståndarnas händer påverkar svaren mer än antalet simuleringar.

## Rundowns: från vilket lägsta kort lönar de sig? (version 1.17)

Händerna grupperas efter lägsta kortet i handens högsta rundown (A–3, 4, 5, 6, 7, 8, 9, T eller högre). För rena rundowns (utan suited ess och högt par) visas resultat jämfört med fold med 95 %-intervall, medianpotten när du vann med en stege och hur ofta din stege förlorade vid showdown. Överst står ett svar i klartext om var gränsen går, och en tabell visar resultatet om du bara spelar rundowns från ett visst lägsta kort och uppåt.

## Turn: syna och fortsätta – eller folda direkt? (version 1.16)

För varje syn mot en turn-bet räknas hur handen slutade jämfört med att folda på turn (allt efteråt inräknat), uppdelat på vad som hände på river: synade river-bet, foldade, höjde, check-check, bettade själv. Raden "Alla turn-syner" svarar på om turn-synen var rätt; uppdelningen efter river är beskrivande eftersom den också beror på river-kortet.

## Lättläst rapport (version 1.15)

Rapporten börjar med **Det viktigaste** – de viktigaste slutsatserna i klartext (resultat, rake, starthänder, öppningar, river, läckor). Därefter en meny som hoppar till fem avsnitt: **Resultat**, **Preflop**, **River**, **Läckor** och **Detaljer och kontroll** (metod, statistik, DriveHUD-kontroll och datakvalitet längst ner).

**River: syna eller folda mot en bet?** visar per betstorlek (under 40 %, 40–60 %, 60–85 %, över 85 % av potten) hur ofta du foldat och hur dina syner gått jämfört med fold, med 95 %-intervall. Resultatet är exakt eftersom river-synen är handens sista beslut. En färgad tabell visar samma sak per handstyrka: grönt = klart lönsamt, rött = klart förlorande.

## Öppningsguide (version 1.14)

För varje position: hur dina öppningar (när det foldats till dig) gått jämfört med fold, uppdelat på vilka nöt-egenskaper handen har. "Folda" när hela 95 %-intervallet ligger under noll, "Öppna" när det ligger över, annars "Osäkert". Intervallen tar hänsyn till att händer från samma spelpass hänger ihop. Med många celler testade samtidigt kan enstaka utslag vara slump – lita mest på mönster som återkommer över flera positioner.

## Var går gränsen för lönsamma starthänder? (version 1.8)

För varje situation (öppna från HJ, CO, BTN, SB; försvara BB; mot öppning; mot 3-bet) räknar programmet ut hur brett det är lönsamt att spela:

1. Varje hand får en poäng från tolv egenskaper (nöt-egenskaper, färgstruktur, par, sammanhängning, låga kort m.m.). Vikterna lärs från dina egna beslut jämfört med fold, korsvaliderat: en hand får alltid sin poäng från vikter lärda på den andra halvan av dina spelpass.
2. Alla händer du fått i situationen rangordnas från topp 0 % till 100 %.
3. Resultatet jämfört med fold anpassas till en fallande kurva; gränsen är där den korsar noll. Felmarginalen (80 %) tas fram genom att dra om hela spelpass 300 gånger.
4. **"För brett"** visas bara om händerna bortom gränsen förlorar även i den halva av spelpassen som inte användes för att hitta gränsen (Bonferroni över alla situationer). I test där händernas kvalitet inte spelade någon roll gav det 0 falska larm på 30 körningar.

Gränsen gäller händerna du själv valt att spela – den säger inget säkert om händer du foldat.

Version 1.9: varje tiondel visar fyra exempel ur dina egna händer, och vid gränsen visas sex händer precis innanför (spela) och sex precis utanför (folda), med vilka nöt-egenskaper de har.

## Nöt-egenskaper (version 1.7)

Starthänderna delas också in efter Grinders Vaults regel för PLO6: spela händer med minst två av tre nöt-egenskaper – högt par (knektar eller bättre, inte trips), suited ess (2–3 kort i essets färg) och rundown (fyra valörer från 5 och uppåt med högst en lucka). Rapporten visar resultat per antal egenskaper, hur ofta du spelar dem från varje position och uppdelning på vilka egenskaper. Bevismotorns preflop-grupper använder nu den här indelningen (färre och större grupper ger bättre chans att bekräfta en läcka).

"Netto när spelad" är allt du vunnit minus allt du förlorat i händerna du frivilligt spelade (all-in EV, efter rake), inklusive mörkar du redan postat – inte samma sak som jämfört med fold.

## Egen databas (version 1.6)

Programmet sparar alla händer i en egen databas: `~/.plo_leak_cache/plo_leak.db`.

- **Första gången** läses alla händer in och de tunga beräkningarna görs, så det tar några minuter.
- **Därefter** läggs bara nya händer till. Exportera gärna bara de senaste händerna från DriveHUD, eller hela databasen igen: händer som redan finns hoppas över. Filer som inte ändrats läses inte alls.
- **Tunga beräkningar** (all-in EV och handstyrka) sparas per hand, så en ny analys av samma händer går flera gånger fortare.
- **Utan mapp** analyseras bara det som redan finns i databasen.
- **Period:** ange "Från" och "Till" (ÅÅÅÅ-MM-DD) för att bara analysera en viss tid, t.ex. händerna efter att du ändrat något i ditt spel.
- **Bara vissa filer:** avmarkera "Analysera alla händer i databasen".
- **Töm databasen** finns längst ner på startsidan. Dina originalfiler påverkas aldrig. Databasfilen kan också raderas när som helst; den byggs då upp igen.

Kommandorad:

```bash
python -m plo_leak ~/PLO/ny-export            # lägg till nya händer och analysera allt
python -m plo_leak                            # analysera bara databasen
python -m plo_leak --fran 2026-10-01          # bara händer från 1 oktober
python -m plo_leak ~/PLO/export --utan-databas  # som förut, utan databas
```

Databasen tar ungefär 1,5 kB per hand, alltså cirka 300 MB för 180 000 händer.

## Resultat per nivå (version 1.11)

Direkt under "Resultat och rake" visar rapporten en tabell per nivå ($0.5/1, $1/2 …) med händer, vunnet, bb/100, all-in EV (pengar och bb/100), rake (pengar och bb/100), bb/100 före rake och all-in EV bb/100 före rake, plus en totalrad. Nivåer med färre än 100 händer slås ihop till "Övriga". Samma tabell skrivs ut på kommandoraden och finns i filen till Claude.

## Resultat och rake (version 1.4–1.5)

Överst i rapporten finns en tabell med totalt (bb och pengar) och per 100 händer för: vunnet, all-in EV, rake + avgifter betald, vunnet före rake och all-in EV före rake. Rake + avgifter är det som dragits från pottar du vunnit (rake, jackpot och övriga GG-avgifter), alltså de pengar du hade fått utan rake. Rakeback ingår inte. Tabellen per nivå visar samma sak för varje nivå. Vinstkurvan har en tredje, streckad linje som visar hur den betalda raken växer hand för hand. Från version 1.13 finns samma graf även i dollar (faktiskt resultat, all-in EV och rake).

## Hur programmet hittar läckor (version 1.3)

Programmet visar bara läckor som är bekräftade. Råder det tvivel säger det ingenting.

I varje beslut kan du folda, och då kostar det exakt det du redan lagt i potten. För varje grupp av beslut (t.ex. "öppna Svag struktur från CO", "syna en turn-bet med svag hand + stort drag", "syna en river-raise") jämförs ditt resultat, räknat med all-in EV, med vad det hade kostat att folda.

1. **Två halvor.** Händerna delas i två fasta halvor per bord och tre-timmarsblock, så att händer från samma pass hamnar i samma halva.
2. **Upptäckt i halva A.** Alla grupper testas med en test som tar hänsyn till att pokerresultat är snedfördelade (Johnsons korrigering), och Benjamini–Hochberg används över alla tester.
3. **Bekräftelse i halva B.** Halva B har sökningen inte sett. Varje kandidat testas igen med kluster-bootstrap och Bonferroni-korrektion. Det krävs minst 100 tillfällen och minst 5 vinster över +10 bb i varje halva, och minst 0,3 bb förlust per gång i båda.
4. **Senare gator först.** En bekräftad läcka på t.ex. turn räknas bort från flop- och preflop-grupperna, så att samma förlust inte skylls på ett tidigare beslut.
5. **Kostnaden** räknas från halva B. En försiktig gräns ("minst") visas också. Kostnader för olika läckor kan överlappa och ska inte summeras.

En oberoende granskning har testat motorn på data utan läckor: falska larm i cirka 0,5 % av körningarna. Priset är att bara ganska stora läckor syns. Avsnittet **Hur stora läckor ditt urval kan se** visar gränsen för dina händer. "Ingen bekräftad läcka" betyder inte "ingen läcka".

### Borttaget i 1.3

- **"Troliga" läckor.** Tester på data utan läckor visade att de till stor del var brus.
- **River-coach (2.40).** River-modellen körs i programmet: vinstchans mot poolens visade händer i samma linje och EV per alternativ med rake, för varje river-beslut heads-up. Visas på Turn & river, i uppspelningen (på river) och i sessionsfilen. Delar av modellen som inte klarar kontrollen mot dina egna utfall visas bara som fingervisning. Folds och egna bets kan inte kontrolleras direkt mot utfall – bara modellens vinstchans kan det.
- **Tilt-läckan.** Den gick inte att skilja från effekter av bord, tid och motståndare.

### Rättat i 1.3

- All-in EV räknas utan GG:s EV Cashout-premie och från den gata där du själv gick all-in.
- "Receives Cashout" räknas inte som en vunnen pott.
- Att möta en raise räknas inte som att möta en bet. Besluten har nu egna grupper: "mot en raise".
- Straddle-option räknas inte som en öppning.
- En kort all-in-höjning räknas inte som en 3-bet.
- Blinds räknas rätt med en kort all-in SB.
- Ingen får etiketten SB när ingen small blind postats.

### Vad programmet inte kan

- Beslut på flop och turn när du själv bettar eller checkar först värderas inte, eftersom fortsättningen av handen inte går att räkna ut säkert. Syn, raise och fold mot bets och raises ingår.
- Det kan bara bevisa att något du *gör* förlorar mot att folda, inte att något du inte gör skulle vinna.
- Små läckor (under några bb per beslut) syns sällan ens med 180 000 händer.

## Få hjälp av Claude att tolka resultatet

Överst i rapporten finns knappen **Ladda ner fil till Claude**. Den sparar en fil med all statistik, testerna och ett urval anonymiserade exempelhänder. Ladda upp filen i chatten med Claude. Kommandoraden skriver samma fil automatiskt.

## Kontrollera att siffrorna stämmer

Avsnittet **Kontrollera mot DriveHUD** listar händer, vinst, all-in EV, VPIP, PFR, 3-bet, c-bet, WTSD med mera. Jämför med DriveHUD för samma händer.

## Tester

```bash
python tools/run_tests.py
```

Testerna körs mot bland annat 95 riktiga, anonymiserade GG PLO6-händer: pengarna ska gå jämnt ut i varje hand, all-in EV ska stämma med räkning för hand, och handstyrkan ska stämma exakt med en långsam referensberäkning. River-modellen testas end-to-end på en syntetisk pool.

## Testa utan egen data

```bash
python tools/generate_sample.py --hands 20000 --out sample_hands
python -m plo_leak sample_hands
```

## Äldre läge med riktvärden

`python -m plo_leak … --visa-hypoteser` visar de gamla, obevisade läckorna som bygger på riktvärden. Använd det bara som inspiration.
