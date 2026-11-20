# Šablona týmu Codex agentů

Univerzální základ pro jednu hlavní relaci Codexu a projektové specialisty. Profil `analytik` porovnává podklady a dokládá zjištění. Profil `overovatel` dostává původní zadání, zdroje a skutečný výstup. Koordinátor může současně spustit až dva podagenty včetně dvou instancí téže role.

## Rychlý start

1. Otevři repozitář v Codexu jako důvěryhodný projekt. Pro ukládání auditu na místním hostu je potřeba `python3` a schválené [projektové hooky](.codex/hooks.json). V terminálu je zkontroluješ a schválíš přes `/hooks`.
2. Napiš nebo nadiktuj úkol hlavní relaci. Pro strukturované zadání použij [šablonu úkolu](templates/task.md).
3. Výběr specialisty můžeš říct přímo. Koordinátor předá práci podle [dílčího zadání](templates/assignment.md) a převezme ji podle [šablony výsledku](templates/result.md).

Příklad zadání v jednom chatu:

> Spusť souběžně dvě instance profilu analytik. První ať vypočte rozdíl mezi 15 a 12, druhá mezi 27 a 20. Předej oba výsledky ověřovateli spolu s tímto zadáním, ať výpočty přepočítá. Uveď, která dvojice má větší rozdíl, a připoj jeho verdikt.

Při výhradách má koordinátor nejvýše dvě kola oprav. Bez schválení po druhém kole vrátí úkol uživateli s důvodem. Další roli vytvoř z [profilu specialisty](templates/specialist.toml), přejmenuj pole `name` a ulož profil do `.codex/agents/`.

## Projektové dokumenty

- [Implementace a testování V1.0](docs/Codex_implementace_testovani_V1_0.docx)
- [Architektura, roadmapa a zadání pro Codex](docs/Codex_Agent_Platform_architektura_roadmap_a_zadani_pro_Codex.docx)
- [Testování a release management V1–V2](docs/Codex_Agent_Platform_testovani_a_release_management_V1-V2.docx)

## Evidence běhů

Schválené lokální hooky ukládají minimum automaticky do `.runs/<session_id>/audit.jsonl`. Každý záznam obsahuje čas UTC a ID úkolu. Závěrečný záznam obsahuje stav, výsledek ověření, počet oprav a provedené akce podle koordinátora. Záznamy událostí zachycují také vlastní verdikt ověřovatele, start a konec podagentů a názvy nástrojů, pro které Codex hook zavolal. Vyvolání nástroje samo nedokládá úspěch externí akce.

Audit ukládá identifikátory a krátké hodnoty. Text zadání, výstupy modelu, parametry a odpovědi nástrojů se do něj nekopírují. Chybějící nebo neplatný závěrečný řádek se zaznamená se stavem `audit_neuplny`. Podrobný audit lze vyžádat zvlášť do `.runs/<run_id>/audit.md`. Git složku `.runs/` ignoruje.

## Oprávnění k akcím

Projekt ve výchozím nastavení používá sandbox pouze pro čtení a předává žádosti o rozšíření oprávnění uživateli. Vestavěné aplikace a pluginy jsou ve výchozím projektu vypnuté. Když úkol vyžaduje zápis, odeslání nebo nasazení, musí běžet s oprávněním pro určený cíl. Ověřovatel přitom dál rozhoduje pouze o kvalitě výstupu.

Pokud host dědí vlastní MCP servery, jejich přístup vynucuje správce hostu v `requirements.toml` a cílová služba. Prázdná spravovaná tabulka `[mcp_servers]` servery vypne, případně správce povolí konkrétní server a omezí jeho účet či nástroje. Pro neobcházené omezení sandboxu používej také spravovanou konfiguraci hostu. [Schvalování nástrojů](https://learn.chatgpt.com/docs/agent-approvals-security) · [Spravovaná oprávnění a MCP](https://learn.chatgpt.com/docs/enterprise/security-cookbook#allow-only-approved-mcp-servers)
