# Společná pravidla jádra 2.0.0

Tento dokument je normativní pro všechny AI runtime. [Codex](../AGENTS.md),
[Claude](../CLAUDE.md), Antigravity a lokální modely jsou pouze adaptéry.
Deterministické kontrakty a logiku fronty, ověřování a syntézy poskytuje
Python balíček `core/`; runtime nesmí měnit níže uvedené významy.

## Společné zásady

- Co lze rozhodnout kódem, rozhoduje kód. Model nesmí přepsat programový verdikt.
- Stav práce, pokusy, závislosti a zámky jsou trvale uložené v SQLite frontě.
- Specialisté vracejí doložitelná data, ne vlastní schválení. Ověřovatel je
 nezávislý a syntetizátor smí použít pouze schválené výsledky.
- Evidence i výsledky se váží k trojici `task_id`, `step_id`, `attempt`.
- `schema_version` je povinná vlastnost všech obálek. Verze schématu této
 revize je `"1.0"`.

## TaskEnvelope

```json
{
  "schema_version": "1.0",
  "task_id": "t-007",
  "step_id": "s2",
  "kind": "files",
  "goal": "Zkontrolovat přidělené soubory.",
  "input": {},
  "constraints": {},
  "attempt": 1,
  "feedback": []
}
```

`attempt` začíná na 1 a jeho autoritou je SQLite. `input` odpovídá schématu
konkrétního `kind`. `feedback` obsahuje jen relevantní nálezy předchozího
pokusu; NEOVĚŘENO se specialistovi neposílá jako věcná oprava.

## ResultEnvelope a evidence

```json
{
  "schema_version": "1.0",
  "task_id": "t-007",
  "step_id": "s2",
  "attempt": 1,
  "kind": "files",
  "status": "ok",
  "result": {},
  "evidence": [{
    "ref": "s2#0",
    "type": "file",
    "id": "invoice-1",
    "uri": "data/invoice.pdf",
    "excerpt": "Celkem: 12 100 Kč",
    "sha256": "…",
    "attempt": 1
  }],
  "confidence": 0.8,
  "notes": ""
}
```

`status` je `ok`, `failed` nebo `needs_input`. `confidence` je pouze pomocný
údaj. Typy evidence jsou `quote`, `file`, `screenshot`, `log`, `calc` a `url`.
`uri` je povinné pro soubor, screenshot a log. Každý `ref` je kanonicky
`<step_id>#<index>` (např. `s2#0`), unikátní v rámci úlohy a svázaný se stejným
`attempt` jako obálka. Výstup nesmí odkazovat na neuloženou evidenci.

## Verdict

```json
{
  "schema_version": "1.0",
  "task_id": "t-007",
  "step_id": "s2",
  "attempt": 1,
  "verdict": "NEOVĚŘENO",
  "retry_class": "needs_evidence",
  "criteria": [{
    "criterion": "files_readable",
    "status": "unverified",
    "evidence": [],
    "reason": "Chybí čitelný soubor s důkazem.",
    "required": true,
    "retry": "needs_evidence"
  }],
  "notes": [],
  "fix_hint": "Doložte chybějící soubor."
}
```

Přípustné verdikty jsou přesně:

- `SPLNĚNO`: každé povinné kritérium je doloženě splněno.
- `NESPLNĚNO`: alespoň jedno povinné porušení je podloženo důkazem.
- `NEOVĚŘENO`: chybí důkaz, zdroj, čitelnost nebo dokončení kontroly; nesmí se
  zaměnit za porušení ani úspěch.

Stav kritéria je `met`, `violated` nebo `unverified`. Důkaz je nutný pro
potvrzení i zamítnutí; `violated` bez důkazu znamená NEOVĚŘENO. Třídy opakování
jsou `substantive`, `needs_evidence`, `technical`, `waiting_input` a `none`.
Model, confidence ani syntéza verdikt nepřepisují.

## Deliverable

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "deliverable": {"format": "report", "content": "…"},
  "claims": [{"text": "Celkem 12 100 Kč", "evidence_refs": ["s2#0"]}],
  "conflicts": [],
  "gaps": []
}
```

Všechna podstatná tvrzení mají `evidence_refs` z `known_refs`, složených pouze
z výstupů s verdiktem SPLNĚNO. Rozpory patří do `conflicts`; každý vynechaný,
neúspěšný nebo neověřený krok se uvede v `gaps`. Syntetizátor nesmí doplňovat
fakta ani použít nepovolený výstup. Po neúspěšné opravě vrací strukturovaný
fallback s verdiktem NEOVĚŘENO, nikoli volný text.

## Opravy, fronta a audit

Věcné opravy mají nejvýše 2 kola. Technické opakování a doplnění důkazů mají
samostatné limity stanovené konfigurací. Čekání na vstup smyčku ukončí.
Vyčerpané limity nebo neověřená závislost vedou k blokaci a kaskádovému
zablokování závislých kroků, které vyžadují SPLNĚNO. Dávky URL rozděluje
koordinátor deterministicky; `close_children` uzavře jejich příjem.

SQLite používá WAL. Jedna aktivní práce dané dvojice `(task, role)` je chráněna
zámkem; každé převzetí má token a `lease_until`. Vypršení lease samo o sobě
neopravňuje k souběžnému spuštění: `recover` vyžaduje potvrzení, že pracovník
skončil, a bezpečné opakování je povoleno jen po posouzení vedlejších účinků.
Zápis s expirovaným tokenem se odmítne.

Audit běhu musí skončit platným záznamem se stavem, výsledkem ověření a počtem
oprav v rozsahu 0–2. Chybějící nebo neplatný závěr se označuje
`audit_neuplny`; událost volání nástroje sama nedokládá vnější účinek.
Oprávnění k zápisu či externí akci jsou oddělená od verdiktu kvality a řídí je
hostitel/runtime.

Podrobné referenční požadavky jsou v [SPECIFICATION_V2.md](../docs/SPECIFICATION_V2.md).
