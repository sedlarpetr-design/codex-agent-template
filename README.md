# Šablona týmu Codex agentů

Univerzální základ pro jednu hlavní relaci Codexu a projektové specialisty. Výchozí profil `analytik` porovnává podklady a dokládá zjištění. Profil `overovatel` samostatně kontroluje výstupy proti původním kritériím a důkazům. Koordinátor může souběžně použít až dvě instance podagentů, včetně dvou instancí téže role. Rozdělení práce zůstává u koordinátora podle instrukcí profilu. Nastavení V1 omezuje delegování také technicky na jednu úroveň.

## Rychlý start

1. Otevři tento repozitář v Codexu jako důvěryhodný projekt.
2. Napiš nebo nadiktuj úkol hlavní relaci. Pro strukturované zadání použij [šablonu úkolu](templates/task.md).
3. Výběr specialisty můžeš říct přímo. Koordinátor předá práci podle [dílčího zadání](templates/assignment.md) a převezme ji podle [šablony výsledku](templates/result.md).

Příklad zadání v jednom chatu:

> Spusť souběžně dvě instance profilu analytik. První ať v dvojici 12 a 15 vypočte rozdíl druhého čísla vůči prvnímu, druhá ať totéž udělá pro 20 a 27. Předej oba výsledky ověřovateli, aby výpočty přepočítal. Uveď, která dvojice má větší rozdíl, a připoj jeho verdikt.

Pro další projekt vyjdi z tohoto repozitáře a uprav pravidla v [AGENTS.md](AGENTS.md). Další roli vytvoř z [profilu specialisty](templates/specialist.toml), přejmenuj pole `name` a ulož profil do `.codex/agents/`. [Dokumentace vlastních agentů Codexu](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)

## Evidence běhů

Koordinátor uvádí přehled předávek a kontrol v závěru. Pokud zakázka vyžaduje soubor s auditem, může ho uložit do `.runs/`, kterou Git ignoruje. Pro technické události neinteraktivního běhu lze použít `codex exec --json`. [Strojově čitelné výstupy Codexu](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)
