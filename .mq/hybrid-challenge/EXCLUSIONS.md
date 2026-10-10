# Uteslutna challenge-case

Här står varje case som tagits ur bruk, med skälet. Inget case raderas; poolen
och dess output ligger kvar så att skälet kan granskas i efterhand.

## Regeln

Ett challenge-case får inte användas om kandidatpoolen domineras av derivat från
samma logiska källdokument, exempelvis flera PNG-slides från samma deck. Ett
giltigt case ska innehålla minst tre distinkta logiska källdokument bland
kandidaterna.

Regeln är maskinkontrollerad av `scripts/check_candidate_source_diversity.py`
och skrevs ned **innan** någon fixtur hade märkts. Vid tidpunkten fanns alltså
inga relevansetiketter, så inget case kunde ha valts för det svar det ger.

## EXCLUDED_SOURCE_COLLAPSE

### keyword2

- **query:** `IGEL UMS Web App advanced search and management interface`
- **pool:** `keyword2-candidates.json` (behållen)
- **skäl:** `notebook-keyword` returnerade 10 kandidater som faller på 2
  logiska källdokument — 8 av dem `IGEL_UMS_Web_App_Guide_-_Slide_N.png`
  plus decket de kommer ur, och 2 renderingar av `03d-IGEL_UMS_Web_App`.
  I en sådan pool blir "hittade kanalen den förväntade refen" nästan samma
  fråga som "returnerade den något alls", och recall 1.0 säger inget om
  rankning.
- **ersatt av:** `keyword3` — `WQL syntax for querying thin client device
  properties`. Samma ämnesområde (WQL/UMS), 6 distinkta källdokument i
  keyword-poolen. Valet gjordes på poolens form; frågan byttes inte för att
  någon kanal gav ett visst utfall, och ingen etikett existerade än.

## EXCLUDED_NO_ON_TOPIC_CANDIDATE

### keyword3

- **query:** `WQL syntax for querying thin client device properties`
- **pool:** `keyword3-candidates.json` (behållen)
- **skäl:** poolen passerade diversitetsregeln med 6 distinkta dokument, men
  innehöll **inget** dokument vars titel matchar frågans särskiljande term.
  Indexets enda WQL-dokument (`Avancerad sökning med WQL i IGEL UMS Web App.html`)
  returnerades inte av någon kanal. Poolen domineras i stället av
  SafeNet/smartcard-material. Ett target-kanalcase vars pool saknar allt
  ämnesmatchande lämnar inget att märka `E` på och blir därmed omätbart —
  diversitet är inte ämnesmatchning.
- **ersatt av:** `keyword4` — `WQL query syntax for device properties in UMS`.
  8 distinkta dokument, WQL-dokumentet i poolen, noll slides.

**Redovisning av hur `keyword4` valdes.** Fyra formuleringar testades och valet
gjordes på ett lexikalt kriterium: finns det någon kandidat vars titel innehåller
frågans särskiljande term. Det är inte en relevansdom — ingen ref utpekades som
`expected` — men kriteriet är inte heller helt oberoende av relevans, eftersom
det förutsätter att ett ämnesmatchande dokument *borde* vara hämtbart. Gränsen är
tunn och står här i stället för att utelämnas. Operatören fattade beslutet.

## Avgjord fråga: enheten för codegraph

Första implementationen grupperade codegraph-refs per **fil**, eftersom en
symbol adresseras som `path#symbol`. Tillämpad likformigt fällde den regeln
`codegraph` på **fyra av sex** uppmätta pooler, inklusive alla tre case i den
befintliga platshållarsuiten:

| pool | keyword | vector | codegraph (fil) |
|---|---|---|---|
| keyword-candidates | 3 | 10 | **2** |
| vector-candidates | 5 | 10 | **1** |
| codegraph-candidates | 4 | 20 | **2** |
| keyword2 | **2** | 10 | 5 |
| codegraph2 | 6 | 10 | **1** |
| vector2 | 9 | 10 | 4 |

**Beslut (operatören): symbolen är enheten.** Skälet är att regelns princip är
*derivatförhållande*, inte samlokalisering. Tre funktioner i en modul är tre
distinkta kodenheter; åtta slides av ett deck är åtta renderingar av ett
dokument, vilket korpusen själv märker `derived`. Filgruppering mäter "delar
behållare", vilket är en annan egenskap.

**Ordningen är redovisad, inte bortförklarad.** Argumentet ovan är oberoende av
utfallet och höll före mätningen — men rättelsen gjordes efter den. Det är en
reell risk för efterhandsrationalisering och står därför här. Det som begränsar
den: inga relevansetiketter existerade vid beslutet, så inget case kunde väljas
för det svar det ger, och de tre valda poolerna (`keyword3`, `vector2`,
`codegraph3`) passerar under **båda** enhetstolkningarna.

Med rättad enhet fäller regeln numera endast `keyword2`. Det är en svagare
filtrering än den felaktiga versionen gav, och det är avsiktligt: den mäter det
regeln säger.
