# Haderner Ergebnistracker (Prototyp)

Push-Nachrichten für alle Spiele des TSV Großhadern – Anpfiff, jedes Tor (bei Spielen mit BFV-Liveticker) und Endstand. Läuft komplett in der Cloud (GitHub Actions), kein Mac nötig.

## Was passiert

1. **Mannschaften:** Einmal täglich liest das Skript von der BFV-Vereinsseite alle Teams aus – auch nach Saisonwechsel ohne Handarbeit.
2. **Spielplan:** Über den offiziellen iCal-Export des BFV (pro Team).
3. **Beobachtung:** Ab 10 Min. vor Anpfiff wird die Spielseite jede Minute gelesen (ca. 2,5 h lang). Danach wird bis zu 48 h alle 20 Min. nach einem nachgetragenen Ergebnis geschaut.
4. **Push:** über [ntfy](https://ntfy.sh) – kostenlose App, kein Account nötig.
5. **Kalender:** `docs/ergebnisse.ics` enthält alle Spiele, Ergebnisse stehen im Titel („U17: SV Planegg – TSV Großhadern U17 1:3“).

Push-Beispiele:
- `⚽ U17: TOR! 1:0` – 23' Max Mustermann
- `1. Mannschaft: Gegentor 1:1` – 41' …
- `U17: Endstand 3:1 ✅ Sieg` – (HZ 1:1)

## Einrichten (ca. 10 Minuten)

1. **GitHub-Repo anlegen** (öffentlich empfohlen – dann sind die Actions-Minuten unbegrenzt kostenlos; privat sind es 2.000 Min./Monat, was an vollen Wochenenden knapp wird). Alle Dateien aus diesem Ordner hochladen, inkl. `.github/workflows/tracker.yml`.
2. **Push-Thema ausdenken:** ein schwer zu erratender Name, z. B. `tsv-hadern-erg-7k3q9`. Wer den Namen kennt, kann mitlesen – also nur an Trainer weitergeben.
3. **Secret setzen:** Repo → Settings → Secrets and variables → Actions → *New repository secret* → Name `NTFY_TOPIC`, Wert = dein Thema.
4. **App:** ntfy (iOS/Android) installieren → „+“ → Thema eintragen. Fertig.
5. **Testlauf:** Repo → Actions → *Ergebnistracker* → *Run workflow*. Im Log siehst du die erkannten Teams und Spiele.
6. **Optional Kalender:** Settings → Pages → Branch `main`, Ordner `/docs`. Abo-Link: `https://<dein-name>.github.io/<repo>/ergebnisse.ics`

## Hinweise

- **Tore live** gibt es nur, wenn jemand beim BFV tickert. Ohne Ticker kommt der Endstand, sobald das Ergebnis eingetragen ist.
- **U9/U8** haben beim BFV keinen Spielplan-Export (keine offiziellen Ergebnisse) – die fehlen also.
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
