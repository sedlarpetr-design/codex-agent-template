# Changelog

## 2.0.0 (2026-11-25)

- Oddělené platformově nezávislé jádro od runtime adaptérů; společné kontrakty,
  tři verdikty, kanonické evidence a pravidla auditu jsou v
  `templates/CORE_RULES.md`.
- Přidán Python balíček `core/` s validovanými obálkami, WAL SQLite frontou,
  lease/recovery, závislostmi, URL dávkami, verifierem a bezpečnou syntézou.
- Přidáni specialisté pro soubory, účetní výpočty a webové testy v Chromium /
  Firefoxu s recyklací izolovaných BrowserContext.
- Přidány adaptéry pro Codex, Claude, Antigravity a lokální Ollamu. Codex
  používá `AGENTS.md` a `.codex/` jako autoritativní konfiguraci.
- Přidány místní regresní testy kontraktů, kritérií ověřovatele, fronty a
  fallback syntézy.

## 1.6.2 (2026-11-23)

- Koordinátor vybírá jednotlivé připravené položky napříč schválenými vstupy při uvolnění role. Převzetí chrání zámek položky.
- Výchozí priorita je 10. Nižší číslo má přednost a při shodě rozhoduje pořadí přijetí. Nová prioritní položka nepřerušuje rozpracovanou práci.
- Uživatelská oprava zachová původní ID a historii. Rozpočet pokusů se obnoví pouze u opravované položky.
- Přenositelný příklad a místní regrese pokrývají pozdě přijatou prioritu, výběr z 1 000 položek, ochranu proti dvojímu převzetí a využití ověřeného výsledku z uzavřeného vstupu.

## 1.6.1 (2026-11-23)

- Ověřené výstupy z dokončených seznamů lze použít v nové schválené práci.
- Kapacita role se uvolní po předávce. Zpracování dalšího zdroje může běžet souběžně s ověřováním předchozího.
- Dvě místní regrese pokrývají souběh fází a použití kladného verdiktu z jiného seznamu.

## 1.6.0 (2026-11-23)

- Šablona fronty vybírá připravené položky v pořadí schváleného seznamu. Nezávislé role mohou pracovat souběžně podle kapacity prostředí.
- Návazná práce se uvolní po kladném verdiktu původní položky. Dokončené úlohy se při obnově znovu nepřidělují.
- Přenositelný příklad a čtyři místní regresní testy ověřují výběr připravených položek, obsazené role, závislosti a zastavení. Zámky, deník a skutečné spuštění ověřuje cílový projekt.

## 1.5.0 (2026-11-23)

- Pravidla pro zachování předávek, ověření a auditu při výměně modelu.
- Evidence kroků, samostatně konfigurovatelné hlášení a obnova od potvrzeného kroku.
- Předání původních důkazů a opětovné ověření dotčených položek.

## 1.4.0 (2026-11-22)

- Volitelný profil Testera implementace a vzor předání reportu z místní projektové sady.
- Pravidla pro převzetí testovacího modulu, opakované použití důkazů a přenos obecných regresí zpět do šablony.

## 1.3.0 (2026-11-21)

- Volitelný spouštěč a místní kontrola startu bez modelu. Windows používá MXC. Linux a WSL2 používají Bubblewrap.
- Vzor projektové specifikace pokrývá role, čtení přiděleného PDF a přejímku oprávnění v cílovém prostředí.

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
