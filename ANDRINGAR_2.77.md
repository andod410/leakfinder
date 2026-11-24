# Leakfinder 2.77 – ändringar (2026-11-18)

**Viktigast:** GG förbjuder från 1 dec all pokermjukvara som körs samtidigt som klienten. Leakfinder startar inte när GG körs och stänger sig själv inom 5 sekunder om GG startar. Analysera efter passet.

- 🛑 GG-stopp (programmet och nattkörningen).
- 🧮 Solvern är facit preflop: klart fel = solvern gör handlingen < 1 %, tveksamt = 1–10 %.
- 🎯 Översikten har en enda Topp 3. Allt annat ligger under "Mer". 🚀-panelen är borttagen.
- 🏋️ Träningsruta under Solver & träning: dina tre lägen med flest fel senaste 7 dagarna, tumregler, egna exempel, vecka för vecka.
- Träna starthänder: nya 🧮-lägen med solvern som facit.
- Sessioner: omdöme = klara fel per 100 händer. Pass > 4 h varnas bara om du ligger minus i all-in EV eller om felen ökat efter 4 h. 2 h-regeln är inte längre en läcka.
- Sessionsfilen: solverns frekvens per preflopbeslut, klara fel per pass, återkommande misstag (överpar mot höjning på parat bord, låg stege på fyrstegebord, syn mot 4-bet utan par = granska).
- 🎲 River-bluff-test v2 från 19 nov: river ♥️/🔷 = betta ¾ pott, ♠️/☘️ = checka (bara när rivern ändrar nöten). v1 visas inte.
- Rakeback: veckoformulär (från 1 dec).
- Dolda råd som motsäger solvern: UTG suited ess-regeln, hj_sa_low, bb_0nut_hu, låga par, AA i position 3-bet, river-bluff var tredje gång. Nedgraderade: höj tvåpar mot bet, bluffa oftare multiway, c-bet-storlek.
- River-coachens rader visas inte när modellen inte klarar kontrollen.
- Menyn: Aggression, Utveckling, När du vinner och Dela ligger under "Mer".

Kvar till 2.77.1: skuggmodell v3, rutan för nya solverlägen (formatet kontrolleras när solvern är uppe igen), graferna (datum i hover, markera med musen, valfritt antal sessioner).

## 2.77.1
- Träna starthänder: tydlig rad om solverns facit är på, och varför inte annars (ingen solverfil, GG körs). 🧮-läget väljs först.
- Reglaget 📏 startar på solverns öppningsfrekvens per position.

## 2.77.2
- Solverfilen följer med i mappen `privat/` och läggs in automatiskt första gången – ingen uppladdning. Mappen tas aldrig med i kodpaketet till Claude-projektet, i export eller i delning.

## 2.77.3 (efter Claudes test på riktig data)
- Sessionsfilen: solverraden visas bara vid första preflopbeslutet (inte vid syn mot 3-bet senare i handen).
- Den gamla fokusen "river-bluff var tredje gång" är borta ur sessionsfilen och fokuslistan (ersatt av test v2).

## 2.77.4
- Rakeback mäts per dygn från 18 nov (GEMs intjänade, GEM-värde eller kurs per GEM, leaderboard och övrigt mot dygnets rake), med summering per vecka.

## 2.77.5
- GEM-kursen bestäms vid inlösen (datum, GEMs, $). Före första inlösen används en planerad kurs. Rakeback visas både kontant (leaderboard + övrigt) och med GEMs.
- Dygnet följer GG:s leaderboard: 09:00–09:00 vintertid, 10:00–10:00 sommartid (08:00 UTC).

## 2.77.6
- 🌙 Skuggmodell v3 (`night3.py`): motståndarens range efter hans linje, lärd från visade händer, med solverns preflop-ranges (vikt w^β, β skattas – poolen spelar bredare än solvern). Anpassas en gång vid nattkörningen på händer före 19 nov (40 dagar), kalibreras korsanpassat och fryses med fingeravtryck. Förregistrerat test på dina heads-up river-beslut efter 19 nov (A bättre än v2, B kalibrering ±5 pe, C bättre än slump; 20/40/80 pass). Status under Exportera → nattberäkning. Ger inga råd.
- Grafer: datum och tid i hover; dra med musen för att markera ett stycke (resultat, all-in EV och bb/100 för markeringen) och "Visa som urval".
- Sessioner: välj valfritt antal, knappen "📈 Graf och resultat" visar dem tillsammans (resultat, all-in EV, EV per timme, rake, klara fel, graf). Sessionsfil för fler än 5: sammanställning + de 20 största potterna totalt.
