# Haderner Ergebnistracker

Push-Nachrichten für alle Spiele des TSV München-Großhadern: Spieltag-Übersicht, Anpfiff,
Tore und Endstand. Die Daten kommen von bfv.de, die Pushes laufen über [ntfy](https://ntfy.sh).
Alles läuft auf GitHub Actions, ohne eigenen Server und ohne laufende Kosten.

## Was passiert

1. **Mannschaften:** Einmal täglich liest das Skript alle Teams von der BFV-Vereinsseite,
   auch nach einem Saisonwechsel ohne Handarbeit.
2. **Spielplan:** je Mannschaft von heute −2 bis +21 Tage, auch für Festival-Teams ohne Ergebnisse.
3. **Pushes:** kurz, Ergebnis vorn im Titel, immer aus Haderner Sicht (siehe Tabelle).
4. **Kalender:** `docs/ergebnisse.ics` enthält alle Spiele, Ergebnisse stehen im Titel.

| Anlass | Titel | Text |
|---|---|---|
| Spieltag | `📅 SPIELTAG! 7 Spiele heute!` | je Zeile `09:00 U10 2 – Gegner (H)`, Festivals mit 🎪 |
| Anpfiff | `U17 · Anpfiff` | `gg. Gegner (A)` |
| Festival (U9/U8/U7) | `U9 · Festival` | `gg. Gegner (A)`, danach nichts mehr |
| Tor | `Erste · 1:0 ⚽` | `57' Tor` oder Torschütze |
| Gegentor | `Erste · 1:1` | `63' Gegentor` |
| Ergebnis | `U17 · 3:1 🟢` | `gg. Gegner (H) · HZ 1:0` |
| Absage | `U12 · abgesagt 🚫` | `gg. Gegner (A)` |

- 🟢 Sieg, 🟡 Remis, 🔴 Niederlage.
- **Spieltag-Übersicht** um 11:00 Uhr, oder 30 Minuten vor dem ersten Anpfiff, falls der vor 11:30 liegt.
- **Tore** gibt es nur, wenn jemand beim BFV tickert. Ohne Ticker kommt der Endstand, sobald das
  Ergebnis eingetragen ist.
- **Nur eine Ergebnis-Push je Spiel.** Nach einem Ticker-Abpfiff trägt sie „· vorläufig“. Die
  Bestätigung durch den Spielleiter löst nur dann eine zweite Push aus, wenn sich das Ergebnis
  geändert hat („· korrigiert“).
- **Festivals** (U9/U8/U7 und alle Spiele mit „Kinderfestival“ im Namen): nur Übersicht und
  Anpfiff, kein Ergebnis.
- Beim ersten Sehen eines längst laufenden oder beendeten Spiels wird nichts nachgeholt.
- Antippen öffnet das Spiel bei fussball.de (App, falls installiert), der Knopf „BFV“ die BFV-Seite.

## Wie der Tracker läuft

- **Start:** Ein externer Wecker bei [cron-job.org](https://cron-job.org) startet den Workflow
  täglich von 8 bis 20 Uhr zur vollen Stunde. GitHubs eigener Zeitplan lässt Starts aus oder
  verspätet sie um Stunden; die Cron-Zeilen im Workflow sind deshalb nur Reserve.
- **Ein Lauf gleichzeitig:** Ein Lauf bleibt aktiv, solange am Tag noch etwas ansteht, und schläft
  zwischen den Prüfungen. Weitere Starts warten. Ein Wartender, der durch einen neueren ersetzt
  wird, erscheint unter Actions als „cancelled“. Das ist normal.
- **Prüf-Takt je Spiel:** ab 10 Minuten vor Anpfiff; mit Liveticker alle 60 Sekunden; ohne Ticker
  alle 5 Minuten bis 150 Minuten nach Anpfiff, dann alle 20 Minuten, ab 6 Stunden nach Anpfiff
  stündlich, nach 48 Stunden ist Schluss. Zwischen 23 und 7 Uhr wird nicht nach nachgetragenen
  Ergebnissen gefragt.
- **Speichern:** Nach jedem Lauf schreibt der Workflow `state.json` und den Kalender zurück ins
  Repo (Commits von `ergebnistracker-bot`).
- **Übergabe:** GitHub beendet einen Lauf nach 6 Stunden. Steht dann noch etwas an, startet der
  Tracker nach 5 h 40 selbst einen neuen Lauf (bis 23 Uhr).
- **Manueller Start:** Actions → *Ergebnistracker* → *Run workflow*. Es kommt keine Test-Push.

## Einrichten

1. **GitHub-Repo anlegen** und alle Dateien hochladen, inklusive `.github/workflows/tracker.yml`.
   Öffentlich empfohlen: Dann sind die Actions-Minuten kostenlos und unbegrenzt.
2. **`config.json` anpassen:** Verein (`club_id`, `club_slug`, `club_name`, `club_key`),
   Kurznamen der Teams (`labels`), Festival-Teams (`ohne_ergebnis`).
3. **Push-Kanal ausdenken:** ein langer, zufälliger, nicht zu erratender Name. Wer ihn kennt, kann
   mitlesen und mitschreiben. Deshalb nur an die Trainer weitergeben und nie ins Repo schreiben.
4. **Secret setzen:** Repo → Settings → Secrets and variables → Actions → *New repository secret*,
   Name `NTFY_TOPIC`, Wert = der Kanalname.
5. **App:** ntfy (iOS/Android) installieren, „+“ antippen, Kanalnamen eintragen.
6. **Wecker einrichten** bei cron-job.org:
   - Bei GitHub ein fein eingegrenztes Token anlegen (Settings → Developer settings →
     Fine-grained tokens): nur dieses Repo, nur die Berechtigung *Actions: Read and write*.
   - Job: täglich 8 bis 20 Uhr zur vollen Stunde, Methode `POST` auf
     `https://api.github.com/repos/<name>/<repo>/actions/workflows/tracker.yml/dispatches`
   - Header: `Authorization: Bearer <Token>` und `Accept: application/vnd.github+json`
   - Body: `{"ref":"main"}`
7. **Optional Kalender:** Settings → Pages → Branch `main`, Ordner `/docs`.
   Abo-Link: `https://<name>.github.io/<repo>/ergebnisse.ics`

## Lokal ausprobieren

```bash
pip install -r requirements.txt
python tracker.py --dry-run          # ein Durchlauf, Pushes nur ins Log
python tracker.py --watch --dry-run  # bleibt aktiv wie im Workflow
```

Lokal immer `--dry-run` nutzen: Der echte Kanal geht an alle Trainer. Ein lokaler Lauf verändert
`state.json`; diese Änderung nicht committen.

In `tests/` liegen Simulations-Skripte, die ganze Spieltage im Zeitraffer durchspielen, ohne
bfv.de abzurufen und ohne zu pushen. Näheres in `tests/README.md`.

## Hinweise

- **Datenquelle:** die BFV-Webseite, keine offizielle Schnittstelle. Baut der BFV die Seite um,
  kann der Tracker brechen. Er stürzt dann nicht ab, sondern meldet Fehler im Log. Nur für den
  internen Vereinsgebrauch gedacht.
- **Rücksicht auf bfv.de:** Abrufe nacheinander mit kurzen Pausen und eigenem User-Agent.
- **iPhone:** ntfy stellt unter iOS teils erst zu, wenn die App geöffnet wird (Stromsparmodus,
  Hintergrundaktualisierung).
- `"kickoff": false` unter `notify` in `config.json` schaltet die Anpfiff-Pushes ab.

## Dateien

| Datei | Zweck |
|---|---|
| `tracker.py` | das Skript mit der gesamten Logik |
| `config.json` | Verein, Kurznamen der Teams, Festival-Teams, Trainerliste |
| `state.json` | Zustand zwischen den Läufen, wird vom Workflow gepflegt; nicht von Hand ändern |
| `docs/ergebnisse.ics` | Kalender mit Spielen und Ergebnissen, wird bei jedem Lauf neu geschrieben |
| `.github/workflows/tracker.yml` | Start, Speichern des Zustands, Selbst-Übergabe |
| `tests/`, `sample/` | Simulations-Skripte und gespeicherte BFV-Seiten dafür |
| `CLAUDE.md` | ausführliche Projektnotizen (Datenquellen, Push-Regeln, offene Punkte) |
