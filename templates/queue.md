# Fronta se závislostmi

Položka má stabilní ID, roli, zadání, výstup, podmínku dokončení a seznam závislostí na ověřených výstupech. Jeden řídící proces drží zámek seznamu, role mohou zpracovávat nezávislé položky souběžně.

1. Před přidělením vynech hotové položky a ověř značku zastavení.
2. Z připravených položek vybírej podle pořadí seznamu a volných rolí. Počet souběžných úloh nastav podle prostředí.
3. Každé předání a návrat zaznamenej. Závislá položka se uvolní až po kladném verdiktu v reportu původní položky.
4. Po restartu načti schválený seznam, uložené výsledky a kontrolní body. Pokračuj bez opakování hotových výstupů. Pokud zbývají položky čekající na závislost, seznam zůstává otevřený.
5. Při ručním zastavení nebo dosažení limitu zastav přidělování. Další běh se řídí pravidly obnovy projektu.

[queue_selection.py](queue_selection.py) ukazuje přenositelný výběr položek bez modelu. Zámky, zápis reportů, deník a skutečné spuštění specialistů obstarává implementace projektu.

## Práce po dokončení vstupního seznamu

Návazná položka může být součástí stejného schváleného seznamu nebo může odkazovat na jiný schválený seznam a stabilní ID jeho položky. Report s kladným verdiktem je použitelný i po uzavření seznamu. Blokovaný nebo rozpracovaný podklad udržuje navazující položku ve stavu čekání.

Kapacitu počítej podle právě běžící předávky. Jakmile Knihovník vrátí první zdroj, Koordinátor může přidělit Knihovníkovi další zdroj a první výstup současně předat Ověřovateli. Metodik může pracovat s dříve ověřeným zdrojem. Zámek seznamu chrání jedinečné řízení a samostatný zámek role chrání její kapacitu i mezi seznamy.

Příklad `verified_dependencies` načítá stavy odkazovaných původních reportů. Příklad `ready_items` dostává obsazenost právě běžících předávek. Projekt ověřuje skutečné předávky, uvolnění slotu, zápis deníku a obnovu.

## Výběr práce podle volných rolí

Při každém přidělení projdi připravenou práci od začátku do konce. Položku obsazené role nebo položku čekající na závislost přeskoč. Pro každou volnou roli vyber její nejstarší připravenou položku. Volné role mohou pracovat současně a dokončením vstupního seznamu příjem dalších schválených požadavků nekončí. Pokud implementace zpracovává více vstupů, musí mít pro jejich položky společné pořadí příjmu. Kapacitu rolí vyhodnocuj odděleně od zápisu nových požadavků.

## Priorita a uživatelská oprava

Priorita je kladné celé číslo s výchozí hodnotou 10. Připravené položky vybírej podle vzestupné priority a při shodě podle pořadí přijetí. Rozpracované položky pokračují. Před zadáním opravy eviduj původní ID, popis chyby a prioritu. Při zahájení opravy zachovej starý report a pokusy v historii. Nový rozpočet pokusů platí pouze pro opravovanou položku.
