# Leakfinder 2.75 – ändringar

15 november 2026.

## 1. Träna öppningar med ett reglage (📏)
Under **Träna** finns nu "📏 UTG/CO/BTN/SB – öppna topp X %". **Reglaget är facit:** du väljer hur stor del av händerna du vill
öppna (0–100 %), och svaret är rätt om du öppnar händer inom topp X % och foldar resten. Dina regler visas bara som extra
information ("info") och ändrar inte facit. Hälften av händerna ligger nära gränsen, där det är svårast. Värdet sparas per position.

Handstyrkan är samma poäng som gränsreglerna använder (vikterna sparas i regelfilen vid nästa fulla analys).

**Förväntad winrate vid reglaget:** för varje % visas vad dina öppningar i positionen gett mot fold i hela databasen, som om du
öppnat exakt topp X %, i bb/100 i positionen och ≈ bb/100 på hela ditt spel. Bästa gränsen och en "nästan lika bra"-platå visas,
med en knapp som sätter reglaget där.
- Där du bara öppnat en del av händerna (de du själv valt) visas inget tal – bara "troligen sämre än vid X %". Händerna som
  tillkommer när du öppnar bredare är svagare än allt du redan spelar, och de du valde ut ser för bra ut.
- Ovanför din spelade range finns ingen data.
- På BTN i din data: bäst runt topp 30 % (platå ca 29–37 %); du öppnar 55 %.

Kurvan räknas vid nästa fulla analys av hela databasen (version 2.75) – innan dess står "ingen winrate-kurva än".

## 2. Positionsläckor (Preflop → Positionsläckor)
Per position: vilka första beslut preflop (situation × handling × nöt-egenskaper) som förlorat mot fold, med bb/100 totalt
och i positionen. "Säkert minus" = hela intervallet under noll; "bekräftad förlust" klarar dessutom korrigering för alla
grupper. Positionen vars säkra minus kostar mest står först, med öppningsgränsen från winrate-kurvan och en länk till reglaget.

## 3. Nattberäkningen har en egen kö
Startar du nattberäkningen från programmet kan du analysera, visa och exportera samtidigt. Natten väntar bara på andra jobb
under de korta stegen backup, inläsning och fakta, och har en egen databasanslutning. Den schemalagda nattkörningen var redan
en egen process och är oförändrad.

## 4. Nya hypoteser i framåttestet (frysta 2026-11-15)
Mäts bara på händer efter 15 november, räknas **aldrig som regelbrott** och rör inte de frysta reglerna från 13 november
(fingeravtrycket `919456190dbe31c4` är oförändrat). Egen definition med fingeravtryck `e4e93fbb9face71d`. Visas på Översikt (🧪).
- **H1** BTN: öppna bara topp 30 % (mäts: BTN-öppningar sämre än topp 30 % mot fold).
- **H2** SB/BB: folda 0 nöt-egenskaper mot en öppning i stället för att syna (mäts: synen mot fold).
- **H3** Rundown utan suited ess: syna i stället för att 3-betta (mäts: 3-beten mot fold; synen visas bara beskrivande).

Läses tidigast vid 100 händer och 20 spelpass per hypotes.

## 5. Rundown förklaras i texterna
Rundown (i programmet) = fyra valörer inom fem steg, högst en lucka, alla 5 eller högre – t.ex. 9-8-7-6 (4 i rad) eller 9-8-7-5
(rundown med lucka). Står nu i ordlistan under Följ upp, i preflop-tabellerna, positionsläckorna, hypoteserna och träningen.

## Behöver du göra något?
Kör **en full analys av hela databasen** (PLO6, utan period och utan "senaste händerna") så sparas handvikter och winrate-kurvor.
Ingen nattkörning behövs.

## Tester
180/180 med `python tools/run_tests.py`; 11 nya i `tests/test_v275.py`.

Tidigare ändringar: `historik/ANDRINGAR_2.74.md`, `historik/ANDRINGAR_2.73.md`.
