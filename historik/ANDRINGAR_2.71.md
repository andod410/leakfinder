# Leakfinder 2.71 – ändringar

13 november 2026. Mål från och med nu: **maximera timlönen**.

## Start
Packa upp i en egen mapp och starta med Mac- eller Windows-filen. Fakta och beräkningar räknas om automatiskt första gången (några minuter). Originalhänderna i databasen behålls.

## Sammanslagning
- **Grund:** den externt granskade 2.70 med rättningarna LF-01–LF-10. Det gäller EV-låsning per pott, kända kort i sidopotter, outs utan överlapp, SPR vid beslutet, position efter fold och strängare holdout.
- **Inlagt från Claudes 2.70:**
  - 🌙 Nattberäkning med start och paus på Exportera-sidan. Den fungerar på både PC och Mac, använder högst 8 processer och startar inte medan GG är öppet.
  - Knappen 📦 Exportera hela databasen.
  - 🏁 Prio-lista överst i Översikt och i sessionsfilen.
  - Riktlinjerna #13 (check-raise med set) och #14 (c-bet-storlek).
  - Kolumnerna `board`, `board_type` och `set_rank` i djupexporten.

## Nytt i 2.71
1. **Synbeloppsbuggen är rättad.**
   - En syn räknas nu som högst din kvarvarande stack.
   - Pott, `facing_pct` och `facing_size_pct` räknas på den pott du faktiskt kan vinna.
   - De tre händerna från granskningen ger nu rätt värden:

     | Hand | Syn | Pott efter syn |
     |---|---:|---:|
     | OM115885731 | 42,96 bb | 292,92 bb |
     | OM115916355 | 60,69 bb | 323,88 bb |
     | OM115961216 | 41,5 bb | 215 bb |

2. **Effektiv risk.**
   - Nya kolumner: `raw_amount_bb`, `effective_risk_bb`, `uncalled_return_bb` och `effective_bet_pct`.
   - Exempel: river-betten i OM115693387 får effektiv risk 41 bb, alltså 36,4 % av potten.
   - River-coachen räknar också bet-storlek på effektiv risk.
3. **`draw_calc_status`** finns på varje postflop-rad: computed / zero_outs / no_qualifying_draw / made_hand_not_evaluated / river / light_export. Ett tomt outs-fält betyder aldrig noll.
4. **`hourly_summary.csv`** i djupexporten.
   - Innehåller timlönen exakt som appen räknar den: total, per nivå, vecka och session.
   - Nivåtimmar överlappar i pass där du spelat flera nivåer. Raden `overlap` visar hur mycket, och de timmarna ska inte summeras.
   - Rakeback ingår inte, och det står i kolumnen `rakeback`.
5. **`METOD_2.71.txt`** beskriver vad varje mått betyder.
   - Utfall i spelade händer är inte beslut-EV.
   - Standardfel klustras per hand och per session.
   - Det står uttryckligen vad som inte räknas som bevis.
6. **Framåttest.**
   - Reglerna fryses 2026-11-13. De letas bara i händer före frysdatum och sparas oförändrade i `frysta_regler_PLO6_2026-11-13.json` i programmappen.
   - Reglerna mäts bara på händer spelade efter frysdatum. Översikten visar panelen 🔒 Framåttest.
   - En regel blir ✅ bekräftad först med minst 100 brott, minst 20 pass, ett korrigerat intervall under noll och ett godkänt bootstrap-test.
7. **Prio-listan** har en ny första rad: 💵 Spela $0.5/$1.
   - All-in EV på $1/$2 är −16,5 ± 4,1 bb/100 och på $0.5/$1 −5,4 ± 4,7 bb/100.
   - Det motsvarar ungefär −$105 per timme mot −$17 per timme, före rakeback.
   - Gå upp igen först när $0.5/$1 visar plus över minst 50 000 nya händer.
8. **Riktlinje #10** (drag mot höjning på floppen) visas inte längre. Agentens granskning drog tillbaka de fasta outs-gränserna, och nöt-outs har nu en ny definition. Regeln kan komma tillbaka om den håller i framåttestet.

## Medvetet inte byggt
- Motståndarprofiler per spelare: avstått enligt Andreas regel att bara använda poolstatistik.
- Rakeback i timlönen: tas med senare.
- Rekommendationer om pausgräns eller antal bord byggda på nuvarande data. Stoppregeln finns kvar som rutin och ska utvärderas framåt.
- Framåttest av postflop-riktlinjerna, som kräver att varje riktlinje skrivs om till situation plus rekommenderad handling. Det får komma i 2.72.

## Tester
120 av 120 godkända med `python tools/run_tests.py`. Sex nya regressionstester finns för 2.71: bugghänderna, river-överbet, multiway-pott utan begränsning, metodfilen, frysdatum och timlön med blandade nivåer.
