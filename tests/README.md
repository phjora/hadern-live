# Simulationen für den Ergebnistracker

Wegwerf-Skripte aus der Entstehung, keine pytest-Tests. Jedes Skript ersetzt Uhr,
`time.sleep` und die BFV-Abrufe und spielt einen Ablauf im Zeitraffer durch.
Es werden keine echten Pushes verschickt und keine Seiten abgerufen.

Aus dem Hauptverzeichnis des Repos starten:

    python tests/test_weekday.py

| Skript | Was es durchspielt | Erwartung |
|---|---|---|
| `test_day.py` | Sonntag mit Festival, Spiel ohne Ticker, Spiel mit Ticker, Abendspiel | Lauf endet mit Übergabe (`.chain`) |
| `test_weekday.py [Minuten]` | Wochentag, ein Spiel um 18:00, Start 07:05; Ergebnis n Minuten nach Anpfiff (Standard 100) | 3 Läufe, Übersicht 11:00, Anpfiff 18:00, Ergebnis |
| `test_digest.py` | wie oben, mit echter Spieltag-Übersicht | `📅 SPIELTAG!` um 11:00 |
| `test_digest_sat.py` | erstes Spiel 09:00 | Übersicht um 08:30 |
| `test_digest_late.py` | Start erst nach dem Anpfiff | keine Übersicht |
| `test_two_tickers.py` | U17 in Planegg vom 08.11.: Vereins-Ticker bleibt bei 1:0 stehen, Fanticker läuft weiter | 6 Pushes, prüft sich selbst (`OK`) |
| `test_v2.py` | Einzelfälle für `process_match` gegen die gespeicherte Spielseite in `sample/` (Absage, nachgetragenes Ergebnis usw.) | läuft ohne Fehler durch |

Nur `test_two_tickers.py` prüft sein Ergebnis selbst. Bei den anderen muss man die
ausgegebenen `PUSH`-Zeilen lesen. Sinnvoller nächster Schritt: in pytest überführen und
die Erwartungen als Assertions festschreiben.

Die Skripte legen beim Lauf Dateien in `tests/` an (`state_*.json`, `erg_*.ics`, `.chain*`).
Diese gehören in `.gitignore`.

`sample/` enthält gespeicherte BFV-Seiten (Spielseite samt Schrift, Spielpläne) vom November 2026.
