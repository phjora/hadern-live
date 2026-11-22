# Haderner Ergebnistracker (hadern-live)

Push-Dienst für die Trainer des TSV München-Großhadern: liest Spielpläne und Spielstände
aller Vereinsmannschaften von bfv.de und verschickt kurze Push-Nachrichten über ntfy.
Läuft komplett auf GitHub Actions, ohne eigenen Server und ohne laufende Kosten.
Besitzer: Philipp (GitHub `phjora`). Stand dieser Datei: 22.11.2026.

## Dateien

| Datei | Zweck |
|---|---|
| `tracker.py` | Die gesamte Logik (ein Skript, ~820 Zeilen) |
| `config.json` | Verein, Team-Kurznamen, Festival-Teams, Trainerliste |
| `state.json` | Zustand zwischen den Läufen. Wird vom Workflow committet, nie von Hand ändern |
| `docs/ergebnisse.ics` | Kalender mit Spielen und Ergebnissen, wird bei jedem Lauf neu geschrieben |
| `.github/workflows/tracker.yml` | Start, Speichern des Zustands, Selbst-Übergabe |
| `requirements.txt` | requests, fonttools, tzdata |

## Ausführen

```bash
pip install -r requirements.txt
python tracker.py --dry-run          # ein Durchlauf, Pushes nur ins Log
python tracker.py --watch --dry-run  # bleibt aktiv wie im Workflow
```

Ohne `--dry-run` wird nur gepusht, wenn `NTFY_TOPIC` gesetzt ist. Lokal immer `--dry-run`
nutzen: Der echte Kanal geht an alle Trainer. Ein lokaler Lauf verändert `state.json`;
diese Änderung nicht committen.

## Ablauf in `tracker.py`

1. `refresh_schedule`: Teams von der Vereinsseite (einmal pro Tag), Spielplan je Team
   (heute −2 bis +21 Tage) nach `state["games"]`. Spiele älter als 60 Tage fliegen raus.
2. `send_digest`: Spieltag-Übersicht (siehe Push-Regeln).
3. Schleife `one_pass`: prüft fällige Spiele, `process_match` vergleicht mit dem
   gespeicherten Stand und pusht. Rückgabe ist der nächste Prüfzeitpunkt; bis dahin schläft der Lauf.
4. Reicht die Laufzeit nicht (`MAX_RUNTIME` 5 h 40, GitHub-Limit 6 h), schreibt das Skript
   die Datei `.chain`; der Workflow startet dann einen neuen Lauf.

Prüf-Takt je Spiel: ab 10 min vor Anpfiff; mit Liveticker alle 60 s; ohne Ticker alle 5 min
bis 150 min nach Anpfiff, dann alle 20 min, ab 6 h nach Anpfiff stündlich, nach 48 h Schluss.
Zwischen 23 und 7 Uhr wird nicht nach nachgetragenen Ergebnissen gefragt (laufende Spiele ausgenommen).

## Datenquellen bei bfv.de (alles inoffiziell, kann jederzeit brechen)

- **Teams:** Links `/mannschaften/{slug}/{id}` auf `/vereine/{club_slug}/{club_id}`.
- **Spielplan:** `/partial/mannschaftsprofil/spielplan/{teamId}/alle`, normales HTML
  (Blöcke `bfv-spieltag-eintrag`), Namen und Zeiten im Klartext.
- **Spielseite:** `/ergebnisse/spiel/-/{matchId}`, Next.js-Seite. Die Daten stecken in
  `self.__next_f.push(...)`-Blöcken (`rsc_payload`). Texte sind über eine pro Abruf wechselnde
  Webfont verschleiert; `font_map` lädt die Schrift und übersetzt über die Glyphennamen zurück.
  Zahlen, IDs und Wahrheitswerte sind nicht verschleiert.
- **Status-Werte:** `scheduled`, `live`, `finished`, `acknowledged` (bestätigt), `cancelled`.
- **Liveticker:** `/ergebnisse/spiel/-/{matchId}/liveticker[/{tickerId}]`, Objekt `"ticker"` mit
  `score`, `scoreHalftime`, `live`, `timeplayed`, `events` (typeId 1 = Tor) und `tickers` (alle Ticker des Spiels).
- **Wichtig:** Die Torliste der Spielseite füllt der BFV oft erst nach Abpfiff. Tore werden deshalb
  über Änderungen des Spielstands erkannt.
- **Wichtig:** Die Spielseite zeigt nur den ersten Ticker. Bricht der ab, während ein zweiter
  (Fanticker) weiterläuft, bleibt sie stehen. Bei `liveTickerCount >= 2` liest `apply_best_ticker`
  alle Ticker und nimmt den am weitesten fortgeschrittenen.
- fussball.de nutzt dieselben Spiel-IDs: `https://www.fussball.de/spiel/spiel/-/spiel/{ID}`.

## Push-Regeln (von Philipp so entschieden, nicht ohne Rückfrage ändern)

Oberste Priorität: kurz, auf einen Blick lesbar. Ergebnis vorn im Titel, immer aus Haderner
Sicht, Gegner in der zweiten Zeile mit (H)/(A).

