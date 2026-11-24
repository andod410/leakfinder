# Leakfinder 2.70 – ändrings- och verifieringsrapport

Byggd för Andreas Ödman från den uppladdade versionen 2.69. Datum: 13 november 2026.
Detta är en fristående ändring av källkoden. Originalfilerna i 2.69 har inte ändrats.

## Start och uppgradering

1. Stäng den tidigare versionen.
2. Packa upp denna zip till en egen mapp.
3. Starta med den vanliga Mac- eller Windows-startfilen.
4. Låt programmet räkna om hela databasen och öppna en fullständig PLO6-analys innan du använder uppföljning eller tränaren.

Originalhänderna i din befintliga databas behålls. Beräkningscache, faktaversion, analysnycklar, snapshots och regler är versionsändrade. Första omräkningen kan ta några minuter. Äldre regler återanvänds inte som om de validerats med den rättade metoden. Gamla sparade rakebackkalkylatorvärden återläses inte automatiskt, eftersom de kan bygga på den felaktiga konverteringen av blandade nivåer.

Inga nya produktberoenden har lagts till. `python tools/run_tests.py` kör testsviten utan pytest. Med pytest installerat fungerar även `python -m pytest -q`.

## Rättningar

| Ärende från granskningen | Ändring i 2.70 | Avgränsning |
|---|---|---|
| LF-01: Läckor kraschar | Ett adapterlager ger undergrupper ett konsekvent visningsschema. Rått snitt märks som rått, inte som en påhittad krympt skattning. | Originalregelns data ändras inte av visningsadaptern. |
| LF-02: blandade riverunderlag | Riversituationer och avgiftsmodell filtreras med modellens faktiska handindex. | Datum kan fortfarande använda programmets uttryckliga större modellbas; PLO4 och PLO5 blandas inte in i en PLO6-modell. |
| LF-03: kända kort i sidopott | Alla kända kort förblir blockerade även om deras ägare inte får vinna just den potten. | Samma proportionella fördelning av observerad pottavgift används som tidigare. |
| LF-04: täckande stackar | Varje pott får sin egen låsningstidpunkt från bidragen. Senare checks bestämmer inte EV-gatan. | Händer med senare folds eller pottlager som inte säkert låsts före river behåller konservativt faktiskt utfall. |
| LF-05: holdout | Regler måste ha identisk exekverbar definition. Delning sker mellan hela sessioner. Bekräftelse kräver minst 20 kluster, korrigerat intervall och bootstrap. Valideringsfel sänker säkerheten. | En jämförelse mellan historiska syn- och höjningshänder blir inte oberoende kausal bekräftelse. |
| LF-06: beslutsfält | Spelare och relativ position uppdateras efter varje fold. Position avser dem som fortfarande kan agera. | Spelare kvar i potten inkluderar all-in-spelare; detta dokumenteras separat. |
| LF-07: felräknade nöt-outs | Unika träffkort räknas utan överlapp. Ett separat mått kontrollerar nästa gatas nöt-hand mot alla lagliga tvåkortskombinationer. | Detta är inte range-equity till river. De tidigare automatiska 9/12/13-outsreglerna för jam/syn/fold har dragits tillbaka. |
| LF-08: fel SPR | Exporten får pott vid beslut, pott efter syn och korrekt effektiv stack efter syn. | Äldre exportfält pot_bb och spr fortsätter betyda gatans start, för kompatibilitet. |
| LF-09: singulär regression | Tomma kolumner hanteras och bara identifierbara koefficienter visas. Kollinearitet mellan förlust och tid får inte godtyckligt räknas som förlusteffekt. | Icke identifierbara effekter märks uttryckligen; de betyder inte att effekten är noll. |
| LF-10: blandad nivå i kalkylator | Blandade urval visar direkt beräknad USD/timme separat. Kalkylatorns underlagsknappar använder enskilda nivåer. | Ingen omräkning av ett blandat bb-medel med median-big-blind. |

Ytterligare rättningar:

- Flop-/turnstyrka beräknas med heros egna kort borttagna ur motståndarens möjliga lek.
- Hela pottens avgift sparas separat för avgiftsmodellen; heros tilldelade rake används inte som om den vore pottens hela avgift.
- Kandidatbets på river begränsas till pott och effektiv stack. Överbet-inmatningar används inte som träningsdata för vanliga PLO-riverbets.
- River-modellens showdownselektion kvarstår som en metodbegränsning. Därför märks dess råd som hypoteser och promoveras inte till säkra fel bara för att modellkalibreringen är godkänd.
- Historiska hårdkodade riktlinjer markeras som historiska hypoteser, inte som ny oberoende validering av aktuellt urval.
- ”Upp till tio procent av slumpade händer slår dig” kallas inte längre nöten.
- Paus- och tidsanalyser beskriver samband. En mekanisk ny session efter 30 minuter är inte ett påstående om säker återhämtning.
- Testköraren upptäcker både gamla och nya testfiler och hanterar projektets använda fixtures utan extra testberoenden.

## Vad som inte har byggts

Ingen GTO-solver eller modell som kan bevisa det optimala beslutet i varje hand har lagts till. Rättningen gör inte historiska gruppmedel till kausala vinster. Osäkra råd har sänkts i säkerhetsgrad eller ersatts av uppgifter att granska; de har inte ersatts med andra obestyrkta facit.

All-in EV är fortsatt en blandning av justerade all-ins och faktiskt utfall i andra händer. Preflop används fortfarande Monte Carlo, normalt 1 500 eller 6 000 utfall. Flop och turn räknas exakt för de kända händerna. Varje pott använder sin egen låsningstidpunkt, medan handens etikett anger den tidigaste av dessa tidpunkter och equityfältet den första potten hero deltar i.

Run-it-twice kan behålla samma all-in-förväntan som ett runout: medelvärdet över två runouts har samma marginala förväntan. Det finns ett uttryckligt regressionstest för detta. Mer komplicerade händer kan fortfarande lämnas ojusterade på grund av senare actions eller okända kort.

## Verifiering

Den slutliga körningen, antal godkända tester och ekonomiska differenser redovisas i `VERIFIERING_2.70.md` och `testprotokoll/`. Full rå handhistorik och den lokala databasen ingår inte i leveransen.

Verifiering sker i Linux med Python 3.12. Mac-startfilens shellsyntax kontrolleras, men Mac-/Windows-installation har inte körts på respektive system. Rutter och mallar kontrolleras med hela PLO6-underlaget. Klientlogik för tränare, listor, replayer, grafer och bildreglage testas separat med DOM-/canvas-stubbar. Dessa ersätter inte en riktig webbläsare: visuell layout och faktisk PNG-nedladdning måste fortfarande kontrolleras lokalt.

## Export och kompatibilitet

Postfloptabellen behåller befintliga kolumner och lägger till:

- `pot_at_decision_bb`
- `pot_after_call_bb`
- `spr_after_call`
- `draw_outs`
- `nut_outs`

Tomma outsfält betyder inte beräknat. `draw_outs` är unionen av möjliga nästa kort som gör stege/färg. `nut_outs` betyder att ingen möjlig motståndarkombination slår handen på nästa synliga bord; delad nöt är möjlig. Måttet säger inte hur ofta handen vinner till river mot en actionsrange.

CSV-paketet innehåller en separat metodbeskrivning. JSON-exporten anger program- och metodversioner. Mottagande AI-agent bör använda kolumnnamn och metodbeskrivning, och skilja observerat utfall från bevisat beslut-EV.
