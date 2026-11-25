# **Univerzální multi-agentní šablona**

Koordinátor, specialisté, ověřovatel s pluginy a syntetizátor. Návrh pro lokální provoz (Ollama, cca 10 GB použitelné paměti), použitelný pro libovolné úkoly.

## **1\. Základní principy**

1. **Kostra je pevná, úkol je konfigurace.** Nový úkol znamená nový YAML a případně nový plugin, ne přepisování systému.  
2. **Co jde ověřit kódem, ověřuje se kódem.** LLM se používá jen tam, kde kód nestačí (porozumění textu, věcná podpora tvrzení).  
3. **Všichni mluví stejnou obálkou.** Jednotný kontrakt vstupu a výstupu je důvod, proč ověřovatel a koordinátor nemusí znát obsah úkolů.  
4. **Ověřovatel posuzuje, neopravuje.** Opravu dělá specialista na základě konkrétních nálezů.  
5. **Stav žije mimo model.** Plán, výsledky, počty pokusů a logy jsou v souboru nebo databázi, ne v kontextu LLM.  
6. **Každá smyčka má strop.** Maximum pokusů, kroků i tokenů; po vyčerpání úkol skončí jako neověřený, nikdy ne potichu jako úspěšný.

## **2\. Architektura**

Zadání → jedna fronta → Koordinátor → specialista  
Specialista → Koordinátor → Ověřovatel (programová a podle potřeby obsahová fáze)  
Ověřovatel → Koordinátor → zápis verdiktu a případná cílená oprava  
Ověřené výstupy a doložené mezery → volitelná syntéza → kontrola syntézy → předání  
Toky dat jsou vždy tři typy obálek: **TaskEnvelope** (zadání kroku s historií attempt), **ResultEnvelope** (výstup specialisty s evidencí), **Verdict** (rozhodnutí ověřovatele). Syntetizátor navíc vrací **Deliverable**.

## **3\. Společné kontrakty**

### **3.1 TaskEnvelope (vstup specialisty)**

{

  "task\_id": "t-007",

  "step\_id": "s2",

  "kind": "files",

  "goal": "Zkontroluj validitu všech souborů v adresáři a vytáhni metadata.",

  "input": { },

  "constraints": { "language": "cs", "max\_output\_tokens": 1000 },

  "attempt": 1,

  "feedback": \[\],

}

* kind určuje, který specialista a které kontroly se použijí.  
* input má pevné schéma podle kind (viz sekce 5).  
* feedback je při opakování seznam nálezů ověřovatele (issues), jinak prázdný.  
* attempt udává aktuální číslo pokusu (od 1), které se propaguje napříč TaskEnvelope, ResultEnvelope, Verdict a databázovým zápisem.

### **3.2 ResultEnvelope (výstup specialisty)**

{

  "task\_id": "t-007",

  "attempt": 1,

  "step\_id": "s2",

  "kind": "files",

  "status": "ok",

  "result": { },

  "evidence": \[

    { "ref": "s2\#0", "type": "file", "id": "ev-001", "uri": "data/faktura.pdf", "excerpt": "Celkem: 12 100 Kč", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "attempt": 1 }

  \],

  "confidence": 0.8,

  "notes": ""

}