| Anlass | Titel | Text |
|---|---|---|
| Spieltag | `📅 SPIELTAG! 7 Spiele heute!` | je Zeile `09:00 U10 2 – Gegner (H)`, Festivals mit 🎪 |
| Anpfiff | `U17 · Anpfiff` | `gg. Gegner (A)` |
| Festival (U9/U8/U7) | `U9 · Festival` | `gg. Gegner (A)`, danach nichts mehr |
| Tor | `Erste · 1:0 ⚽` | `57' Tor` oder Torschütze |
| Gegentor | `Erste · 1:1` | `63' Gegentor` |
| Ergebnis | `U17 · 3:1 🟢` | `gg. Gegner (H) · HZ 1:0` |
| Absage | `U12 · abgesagt 🚫` | `gg. Gegner (A)` |

- 🟢 Sieg, 🟡 Remis, 🔴 Niederlage. Kein ❌ und kein ✅.
- Nur **eine** Ergebnis-Push. Nach einem Ticker-Abpfiff trägt sie „· vorläufig“; die Bestätigung
  löst nur dann eine zweite Push aus, wenn sich das Ergebnis geändert hat („· korrigiert“).
- Spieltag-Übersicht um 11:00, oder 30 min vor dem ersten Anpfiff, falls der vor 11:30 liegt.
- Keine Test-Push beim manuellen Start.
- Beim ersten Sehen eines längst laufenden oder beendeten Spiels wird nichts nachgeholt.
- Antippen öffnet fussball.de (App per Universal Link), der Knopf „BFV“ die BFV-Seite.
  Die BFV-App lässt sich nicht direkt verlinken.
- ntfy wird über die JSON-API angesprochen (POST auf den Server mit `topic` im Body).
  Umlaute und Emojis in HTTP-Headern schlagen fehl.

## Betrieb auf GitHub Actions

- **Start:** Verlässlich ist nur der externe Wecker bei cron-job.org („Hadern-Ergebniswecker“):
  täglich 8 bis 20 Uhr zur vollen Stunde ein `workflow_dispatch` per fein eingegrenztem Token
  (nur dieses Repo, nur Actions). GitHubs eigener `schedule` lässt Starts aus oder verspätet sie
  um Stunden; die Cron-Zeilen im Workflow sind nur Reserve.
- **Nur ein Lauf gleichzeitig** (`concurrency: ergebnistracker`). Weitere Starts warten; der ältere
  Wartende wird durch den neueren ersetzt und erscheint als „cancelled“. Das ist normal.
- **Speichern:** Der Schritt „Zustand und Kalender speichern“ holt `origin/main`, legt `state.json`
  und die ICS-Datei darüber und pusht, mit bis zu 5 Versuchen. Der Bot committet also laufend:
  vor eigenen Pushes immer `git pull --rebase`.
- **Übergabe:** Existiert `.chain`, startet der letzte Schritt per `gh workflow run` den nächsten Lauf
  (bis 23 Uhr). Ein Lauf sitzt vorher seine Laufzeit ab, sonst entsteht eine Neustart-Schleife.
- **Secret:** `NTFY_TOPIC`. Der Kanalname ist das einzige Zugangshindernis und das Repo ist
  öffentlich: Name nie in Code, Logs, Commits oder diese Datei schreiben.

## Rahmenbedingungen

- Keine laufenden Kosten, keine bezahlten Dienste oder LLM-Aufrufe.
- Bewusst getrennt vom „U9 Teammanager“.
- Kommentare, Logs und Push-Texte auf Deutsch.
- In `config.json` und Pushes nur Vornamen.
- Rücksicht auf bfv.de: Abrufe nacheinander mit kurzen Pausen, eigener User-Agent, kein dichterer Takt.

## Offene Punkte

- **Tor-Pushes über den Spielstand** laufen im echten Betrieb: Liveticker am 15.11. und am
  Wochenende 21./22.11. kamen laut Philipp sauber an. Ob dabei ein Spiel mit zwei Tickern war,
  ist nicht bekannt. Die Mehr-Ticker-Auswahl (`apply_best_ticker`) ist deshalb weiter nur gegen
  nachgestellte Daten getestet (Spiel vom 08.11.); wie die Ticker-Felder `live` und `timeplayed`
  während eines laufenden Spiels aussehen, ist angenommen.
- **Zustellung aufs iPhone:** ntfy stellt unter iOS teils erst zu, wenn die App geöffnet wird
  (Stromsparmodus, Hintergrundaktualisierung). Falls das anhält, ist Telegram die Alternative.
- **Tests fehlen im Repo.** Philipp hat die bisherigen Simulations-Skripte als ZIP bekommen
  (`tests/` und `sample/`, mit eigener README): Sie ersetzen Uhr, `time.sleep` und die BFV-Abrufe
  und spielen ganze Spieltage durch. Erster Schritt: einchecken, erzeugte Dateien in `.gitignore`,
  dann in pytest mit festen Erwartungen überführen.
- **Aufräumen:** Workflow-Eingabe `chained` und die Umgebungsvariable `CHAINED` sind seit dem
  Wegfall der Test-Push ohne Funktion; `_verdict` sowie die Importe `base64` und `sys` sind
  ungenutzt; `actions/checkout@v4` und `setup-python@v5` melden eine Node-20-Warnung.
- **README.md** beschreibt noch einen älteren Stand (Übersicht um 7 Uhr, Start nur über GitHub-Cron).

## Geparkt (erst auf Zuruf)

- Lustige Sprüche mit Bezug auf Trainer, Tabelle und Serien: als eigene dritte Zeile, aus
  festen Textbausteinen ohne LLM. Die Trainerliste in `config.json` ist dafür schon da.
- Tippspiel für die Trainer, das auf den Spieldaten dieses Trackers aufbauen soll (eigenes Vorhaben).
- Nutzung durch andere Vereine: Vereinsdaten stehen schon nur in `config.json`.
