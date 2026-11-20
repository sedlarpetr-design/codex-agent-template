# Changelog

## 1.0.0 (2026-11-20)

- Vydání pro Codex CLI na linuxovém serveru s obsluhou přes SSH.
- Přejímka doložila konzolový běh s auditem a odmítnutí skutečného zápisu sandboxem Codexu.

- Izolované scénáře pro koordinátora, analytiky, ověřovatele, opravné cykly a bezpečnostní hranice.
- Strojově čitelné reporty, samostatný kandidát baseline a deterministická kontrola vydání.
- Rozpor mezi vlastním verdiktem ověřovatele a stavem koordinátora blokuje vydání.

Při přechodu z výchozího commitu zůstávají existující zadání platná. Testy spouští nový příkaz uvedený v [návodu](docs/TESTING.md). Pro návrat lze použít čistou pracovní kopii výchozího commitu `3af0952`. Reporty a zapisovaný audit jsou pracovní data mimo Git.
