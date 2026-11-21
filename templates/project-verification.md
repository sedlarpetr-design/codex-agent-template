# Ověření projektového výstupu

Každý záznam hodnotí jedno kritérium. Pro další kritérium zopakuj všech sedm polí.

| Pole | Hodnota |
| --- | --- |
| ID scénáře (`scenario_id`) | Stabilní ID scénáře v projektové specifikaci |
| Kritérium (`criterion`) | Jedna ověřitelná podmínka |
| Očekávaný výsledek (`expected`) | Hodnota nebo podmínka stanovená před kontrolou |
| Skutečný výsledek (`actual`) | Pozorovaná hodnota, případně `null` |
| Odkaz na důkaz (`evidence`) | Odkaz na dostupný artefakt a případně místo v něm. Chybějící odkaz se uvádí jako `null`. |
| Verdikt (`verdict`) | `SPLNĚNO`, `NESPLNĚNO` nebo `NEOVĚŘENO` |
| Důvod (`reason`) | Jak důkaz dokládá verdikt nebo co ještě potřebujeme ověřit |

- **SPLNĚNO** při doloženém splnění kritéria.
- **NESPLNĚNO** při doloženém porušení kritéria.
- **NEOVĚŘENO** při chybějícím nebo nedostatečném důkazu. Pokud existuje částečný důkaz, odkaž na něj a uveď, co má Ověřovatel posoudit.

Tento číselník se používá pro kritéria projektu. Agentní verdikty, audit, reporty runneru a kontrola vydání používají své stávající číselníky. Postup a příkaz ke spuštění vzoru jsou v [návodu k testování](../docs/TESTING.md#ověřování-projektových-výstupů).
