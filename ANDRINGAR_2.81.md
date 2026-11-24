# Leakfinder 2.81 – ändringar (2026-11-19)

Resten av granskningen av 2.79.1. Regressionstester finns i `tests/test_v281.py` och `tests/test_v280.py`. 266/266 tester passerar, både med pytest och med `tools/run_tests.py`.

## Tester och slutsatser
- **Framåttest och hypoteser läses av vid fasta tillfällen:** 20, 40 och 80 spelpass efter startdatum, på exakt de första K passen (`seqtest.py`).
  - Felrisken delas på avläsningarna.
  - Första "håller" eller "håller inte" står kvar.
  - Senare händer ändrar aldrig ett avläst resultat.
  - Före 20 pass står det "för få".
- **Regelordningen har ett eget fingeravtryck** (`order_hash`). En regel blir "bekräftad" bara om samma regler ligger före den som i den frysta samlingen, alltså om den täcker samma händer. Den gamla `rules_hash` är oförändrad.
- **"Slår dig" på river delas upp** i strikt bättre (`beat_strict`) och delar (`tie_frac`).
  - Sessionsfilen visar strikt bättre med delning i parentes. En nöthand blir 0 % även när den ofta delar.
  - De frysta gränserna använder fortfarande det gamla måttet (bättre + ½ lika).
- **Riverförsöket, protokoll v2.1:** "ny stege" betyder nu att den högsta möjliga stegen ändras, t.ex. 9-hög → T-hög.
- **Showdownrisken** räknas på hela slumpade händer med blockers, i stället för 1 − (1 − f)^15. Fakta byggs om en gång (FACTS_VERSION 19).
- **Timlönens intervall** är en kvotskattning per spelpass och tar med variationen i speltakt. Förut hölls takten fast, och intervallet kunde bli noll.

## Nattberäkning v2
- **λ sparas per beräknad hand.** Byts λ räknas berörda händer om. Avläsningen använder bara rader med det låsta λ.
- **v1-jämförelsens baslinje** byggs bara av händer före frysdatumet, utan dina egna kort och med en reservoar per gata.

## Uppspelning
- **Equity:** kända kort hos en spelare som foldat räknas som döda. OM89894633 visar nu CO 19,4 % och BTN 80,6 % på floppen.
- **Potten:** en osynad bet eller höjning återbetalas när gatan är slut. Potten är 81,5 bb, inte 104,5.

## Solver
- **Extralägena fungerar utan grundlägen.** BB mot SB-limp (fri check) jämförs inte mot fold.
- **Inställningar i solverfilen** kan vara text eller lista, så den falska varningen försvinner.
- **Bortvald solverfil** läggs inte in igen vid nästa sidladdning eller omstart.
- **Texter:**
  - Träningslistan beskrivs som en trend bakåt, inte som en låst uppföljning.
  - SB-reglaget räknar höjning och limp tillsammans.
  - METOD-texten säger att sessionsfilen innehåller solverfrekvenser.

## Råd och vyer
- **Prio-listan** kallas "förvald studieplan" och är ingen uppmätt rangordning efter $/h.
- **Postflopråd med tidigare uppskattad kostnad** märks "uppskattning" och visas inte när analysresultatet är tomt.
- **Exportformuläret** är förifyllt med det aktiva urvalet: variant, bord, nivå, period och antal.

## Import
- **Kort BB:** rubrikens nivå behålls när BB postar kort (all-in) och SB stämmer med rubriken.
- **Zip-arkiv:**
  - Snabbkollen läser textfiler först, upp till 500 filer.
  - Hela arkivet, alla nivåer, har en gemensam storleksbudget.
  - Mer än 64 MB text utan någon ny hand avbryter läsningen med en orsak.
- **Bevakningen** visar ett synligt kvitto för ofärdiga händer och avvisat zip-innehåll, och läser om filerna nästa gång.

## Säkerhet och GG
- **Signerade cachefiler.** Cachefiler med pickle (analysresultat, holdout, senaste analysen, urvalscache, radcache) signeras med en hemlig nyckel per installation (`signcache.py`). En osignerad fil läses aldrig och byggs om i stället. Cachemappen får rättigheterna 700.
- **Kommandoraden** har samma GG-spärr som webben, och utvecklingsläget gäller även där. Kan GG-statusen inte läsas visas en varning.
- **Formulär:**
  - Ett formulär utan Origin/Referer avvisas. Undantaget är en nyare version på samma dator som stänger den här.
  - Uppladdningar tolkas inte innan skyddet har körts.
- **Nätverksläget:** koden byts mot en kaka och tas bort ur adressen.
- **Installation:**
  - `requirements.txt` har övre versionsgränser.
  - Mac-startfilen stänger bara servern som lyssnar på porten.

## Simulering
- **Fröet** ingår i cachefilens namn, och inställningarna sparar simuleringsversion och NumPy-version.

## Kvar, som medvetna val
- **Utvecklingsläget** låter programmet köras med GG igång. Solverdata döljs ändå. Detta gäller till 1 december.
- **SQLite-databasen** sparar händerna med pickle. Den är lika betrodd som databasfilen själv.
- **Nätverksläget** har inte HTTPS och ingen skrivskyddad mobilvy.
- **Frysgränserna** räknas från midnatt på kalenderdatumet.
