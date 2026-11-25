# Univerzální multi-agentní šablona

Platformově nezávislé jádro multi-agentních workflow s deterministickou
SQLite frontou, strukturovanými obálkami, nezávislým ověřováním a bezpečnou
syntézou. Aktuální verze je **2.0.0**; společná pravidla jsou v
[templates/CORE_RULES.md](templates/CORE_RULES.md), implementační požadavky v
[specifikaci V2](docs/SPECIFICATION_V2.md).

## Struktura

- `core/` — obálky se `schema_version`, stavový automat fronty, ověřovatel a
  syntetizátor bez závislosti na konkrétním AI runtime.
- `specialists/` — adaptéry pro kontrolu souborů, účetní výpočty a webové
  scénáře přes Playwright (Chromium nebo Firefox).
- `templates/CORE_RULES.md` — společné kontrakty `TaskEnvelope`,
  `ResultEnvelope`, `Verdict`, `Deliverable`, důkazy a audit.
- `AGENTS.md`, `.codex/` — adaptér pro Codex; `CLAUDE.md` a `adapters/`
  obsahují adaptéry pro Claude, Antigravity a lokální Ollamu.
- `testing/` — lokální regresní a přejímací testy.

## Základní kontrakty

Každá obálka nese `schema_version`, identifikátory úkolu/kroku a číslo pokusu.
Evidence používá kanonické reference `<step_id>#<index>`. Ověřovatel vydává
výhradně `SPLNĚNO`, `NESPLNĚNO` nebo `NEOVĚŘENO`; chybějící důkaz nikdy
neznamená úspěch. Opravný cyklus má nejvýše dvě věcná kola. Syntéza používá
jen schválené výstupy a při neúspěchu vrací strukturovaný fallback.

## Spuštění a testování

Vyžaduje se Python 3.10+ (doporučeno 3.11+). Jádro používá pouze standardní
knihovnu Pythonu; Playwright je volitelný a potřebný jen pro `web_test`.
Z kořene repozitáře spusť:

```text
python -X utf8 -m unittest discover -s testing/tests -v
```

Kompletní strukturu testů, pokrytí kritérií a nativní přejímku popisuje
[docs/TESTING.md](docs/TESTING.md). Testy fronty a verifieru běží lokálně bez
modelu, sítě ani AI CLI.

## Runtime adaptéry

- **Codex:** otevři repozitář a řiď se [AGENTS.md](AGENTS.md); hooky a profily
  jsou v `.codex/`. Výchozí sandbox zůstává pouze pro čtení.
- **Claude / Claude Code:** viz [CLAUDE.md](CLAUDE.md) a
  [adapters/claude/](adapters/claude/).
- **Antigravity:** viz [ANTIGRAVITY.md](adapters/antigravity/ANTIGRAVITY.md).
- **Lokální Ollama (~10 GB):** konzervativní výchozí nastavení je v
  [config.yaml](adapters/local_ollama/config.yaml); spusť
  `python adapters/local_ollama/run.py`.

Runtime určuje dostupné nástroje a oprávnění, nikoli význam obálek nebo
verdiktů. Zápis a vnější akce vyžadují oprávnění hostitele a nesmějí být
odvozovány z verdiktu kvality.

## Verze

Verzi najdeš v [VERSION](VERSION). Historii změn obsahuje
[CHANGELOG.md](CHANGELOG.md); plán a původní Codex přejímky jsou v
[docs/ROADMAP.md](docs/ROADMAP.md).
