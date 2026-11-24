# Leakfinder 2.73 – ändringar

14 november 2026. Rättningar efter den externa granskningen av 2.72.2 (rapporten och jämförelsen finns i projektet).
Mål som förut: **maximera timlönen**. Inga nya spelråd – versionen gör mätningarna och etiketterna ärligare.

## Start
Packa upp i en egen mapp och starta med Mac- eller Windows-filen. Fakta räknas om automatiskt första gången (ny kolumn för
effektiv betstorlek, några minuter). **Kör nattkörningen en gång** – nattberäkning v2 räknas om från början (ca 45 minuter),
eftersom λ nu prövas upp till 0,5. Schemalägg nattkörningen igen (schemat pekar på versionens mapp).

## Rättade fel
1. **Stora zip-filer läses in.** En textfil över 200 MB i en zip hoppades över utan besked (din export på 273 746 händer
   gav 0 händer). Nu läses stora filer i delar, och det som ändå avvisas visas med skäl under Import.
2. **River-bluff-testet** kunde bli "klart" på fel grunder. Nu:
   - fold-andelen räknas bara på pott-bets (minst 85 % av potten, räknat på det motståndaren kan syna);
   - jämförelsen är pott-bet mot check, och båda måste finnas (minst 60 lägen var);
   - bet-andelen ska vara 35–65 %, högst var femte bet får vara för liten, och det krävs minst 20 pass;
   - siffrorna läses av bara vid 300 och 500 lägen – däremellan visas ingen fold-andel;
   - säkerhetsstopp när som helst om hela intervallet för fold-andelen ligger under 51 %.
3. **"Bekräftad" sätts bara av framåttestet.** River-bluffen i fokuskön är nu "trolig" (hypotes, uppskattad kostnad), och
   målet är 35 % överallt. En regel är bekräftad först när den frysta regeln håller på händer efter 13 nov och dagens
   regel har samma definition. Rutan "Om du tätar alla bekräftade läckor" räknar bara sådant (i dag: ingenting).
4. **Riktlinje #5 (drag mot all-in).** En fold får inte längre rådet "syna" – den markeras 🔎 för granskning, med kravet och
   antalet nöt-outs. Ingen vinst bokförs. Skäl: dina 873 syner i läget hade 42 % faktisk equity mot krav 20 %, men dina 411
   folder låg nära kravet.
5. **Acceptanstestet för nattberäkning v2** är omgjort (plan 2.73/2026-11-14):
   - "bättre än v1" räcker inte: prognosen ska också ligga inom ±5 procentenheter från faktisk all-in-equity;
   - fold-prognosen ska ligga inom ±10 procentenheter;
   - turen prövas med ett ekvivalenstest (medel visat inom ±0,05 bb/hand) och variansen ska bli minst 20 % lägre;
   - avläsning bara vid 20, 40 och 80 pass efter frysdatum, inga mellanresultat; första avgörandet är slutligt;
   - λ prövas på 0–0,5 (0,3 var högsta värdet och blev valt i 2.72).
6. **Frysdatum och teststart räknas i handtid**, inte i datorns tidszon (gränsen låg en timme fel i Sverige; inga av dina
   händer berördes).
7. **Fingeravtryck av de frysta reglerna** visas i översikten, morgonrapporten och nattkvittot. Nattkörningen varnar om det
   ändras. Postflop-riktlinjernas definitioner är låsta 2026-11-14 med eget fingeravtryck.
8. **Postflop-framåttestet** räknar minsta antal på beslut med känt utfall.
9. **GG-vakten:** går det inte att kontrollera om GG körs startar nattkörningen inte ("okänd" räknas inte som "körs inte").
   Programmets sidor är inte låsta när GG körs (ditt val 2026-11-14).

## Tillagt
- Djupexporten: `unmatched_bb` (det som inte kan matchas – samma som gamla `uncalled_return_bb`, som behålls),
  `hand_returned_bb` och `hand_returned_to_hero` (faktisk återbetalning enligt originaltexten). `METOD_2.73.txt`.
- River-coachen säger att bets värderas som **bet/fold** (alltid fold mot check-raise).
- Domen **"osäkert (svansvakt)"** när snittet ligger under noll men gruppen har färre än 5 stora vinster.
- Timlön per nivå varnar för dubbelräknade timmar när flera nivåer spelats i samma pass.
- `PROGRAMBESKRIVNING.md` är uppdaterad (avsnitt 13: vad granskningen ledde till och vad som är kvar).

## Medvetet inte gjort
- Gren för syn/återhöjning mot check-raise i river-modellen, hierarkisk modell för kostnader, full osäkerhet i
  range-gränserna, avgift per sidopott, viktad rangemodell i v2. Inget beslut vid bordet beror på dem innan framåttestet
  har data. De står som kända begränsningar i programbeskrivningen.

## Tester
160 av 160 med `python tools/run_tests.py`. 22 nya i `tests/test_v273.py`, bland dem granskarens motexempel: 600 små bets
utan checkar blir inte ett klart test, fokus blir inte "bekräftad" utan framåttest, acceptanstestet underkänner 40
procentenheters felkalibrering, samma frysgräns i tre tidszoner, okänd GG-status blockerar.
Inte kört på riktig Mac/Windows eller på din riktiga databas.

## 2.73.1 (14 nov) – "Visa urvalet" utan ny analys
- Urvalsraden har två knappar i stället för "Uppdatera" och kryssrutan "Analysera på urvalet":
  - **Visa urvalet** (standard, även Enter): byter bara urvalet. Resultat, all-in EV, EV-graf, dollar, sessioner och timlön
    räknas för urvalet. Läckor, regler och modeller visas från den senaste fulla analysen av samma variant/bord/nivå –
    **även om nya händer kommit in sedan dess**. Inget räknas om, så det går på någon sekund.
  - **🔬 Analysera urvalet**: kör analysen. Har du valt datum eller "senaste händerna" räknas läckor och modeller på just
    det urvalet, annars en full analys av alla händer i varianten (som gamla "Uppdatera").
- En rad överst på sidorna säger när läckor och modeller kommer från en tidigare analys (datum och antal nya händer sedan),
  eller att de inte är analyserade alls (ny bordstyp eller nivå som aldrig analyserats).
- "⚡ Nya händer" och den automatiska uppdateringen fungerar som förut.
- 165/165 tester (5 nya i `tests/test_v2731.py`).

## 2.73.2 (15 nov) – Översikten börjar med resultatet
- Överst på Översikt: nyckeltalen (händer, resultat, bb/100, all-in EV, rake, pengar, timlön), vinstkurvan och Det viktigaste.
  Prio-listan, framåttesten, river-bluff-testet och fokusläckan kommer därefter. Inget annat är ändrat.
