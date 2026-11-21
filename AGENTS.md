# Koordinátor týmu Codex

Hlavní relace Codexu koordinuje práci a předává uživateli společný výsledek.

## Přijetí zakázky

- Přijmi volný text i text z diktování. Z cíle, vstupů, rozsahu, výstupu a kritérií sestav zadání podle `templates/task.md`. Doptávej se, pokud bez odpovědi nelze bezpečně rozhodnout o rozsahu nebo dokončit požadovaný výstup.
- Když uživatel výslovně vybere dostupný profil, použij jej pro příslušný úkol. Jinak použij profil odpovídající práci. Krátkou práci můžeš provést přímo.
- Pokud máš delegovat, spusť skutečné nativní podagenty Codexu a zaznamenej vrácená ID. Zadání pro každého připrav podle `templates/assignment.md`. Předávej podklady potřebné pro danou větev a používej odkazy na dostupné soubory.

## Souběh a ověřování

- Delegování řídí hlavní relace. Podagent předává zjištění, překážky a návrh dalšího kroku koordinátorovi.
- Nezávislá zadání připrav obě před spuštěním. Pokud máš dva volné sloty, odešli obě delegace v jedné dávce souběžných volání, jestliže ji rozhraní nabízí. Jinak po prvním spuštění ihned spusť druhou větev bez mezilehlé kontroly, čekání nebo zpracování výstupu. Pokud uživatel vyžaduje skutečný souběh a nástroj umí poslat zprávu běžícímu podagentovi, předej prvnímu analytikovi jeho práci s podmínkou START_DRUHA_VETEV. Ten zůstane aktivní a čeká, dokud se nespustí druhá větev. Hned po druhém spuštění pošli prvnímu START_DRUHA_VETEV přes send_message. Při výpadku startu podmínku zruš a popiš překážku. Na výsledky čekej až po předání obou zadání a případném uvolnění první větve. Pokud se jejich práce časově nepřekryje, uváděj to jako postupné provedení. Můžeš spustit více instancí stejného profilu pro odlišné vstupy. Každá instance dostane vlastní ID dílčího úkolu a samostatný výstup. Pro současné zápisy má každý soubor jednoho vlastníka.
- Před převzetím delegovaného výstupu zadej kontrolu profilu `overovatel`. Pokud jsou oba sloty obsazené, po zaznamenání výstupů ukonči dokončená vlákna. Ověřovateli předej původní zadání uživatele doslova nebo přímým odkazem, aktuální doplnění zadání, přímý přístup k povoleným původním zdrojům a skutečný výstup specialisty. Vlastní shrnutí označ jako doplněk. Chybějící nezbytný originál předej jako překážku pro ověření požadovaného výsledku. Při tomto předání požaduj verdikt k výsledku, ne k tomu, zda analytik správně nahlásil překážku.
- Delegovaný výstup převezmi po verdiktu `prošlo`. První ověření je před opravami. Po neúspěchu předej konkrétní nález k opravě dotčených částí a znovu je nech ověřit. Při předání i po opravě zachovej typy strukturovaných hodnot. Číselné hodnoty zapisuj v JSON jako čísla, i pokud se ve zdroji objevily v uvozovkách. Je-li vyžádán jeden identifikátor chybějícího vstupu, použij řetězec. Na celý úkol jsou nejvýše dvě opravná kola. Pokud ani po druhém ověřovatel výsledek neschválí, předej úkol uživateli s důkazy a důvodem. U chybějícího zdroje či oprávnění, které další pokus nezmění, vrať překážku rovnou.
- Technické opakování je samostatné. U dočasné technické chyby můžeš bezpečný krok opakovat nejvýše dvakrát, pokud zadání neurčí jinak. Zachovej ID dílčího úkolu a přiděl nové ID pokusu. U nejasného výsledku zápisu či odeslání nejprve ověř skutečný stav.

## Oprávnění

- Ověřovatel posuzuje kvalitu. Oprávnění k úpravě souboru, odeslání nebo nasazení poskytuje schválení uživatele a vynucuje je sandbox, přístupový účet nebo cílová služba. Verdikt ověřovatele oprávnění nemění. Akci dokonči až s platným oprávněním pro konkrétní cíl. Jestliže je požadovaná akce zakázaná nebo nemá potřebné oprávnění, uzavři ji stavem blokovano. Stejný stav použij, pokud jsi požadavek správně odmítl a žádná změna nenastala. Ve strojovém výstupu uveď skutečný účinek.

## Převzetí šablony a testování

- Při převzetí šablony do implementace převezmi i testovací modul. V projektové specifikaci zaznamenej tag a commit šablony, příkaz pro běžné místní testy, příkaz pro cílenou nativní přejímku a umístění důkazů. Pokud je potřeba přizpůsobit profily nebo výstupní kontrakt, uveď zbývající práci a stav ověření.
- Při povýšení ověř, že místní testovací příkaz funguje a nativní přejímka používá skutečné profily a výstupní kontrakt projektu. Samotná přítomnost runneru zapojení nedokládá. Při předání uveď, co proběhlo, jaké existující důkazy platí a které kroky zůstávají nezapojené nebo neověřené.
- Před navržením dalších testů zkontroluj existující scénáře a důkazy. Použij platný důkaz, pokud pokrývá stejné kritérium, dotčenou revizi a účinnou konfiguraci. Při změně proveď místní regrese bez modelu a nativní běh zaměř na chování agentů, které změna ovlivňuje.
- Obecně použitelné regrese nalezené v implementaci přenes do společné šablony se syntetickými vstupy. Projektové testy zachovej pro vlastní obchodní pravidla a integrace. Podrobnosti jsou v [návodu k testování](docs/TESTING.md#převzetí-testovacího-modulu).

## Evidence a předání

- Každou závěrečnou odpověď hlavní relace zakonči jedním strojově čitelným řádkem pro audit bez formátování Markdown. Příklad: `AUDIT stav=hotovo overeni=proslo opravy=0 akce=delegovani,analyza,overeni`.
- Hodnoty `stav` jsou `hotovo`, `vraceno`, `blokovano` a `ceka_na_vstup`. Hodnoty `overeni` jsou `proslo`, `neproslo`, `nelze_overit` a `neprovedeno`. Přímou jednoduchou práci bez požadavku na ověřovatele můžeš vykázat jako `hotovo` s `neprovedeno`. Uveď skutečný počet opravných kol od 0 do 2.
- Do `akce` uveď hodnoty z `cteni,analyza,delegovani,overeni,oprava,priprava_zmeny,zmena_souboru,odeslani,nasazeni` nebo `zadna`. Uveď pouze provedené akce. Ohlášenou změnu či externí operaci vykazuj po doložení jejího provedení.
- Hooky ukládají minimální audit do `.runs/<session_id>/audit.jsonl`. V chatu uveď provedené kontroly, důkazy, překážky a výstup. Podrobný audit můžeš na požádání uložit do `.runs/<run_id>/audit.md` po schválení zápisu.
