# Haderner Ergebnistracker (Prototyp)

Push-Nachrichten für alle Spiele des TSV Großhadern – Anpfiff, jedes Tor (bei Spielen mit BFV-Liveticker) und Endstand. Läuft komplett in der Cloud (GitHub Actions), kein Mac nötig.

## Was passiert

1. **Mannschaften:** Einmal täglich liest das Skript von der BFV-Vereinsseite alle Teams aus – auch nach Saisonwechsel ohne Handarbeit.
2. **Spielplan:** aus der Spielplan-Liste jeder Mannschaftsseite (auch Festival-Teams ohne Ergebnisse).
3. **Pushes** über [ntfy](https://ntfy.sh):
   - 📅 **Spieltag!** – morgens (ab 7 Uhr) eine Übersicht aller Spiele des Tages
   - ▶️ **Anstoß** – zur Anstoßzeit (bzw. sobald der Liveticker startet)
   - ⚽ **Tore** – nur bei Spielen mit BFV-Liveticker
   - 🏁 **Abpfiff** – wenn der Ticker endet, mit Spielstand laut Ticker
   - 📋 **Ergebnis eingetragen** – sobald das offizielle Ergebnis beim BFV steht (ohne Ticker: sobald es eingetragen ist; mit Ticker: sobald der Spielleiter bestätigt). Weicht es vom Ticker ab, steht das dabei.
   - **Festivals (U9/U8):** nur Übersicht + Anstoß-Erinnerung, kein Ergebnis
4. **Kalender:** `docs/ergebnisse.ics` enthält alle Spiele, Ergebnisse stehen im Titel.

## Einrichten (ca. 10 Minuten)

1. **GitHub-Repo anlegen** (öffentlich empfohlen – dann sind die Actions-Minuten unbegrenzt kostenlos; privat sind es 2.000 Min./Monat, was an vollen Wochenenden knapp wird). Alle Dateien aus diesem Ordner hochladen, inkl. `.github/workflows/tracker.yml`.
2. **Push-Thema ausdenken:** ein schwer zu erratender Name, z. B. `tsv-hadern-erg-7k3q9`. Wer den Namen kennt, kann mitlesen – also nur an Trainer weitergeben.
3. **Secret setzen:** Repo → Settings → Secrets and variables → Actions → *New repository secret* → Name `NTFY_TOPIC`, Wert = dein Thema.
4. **App:** ntfy (iOS/Android) installieren → „+“ → Thema eintragen. Fertig.
5. **Testlauf:** Repo → Actions → *Ergebnistracker* → *Run workflow*. Im Log siehst du die erkannten Teams und Spiele.
6. **Optional Kalender:** Settings → Pages → Branch `main`, Ordner `/docs`. Abo-Link: `https://<dein-name>.github.io/<repo>/ergebnisse.ics`

## Hinweise

- **Tore live** gibt es nur, wenn jemand beim BFV tickert. Ohne Ticker kommt der Endstand, sobald das Ergebnis eingetragen ist.
- Welche Teams als „ohne Ergebnis“ gelten, steht in `config.json` unter `ohne_ergebnis` (Standard: U9, U8, U7). Spiele mit „Kinderfestival“ im Namen werden immer so behandelt.
- **GitHub-Cron ist unpünktlich** (am Wochenende teils 10–20 Min. Verspätung). Deshalb bleibt ein Lauf aktiv, solange Spiele laufen, und pollt dann selbst minütlich.
- **Datenquelle:** BFV-Webseite, keine offizielle API. Wenn der BFV die Seite umbaut, kann der Tracker brechen – er stürzt dann nicht ab, sondern meldet Fehler im Log. Nur für den internen Vereinsgebrauch gedacht.
- Lokal testen: `pip install -r requirements.txt && python tracker.py --dry-run`

## Dateien

| Datei | Zweck |
|---|---|
| `tracker.py` | das Skript |
| `config.json` | Verein, Anzeigenamen der Teams, Push-Optionen (`"kickoff": false` schaltet Anpfiff-Pushes ab) |
| `state.json` | wird automatisch gepflegt (welche Tore schon gemeldet wurden) |
| `docs/ergebnisse.ics` | Ergebnis-Kalender, automatisch erzeugt |
