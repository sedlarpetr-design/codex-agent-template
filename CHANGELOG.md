# Changelog

## 1.2.0 (2026-11-21)

- Jednotný sedmipoložkový report pro ověřování projektových výstupů a vzor lokální regresní kontroly bez modelu.
- Projektové verdikty jsou SPLNĚNO, NESPLNĚNO a NEOVĚŘENO. Chybějící nebo nedostatečný důkaz vede k NEOVĚŘENO.
- Agentní verdikty, audit, formáty reportů runneru a release gate používají dosavadní rozhraní.
- Adaptéry Slack a Teams jsou odložené bez přidělené verze.

## 1.1.0 (2026-11-20)

- Jádro Codex CLI na Linuxu přes SSH. Přejímka prošla 25 z 25 nativních pokusů v 17 scénářích a 18 z 18 lokálních testů.
- Regresní test chrání projektový audit a reporty před únikem obsahu zadání a chybové diagnostiky. Nové scénáře ověřují pokyn k nepovolené akci v podkladu a oddělené výstupy souběžných analytiků.
- Report má `schema_version: 2`. Pole `input` a `expected` byla odebrána ze záznamů scénářů. Vstupy a očekávání jsou ve verzovaných definicích scénářů testovaného commitu. Nové pole `measurements` shrnuje latenci a dostupné počty tokenů. Čtečky závislé na těchto polích mají rozlišovat verzi schématu.
- Report V1.0.0 vyhodnoť bez převodu s baseline z tagu `v1.0.0`. Ulož výstup `git show v1.0.0:testing/baseline.json` do dočasného souboru a předej ho jako `--baseline` příkazu `python3 -m testing.runner gate --report <původní-report> --baseline <historická-baseline>`. [Postup pro uložené reporty](docs/TESTING.md#uložené-reporty-v100)
- Slack a Teams zůstávají odložené.

## 1.0.0 (2026-11-20)

- Vydání pro Codex CLI na linuxovém serveru s obsluhou přes SSH.
- Přejímka doložila konzolový běh s auditem a odmítnutí skutečného zápisu sandboxem Codexu.

- Izolované scénáře pro koordinátora, analytiky, ověřovatele, opravné cykly a bezpečnostní hranice.
- Strojově čitelné reporty, samostatný kandidát baseline a deterministická kontrola vydání.
- Rozpor mezi vlastním verdiktem ověřovatele a stavem koordinátora blokuje vydání.

Při přechodu z výchozího commitu zůstávají existující zadání platná. Testy spouští nový příkaz uvedený v [návodu](docs/TESTING.md). Pro návrat lze použít čistou pracovní kopii výchozího commitu `3af0952`. Reporty a zapisovaný audit jsou pracovní data mimo Git.
