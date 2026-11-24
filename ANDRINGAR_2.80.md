# Leakfinder 2.80 – ändringar (2026-11-19)

Rättningar efter den oberoende granskningen av 2.79.1 (sex granskare, 19 nov). Varje rättning har ett regressionstest i `tests/test_v280.py`.

## Riverförsöket (v2)
- **Fold på river tog bort läget.** Läget krävde att motståndaren fanns kvar i handen efter rivern. En fold mot din bet gjorde därför att läget försvann. Foldprocenten blev systematiskt för låg (60 fold + 20 syn visades som 0 % fold och "avbryt"). Nu bestäms läget av bordet precis före river.
- **Protokoll v2.1**, ändrat 19 nov innan någon avläsning gjorts:
  - Avläsningarna gäller exakt de första 100 respektive 200 lägena i tidsordning. Senare händer ändrar aldrig ett avläst besked.
  - Grönt besked kräver även att bet-armen ger mer än check-armen (ITT).

## Import och bokföring
- **Ofärdiga händer sparas inte.** En hand utan SUMMARY-rad (avbruten nedladdning eller fil som fortfarande skrivs) låste tidigare fel resultat, t.ex. −27 i stället för −135. Filen läses nu om tills handen är komplett. Gamla ofärdiga händer tas bort en gång och läses in på nytt.
- **Filtrerad läsning spärrar inte längre en full läsning** av samma fil.
- **Avvisat zip-innehåll läses om** vid nästa kontroll.
- **Samma fysiska kort på två ställen** (visade kort, bord) gör att handen avvisas.
- **All-in EV före rake = equity × pott utan avgift.** Tidigare lades den faktiskt betalda raken till, och den är 0 när du förlorar. Ny faktakolumn `evr`, FACTS_VERSION 18, så fakta byggs om en gång.
- **Djupanalysens beslutsexport har återbetalningar igen.** Originaltexten följde inte med vid inläsningen.
- **facing_size_pct räknas i potten när betten gjordes.** En syn före dig gjorde förut betten mindre, t.ex. 33 % i stället för 50 %.
- **Härledda folds räknas i bordsläget.** Det ger rätt antal spelare och rätt position när fold-raden saknas.

## Råd och coachning
- **Nötstegen kallas aldrig "låg stege".** Båda misstagsmarkeringarna (låg stege, överpar mot höjning på parat bord) heter nu "granska", eftersom pris och range inte kontrolleras.
- **Set mot en motståndare som redan är all-in** får inget check-raise-råd.
- **Solvergrupper:** en hand utan ess i färg får aldrig gruppen "Suited Ace". "2+ Broadway" kräver två klädda kort.
- **4 h-flaggan** säger "gick sämre mot slutet" bara när klara fel faktiskt ökade efter 4 h. Annars står det att passet slutade minus.

## Timlön och nivåval
- **Samma aktiva tid överallt.** Flera markerade pass på Sessioner använder samma aktiva tid som Översikt, så samma händer ger samma $/h.
- **Nivåvalet jämför dollar per aktiv timme** och visar både bb/100 och $/h. +10 bb/100 på 0,25/0,5 blir inte "bättre" än +5 bb/100 på 1/2.
- **Rakeback-procenten räknas på alla dina händer** samma dygn, oberoende av urval. Bonus utan inläst rake visas separat.
- **Rakeback-kalkylatorn blandar inte nivåer.**

## Export och jobb
- **Två olika beställningar får aldrig samma jobb eller fil.** Djupanalysens filnamn är unikt per jobb.
- **Sessionszippen klipper inte tyst vid 5 pass.** Högst 60, med tydligt besked.

## Nattberäkning v2
- **Inget besked förrän alla händer är beräknade.** Ingen avläsning och inget slutbesked sparas förrän varje hand i avläsningens pass är beräknad. Tidigare kunde en avbruten kö låsa "inte avgjord" för gott.

## GG och solverdata
- Öppna flikar med Träna eller Solver laddas om inom 3 s när GG startar. Sparade solversvar i webbläsaren tas bort.
- Träna visar inte gamla solversvar när solvern är spärrad.

## Övrigt
- `tools/run_tests.py` har huvudvakt, `capsys`/`setenv` och samma solverskydd som conftest. 252/252 tester.

## Inte åtgärdat än (kvar från granskningen)
- "Slår dig" räknar lika som halv förlust. De frysta gränserna bygger på det måttet, så det ändras inte mitt i testerna.
- Upprepade avläsningar i framåttest och hypoteser. Regelordning i fingeravtrycket.
- λ per rad i v2. Exportformulärets förval. Utvecklingsläge och CLI utan GG-vakt (ditt val, gäller till 1 dec).
- Pickle i lokala cachefiler. Låsta beroenden.
- Uppspelningens equity efter fold och potten efter osynad höjning.
- Showdownrisk-formeln. Kort BB på andra nivåer. Zip med fler än 50 informationsfiler.
- Simuleringens frö i cachenyckeln.
