# Leakfinder 2.78 – ändringar (2026-11-18)

Bygger på 2.77.6 (se ANDRINGAR_2.77.md).

- 🧮 **12 nya solverlägen** (hämtade 18 nov, ligger i `privat/solver_extra.json`, läggs in automatiskt):
  öppnaren mot 3-bet (BTN mot BB, BTN mot SB, CO mot BTN, CO mot BB, UTG mot BTN, SB mot BB), BB kallsyn (BTN öppnar,
  SB 3-bettar), BB överkall (CO öppnar + BTN synar, BTN öppnar + SB synar), BB mot SB-limp, och 3-bettaren mot 4-bet
  (BB mot BTN, BTN mot CO).
- De nya lägena ingår i solverfacit: klara fel, Topp 3, träningsrutan, sessionsfilen och Solver-sidan.
- Träna starthänder: 🧮-läge för varje nytt läge. Händerna dras som om du tagit dig dit (t.ex. bara händer BTN öppnar
  i "BTN öppnade, BB 3-bettar"). Knapparna heter rätt (checka/höja mot limp).
- Fakta byggs om en gång vid första analysen (ny faktatabell `spx`, FACTS_VERSION 16).

## 2.78.1
- 🌙 "Starta direkt (GG är stängt)" vid nattkörningen (ikryssad som standard): hoppar över väntan på 10 minuter efter ny handhistorik. GG måste fortfarande vara stängt.
- v3 tränades inte: paketet scipy saknades på datorn. Det installeras nu av startfilen (requirements.txt), och nattkörningen säger tydligt till om det saknas.
- Sessionsfilen: solverraden hamnar på rätt beslut när en hand har flera (öppning och sedan svar på 3-bet, kallsyn, limp, 4-bet).
- Träna: höjningen heter rätt i de nya lägena (4-betta, squeeza, all-in).

## 2.78.2
- Träna och träningsrutan: varje solverläge förklaras utförligt – vilken position du har och vad som hänt före ditt beslut (t.ex. "Du sitter på BTN och ÖPPNADE. SB 3-bettade, BB foldade. Ditt beslut: …").
- Knappen "↩ Hela perioden" överst när ett datumurval är aktivt (t.ex. efter "Visa som urval" i grafen).
- v3-träningen använder alla kärnor utom en (låg prioritet): egenskaperna räknas i flera processer och de tre anpassningarna körs samtidigt. Första träningen går från ca 30 till ca 5–10 min på en 6-kärnig dator.
- Kärnor: nattkörningen (v2 och v3), inläsning och fakta använder alla kärnor utom en (tidigare högst 8). Windows 10600K: 11 processer. Mac M4-familjen: 9–15 processer beroende på modell. Varje process får en tråd i numpys räknebibliotek så att de inte trängs.