* status: ok (hotovo), failed (nepodařilo se, důvod v notes), needs\_input (chybí vstup).  
* evidence je povinné pole položek důkazů se sjednocenou strukturou: ref (kanonický odkaz ve tvaru \<step\_id\>\#\<index\>, např. s2\#0), type (quote \| file \| screenshot \| log \| calc \| url), id / evidence\_id, uri, excerpt, sha256 a attempt.  
* confidence je pomocný údaj. Nikdy nerozhoduje o schválení.

### **3.3 Verdict (výstup ověřovatele)**

{

  "schema\_version": "1.0",

  "task\_id": "t-007",

  "step\_id": "s2",

  "attempt": 1,

  "verdict": "NESPLNĚNO",

  "retry\_class": "substantive",

  "criteria": \[

    { "criterion": "files\_readable", "status": "violated",

      "evidence": \["data/a.csv"\], "reason": "data/a.csv: nejde přečíst" },

    { "criterion": "all\_inputs\_covered", "status": "met",

      "evidence": \["data/a.csv", "data/b.pdf", "data/c.json"\] },

    { "criterion": "status\_ok", "status": "unverified",

      "evidence": \[\], "reason": "status=failed: timeout čtečky PDF" }

  \],

  "notes": \[ { "criterion": "length\_ok", "reason": "delší než limit" } \],

  "fix\_hint": "data/a.csv: nejde přečíst"

}

* SPLNĚNO: každé povinné kritérium je met a má aspoň jeden důkaz.  
* NESPLNĚNO: aspoň jedno povinné kritérium je violated a porušení je doložené důkazem. Specialista dostane jen tato kritéria jako zpětnou vazbu.  
* NEOVĚŘENO: žádné doložené porušení, ale některé povinné kritérium chybí, nemá důkaz nebo je unverified (timeout, přeskočený krok, chybějící zdroj, pád kontroly). Není to chyba specialisty a neposílá se mu jako oprava.  
* retry\_class: substantive (věcná oprava), needs\_evidence (doplnit důkaz), technical (zopakovat stejný krok), waiting\_input (čekat na podklad), none.  
* notes: nepovinné poznámky (dřívější warn), verdikt neovlivňují.

Verdikt skládá výhradně kód (build\_verdict, sekce 6.1) z výsledků jednotlivých kontrol. Ani LLM kontrola ho nemůže přepsat. Všechny obálky nesou schema\_version a trojice task\_id \+ step\_id \+ attempt jednoznačně identifikuje každý zápis. Všechny platné odkazy z výstupu specialisty tvoří available\_refs, zatímco sjednocená sada odkazů ze všech schválených kroků představuje known\_refs pro Syntetizátor.

## **4\. Koordinátor**

### **4.1 Co musí umět**

| Schopnost | Popis |
| :---- | :---- |
| Rozklad zadání | Převést cíl na kroky s typem (kind), vstupem a závislostmi |
| Plánování | Seřadit kroky podle závislostí, najít paralelizovatelné |
| Přidělování | Každý krok předat správnému specialistovi |
| Řízení opakování | Předat feedback, hlídat počet pokusů |
| Rozpočty | Hlídat max. kroky, tokeny, čas |
| Eskalace | Když krok selže opakovaně, označit ho a pokračovat nebo skončit |
| Sloučení | Předat schválené výstupy syntetizátoru |
| Ukončení | Umět skončit s výsledkem nelze splnit a důvodem |

### **4.2 Může běžet lokálně?**

Ano. Důležité je, kolik práce necháte na modelu.

* **Pevný postup (mode: fixed \- výchozí doporučený):** koordinátor je deterministický Python skript nad SQLite frontou. Plán je daný v YAML nebo šabloně, spotřebovává 0 LLM tokenů a garantuje 100% předvídatelnost pro opakovatelné produkční úlohy.  
* **Dynamický plánovací modul (mode: llm):** LLM se používá pouze pro jednorázový návrh struktury plánu na samém začátku ad-hoc úkolu (kdy není k dispozici hotový YAML). Není určen pro průběžné řízení smyčky ani vyhodnocování verdiktů. Výstupní plán je striktně omezen JSON schématem a validován kódem.  
  * výstup je omezen JSON schématem s nízkou teplotou (0.0 až 0.2),  
  * plán smí používat pouze známé registrované kind z registru specialistů. LLM nesmí generovat desítky ani stovky položek dávky – místo toho navrhne jediný krok s definovaným pravidlem rozpadu, který deterministický kód koordinátoru následně rozepíše na podúlohy,  
  * plán validuje funkce validate\_plan() (kontrola cyklů, závislostí a limitu kroků). Při selhání validace je povolen nejvýše 1 opravný pokus se zasláním chybové hlášky pod stropem tokenů, po vyčerpání systém selže.

### **4.3 Nároky na model koordinátora**

* spolehlivý strukturovaný výstup (JSON podle schématu),  
* vykonávání instrukcí bez fantazie (nízká teplota 0.0 až 0.2),  
* krátký kontext (zadání \+ seznam dostupných specialistů \+ schémata, cca 2 až 4 tisíce tokenů),  
* žádné dlouhé texty ani znalosti domény. Podle verze AI a dostupných limitů/kvót lze pro plánování využít lokální LLM (např. Ollama) i cloudové API.

Na 10 GB stačí stejný malý model (např. 4B) jako u specialistů, takže se nepřepíná. Silnější model se vyplatí až u syntetizátoru.

### **4.4 Schéma plánu**

{

  "steps": \[

    { "id": "s1", "kind": "files", "goal": "...", "input": { }, "depends\_on": \[\] },

    { "id": "s2", "kind": "accounting", "goal": "...", "input": { }, "depends\_on": \["s1"\] }

  \],

  "synthesis": { "format": "report", "language": "cs" }

}

Validace plánu v kódu:

from graphlib import TopologicalSorter

def validate\_plan(plan, known\_kinds, max\_steps=20):

    steps \= plan.get("steps", \[\])

    ids \= {s\["id"\] for s in steps}

    if not steps or len(steps) \> max\_steps or len(ids) \!= len(steps):

        raise ValueError("špatný počet kroků")

    for s in steps:

        if s\["kind"\] not in known\_kinds:

            raise ValueError(f"neznámý kind: {s\['kind'\]}")

        if not set(s\["depends\_on"\]) \<= ids:

            raise ValueError(f"neexistující závislost v {s\['id'\]}")

    return list(TopologicalSorter({s\['id'\]: s\['depends\_on'\] for s in steps}).static\_order())

## **5\. Specialisté**

Specialista je **konfigurace \+ adaptér**: prompt, nástroje, model, vstupní a výstupní schéma. Jeho vstup a výstup vždy balí do obálek ze sekce 3\. Rozhodující pravidlo: **skutečnou práci dělají nástroje (kód), model jen rozhoduje a interpretuje**. U testu webu spouští prohlížeč Playwright, u účetnictví počítá Decimal.

### **5.1 Šablona specialisty**

class Specialist:

    kind \= "base"

    model \= "qwen3.5:4b"

    def run(self, task: dict) \-\> dict:

        raw \= self.work(task)  \# nástroje \+ volitelně LLM

        return {

            "task\_id": task\["task\_id"\], "step\_id": task\["step\_id"\],

            "kind": self.kind, "status": raw.get("status", "ok"),

            "result": raw\["result"\], "evidence": raw.get("evidence", \[\]),

            "confidence": raw.get("confidence", 0.5), "notes": raw.get("notes", ""),

        }

    def work(self, task):  \# implementuje konkrétní specialista

        raise NotImplementedError

### **5.2 Specialista web\_test (test webu podle scénáře)**

**Vstup (input):**

{

  "base\_url": "https\://example.test",

  "scenario": \[

    { "step\_id": "open", "step": "Otevřít přihlášení", "action": "goto", "target": "/login", "expect": "viditelné pole e-mail" },

    { "step\_id": "login", "step": "Přihlásit se", "action": "fill\_submit", "target": "\#login-form", "expect": "přesměrování na /dashboard" }

  \]

}

**Výstup (result):**

{

  "steps": \[

    { "step\_id": "open", "evidence\_ref": "steps/open.json", "name": "Otevřít přihlášení", "status": "passed", "expected": "...", "actual": "...", "duration\_ms": 420 }

  \],

  "summary": { "passed": 5, "failed": 1, "skipped": 0 }

}

evidence: typ screenshot a log pro každý krok, zejména pro neúspěšné. LLM může scénář převést na akce, ale provedení a vyhodnocení expect má dělat kód.

### **5.2.1 Provoz a přenosnost prohlížeče (portable Chromium):**

* **Přenosná binárka:** Chromium nevyžaduje systémovou instalaci. Playwright stahuje vlastní izolovanou binárku, kterou lze přes proměnnou PLAYWRIGHT\_BROWSERS\_PATH uložit přímo do adresáře projektu a přenášet mezi stroji se stejným OS a architekturou bez zásahu do systémového prohlížeče.  
* **Izolované profily (\--user-data-dir):** Každý běh nebo kontext musí používat oddělený dočasný adresář pro cache a cookies (Playwright jej zakládá automaticky), aby nedocházelo ke kolizím mezi paralelními pracovníky ani k zanášení uživatelského profilu.  
* **Systémové závislosti na Linuxu:** Na Linuxu se ověří knihovny i start prohlížeče v cílovém prostředí. Chromium se testuje s chromium\_sandbox=True. Pokud start selže, Tester zaznamená překážku a použije schválené prostředí s funkční izolací. Volba prohlížeče závisí na scénáři.

### **5.2.2 Deterministický rozpad dávkových úloh a správa paměti:**

* **Deterministický rozpad dávek:** Dávkové úlohy (např. testování 100 URL při přechodu z nabídky na detail) Koordinátor deterministicky rozpadá na samostatné podúlohy (s parent\_id a children\_closed) po 1 URL nebo v malých dávkách (5–10 URL) podle příznaku v zadání.  
* **Izolace kontextu a restart prohlížeče:** Pro každou položku se recykluje čistý BrowserContext. Pro zamezení únikům paměti Chromium provede kompletní restart prohlížeče v pravidelných intervalech (cca po každých 20–25 zpracovaných URL).  
* **Optimalizace důkazů:** Snímky obrazovky (type screenshot) se pořizují přednostně při výskytu chyby, zatímco u úspěšných položek se ukládají pouze stručné logy (type log).

### **5.3 Specialista files (kontrola a extrakce souborů)**

**Vstup:**

{

  "paths": \["data/a.csv", "data/b.pdf", "data/c.json"\],

  "rules": { "csv": { "required\_columns": \["id", "datum", "castka"\] }, "max\_size\_mb": 50 }

}

**Výstup:**

{

  "files": \[

    { "path": "data/a.csv", "type": "csv", "size": 10234, "sha256": "...",

      "parsed\_ok": true, "errors": \[\], "extracted": { "rows": 312 } }

  \]

}

Validita se zjišťuje kódem (json.load, csv.reader, čtečka PDF, test archivu). Model smí nanejvýš shrnout obsah. Soubor, který nejde přečíst, je parsed\_ok: false, ne vymyšlený obsah.

### **5.4 Specialista marketing\_mail (e-maily, marketing)**

**Vstup:**

{

  "product": "...", "audience": "stávající zákazníci", "tone": "přátelský",

  "language": "cs", "cta": { "text": "Zobrazit nabídku", "url": "https\://..." },

  "facts": \["sleva 15 % do 30\. 11.", "doprava zdarma nad 1 000 Kč"\],

  "constraints": { "max\_words": 150 }

}

**Výstup:**

{

  "subject": "...", "preheader": "...", "body": "...",

  "cta\_url": "https\://...", "language": "cs", "facts\_used": \[0, 1\]

}

facts\_used odkazuje na indexy facts ze vstupu. Ověřovatel tak pozná, že e-mail neobsahuje vymyšlenou slevu.

### **5.5 Specialista accounting (účetní)**

**Vstup:**

{

  "rows": \[ { "desc": "Licence", "net": 1000.00, "vat\_rate": 0.21 } \],

  "currency": "CZK", "period": "2026-10", "rules": { "rounding": "2dp" }

}

**Výstup:**

{

  "items": \[ { "desc": "Licence", "net": 1000.00, "vat": 210.00, "amount": 1210.00 } \],

  "total\_net": 1000.00, "total\_vat": 210.00, "total": 1210.00, "currency": "CZK"

}

Výpočty provádí kód s Decimal. LLM nikdy neprovádí aritmetiku, jen třeba přiřazuje kategorie nebo vysvětluje odchylky.

### **5.6 Přidání nového specialisty**

1. Definovat vstupní a výstupní schéma pro nový kind.  
2. Napsat třídu s metodou work.  
3. Zaregistrovat plugin kontrol pro tento kind (sekce 6).  
4. Přidat ho do YAML úkolu.

### **5.7 Vlastní kontrola specialisty před odevzdáním**

Specialista před předáním výsledku Koordinátorovi ověří formát a povinná pole výstupu, shodu ID úlohy, kroku a pokusu, dostupnost odkazovaných důkazů a záznam povinných kroků. Kontroly provede místním kódem, pokud jsou měřitelné. Například Tester webu zkontroluje, že report obsahuje očekávané položky a snímky odkazují na soubory tohoto běhu.

Odstranitelnou technickou chybu specialista opraví v mezích přiděleného rozpočtu. Chybějící podklad, nedokončený krok nebo nečitelný důkaz uvede ve výstupu s konkrétním důvodem a místem, kde se práce zastavila. Koordinátor převzetí zapíše a předá skutečný výsledek nebo doloženou překážku.

Vlastní kontrola je součást odevzdání. Nezávislý verdikt vydává jediný Ověřovatel, který od Koordinátora dostane původní zadání, předem daná kritéria a skutečné důkazy. První vrstva používá místní programové kontroly. Pokud tím pokryje všechna povinná kritéria, obsahová vrstva se nespouští. Obsahové posouzení je potřeba jen pro zbývající povinná kritéria s dostupnými důkazy. Koordinátor zapíše vrácený verdikt do fronty.

Přejímka ověří tři cesty. Měřitelný případ dojde k verdiktu bez modelu. Případ s povinným obsahovým kritériem předá do druhé vrstvy jen toto kritérium s důkazy. Chybějící důkaz vede k NEOVĚŘENO a sám nespustí model.

## **6\. Ověřovatel**

### **6.1 Jádro (nezná obsah úkolů)**

from dataclasses import dataclass, field, asdict

@dataclass

class R:  \# výsledek jedné kontroly \= jednoho kritéria

    criterion: str

    status: str                  \# 'met' \| 'violated' \| 'unverified'

    evidence: list \= field(default\_factory=list)

    reason: str \= ''

    required: bool \= True        \# False \= jen poznámka, verdikt neovlivní

    retry: str \= 'technical'     \# u 'unverified': 'technical' \| 'needs\_evidence'

def met(c, evidence): return R(c, 'met', evidence)

def violated(c, reason, evidence): return R(c, 'violated', evidence, reason)

def unverified(c, reason, retry='technical'): return R(c, 'unverified', \[\], reason, retry=retry)

def note(c, reason): return R(c, 'violated', \[\], reason, required=False)

REGISTRY, REQUIRED \= {}, {}   \# kind \-\> \[kontroly\], kind \-\> {povinná kritéria}

def check(kind, criterion, required=True):

    def deco(fn):

        if any(f.criterion \== criterion for f in REGISTRY.get(kind, \[\])):

            raise ValueError('duplicitní kritérium: ' \+ criterion)

        fn.criterion \= criterion

        fn.required \= required

        REGISTRY.setdefault(kind, \[\]).append(fn)

        if required:

            REQUIRED.setdefault(kind, set()).add(criterion)

        return fn

    return deco

def verify(kind, out, ctx, common=True):

    fns \= (REGISTRY.get('\*', \[\]) if common else \[\]) \+ REGISTRY.get(kind, \[\])

    results, n\_a \= \[\], set()

    for fn in fns:

        if ctx.get('inapplicable', {}).get(fn.criterion):

            n\_a.add(fn.criterion)

            continue

        try:

            r \= fn(out, ctx)

        except Exception:   \# diagnostika bez obsahu zdroje

            r \= unverified(fn.criterion, 'kontrola selhala')

        if r is None:

            if not fn.required:

                n\_a.add(fn.criterion)

                continue

            r \= unverified(fn.criterion, 'chybí důkaz nebo rozhodnutí o použitelnosti')

        if r.criterion \!= fn.criterion:

            r \= unverified(fn.criterion, 'kontrola vrátila jiné ID kritéria')

        r.required \= fn.required

        results.append(r)

    return build\_verdict(kind, out, results, n\_a, common)

def build\_verdict(kind, out, results, n\_a, common=True):

    required \= ((REQUIRED.get('\*', set()) if common else set())

                \| REQUIRED.get(kind, set())) \- n\_a

    by \= {r.criterion: r for r in results}

    violations \= \[r for r in results

                  if r.required and r.status \== 'violated' and r.evidence\]

    unproven \= \[c for c in required

                if c not in by or not by\[c\].evidence or by\[c\].status \== 'unverified'\]

    if violations:

        verdict, retry \= 'NESPLNĚNO', 'substantive'

        hint \= '; '.join(r.reason for r in violations)

    elif unproven or not required:

        kinds \= {by\[c\].retry for c in unproven if c in by}

        if out.get('status') \== 'needs\_input':

            retry \= 'waiting\_input'

        elif 'needs\_evidence' in kinds:

            retry \= 'needs\_evidence'

        else:

            retry \= 'technical'

        verdict, hint \= 'NEOVĚŘENO', ('chybí důkaz pro: ' \+ ', '.join(sorted(unproven))

                                  if unproven else 'není doložené povinné kritérium')

    else:

        verdict, retry, hint \= 'SPLNĚNO', 'none', ''

    return {

        'schema\_version': '1.0',

        'task\_id': out.get('task\_id'), 'step\_id': out.get('step\_id'),

        'attempt': out.get('attempt', 0),

        'verdict': verdict, 'retry\_class': retry,

        'criteria': \[asdict(r) for r in results if r.required\],

        'notes': \[asdict(r) for r in results if not r.required\],

        'fix\_hint': hint\[:500\],

    }

Kontrola bez důkazu nemůže nic potvrdit ani zamítnout: met bez evidence i violated bez evidence se počítají jako neověřené. Pád kontroly, timeout nebo chybějící zdroj dávají NEOVĚŘENO, nikdy NESPLNĚNO. Použitelnost určí profil před během a doloží důvod. Prázdný výsledek povinné kontroly bez takového rozhodnutí znamená NEOVĚŘENO. Povinná jsou jen kritéria registrovaná s required=True, ostatní jsou poznámky.

Pozor: tato pravidla zpřísňují SPLNĚNO. Pokud ověřovatel už dnes skoro nic nepouští, držte seznam povinných kritérií krátký a nová kritéria zařazujte nejdřív jako nepovinná (sekce 6.5).

### **6.2 Společné kontroly (\*)**

def normalized\_quote(value):

    return ' '.join(value.translate(str.maketrans('„“”«»’‘', '"""""\\'\\'')).split())

@check('\*', 'envelope\_ok')

def envelope\_ok(out, ctx):

    need \= {'task\_id', 'step\_id', 'kind', 'status', 'result', 'evidence'}

    missing \= need \- out.keys()

    if missing:

        return violated('envelope\_ok', 'chybí pole: ' \+ str(sorted(missing)), \['envelope'\])

    return met('envelope\_ok', \['envelope'\])

@check('\*', 'status\_ok')

def status\_ok(out, ctx):

    s \= out.get('status')

    if s \== 'ok':

        return met('status\_ok', \['envelope.status'\])

    \# failed / needs\_input \= specialista sám nedokončil, není co posoudit

    return unverified('status\_ok', 'status=' \+ str(s) \+ ': ' \+ str(out.get('notes', '')))

@check('\*', 'evidence\_present')

def evidence\_present(out, ctx):

    ev \= out.get('evidence') or \[\]

    if not ev:

        return unverified('evidence\_present', 'specialista nedodal důkaz', 'needs\_evidence')

    refs \= \[e.get('ref') for e in ev\]

    if any(ref not in ctx.get('available\_refs', ()) for ref in refs):

        return unverified('evidence\_present', 'odkaz na důkaz nelze načíst', 'needs\_evidence')

    return met('evidence\_present', refs)

@check('\*', 'quotes\_in\_source')

def quotes\_in\_source(out, ctx):

    src \= ctx.get('source\_text')

    quotes \= \[e for e in out.get('evidence', \[\]) if e.get('type') \== 'quote'\]

    if not src or not quotes:

        return unverified('quotes\_in\_source', 'chybí původní zdroj nebo citát', 'needs\_evidence')

    source \= normalized\_quote(src)

    bad \= \[e for e in quotes if not normalized\_quote(e\['excerpt'\])

           or normalized\_quote(e\['excerpt'\]) not in source\]

    if bad:

        return violated('quotes\_in\_source', str(len(bad)) \+ ' citátů není ve zdroji',

                        \[e\['ref'\] for e in bad\])

    return met('quotes\_in\_source', \[e\['ref'\] for e in quotes\])

### **6.3 Pluginy pro jednotlivé typy specialistů**

Číselná kontrola přijímá normalizované dvojice hodnota a jednotka nebo explicitní formát zdroje a výstupu (source\_number\_locale a output\_number\_locale). Ukázkový parser pokrývá cs a en se známými jednotkami. Nejednoznačné formáty se předají k posouzení. Porovnání je předběžná kontrola výskytu hodnot. Věcnou vazbu údaje na tvrzení posoudí odpovídající kritérium.

import re

from decimal import Decimal

from pathlib import Path

def extract\_normalized\_numbers(text, locale):

    """Return (Decimal, unit) values and fragments needing interpretation."""

    formats \= {

        'cs': r'(?:\[0-9\]{1,3}(?:\[ \\u00a0\\u202f\]\[0-9\]{3})+\|\[0-9\]+)(?:,\[0-9\]+)?',

        'en': r'(?:\[0-9\]{1,3}(?:,\[0-9\]{3})+\|\[0-9\]+)(?:\\.\[0-9\]+)?',

    }

    if locale not in formats:

        raise ValueError('číselný formát musí být cs nebo en')

    tokens \= re.finditer(

        r'(?\<\!\\w)(?P\<sign\>\[+\\-−\]?)(?P\<number\>\[0-9\]+(?:\[.,\]\[0-9\]+\|\[ \\u00a0\\u202f\]\[0-9\]{3}(?\!\[0-9\]))\*)'

        r'(?:\[ \\t\\u00a0\\u202f\]\*(?P\<unit\>%\|Kč\|CZK\|EUR\|USD\|€\|\\\$\|kg\|km\|mm\|ms\|h\|m\|s)(?\!\\w))?',

        text, re.IGNORECASE)

    units \= {'kč': 'CZK', 'czk': 'CZK', '€': 'EUR', 'eur': 'EUR', 'usd': 'USD'}

    values, ambiguous \= set(), \[\]

    for token in tokens:

        raw \= token\['number'\]

        unit \= (token\['unit'\] or '').lower()

        if not re.fullmatch(formats\[locale\], raw) or unit \== '\$':

            ambiguous.append(token\[0\])

            continue

        if locale \== 'cs':

            raw \= re.sub(r'\[ \\u00a0\\u202f\]', '', raw).replace(',', '.')

        else:

            raw \= raw.replace(',', '')

        sign \= '-' if token\['sign'\] \== '−' else token\['sign'\]

        values.add((Decimal(sign \+ raw), units.get(unit, unit)))

    return values, ambiguous

def compare\_numbers(out\_text, source\_texts, ctx):

    allowed, used \= ctx.get('numeric\_facts'), ctx.get('numeric\_claims')

    if allowed is not None and used is not None:

        return set(used) \- set(allowed), False

    if 'source\_number\_locale' not in ctx or 'output\_number\_locale' not in ctx:

        return set(), True

    used, output\_uncertain \= extract\_normalized\_numbers(out\_text, ctx\['output\_number\_locale'\])

    if not used and not output\_uncertain:

        return set(), False

    allowed, uncertain \= set(), bool(output\_uncertain) or not source\_texts

    for source in source\_texts:

        values, ambiguous \= extract\_normalized\_numbers(source, ctx\['source\_number\_locale'\])

        allowed.update(values)

        uncertain \|= bool(ambiguous)

    return used \- allowed, uncertain

\# \--- web\_test \---

@check('web\_test', 'steps\_passed')

def steps\_passed(out, ctx):

    steps \= out\['result'\]\['steps'\]

    if not steps or any(not s.get('evidence\_ref') or s\['evidence\_ref'\] not in ctx.get('available\_refs', ())

                        for s in steps):

        return unverified('steps\_passed', 'chybí důkaz kroku', 'needs\_evidence')

    failed \= \[s for s in steps if s\['status'\] \== 'failed' and s.get('target\_observed') is True\]

    broken \= \[s for s in steps if s\['status'\] \!= 'passed' and s not in failed\]

    if failed:

        reason \= '; '.join(s\['name'\] \+ ': ' \+ str(s.get('actual')) for s in failed)

        return violated('steps\_passed', reason, \[s\['evidence\_ref'\] for s in failed\])

    if broken:

        return unverified('steps\_passed', 'nespuštěno nebo chyba: ' \+ str(\[s\['name'\] for s in broken\]))

    return met('steps\_passed', \[s\['evidence\_ref'\] for s in steps\])

@check('web\_test', 'scenario\_covered')

def scenario\_covered(out, ctx):

    want \= \[s\['step\_id'\] for s in ctx\['task\_input'\]\['scenario'\]\]

    steps \= out\['result'\]\['steps'\]

    got \= \[s\['step\_id'\] for s in steps\]

    if not want or len(set(want)) \!= len(want) or sorted(want) \!= sorted(got):

        return unverified('scenario\_covered', 'neúplná nebo duplicitní ID kroků')

    return met('scenario\_covered', \[s\['evidence\_ref'\] for s in steps\])

@check('web\_test', 'failed\_have\_screenshot', required=False)

def failed\_have\_screenshot(out, ctx):

    has \= any(e\['type'\] \== 'screenshot' for e in out\['evidence'\])

    if out\['result'\]\['summary'\]\['failed'\] and not has:

        return note('failed\_have\_screenshot', 'chybí screenshot')

    return None

\# \--- files \---

@check('files', 'files\_readable')

def files\_readable(out, ctx):

    bad, ok \= \[\], \[\]

    for f in out\['result'\]\['files'\]:

        if not Path(f\['path'\]).exists():

            bad.append((f\['path'\], 'neexistuje'))

        elif not f.get('parsed\_ok'):

            bad.append((f\['path'\], 'nejde přečíst: ' \+ str(f.get('errors'))))

        else:

            ok.append(f\['path'\])

    if bad:

        return violated('files\_readable', '; '.join(p \+ ': ' \+ m for p, m in bad), \[p for p, \_ in bad\])

    return met('files\_readable', ok)

@check('files', 'all\_inputs\_covered')

def all\_inputs\_covered(out, ctx):

    want \= set(ctx\['task\_input'\]\['paths'\])

    got \= {f\['path'\] for f in out\['result'\]\['files'\]}

    if want \- got:

        return unverified('all\_inputs\_covered', 'nezpracováno: ' \+ str(sorted(want \- got)))

    return met('all\_inputs\_covered', sorted(got))

\# \--- marketing\_mail \---

@check('marketing\_mail', 'mail\_complete')

def mail\_complete(out, ctx):

    r, bad \= out\['result'\], \[\]

    if '{{' in r\['body'\] or '\[' in r\['subject'\]:

        bad.append('nevyplněný placeholder')

    if r\['cta\_url'\] \!= ctx\['task\_input'\]\['cta'\]\['url'\]:

        bad.append('jiný odkaz než ve vstupu')

    if bad:

        return violated('mail\_complete', '; '.join(bad), \['result.body', 'result.cta\_url'\])

    return met('mail\_complete', \['result.body', 'result.cta\_url'\])

@check('marketing\_mail', 'numbers\_from\_facts')

def numbers\_from\_facts(out, ctx):

    missing, uncertain \= compare\_numbers(out\['result'\]\['body'\],

                                         ctx\['task\_input'\].get('facts', \[\]), ctx)

    if missing or uncertain:

        return unverified('numbers\_from\_facts', 'část čísel nebo jednotek vyžaduje věcnou kontrolu',

                          'needs\_evidence')

    return met('numbers\_from\_facts', \['result.body', 'input.facts'\])

@check('marketing\_mail', 'length\_ok', required=False)

def length\_ok(out, ctx):

    r \= out\['result'\]

    if len(r\['body'\].split()) \> ctx\['task\_input'\]\['constraints'\]\['max\_words'\] or len(r\['subject'\]) \> 80:

        return note('length\_ok', 'delší než limit')

    return None

\# \--- accounting \---

@check('accounting', 'totals\_match')

def totals\_match(out, ctx):

    r \= out\['result'\]

    net \= sum(Decimal(str(i\['net'\])) for i in r\['items'\])

    vat \= sum(Decimal(str(i\['vat'\])) for i in r\['items'\])

    bad \= \[\]

    if net \!= Decimal(str(r\['total\_net'\])):

        bad.append('součet net ' \+ str(net) \+ ' ≠ ' \+ str(r\['total\_net'\]))

    if net \+ vat \!= Decimal(str(r\['total'\])):

        bad.append('net \+ vat ' \+ str(net \+ vat) \+ ' ≠ ' \+ str(r\['total'\]))

    if bad:

        return violated('totals\_match', '; '.join(bad), \['items\[' \+ str(i) \+ '\]' for i in range(len(r\['items'\]))\])

    return met('totals\_match', \['calc:sum(items)'\])

@check('accounting', 'rows\_match\_input')

def rows\_match\_input(out, ctx):

    want, got \= len(ctx\['task\_input'\]\['rows'\]), len(out\['result'\]\['items'\])

    if want \!= got:

        return violated('rows\_match\_input', str(got) \+ ' položek, ve vstupu ' \+ str(want), \['result.items', 'input.rows'\])

    return met('rows\_match\_input', \['result.items', 'input.rows'\])

### **6.4 LLM kontrola (jen tam, kde kód nestačí)**

Právě LLM kontrola bývá důvodem, že ověřovatel nepouští skoro nic. Platí tato pravidla:

* ptá se na **jedno tvrzení po druhém**, ne na celek,  
* dostane tvrzení **a původní zdroj**,  
* může tvrzení **potvrdit** jen doslovným citátem, který kód ověří ve zdroji, jinak je výsledek NEOVĚŘENO,  
* může tvrzení **zamítnout** jen doslovným citátem ze zdroje, který mu odporuje (NESPLNĚNO); samotné nenašel jsem podporu zamítnutí není,  
* nikdy nepřepisuje výsledek kontroly provedené kódem, je to jen další kritérium vedle ostatních,  
* teplota 0 až 0.2, výstup jako JSON.

CLAIM\_SCHEMA \= {

    'type': 'object',

    'properties': {

        'supported': {'type': 'boolean'}, 'quote': {'type': 'string'},

        'contradicts': {'type': 'boolean'}, 'contradiction\_quote': {'type': 'string'},

    },

    'required': \['supported', 'quote', 'contradicts', 'contradiction\_quote'\],

}

def llm\_claim\_check(claim, source, llm\_json):

    if not source or not source.strip():

        return unverified('llm\_claim', 'chybí zdroj', 'needs\_evidence')

    r \= llm\_json(

        system=('Posuzuješ, zda zdroj výslovně obsahuje dané tvrzení. '

                'Pokud ho potvrzuje, dej supported=true a vlož podporující větu doslova do quote. '

                'Pokud mu zdroj výslovně odporuje, dej contradicts=true a vlož odporující větu '

                'doslova do contradiction\_quote. Jinak obě hodnoty false a citáty prázdné.'),

        user='TVRZENÍ:\\n' \+ claim \+ '\\n\\nZDROJ:\\n' \+ source,

        schema=CLAIM\_SCHEMA)

    cq, q \= r\['contradiction\_quote'\], r\['quote'\]

    src \= normalized\_quote(source)

    cq, q \= normalized\_quote(cq), normalized\_quote(q)

    if r\['contradicts'\] and r\['supported'\]:

        return unverified('llm\_claim', 'model vrátil rozporné hodnocení', 'needs\_evidence')

    if r\['contradicts'\] and cq and cq in src:

        return violated('llm\_claim', 'zdroj tvrzení vyvrací: ' \+ claim\[:80\], \[cq\])

    if r\['supported'\] and q and q in src:

        return met('llm\_claim', \[q\])

    return unverified('llm\_claim', 'tvrzení nepotvrzeno zdrojem: ' \+ claim\[:80\],

                      retry='needs\_evidence')

### **6.5 Proč ověřovatel nic nepouští a jak to ladit**

* **Tři verdikty, ne dva.** SPLNĚNO je přísnější než dřívější pass: chce důkaz ke každému povinnému kritériu. Proto držte povinná kritéria krátká (jen to, co opravdu znehodnocuje výsledek), jinak bude NEOVĚŘENO vznikat skoro vždy a ověřovatel zase nic nepustí.  
* **Nová kritéria nejdřív nepovinná** (required=False). Po ověření na testech je povyšte na povinná.  
* **NEOVĚŘENO není chyba specialisty.** Neposílá se zpět jako oprava. Sledujte jeho podíl: vysoký podíl značí problém prostředí (timeouty, chybějící zdroje), ne špatného specialistu.  
* **Kontrolujte kontrakt, ne vkus.** Ověřovatel se ptá, zda výstup splňuje zadání a schéma, ne zda by to napsal jinak.  
* **Měřte po kritériích.** Kritérium, které skoro vždy končí NESPLNĚNO nebo NEOVĚŘENO, je špatně napsané nebo příliš náročné.  
* **Tři testy na každé kritérium:** doložené splnění, doložené porušení a chybějící důkaz. Spouštějte je po každé změně pluginu, nejlépe na cílovém hardwaru.  
* **Konkrétní fix\_hint.** Musí říkat, co přesně opravit.

### **6.6 Smyčka opakování**

def next\_action(verdict, used, limits):

    \# Koordinátor použije uložený výsledek a trvale evidované počty.

    action \= verdict\['retry\_class'\]

    if verdict\['verdict'\] \== 'SPLNĚNO':

        return 'finalize'

    if action \== 'waiting\_input':

        return 'waiting\_input'

    if action in ('substantive', 'technical', 'needs\_evidence'):

        if used.get(action, 0\) \< limits.get(action, 0):

            return action

    return 'finalize'

Koordinátor eviduje samostatné rozpočty pro věcnou opravu, technické opakování a doplnění důkazu. Rozhoduje podle uloženého verdiktu a historie pokusů. Věcná oprava dostane jen porušená kritéria a má opravit pouze vadnou část výstupu. waiting\_input smyčku ukončí: krok čeká na podklad a koordinátor ho vrátí s důvodem. Po dvou neúspěšných věcných opravách se krok vrací s důvodem a důkazy, nepouští se dál.

### **6.7 Souběh programového a obsahového ověřování**

Ověřovatel je jedna logická role se dvěma typy práce v téže frontě. Programová kontrola používá místní pracovníka se zdrojem verify\_cpu. Obsahová kontrola používá samostatnou kapacitu, například zdroj llm, pokud se volá model. Obsahový pracovník nedrží slot verify\_cpu po dobu čekání na výsledek.

Koordinátor přijme a uloží programový výsledek. Obsahovou fázi zařadí pouze podle stavu připravenosti, který vrátí programová vrstva podle § 6.8. Mezitím může programový pracovník ověřovat jiné úlohy. Pro stejnou úlohu zůstávají fáze postupné a platí zámek úlohy a role. Koordinátor složí a zapíše výsledný verdikt po dokončení potřebných kontrol.

Konfigurace musí pro tento souběh povolit nejméně dva sloty fronty a dva sloty role Ověřovatel. Typické nastavení pro první zkoušku je fronta 2, Ověřovatel 2, verify\_cpu 1 a llm 1\. Při jednom globálním slotu nebo jednom slotu role se kontroly vykonávají postupně. U vytížené fronty lze vyhradit jeden slot programovým kontrolám. Dispečer v takovém režimu nepřidělí poslední vyhrazený slot jinému zdroji.

Přejímka zablokuje obsahové ověření úlohy A na řízeném vstupu. Programové ověření nezávislé úlohy B musí mezitím vrátit svůj verdikt. Opakování s limitem 1 má prokázat sériové zpracování. Přejímka také ověří, že obsahová fáze nemůže začít pro stejnou úlohu před dokončením programové kontroly a předávkou přes Koordinátora.

### **6.8 Podmínka spuštění obsahové kontroly a stavy připravenosti**

Před během profil scénáře určí povinná obsahová kritéria a u každého požadované důkazy. Například pro porovnání podmínek dvou stránek vyžaduje dva textové výřezy, očekávané zdrojové stránky, jazyk a vazbu na pokus.

Specialista uloží skutečné artefakty a záznam jejich původu. Programová vrstva Ověřovatele podle profilu zkontroluje, že požadované artefakty existují, jsou čitelné a mají doloženou shodu identifikátorů úlohy, pokusu a zdroje. Obsahovou přiměřenost posoudí až obsahová vrstva.

Programová vrstva Ověřovatele (fáze verify\_cpu) vyhodnotí přechod do obsahové fáze (verify\_content se zdrojem llm) a vrátí právě jeden ze čtyř stavů připravenosti:

* **not\_needed**: Žádné povinné obsahové kritérium není vyžadováno. Obsahová fáze se nespouští.  
* **skipped\_due\_to\_failure**: Programová kontrola již doložila porušení (violated). Výsledek je ihned NESPLNĚNO a LLM se nevolá.  
* **waiting\_for\_evidence**: Chybí nebo nelze načíst požadované podklady. LLM se nespouští, vrací se verdikt NEOVĚŘENO s třídou opakování needs\_evidence.  
* **ready**: Všechny programové kontroly prošly a podklady jsou kompletní. Do obsahové fáze se předají výhradně zbývající povinná obsahová kritéria a ověřené odkázané důkazy.

Koordinátor přidělí obsahovou fázi v téže frontě jen při stavu ready. Přenese ID kritérií a odkazy na důkazy. Kontrolu čitelnosti, původu a úplnosti podkladů provádí programová vrstva Ověřovatele. Pokud stav zůstane waiting\_for\_evidence, zaznamená se překážka a dotčené kritérium zůstane NEOVĚŘENO.

Přejímka. U shody podmínek scénář s oběma čitelnými výřezy ze správného pokusu vede k ready. Chybějící výřez, nečitelný soubor nebo odkaz na jiný pokus vede k waiting\_for\_evidence a obsahový pracovník se nespustí. Výslednou významovou shodu vydá jako verdikt až Ověřovatel.

Stav implementace. Současná ukázka webové kontroly rozpoznává potřebu obsahové vrstvy. Stav required ještě nepotvrzuje připravenost jejích vstupů. Pro automatické zařazení je nutné doplnit programovou kontrolu důkazů a výslovný stav ready podle této sekce.

## **7\. Syntetizátor**

### **7.1 Úloha**

Sestaví jeden finální výstup ze **schválených** výstupů. Nepřidává fakta, nezahlazuje rozpory a vše podstatné opírá o evidence.

### **7.2 Vstupní kontrakt**

{

  "goal": "Měsíční přehled pro vedení",

  "format": "report",

  "language": "cs",

  "approved": \[ { "step\_id": "s1", "kind": "files", "result": { }, "evidence": \[ \] } \],

  "unverified": \[ { "step\_id": "s3", "reason": "3 pokusy, stále fail: součet nesedí" } \]

}

Syntetizátor dostává výtahy, ne původní dlouhé texty. Díky tomu se vejde do menšího kontextu.

### **7.3 Výstupní kontrakt (Deliverable)**

{

  "status": "ok",

  "deliverable": { "format": "report", "content": "..." },

  "claims": \[ { "text": "Celkem 12 100 Kč", "evidence\_refs": \["s2\#0"\] } \],

  "conflicts": \[ { "topic": "datum", "a": "s1: 3\. 10.", "b": "s2: 5\. 10." } \],

  "gaps": \[ "Krok s3 nebyl ověřen, jeho data nejsou ve výstupu." \]

}

### **7.4 Prompt a pravidla**

* Používej výhradně data ze vstupu. Žádná nová fakta ani čísla.  
* U každého tvrzení uveď evidence\_refs.  
* Rozpory nevyhlazuj, uveď je v conflicts.  
* Neověřené kroky nepoužívej, uveď je v gaps.  
* Piš česky, věcně.

### **7.5 Kontroly po syntéze (kód)**

@check('synthesis', 'refs\_exist')

def refs\_exist(out, ctx):

    refs \= \[r for c in out\['claims'\] for r in c\['evidence\_refs'\]\]

    bad \= \[r for r in refs if r not in ctx\['known\_refs'\]\]   \# např. {'s2\#0', 's2\#1'}

    if bad or any(not c\['evidence\_refs'\] for c in out\['claims'\]):

        return violated('refs\_exist', 'chybějící nebo neznámé reference', \['claims'\])

    if not out\['claims'\] and out\['deliverable'\]\['content'\].strip():

        return unverified('refs\_exist', 'text nemá doložený seznam tvrzení', 'needs\_evidence')

    return met('refs\_exist', refs or \['claims'\])

@check('synthesis', 'numbers\_known', required=False)

def numbers\_known(out, ctx):

    missing, uncertain \= compare\_numbers(out\['deliverable'\]\['content'\],

                                         \[ctx\['allowed\_text'\]\] if ctx.get('allowed\_text') else \[\], ctx)

    if missing or uncertain:

        return note('numbers\_known', 'část čísel nebo jednotek vyžaduje kontrolu zdroje')

    return None

@check('synthesis', 'gaps\_reported')

def gaps\_reported(out, ctx):

    if ctx\['unverified\_count'\] and not out\['gaps'\]:

        return violated('gaps\_reported', 'neověřené kroky nejsou v gaps',

                        \['unverified:' \+ str(ctx\['unverified\_count'\])\])

    return met('gaps\_reported', \['gaps'\])

\# volání: verify('synthesis', deliverable, ctx, common=False)

Syntetizátor má vlastní obálku (bez task\_id a step\_id), proto se pro něj verify volá s common=False a společné kontroly se přeskočí.

**Opravná smyčka a záložní režim syntézy:**

* Pokud verify('synthesis', ...) vrátí NESPLNĚNO (např. chybějící reference v refs\_exist nebo nezapsané neověřené kroky v gaps\_reported), Koordinátor předá Syntetizátoru cílenou opravu s fix\_hint v rámci limitu pokusů (výchozí 1–2 pokusy).  
* Pokud syntéza neprojde ani po vyčerpání pokusů, výstup se nepředá jako neověřený volný text, ale Koordinátor vrátí strukturovaný záložní výstup (seznam schválených výstupů a mezer gaps) s označením NEOVĚŘENO.

def synthesize\_or\_fallback(generate, validate, approved, gaps, max\_repairs=1):

    if type(max\_repairs) is not int or max\_repairs \< 0:

        raise ValueError('limit oprav musí být nezáporné celé číslo')

    feedback \= None

    for attempt in range(1 \+ max\_repairs):

        output \= generate(approved, gaps, feedback)

        decision \= validate(output)

        if decision\['verdict'\] \== 'SPLNĚNO':

            return {'verdict': 'SPLNĚNO', 'mode': 'synthesis', 'output': output}

        if decision\['verdict'\] \!= 'NESPLNĚNO' or attempt \== max\_repairs:

            break

        feedback \= decision\['fix\_hint'\]

    return {'verdict': 'NEOVĚŘENO', 'mode': 'structured\_fallback',

            'approved': approved, 'gaps': gaps,

            'reason': 'Souhrnný text neprošel ověřením.'}

Kdy syntetizátor vynechat: pokud je výsledkem jeden strukturovaný výstup (např. extrakce do JSON), koordinátor jej jen předá dál.

## **8\. Konfigurace úkolu (YAML)**

task: "Zkontrolovat nové podklady, spočítat součty a připravit informační e-mail"

language: cs

coordinator:

  mode: fixed          \# fixed \= deterministický pipeline (0 tokenů), llm \= jednorázový planner

  llm\_planner:

    enabled: false

    max\_plan\_tokens: 1500

    max\_plan\_repairs: 1

llm\_routing:

  defaults:

    provider: local    \# local (Ollama) \| cloud (API)

    model: qwen3.5:4b

    max\_tokens: 1200

  roles:

    planner: { provider: local, model: "qwen3.5:4b", max\_tokens: 1500 }

    verifier\_content: { provider: local, model: "qwen3.5:4b" }

    synthesizer: { provider: cloud, model: "gemini-2.5-flash", max\_tokens: 2500 }

specialists:

  \- { name: soubory, kind: files }

  \- { name: ucetni,  kind: accounting }

  \- { name: mail,    kind: marketing\_mail }

verification:

  retries:

    substantive: 2

    technical: 2

    needs\_evidence: 1

  llm\_check: false     \# zapnout jen tam, kde to dává smysl

synthesis:

  enabled: true

  format: report

limits:

  max\_steps: 20

  max\_total\_tokens: 200000

  max\_minutes: 60

\# Příklad provozních limitů pro lokální prostředí (\~10 GB RAM):

\# bezpečný start parallelism: 1 nebo 2, prohlížeč vždy browser: 1, llm: 1\.

queue:

  parallelism: 2

  paused: false

  reserve\_verify\_cpu: false

  roles:

    overovatel: 2

    tester\_webu: 1

  resources:

    browser: 1

    verify\_cpu: 1

    llm: 1

## **9\. Společná fronta a pracovníci**

### **9.1 Předávky a závislosti**

Koordinátor řídí jedinou frontu pro všechny specialisty. Tok je fronta → Koordinátor → specialista → Koordinátor → nezávislý Ověřovatel → Koordinátor → zápis. Každá fáze má stabilní ID a ukládá svůj vlastní výstup. Závislost mezi úlohami vyžaduje kladný konečný verdikt. Předání k ověření může následovat i po výsledku s doloženou překážkou. Syntéza čeká na uzavření seznamu podúloh a ukončení všech jeho položek.

### **9.2 Limity a změny za běhu**

Kapacita fronty, role a sdíleného zdroje se vyjadřuje kladným celým číslem. Hodnota 1 představuje jeden slot. Při frontě 5 a limitech 1 u všech rolí může současně běžet až pět různých rolí, pokud mají připravenou práci a volné zdroje. Při frontě 1 poběží vždy nejvýše jedna práce, i kdyby jedna role měla limit 5\. Vynechaný limit role či zdroje ponechá ostatní stropy v platnosti.

Nastavení je uložené v SQLite a projeví se při dalším převzetí. Snížení limitu na 1 nejdřív nechá dotčené práce doběhnout. paused zastaví nová převzetí bez zrušení rozběhnuté práce. Zámek dvojice úloha a role zůstává po celou dobu převzetí. Nezávislé kroky téže role lze rozdělit do samostatných dílčích úloh s vlastními ID.

Programová a obsahová kontrola mají samostatné zdroje verify\_cpu a llm podle § 6.7. Pro souběh zvol alespoň dva globální sloty a dva sloty role Ověřovatele. Rezervace zachová jeden globální slot pro programové kontroly i při zatížení ostatními rolemi. Připravené položky se vybírají podle priority a pořadí přijetí.

### **9.3 Převzetí, zápis a obnova**

Výběr, zámek a rezervace slotu proběhnou v jedné krátké transakci SQLite. Výsledek může zapsat pouze pracovník s aktuálním tokenem v době jeho platnosti. Historie uchovává převzetí, výsledky i obnovu. Vypršení tokenu uvolní slot až po potvrzení ukončení pracovníka a posouzení rizika opakování. Po vyčerpání pokusů se položka uzavře jako blokovaná s neověřeným výsledkem.

### **9.4 Referenční kód SQLite a Pythonu**

Ukázka provádí přidělení a předávky jednotlivých fází. Pracovní funkce a obsahové kontroly se volají mimo transakce. Adaptér před dokončením fáze uloží a validuje artefakt. Koordinátor rozhoduje, kterou následnou fázi zařadí a kdy lze bezpečně opakovat vnější akci.

"""Reference SQLite dispatcher. Handlers execute only outside transactions."""

import json

import sqlite3

import time

from collections import Counter

from contextlib import contextmanager

from uuid import uuid4

SCHEMA \= """

PRAGMA journal\_mode=WAL;

PRAGMA foreign\_keys=ON;

CREATE TABLE IF NOT EXISTS config (

    id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL

);

INSERT OR IGNORE INTO config VALUES (1, '{"parallelism":1}');

CREATE TABLE IF NOT EXISTS job (

    id TEXT PRIMARY KEY, task TEXT NOT NULL, role TEXT NOT NULL,

    resource TEXT NOT NULL, phase TEXT NOT NULL,

    parent\_id TEXT REFERENCES job(id), children\_closed INTEGER NOT NULL DEFAULT 1,

    priority INTEGER NOT NULL DEFAULT 50, payload TEXT NOT NULL,

    state TEXT NOT NULL DEFAULT 'pending',

    attempt INTEGER NOT NULL DEFAULT 0,

    max\_attempts INTEGER NOT NULL CHECK(max\_attempts \>= 1),

    token TEXT, deadline REAL, worker TEXT, ready\_at REAL NOT NULL DEFAULT 0,

    artifact TEXT, verdict TEXT, feedback TEXT,

    CHECK(state IN ('pending','running','done','blocked')),

    CHECK(phase IN ('specialist','verify\_cpu','verify\_content','finalize'))

);

CREATE TABLE IF NOT EXISTS evidence (

    task\_id TEXT NOT NULL, ref TEXT NOT NULL, step\_id TEXT NOT NULL REFERENCES job(id),

    attempt INTEGER NOT NULL, evidence\_id TEXT NOT NULL, type TEXT NOT NULL,

    uri TEXT, excerpt TEXT, sha256 TEXT, PRIMARY KEY (task\_id, ref)

);

CREATE VIEW IF NOT EXISTS v\_evidence\_overview AS

SELECT e.task\_id, e.step\_id, e.attempt, e.ref, e.type, e.evidence\_id, j.verdict AS step\_verdict, e.uri, substr(e.excerpt, 1, 80\) AS excerpt\_preview

FROM evidence e LEFT JOIN job j ON j.task \= e.task\_id AND j.id \= e.step\_id AND j.attempt \= e.attempt;

CREATE UNIQUE INDEX IF NOT EXISTS active\_task\_role

    ON job(task, role) WHERE state='running';

CREATE TABLE IF NOT EXISTS dependency (

    job\_id TEXT NOT NULL REFERENCES job(id),

    predecessor TEXT NOT NULL REFERENCES job(id),

    needs\_pass INTEGER NOT NULL CHECK(needs\_pass IN (0,1)),

    PRIMARY KEY(job\_id,predecessor), CHECK(job\_id \!= predecessor)

);

CREATE TABLE IF NOT EXISTS history (

    seq INTEGER PRIMARY KEY, job\_id TEXT NOT NULL REFERENCES job(id),

    attempt INTEGER NOT NULL, event TEXT NOT NULL, at REAL NOT NULL, details TEXT

);

"""

def connect(path):

    db \= sqlite3.connect(path, isolation\_level=None, timeout=5)

    db.row\_factory \= sqlite3.Row

    db.executescript(SCHEMA)

    return db

@contextmanager

def transaction(db):

    db.execute("BEGIN IMMEDIATE")

    try:

        yield

        db.commit()

    except BaseException:

        db.rollback()

        raise

def configure(db, parallelism=1, \*, paused=False, roles=None, resources=None,

              reserve\_verify\_cpu=False):

    roles, resources \= roles or {}, resources or {}

    if any(type(v) is not int or v \< 1

           for v in \[parallelism, \*roles.values(), \*resources.values()\]):

        raise ValueError("Limity musí být kladná celá čísla.")

    if type(paused) is not bool or type(reserve\_verify\_cpu) is not bool:

        raise ValueError("Přepínače musí být typu boolean.")

    if reserve\_verify\_cpu and parallelism \< 2:

        raise ValueError("Rezervace vyžaduje alespoň dva sloty fronty.")

    value \= dict(parallelism=parallelism, paused=paused, roles=roles,

                 resources=resources, reserve\_verify\_cpu=reserve\_verify\_cpu)

    with transaction(db):

        db.execute("UPDATE config SET value=? WHERE id=1", (json.dumps(value),))

def \_event(db, row, kind, detail=None):

    db.execute("INSERT INTO history VALUES (NULL,?,?,?,?,?)",

               (row\["id"\], row\["attempt"\], kind, time.time(), detail))

def enqueue(db, \*, id, task, role, resource, phase, payload,

            depends\_on=(), parent\_id=None, children\_closed=True,

            priority=50, max\_attempts=3):

    """Each dependency is (previous phase ID, requires a positive verdict)."""

    with transaction(db):

        if parent\_id is not None:

            parent \= db.execute("SELECT \* FROM job WHERE id=?", (parent\_id,)).fetchone()

            if parent is None or parent\["children\_closed"\] or parent\["state"\] \!= "pending":

                raise ValueError("Rodič nepřijímá nové podúlohy.")

        db.execute("""INSERT INTO job(id,task,role,resource,phase,parent\_id,

                     children\_closed,priority,payload,max\_attempts)

                     VALUES (?,?,?,?,?,?,?,?,?,?)""",

                   (id, task, role, resource, phase, parent\_id, int(children\_closed),

                    priority, json.dumps(payload, sort\_keys=True), max\_attempts))

        \# Odkazy pouze na dříve uložené položky. Tím nevznikne cyklus.

        for previous, needs\_pass in depends\_on:

            db.execute("INSERT INTO dependency VALUES (?,?,?)",

                       (id, previous, int(needs\_pass)))

        \_event(db, {"id": id, "attempt": 0}, "queued")

def close\_children(db, id):

    with transaction(db):

        db.execute("UPDATE job SET children\_closed=1 WHERE id=? AND state='pending'", (id,))

def claim(db, worker, resources, lease=300):

    with transaction(db):

        cfg \= json.loads(db.execute("SELECT value FROM config WHERE id=1").fetchone()\[0\])

        active \= db.execute("SELECT \* FROM job WHERE state='running'").fetchall()

        if cfg.get("paused") or len(active) \>= cfg\["parallelism"\]:

            return None

        roles \= Counter(r\["role"\] for r in active)

        used \= Counter(r\["resource"\] for r in active)

        owners \= {(r\["task"\], r\["role"\]) for r in active}

        now \= time.time()

        candidates \= db.execute("""

            SELECT j.\* FROM job j

            WHERE j.state='pending' AND j.children\_closed AND j.ready\_at \<= ?

            AND NOT EXISTS (

                SELECT 1 FROM job c WHERE c.parent\_id=j.id

                    AND c.state NOT IN ('done','blocked'))

            AND NOT EXISTS (

                SELECT 1 FROM dependency d JOIN job p ON p.id=d.predecessor

                WHERE d.job\_id=j.id

                  AND (p.state NOT IN ('done','blocked')

                       OR (d.needs\_pass AND p.verdict IS NOT 'SPLNĚNO')))

            ORDER BY j.priority, j.rowid

        """, (now,))

        for row in candidates:

            role, resource \= row\["role"\], row\["resource"\]

            if resource not in resources or (row\["task"\], role) in owners:

                continue

            if roles\[role\] \>= cfg.get("roles", {}).get(role, float("inf")):

                continue

            if used\[resource\] \>= cfg.get("resources", {}).get(resource, float("inf")):

                continue

            if (cfg.get("reserve\_verify\_cpu") and resource \!= "verify\_cpu"

                    and not used\["verify\_cpu"\] and len(active) \== cfg\["parallelism"\] \- 1):

                continue

            token \= uuid4().hex

            db.execute("""UPDATE job SET state='running', worker=?, token=?,

                          deadline=?, attempt=attempt+1 WHERE id=?""",

                       (worker, token, now \+ lease, row\["id"\]))

            claimed \= dict(row, state="running", token=token, deadline=now \+ lease,

                           worker=worker, attempt=row\["attempt"\] \+ 1\)

            \_event(db, claimed, "claimed", worker)

            return claimed

        return None

def renew(db, id, token, lease=300):

    with transaction(db):

        now \= time.time()

        return db.execute("""UPDATE job SET deadline=? WHERE id=? AND state='running'

                             AND token=? AND deadline\>?""",

                          (now \+ lease, id, token, now)).rowcount \== 1

def finish(db, id, token, artifact, verdict=None, feedback=None):

    if not artifact or verdict not in (None, "SPLNĚNO", "NESPLNĚNO", "NEOVĚŘENO"):

        raise ValueError("Chybí důkaz nebo verdikt není platný.")

    with transaction(db):

        row \= db.execute("""SELECT \* FROM job WHERE id=? AND state='running'

                            AND token=? AND deadline\>?""",

                         (id, token, time.time())).fetchone()

        if row is None:

            return False

        now \= time.time()

        if verdict \== "SPLNĚNO" or row\["phase"\] \== "finalize":

            db.execute("""UPDATE job SET state='done', artifact=?, verdict=?, feedback=?,

                          token=NULL, deadline=NULL, worker=NULL WHERE id=?""",

                       (artifact, verdict, feedback, id))

        elif verdict in ("NESPLNĚNO", "NEOVĚŘENO") and row\["attempt"\] \< row\["max\_attempts"\]:

            backoff \= min(60, 2 \*\* min(row\["attempt"\], 6))

            db.execute("""UPDATE job SET state='pending', artifact=?, verdict=?, feedback=?,

                          ready\_at=?, token=NULL, deadline=NULL, worker=NULL WHERE id=?""",

                       (artifact, verdict, feedback, now \+ backoff, id))

        else:

            db.execute("""UPDATE job SET state='blocked', artifact=?, verdict=?, feedback=?,

                          token=NULL, deadline=NULL, worker=NULL WHERE id=?""",

                       (artifact, verdict or "NEOVĚŘENO", feedback, id))

            \_block\_dependents(db, id)

        \_event(db, row, "finished", artifact)

        return True

def \_block\_dependents(db, failed\_job\_id):

    deps \= db.execute("SELECT job\_id FROM dependency WHERE predecessor=? AND needs\_pass=1", (failed\_job\_id,)).fetchall()

    for d in deps:

        db.execute("UPDATE job SET state='blocked', verdict='NEOVĚŘENO' WHERE id=? AND state='pending'", (d\["job\_id"\],))

        \_block\_dependents(db, d\["job\_id"\])

def enqueue\_url\_check\_batch(db, parent\_task\_id, urls, batch\_size=5):

    """Deterministický rozpad dávky URL na podúlohy pro koordinátor."""

    for i in range(0, len(urls), batch\_size):

        chunk \= urls\[i:i \+ batch\_size\]

        sub\_id \= f"{parent\_task\_id}-batch-{i//batch\_size}"

        enqueue(db, id=sub\_id, task=parent\_task\_id, role="tester\_webu", resource="browser",

                phase="specialist", payload={"urls": chunk}, parent\_id=parent\_task\_id)

\# Komplexní stavový automat, evidence a obnova běhů jsou implementovány v coordinator\_queue.py

\# (včetně register\_evidence, submit\_specialist\_result, advance\_after\_verify\_cpu, finish\_verification, \_propagate\_blocked, collect\_children\_results a recover).

def recover(db, id, token, \*, stopped, safe\_to\_retry):

    """Coordinator confirms termination and resolves any external effects first."""

    if not stopped:

        return False

    with transaction(db):

        now \= time.time()

        row \= db.execute("""SELECT \* FROM job WHERE id=? AND state='running'

                            AND token=? AND deadline\<=?""", (id, token, now)).fetchone()

        if row is None:

            return False

        retry \= safe\_to\_retry and row\["attempt"\] \< row\["max\_attempts"\]

        db.execute("""UPDATE job SET state=?, verdict=?, ready\_at=?, token=NULL,

                      deadline=NULL, worker=NULL WHERE id=?""",

                   ("pending" if retry else "blocked", None if retry else "NEOVĚŘENO",

                    now \+ min(60, 2 \*\* min(row\["attempt"\], 6)), id))

        \_event(db, row, "requeued" if retry else "recovery\_blocked")

        return True

### **9.5 Přejímka fronty**

Ověřit změnu konfigurace za běhu, doběhnutí při snížení, pauzu, souběh nezávislých úloh, zákaz souběhu stejné role nad stejnou úlohou, zámek platnosti převzetí, odmítnutí pozdního zápisu, omezenou obnovu a blokaci neověřených závislostí. Obsahová kontrola úlohy A musí umožnit programovému pracovníkovi dokončit nezávislou úlohu B.

## **10\. Provozní prostředí a kapacita (RAM & limity)**

Limity pracovníků a modely jsou nastavení nasazení. Při provozu v prostředí s cca 10 GB použitelné paměti RAM je nutné počítat s paměťovými špičkami: souběh prohlížeče Chromium (1.5–2.5 GB), lokálního Ollama modelu 4B/12B (4–7 GB) a systémového swapu. Prohlížeč je proto striktně omezen na browser: 1 a aktivuje se vyhrazený slot reserve\_verify\_cpu. Pro první běh se doporučuje začít s jedním globálním slotem a kapacitu rozšiřovat až na základě naměřených profilů.

### **10.1 OS-level sandbox, oprávnění k vnějším akcím a MCP**

* **Izolace procesu na úrovni OS:** Kromě sandboxu samotného prohlížeče (§ 5.2.1) lze celý běh specialisty izolovat na úrovni operačního systému (na Linuxu a WSL2 pomocí Bubblewrap, na Windows přes MXC) s výchozím režimem pouze pro čtení. Před ostrým během se ověřuje start izolovaného prostředí kontrolou bez volání modelu (\--check).  
* **Oddělení oprávnění k akci od ověření kvality:** Výchozí oprávnění specialisty jsou omezena na čtení; zápis do souborového systému, odeslání e-mailu nebo volání externího API vyžaduje explicitní povolení pro konkrétní cíl. Přístup k externím nástrojům a MCP serverům je řízen správcovskou konfigurací hostitele (povolený seznam serverů a omezení nástrojů). Ověřovatel (§ 6\) přitom nadále posuzuje výhradně kvalitu a doložitelnost výstupu, nikoliv udělování oprávnění.

## **11\. Logování a ladění**

Každý krok zapisujte jako jeden řádek (JSONL): čas, task\_id, step\_id, attempt, vstup (nebo jeho hash), výstup, verdikt, trvání, tokeny. Z logů pak zjistíte:

* které kontroly blokují nejčastěji (kandidáti na přehnaně přísné),  
* kteří specialisté potřebují nejvíc opakování (slabý prompt nebo schéma),  
* kolik úkolů končí jako neověřené.

* **Detekce neúplného běhu a uzavření auditu (audit\_neuplny):** Každý běh úlohy musí být v JSONL logu uzavřen validním závěrečným záznamem se stavem úlohy, výsledkem ověření a počtem oprav. Pokud záznam po pádu procesu nebo přerušení chybí či je neplatný, systém běh automaticky označí stavem audit\_neuplny, aby nedošlo k záměně přerušeného běhu za úspěšně dokončený. Samotné zalogování volání nástroje přitom nedokládá úspěch externí akce (ten musí potvrdit důkaz v ResultEnvelope.evidence).

## **12\. Kontrolní seznam implementace**

1. Definujte obálky (zadání kroku, výstup specialisty, verdikt, výstup syntetizátoru) jako JSON schémata s schema\_version.  
2. Napište jádro ověřovatele (R, check, verify, build\_verdict) a společné kontroly.  
3. Implementujte specialisty jako adaptéry nad nástroji (prohlížeč, parsery, kalkulace).  
4. Ke každému kind přidejte plugin kritérií a ke každému kritériu tři testy: doložené splnění, doložené porušení, chybějící důkaz.  
5. Napište koordinátora jako pevný pipeline, LLM plánování přidejte až později.  
6. Přidejte syntetizátora a jeho kontroly po syntéze.  
7. Zaveďte idempotentní stav a zápis (task\_id, step\_id, attempt) a limity (pokusy, kroky, tokeny, čas).  
8. Zapněte logování a kalibrujte povinná kritéria podle podílu NESPLNĚNO a NEOVĚŘENO. Zajistěte uzavírání JSONL auditu s detekcí neúplných běhů (audit\_neuplny) a omezení oprávnění specialistů na výchozí režim jen pro čtení.

## **13\. Otevřené body před nasazením**

* Pro specializované profily zbývá určité konkrétní zdroje důkazů, bezpečné hranice vedlejších účinků a měřitelné podmínky přijetí. Po výběru cílového prostředí je potřeba ověřit kapacitu pracovníků, obsahovou přesnost dostupného modelu a funkčnost prohlížeče se zapnutou izolací.

* Samostatná integrační přejímka má doložit trvalé převzetí výstupu specialisty a následné ověření po restartu, uložení finálního výsledku a zachování všech pokusů. U vnějších akcí musí implementace doložit skutečný stav před bezpečným opakováním. Opravná smyčka syntézy a její záložní režim při selhání jsou specifikovány v § 7.5. U migrace existující databáze ověřit převod i obnovu na kopii dat.

* Závěry k rozdělení úloh, vlastní kontrole specialisty, nezávislému ověřování, souběhu a zámkům jsou součástí hlavního návrhu v § 5.7, § 6.7 a § 9\.

* 

## **14\. Záznam revize (co a proč bylo upraveno)**

* **Oprava formátování § 5.2 (portable Chromium):** Nadpis sekce o přenosnosti prohlížeče byl přesunut nad příslušné odrážky a srovnáno odsazení, aby byl text čitelný a strukturálně konzistentní.

* **Zámek (task, role) v § 9.4 ponechán beze změny (architektonické rozhodnutí):** Zámek jedné běžící instance role na úlohu zůstává záměrně zachován – při dávkovém testování více URL v rámci jedné úlohy se tím předchází opakovanému otevírání a zavírání izolovaného sandboxu prohlížeče a zbytečnému vytěžování prostředků serveru.

* Kontrola čísel v § 6.3 a § 7.5. Ukázky porovnávají dvojici číselná hodnota a jednotka podle předem daného formátu. Regrese pokrývá mezery, záporná čísla, procenta, odlišnou měnu a oddělené řádky.

* Přejímka syntézy v § 7.5. Python po doloženém porušení předá cílenou opravu a při vyčerpání pokusů vrátí strukturovaný souhrn ověřených výstupů a mezer. Příklady byly ověřeny s řízenými odpověďmi adaptéru.

* **Sjednocení kontraktů a evidence (§ 3, § 6.8, § 9.4):** Zaveden kanonický odkaz evidence (\<step\_id\>\#\<index\>), tabulka evidence, pohled v\_evidence\_overview, 4 stavy připravenosti obsahové fáze a kaskádové blokování selhaných závislostí.

* **Deterministický rozpad a správa paměti (§ 4.2, § 5.2, § 8, § 10):** Výchozí režim fixed s 0 tokeny, jednorázový planner llm s validací, dávkový rozpad URL na podúlohy, periodický restart Chromia (po 20–25 URL) a konfigurace limitů pro 10 GB RAM.

* **Doplnění OS sandboxu, řízení oprávnění a detekce neúplného auditu (§ 10.1, § 11, § 12):** Převzaty osvědčené vzory ze šablony codex-agent-template – izolace běhu na úrovni OS (Bubblewrap/MXC s kontrolou \--check), oddělení oprávnění k vnějším akcím a MCP od věcného ověřování a povinné uzavírání JSONL auditu s označením přerušených běhů jako audit\_neuplny.

## **15\. Architektonická revize (důkazy, stavový automat, dávkování URL a směrování LLM)**

### **15.1 Sjednocení důkazů (evidence), available\_refs a předávání attempt**

* Každý důkaz v ResultEnvelope.evidence nese jednotnou strukturu:

```json
{
  "ref": "s2#0",
  "id": "faktura-1",
  "type": "file",
  "uri": "data/faktura.pdf",
  "excerpt": "Celkem: 12 100 Kč",
  "attempt": 1
}
```

* ref je unikátní odkaz v rámci úlohy ve formátu \<step\_id\>\#\<index\> (např. s2\#0), id je stabilní lidský identifikátor důkazu, uri je cesta k fyzickému artefaktu (povinná u file, screenshot, log) a attempt váže důkaz na konkrétní pokus běhu.  
* Číslo pokusu (attempt) vzniká při převzetí v SQLite frontě (attempt \+ 1), přenáší se do TaskEnvelope.attempt, ResultEnvelope.attempt i Verdict.attempt. Autoritativním zdrojem pravdy je databáze.

### **15.2 Duální režim koordinátoru (fixed vs. llm) a směrování lokálního/cloudového LLM**

* Koordinátor je vždy deterministický Python stavový automat nad SQLite frontou (řídí pořadí, zámky, rozpad dávek, opakování, rozpočty a ukončení).  
* **mode: fixed (výchozí režim — 0 tokenů, 0 LLM):** Plán kroků, typy (kind), pravidla rozpadu dávek (split\_by) a závislosti (depends\_on) jsou dané v YAML šabloně. Vhodné pro všechny opakovatelné úlohy (noční kontrola URL, kontrola faktur a DPH, přejímka exportů).  
* **mode: llm (řízené dynamické plánování — 1 volání modelu na startu):** Model se volá jen jednorázově pro ad-hoc zadání volným textem bez šablony. Omezení: striktní JSON výstup podle schématu, teplota 0.0–0.2, pouze registrované kind, zákaz generování velkých dávek (model navrhne jen dávkový krok s pravidlem rozpadu a podúlohy založí kód koordinátoru), kontrola přes validate\_plan(), max. 1 opravný pokus (max\_plan\_repairs: 1) a vlastní tokenový strop (max\_plan\_tokens).  
* **Směrování lokálního vs. cloudového LLM (llm\_routing):** Poskytovatel (provider: local pro Ollamu vs. provider: cloud pro API), model a limity se konfigurují přes výchozí profil (defaults) a přepisují podle role (planner, verifier\_content, synthesizer) podle aktuální verze AI a dostupných kvót.

### **15.3 Dávkový rozpad URL a správa prohlížeče (web\_test)**

* Rozpad velkých seznamů (např. 100 URL při kontrole přechodu z nabídky na detail) provádí deterministický kód koordinátoru před/při zařazení do fronty jako podúlohy (parent\_id \+ children\_closed), nikoliv samotný specialista.  
* Specialista web\_test zpracovává každou podúlohu v novém izolovaném BrowserContext (vždy uzavřeném ve finally) a po každých cca 20–25 URL bezpečně zrecykluje samotný proces prohlížeče, aby uvolnil akumulovanou paměť Chromia.  
* Snímky obrazovky (screenshot) se ukládají přednostně při chybě (failed) nebo u vybraných milníků; u všech kroků se ukládá lehký strukturovaný log. Díky zámku (task, role) běží v rámci jednoho ID úlohy vždy nejvýše 1 prohlížeč pro ochranu RAM; pro paralelní běh více prohlížečů na větším stroji je třeba rozdělit dávku do více samostatných ID úloh.

### **15.4 Provozní limity na \~10 GB RAM**

* Bezpečný startovní profil: parallelism: 1 nebo 2, browser: 1, llm: 1, reserve\_verify\_cpu: false (zapnout až po ověření využití RAM a swapu).  
* Oddělení paměťových špiček mezi Chromiem a většími modely (např. 12b při syntéze). Nová kritéria nasazovat nejprve jako required=False a povyšovat na povinná až po odladění podle JSONL logů.

### **15.5 Rozšíření SQLite schématu a stavového automatu (§ 9.4)**

* **Tabulka evidence a pohled v\_evidence\_overview:**

```sql
CREATE TABLE IF NOT EXISTS evidence (
    task_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    step_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    evidence_id TEXT NOT NULL,
    type TEXT NOT NULL,
    uri TEXT,
    excerpt TEXT,
    sha256 TEXT,
    PRIMARY KEY (task_id, ref)
);

CREATE VIEW IF NOT EXISTS v_evidence_overview AS
SELECT
    e.task_id,
    e.step_id,
    e.attempt,
    e.ref,
    e.type,
    e.evidence_id,
    j.verdict AS step_verdict,
    e.uri,
    substr(e.excerpt, 1, 80) AS excerpt_preview
FROM evidence e
LEFT JOIN job j
  ON j.task = e.task_id
 AND j.id = e.step_id
 AND j.attempt = e.attempt;
```

* **Stavový automat opakování a blokování závislostí:**  
  * Při NESPLNĚNO / NEOVĚŘENO se zbývajícím rozpočtem pokusů se úloha vrací do state='pending' se zachováním dosaženého attempt, vynulovaným verdict, doplněným feedback (u substantive) a ready\_at backoffem.  
  * Po vyčerpání pokusů se úloha uzavře jako state='blocked' a kaskádově zablokuje navazující kroky se závislostí needs\_pass=1 (událost blocked\_by\_predecessor).  
  * Při dokončení fáze verify\_cpu se stavem připravenosti 'ready' (§ 6.8) koordinátor přepne tentýž řádek v job do state='pending', phase='verify\_content', resource='llm'.  
  * Dávkový rozpad URL do podúloh řídí deterministický expander (enqueue\_url\_check\_batch) s vazbou parent\_id a uzavřením dětí přes close\_children().

### **15.6 Hlídání živosti běhu (renew / heartbeat), volání LLM a obnova po vypršení lease**

* **Podmíněné prodlužování lease (renew):** Samotný LLM ani prohlížeč do fronty nic nezapisují — živost běhu hlídá Python worker, který krok převzal (claim()). Worker volá renew(db, job\_id, token, lease) pouze tehdy, když zaznamená reálný pokrok (např. další zpracovanou URL v dávce nebo příchozí tokeny ze streamovaného volání LLM), nikoliv naslepo v prázdné smyčce.  
* **Asynchronní / streamované volání LLM:** Při volání lokální Ollamy nebo cloudového API spouští worker požadavek mimo hlavní smyčku (nebo se streamováním tokenů) s klientským timeoutem nečinnosti (např. 30–60 s bez nového tokenu). Pokud model přestane odpovídat, worker požadavek ukončí jako technickou chybu (NEOVĚŘENO / technical) a neprodlužuje deadline donekonečna.  
* **Bezpečná obnova (recover) a vnější akce:** Vypršení deadline uvolní slot až po ověření, že předchozí proces reálně skončil (stopped=True podle PID/stavu procesu), aby nevznikli dva paralelní pracovníci nad stejným krokem. Pozdní zápis se starým token databáze odmítne. U kroků s vedlejším účinkem (rozesílka, externí zápis) musí kód před nastavením safe\_to\_retry=True ověřit idempotenci / skutečný stav venku.

### **15.7 Syntetizátor, obnova dlouhých/LLM běhů, vnější akce a JSONL přejímka**

* **Syntetizátor (§ 7):** Skládá finální výstup pouze ze schválených výsledků (approved) a ověřených důkazů (evidence), pracuje s výtahy namísto celých textů, zaznamenává rozpory do conflicts a neověřené kroky do gaps. Ověřuje se přes verify('synthesis', ..., common=False) (refs\_exist proti known\_refs, gaps\_reported při unverified\_count \> 0); při selhání proběhne cílená oprava s fix\_hint a při jejím vyčerpání se vrátí bezpečný strukturovaný záložní výstup (structured\_fallback) se stavem NEOVĚŘENO (u čistě strukturovaného jednoho výstupu lze syntetizátor vynechat).  
* **Rozlišení dlouhého, ale živého běhu a volání LLM (§ 9.3–9.4):** Model sám do fronty nezapisuje; živost hlídá Python worker, který model volá asynchronně nebo se streamováním tokenů. renew() volá jen při reálném pokroku (další URL v dávce nebo příchozí tokeny/chunky), doplněném o sledování PID/stavu procesu a klientský timeout nečinnosti (např. 30–60 s bez nové odezvy). Vypršení deadline uvolní slot až po ověření stopped=True, pozdní zápis se starým tokenem se odmítne.  
* **Vnější akce a safe\_to\_retry (§ 9.3–9.4, § 13):** U čtení a čistých výpočtů lze opakovat v mezích limitů; u kroků s vedlejším účinkem (např. odeslání e-mailu nebo externí zápis) musí kód před nastavením safe\_to\_retry=True ověřit skutečný stav / idempotenci venku, jinak bezpečně eskaluje/uzavře jako neověřené.  
* **JSONL logování, kalibrace kritérií a přejímkové scénáře (§ 9.5, § 11–13):** Každý krok se loguje na jeden řádek JSONL (ts, task\_id, step\_id, attempt, phase, input\_hash, verdict, retry\_class, duration\_ms, tokeny a model/provider). Nová kritéria se zavádějí nejdříve jako required=False a po ověření se povyšují; NESPLNĚNO řeší věcnou/technickou stránku, zatímco NEOVĚŘENO signalizuje problémy prostředí/důkazů. Přejímka ověří změnu konfigurace za běhu, pauzu, zámek (task, role), odmítnutí pozdního zápisu, souběh verify\_cpu vs. verify\_content, recover() po vypršení lease, kaskádové blokování závislostí (needs\_pass=1), stav po restartu DB, recyklaci BrowserContext a kontroly syntézy.

## **16. Platformová nezávislost a adaptéry pro různé AI runtime**

Šablona je navržena jako platformově neutrální základ (kontrakty, obálky, SQLite fronta, dvouvrstvý ověřovatel a syntetizátor jsou nezávislé na konkrétním AI nástroji). Stejný návrh lze použít napříč různými AI prostředími – od Codexu přes Claude / Claude Code a Antigravity až po lokální modely v Ollamě nebo vlastní skripty.

### **16.1 Podmíněné pokyny pro LLM podle aktivního prostředí**

Při spuštění v konkrétním nástroji se LLM řídí podle dostupných schopností daného prostředí:
- **Pokud běžíš v Codexu:** Využij nativní podagenty/profily a projektové hooky (např. zápis stručného auditu do `.runs/.../audit.jsonl`), respektuj výchozí oprávnění pouze pro čtení a při delegování na specializované role drž úzký kontrakt vstupu a výstupu.
- **Pokud běžíš v Claude / Claude Code:** Využij dostupné nástroje pro čtení/úpravy souborů, spouštění příkazů a subagenty/tasky dle nastavení relace; výstupy kroků vracej strukturovaně s doloženými podklady a rozlišuj ověřená fakta od neověřených odhadů.
- **Pokud běžíš v Antigravity:** Využij dostupné workspace nástroje, artefakty a subagenty/úkoly daného prostředí při dodržení společných rules a obálek (`TaskEnvelope`, `ResultEnvelope`, `Verdict`, `Deliverable`); měřitelné kroky deleguj na sdílené nástroje a kód, stav ukládej mimo kontext modelu a rozlišuj ověřená fakta od neověřených odhadů.
- **Pokud běžíš přes lokální CLI / Ollamu nebo jiný runner:** Spoléhej na deterministický Python kód a SQLite frontu (stav, zámky, limity a ověřování kódem), drž krátký kontext a nízkou teplotu (0.0–0.2) u plánování a ověřování a neukládej stav do paměti modelu.

### **16.2 Co zůstává společné napříč platformami**
- **Obálky a identifikátory:** `TaskEnvelope`, `ResultEnvelope`, `Verdict` a `Deliverable` se všemi identifikátory (`task_id`, `step_id`, `attempt`) a důkazy (`evidence`).
- **Ověřování a stropy:** Co lze ověřit kódem, ověřuje kód; každý krok a smyčka má pevný strop pokusů/tokenů a po vyčerpání končí jako neověřený (`NEOVĚŘENO` / `gaps`), nikoliv potichu jako úspěšný.
- **Izolace a audit:** Výchozí opatrnost vůči zápisům a vnějším akcím, oddělení oprávnění od hodnocení kvality a sledování neúplných běhů.

### **16.3 Kanálové adaptéry (Slack, Microsoft Teams) a napojení na frontu**

Komunikační kanály (Slack, Microsoft Teams) nejsou součástí jádra ani samostatnými orchestrátory, ale fungují jako volitelné vstupně-výstupní adaptéry nad společnou SQLite frontou a kontrakty (§ 3, § 9).
- **Tok dat a kontrakty:** Kanálový adaptér přijme požadavek z konverzace, přeloží ho na vstupní obálku (`TaskEnvelope`), zařadí do fronty (`job`) a průběžné stavy či finální výstup (`Deliverable` / `Verdict`) vrací zpět do původního vlákna (např. přes Slack Bolt / Socket Mode v lokálním pilotu nebo přes registraci aplikace a Adaptive Cards v Teams).
- **Identita, tenanti a oprávnění na straně serveru:** Kontext tenanta, kanálu, vlákna a uživatelských oprávnění se vždy odvozuje z ověřené identity a registrace v adaptéru na straně serveru – nikdy z textu uživatelské zprávy.
- **Idempotence a vnější akce:** Odeslání zprávy do kanálu, schvalovací interakce i zápisy přes konektory / MCP podléhají pravidlům pro vnější akce (§ 10.1, § 15.6) – před opakováním po výpadku se ověří skutečný stav a vyžaduje se jednorázové potvrzení s expirací u rizikových akcí.