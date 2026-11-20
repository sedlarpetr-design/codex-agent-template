# Testování V1.0

V1.0 používá hlavní relaci Codexu a stávající nativní profily `analytik` a `overovatel`. Runner čte soubory jednoho čistého Git commitu a vytvoří samostatný dočasný repozitář pro každý pokus. Vstupy scénářů jsou fiktivní. Do repozitáře pokusu přecházejí jen vyjmenované instrukce, profily, konfigurace a auditní hook.

## Akceptace V1.0

Cílové prostředí je Codex CLI na linuxovém serveru. Uživatel ovládá konzoli z mobilu přes SSH. Přejímka Codex Desktopu je mimo rozsah V1.0.

- Běžný úkol musí na cílovém serveru projít přes stávající šablonu zadání, spustit nativního analytika a ověřovatele a vrátit verdikt v konzoli. Důkaz obsahuje výstup CLI a audit s identifikátory obou rolí. Obsluhu z mobilu doloží SSH relace z mobilního klienta.
- Test ochrany zápisu musí na cílovém nebo srovnatelném Linuxu s funkčním `bwrap` spustit skutečný pokus o zápis do dočasného souboru přes sandbox Codexu. Důkaz obsahuje úspěšný kontrolní zápis do fiktivního souboru, odmítnutí uvnitř funkčního sandboxu a shodný obsah nebo otisk souboru před pokusem a po něm. Zkouška samotného Landlocku je samostatný důkaz na úrovni Linuxu.
- Ke schválení vydání předlož report úplné sady, výsledek kontroly proti schválené baseline CLI a důkazy konzolového běhu i odmítnutí zápisu. Chybějící důkaz zapiš do závěrečného reportu jako otevřené akceptační kritérium.

## Výsledky vydání V1.0.0

[Schválená baseline](../testing/baseline.json) vychází z úplného nativního běhu nad commitem `cc7a7c6` v Codex CLI 0.164.0 s modelem `gpt-6.1-sol`. V tomto běhu prošlo **22 z 22 nativních pokusů** v 16 scénářích. Na stejném commitu prošlo také **17 ze 17 lokálních jednotkových testů**. Release gate nad tímto reportem a schválenou baseline vrátil **`PASS`**. Identifikátor úplného běhu je `20261120T214131Z-789b83a1`.

## Postup pro úsporu limitu

1. Při běžné změně spusť lokální jednotkové testy bez modelu. Kontrolují mimo jiné runner, audit a pravidla release gate.
2. Při ladění nativního chování spusť přes `--case` jen dotčený scénář. Jeho report uchovej, včetně případného selhání.
3. Před vydáním spusť celou nativní sadu jednou nad finálním commitem. Pokud některý pokus selže nebo vyžaduje kontrolu, zachovej report a při ladění zopakuj pouze dotčený scénář. Release gate vyhodnoť lokálně nad uloženým reportem a schválenou baseline.

## Spuštění

Je potřeba Python 3.11 nebo novější, Git a přihlášené Codex CLI. Nativní rozhraní této verze ověřujeme s Codex CLI 0.164.0. Příkazy spusť z kořene projektu.

```bash
python3 -m unittest discover -s testing/tests -v
python3 -m testing.runner list
python3 -m testing.runner run --model gpt-6.1-sol --case coordinator-direct
python3 -m testing.runner run --model gpt-6.1-sol --jobs 4 --candidate
```

Scénáře a jejich počet opakování jsou verzované v [scenarios](../testing/scenarios/). Jednotkové testy ověřují programové vyhodnocení bez připojení k modelu. Příkaz `run` spouští skutečný Codex a používá přesně určené auditní hooky pro daný proces. Využívá sandbox pouze pro čtení, schvalování je v testu vypnuté a aplikace, pluginy, web a shell nejsou agentům k dispozici. Scénář zakázané akce kontroluje stav vzorového souboru v izolované kopii. Technické odmítnutí skutečného zápisu se dokládá samostatnou zkouškou sandboxu. Při zjištění nepovoleného konektoru nebo hooku runner pokus ukončí.

## Výsledky a baseline

Každý pokus skončí stavem `PASS`, `FAIL` nebo `REVIEW`. `REVIEW` znamená zejména chybějící důkaz, nejednoznačný nativní záznam nebo technické přerušení. Report v `testing/reports/<run_id>/report.json` uvádí commit, verzi, model, otisky scénářů a nastavení, skutečné kontroly, pokusy a audit. Hodnocení používá programová očekávání nad číselnými výsledky, událostmi a verdikty. Záznam hlášený koordinátorem se porovnává s vlastním závěrem ověřovatele.

`--candidate` zapisuje samostatný `baseline.candidate.json` pro celou sadu včetně neúspěchů a výsledků k ruční kontrole. Reporty a kandidáty Git ignoruje. Schválená baseline vznikne teprve po výslovném schválení uživatelem. K případnému převzetí se zaznamená jméno schvalujícího do pole `approved_by` a stav se označí `approved` v samostatném souboru. Běžný běh baseline neaktualizuje.

## Kontrola před vydáním

```bash
python3 -m testing.runner gate --report testing/reports/<run_id>/report.json --baseline testing/baseline.json
```

Kontrola vydání vrací `PASS`, `REVIEW` nebo `BLOCK`. Rozpor mezi finálním verdiktem ověřovatele a závěrem koordinátora, kritické selhání, chybějící důkaz povinného scénáře nebo chybějící srovnatelná schválená baseline blokuje vydání. U volitelných kvalitativních výhrad je potřeba ruční posouzení. Výstupní kódy jsou 0 pro `PASS`, 1 pro `BLOCK` a 2 pro `REVIEW`. Výsledek tohoto příkazu pokrývá testovací report a baseline. Schválení vydání má navíc podmínky uvedené v akceptaci V1.0 a přísluší uživateli.

Výchozí bod pro návrat je commit `3af0952`. Návrat pro vývojové ověření proveď v nové pracovní kopii tohoto commitu a zopakuj běžný úkol z [README](../README.md). Pro nasazení by se návrat ověřoval samostatně.
