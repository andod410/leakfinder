# Ändringar i 2.87 (levererad 2026-11-22)

Rättningar efter granskningen av 2.86 (rapport: "Granskning av Leakfinder 2.86").

**GG-spärren (K)**
- Solver, Träna och Översikt döljs i webbläsaren om servern slutar svara, till exempel för att vakten stängt programmet när GG startade. Sparade träningssvar rensas. Översikten har fått markören som laddar om sidan när GG startar (R7-01, R7-02).
- Redan skrivna zip-filer (djupanalys, export) kan bara hämtas när GG säkert inte körs (R7-03).

**Utvecklingsläget och GG-kontrollen**
- Utvecklingsläget gäller högst 24 timmar per påslag och aldrig från 2026-12-01 (R7-04).
- tasklist läses som bytes med OEM-kodsida. Tidigare kunde svensk Windows ge "okänd" varje gång (R7-05).

**Regler och texter**
- En enda tidsregel på alla sidor och i sessionsfilen: sluta efter 2 h (försäkring, inte bevisad EV-effekt), −500 bb, och 15 min paus efter förlorad pott > 175 bb. "4 h", "bara information" och "2 minuter" är borttagna (R6-04, R5-03).
- Regelrubriken blir "UTG: öppna inte händer där suited ess är enda styrkan" (R3-06).
- Prio 2 tar bort undantaget för lågt par + rundown och lägger till BTN cirka 45–49 %. Prio 3 rättar blindarnas 3-bet med KK/QQ + suited ess och lägger till AA-regeln (R3-07, R3-08, kvällsanalysen 21 nov).

**Mätning**
- Stoppregeln räknas per pass. När flera pass väljs anges "nåddes i X av Y pass" (R5-02, R6-01).
- Pauskontrollen mäter från förlusthandens slut och tillåter att händer som redan pågår på andra bord spelas klart (R5-01).
- Sessionsvy, flerpassvy och sessionsfil räknas om när rakeback-procenten ändras (R2-02).

**Data och drift**
- Händer med "time bank card" och showdown tolkas, så att de 8 avvisade händerna kommer med. PARSER_VERSION är höjd till 10, vilket gör att alla händer tolkas om en gång vid första start (R2-01).
- Inställningsfilen sparas atomiskt under lås med en .bak-kopia, och den följer med i nattens backup (R8-01).
- Nattkörningen på Windows skriver UTF-8 (chcp 65001, PYTHONIOENCODING), så att emoji inte kraschar den (R8-03).

300 tester (15 nya i test_v287).

## All-in EV: pott låst tidigt + senare fold (22 nov)
- Tidigare: om en pott låstes av en all-in (t.ex. kort stack preflop) och någon med pengar i potten foldade senare, räknades HELA handen med faktiskt resultat.
- Nu: potten frys efter den sista sådana folden (fold på river → faktiskt resultat som förut).
- Exempel OM117809443 (triss sexor): −$102,28 → +$31,49 (exakt uppräkning bekräftar).
- Hela databasen: 178 händer berörs (0,07 %), all-in EV +$1 139 totalt (1/2 +$1 098, 0.5/1 +$41); från 1 nov 12 händer, +$826.
- Test: test_v287.test_allin_ev_pot_locked_preflop_with_later_fold.
- Även: om någon foldar först på river efter din all-in före river räknas EV nu vid din all-in mot spelarna som gick till showdown (HUD-konvention) i stället för faktiskt resultat. I hela databasen gällde det 3 händer (OM98894034 +$416 → +$163, OM110076055 −$100 → +$41, OM117071533 −$10 → +$1). EV räknas därmed i alla händer där du är all-in före river och motståndarnas kort visas.
- Döda/missade blinds bestämmer inte längre all-in-nivån; pengarna läggs i huvudpotten (som GG). Fold-villkoret gäller bara den som har pengar i just den potten.
- Preflop-all-in räknas exakt (alla bord) i stället för 1 500–6 000 slumpade bord.
- Uppgradering: FACTS_VERSION 25, CALC_VERSION 5 och ny cachenyckel (ev3) – första analysen efter uppgraderingen räknar om all-in EV för hela databasen (tar längre tid en gång, cirka 20 extra minuter för preflop).
- Kontroll mot den oberoende granskningens egen kod: alla 325 händer + 73 händer med döda blinds stämmer inom $0,005.
- Text: GG:s EV Cashout ingår inte i EV men i resultatet (sessionsfil och LÄS_MIG).

## 2.87.1 (2026-11-22) – starta trots att GG körs
- Körs GG när du startar Leakfinder frågar kommandofönstret "Starta Leakfinder ändå? (j)". j = programmet startar; annat = avslutar som förut.
- Webbprogrammet stängs inte längre när GG startas medan det körs; ett meddelande skrivs i kommandofönstret.
- Oförändrat: Solver, Träna och Översikt är dolda medan GG körs, djupanalys-/export-zip kan bara hämtas när GG är stängt, och den schemalagda nattkörningen (ingen som kan svara) startar inte när GG körs.

## 2.87.2 (2026-11-23) – zip för valda sessioner
- Vyn "Graf och resultat" för flera valda sessioner har nu knappen "📦 Zip med händerna för de N sessionerna" (bara de sessionernas händer).
- Knappen i toppen heter nu "Djupanalys hela urvalet (zip)" och förklarar att den tar alla händer i urvalet. Det var den som gav zip-filen med hela databasen 23 nov 02:56 (251 909 händer, ingen sessionsfil).

## 2.87.3 (2026-11-23) – export när GG körs
- Djupanalys- och export-zip kan alltid hämtas. När GG körs visas först en bekräftelse ("Ladda ner ändå") i stället för spärren från 2.87 (R7-03).
