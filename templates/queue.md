# Fronta se závislostmi

Položka má stabilní ID, roli, zadání, výstup, podmínku dokončení a seznam závislostí na ověřených výstupech. Jeden řídící proces drží zámek seznamu, role mohou zpracovávat nezávislé položky souběžně.

1. Před přidělením vynech hotové položky a ověř značku zastavení.
2. Z připravených položek vybírej podle pořadí seznamu a volných rolí. Počet souběžných úloh nastav podle prostředí.
3. Každé předání a návrat zaznamenej. Závislá položka se uvolní až po kladném verdiktu v reportu původní položky.
4. Po restartu načti schválený seznam, uložené výsledky a kontrolní body. Pokračuj bez opakování hotových výstupů. Pokud zbývají položky čekající na závislost, seznam zůstává otevřený.
5. Při ručním zastavení nebo dosažení limitu zastav přidělování. Další běh se řídí pravidly obnovy projektu.

[queue_selection.py](queue_selection.py) ukazuje přenositelný výběr položek bez modelu. Zámky, zápis reportů, deník a skutečné spuštění specialistů obstarává implementace projektu.
