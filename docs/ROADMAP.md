# Roadmapa Codex Agent Platform

| Milník | Rozsah |
|---|---|
| V1.0 | **Vydaná, ověřeno ve V1.0.0.** Codex CLI na linuxovém serveru ovládaný z mobilu přes SSH. Akceptace zahrnuje konzolový běh se šablonou a auditem, skutečné odmítnutí zápisu sandboxem Codexu, izolované scénáře a schválenou baseline. |
| v1.1.0 | **Vydaná.** Dokončení jádra šablony, širší testovací pokrytí, metriky a report schématu 2. |
| v1.2.0 | **Navrhovaná.** Ověřování projektových výstupů, sedmipoložkový report po kritériích a vzor lokální regrese. |
| Adaptér Slack | **Odloženo bez přidělené verze.** Kanálový kontrakt a adaptér se schvalováním a kontraktními testy. |
| Adaptér Teams | **Odloženo bez přidělené verze.** Adaptér Teams se stejným kontraktem, identitou a řízením oprávnění. |
| V2.0 | Firemní instalace, oddělení zákazníků, migrace, návrat, sledování a postupné aktualizace. |

V1.0.0 byla vydaná pro Codex CLI na Linuxu přes SSH. Vydaný commit je `239943b78c71d3b4f5deabe4a306705beffcf19d`. [Tag v1.0.0](https://github.com/sedlarpetr-design/codex-agent-template/tree/v1.0.0)

Podrobnosti a akceptační podmínky jsou v [architektonické roadmapě](Codex_Agent_Platform_architektura_roadmap_a_zadani_pro_Codex.docx). Testování jádra používá stávající šablonu zadání a výstupu. [Akceptační kritéria V1.0](TESTING.md#akceptace-v10) jsou pro tento milník rozhodující. Přejímka Codex Desktopu je mimo rozsah V1.0. Samostatné rozhraní pro vstupní kanály vznikne s prvním adaptérem.

## Navazující úkoly

Vydaný rozsah a důkazy V1.0.0 uvádí [přehled pokrytí](TESTING.md#pokrytí-a-důkazy). Níže je vydaný rozsah jádra, návrh projektového ověřování a plán odložených adaptérů.

### Dokončení jádra ve v1.1.0

Vydaná **v1.1.0** dokončila jádro šablony. Rozšířila testovací pokrytí a metriky, zavedla formát reportu schématu 2 a zachovala způsob zadávání úloh v CLI. Baseline jádra byla schválena a release gate vrátila `PASS`. [Důkazy z přejímky](TESTING.md#přejímka-kandidáta-jádra)

| Úkol | Stav a plán |
|---|---|
| Širší bezpečnostní scénáře | **Částečně pokryto.** V1.0.0 ověřila podvržený verdikt, zakázanou akci a ochranu zápisu. v1.1.0 pokrývá také pokyn k nepovolenému zápisu v nedůvěryhodném podkladu. Další varianty a širší cíl přibližně 30 scénářů zůstávají otevřené. [Důkazy](TESTING.md#pokrytí-a-důkazy) |
| Důvěrnost reportů | **Částečně pokryto.** V1.0.0 omezuje obsah auditu a nativní diagnostiky. v1.1.0 opravuje průnik zadání a textu výjimky do reportu a přidává lokální regresi. Důvěrnost mimo projektový audit a reporty je otevřená. [Důkazy](TESTING.md#pokrytí-a-důkazy) |
| Izolace zápisů analytiků | **Částečně pokryto.** V1.0.0 doložila překryv běhů a samostatné výsledky zpráv. v1.1.0 ověřuje samostatné nativní výstupy i převzetí obou koordinátorem. Izolace dvou zápisů v režimu s povolenými zápisy zůstává otevřená. [Důkazy](TESTING.md#pokrytí-a-důkazy) |
| Kontrolní sada a limity | **Částečně pokryto.** Runner ukládá latenci a dostupné údaje o tokenech. Návrh oddělené kontrolní sady je v dokumentaci testování. Její zavedení a prahy podle více srovnatelných měření zůstávají otevřené. |
| Druhý model ověřovatele | **Otevřené rozšíření.** Podle výsledků kontrolní sady posuď, zda druhý model zlepší odhalování chyb a jak ovlivní latenci a náklady. |

### Projektové ověřování v navrhované v1.2.0

Návrh přidává jednotný report pro projektová kritéria, pravidlo pro chybějící důkaz a místní regresní vzor. Adaptéry Slack a Teams zůstávají odložené bez přidělené verze. [Ověřování projektových výstupů](TESTING.md#ověřování-projektových-výstupů)

### Adaptér Slack (odloženo bez přidělené verze)

| Úkol | Stav a plán |
|---|---|
| Slack – kontrakt a stav | **Odloženo do milníku Adaptér Slack.** Zaveď verzovaný kontrakt úkolu a výsledku. Deduplikuj příchozí události a udrž stav úkolů i schválení po restartu. |
| Slack – limity a schvalování | **Odloženo do milníku Adaptér Slack.** Nastav časové a nákladové limity. Popiš a otestuj životní cyklus schválení akcí od žádosti přes rozhodnutí a expiraci po provedení. Oprávnění, povolené nástroje a síťová spojení vynucuj technicky mimo model. |

### Adaptér Teams (odloženo bez přidělené verze)

| Úkol | Stav a plán |
|---|---|
| Registrace a tok dat | **Odloženo do milníku Adaptér Teams.** Ověř registraci integrace, dosažitelnost HTTPS endpointu a tok dat od události přes zpracování po doručení výsledku. Použij verzovaný kontrakt z milníku Adaptér Slack. |
| Uzavřené firemní sítě | **Odloženo do milníku Adaptér Teams.** Posuď samostatnou bránu jako jednu z možností a ověř, jak by ovlivnila dostupnost endpointu a hranice toku dat. |

### V2.0 – firemní nasazení

| Úkol | Stav a plán |
|---|---|
| Izolace instalací | **Odloženo do V2.0.** Rozhodni o izolovaných instalacích a podmínkách případného sdíleného provozu. |
| Manifest a rozšíření | **Odloženo do V2.0.** Popiš modelové profily v manifestu, pravidla zákaznických rozšíření i pořadí slučování konfigurace a řešení konfliktů. |
| Data a audit | **Odloženo do V2.0.** Urči umístění zpracování dat, dobu uchování, přístupová práva a ochranu auditu. |
| Distribuce | **Odloženo do V2.0.** Prověř uzamčení závislostí a ověřitelnost vydaných artefaktů. Podle způsobu distribuce posuď podpis a SBOM. |
| MCP | **Odloženo do V2.0.** Posuď MCP u prvního konkrétního konektoru navrženého pro tento způsob integrace. Stanov mu vlastní politiku oprávnění. |
| Provozní telemetrie | **Odloženo do V2.0.** Posuď OpenTelemetry podle provozních potřeb a podle toho, jaké signály lze sbírat s ohledem na pravidla ochrany dat. |
