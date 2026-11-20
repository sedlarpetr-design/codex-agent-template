# Roadmapa Codex Agent Platform

| Milník | Rozsah |
|---|---|
| V1.0 | **Vydaná.** Codex CLI na linuxovém serveru ovládaný z mobilu přes SSH. Akceptace zahrnuje konzolový běh se šablonou a auditem, skutečné odmítnutí zápisu sandboxem Codexu, izolované scénáře a schválenou baseline. |
| V1.1 | Kanálový kontrakt a adaptér Slack se schvalováním a kontraktními testy. |
| V1.2 | Adaptér Teams se stejným kontraktem, identitou a řízením oprávnění. |
| V2.0 | Firemní instalace, oddělení zákazníků, migrace, návrat, sledování a postupné aktualizace. |

V1.0.0 byla vydaná pro Codex CLI na Linuxu přes SSH. Vydaný commit je `239943b78c71d3b4f5deabe4a306705beffcf19d`. [Tag v1.0.0](https://github.com/sedlarpetr-design/codex-agent-template/tree/v1.0.0)

Podrobnosti a akceptační podmínky jsou v [architektonické roadmapě](Codex_Agent_Platform_architektura_roadmap_a_zadani_pro_Codex.docx). Testování jádra používá stávající šablonu zadání a výstupu. [Akceptační kritéria V1.0](TESTING.md#akceptace-v10) jsou pro tento milník rozhodující. Přejímka Codex Desktopu je mimo rozsah V1.0. Samostatné rozhraní pro vstupní kanály vznikne s prvním adaptérem.
