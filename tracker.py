#!/usr/bin/env python3
"""Haderner Ergebnistracker – Prototyp.

Holt die Spielpläne aller Mannschaften eines Vereins beim BFV, beobachtet
laufende Spiele und schickt Push-Nachrichten (ntfy) bei Anpfiff, Toren und
Endstand. Schreibt außerdem einen Ergebnis-Kalender (docs/ergebnisse.ics).

Aufruf:
  python tracker.py            # ein Durchlauf
  python tracker.py --watch    # bleibt aktiv, solange Spiele laufen
  python tracker.py --dry-run  # nichts pushen, nur ausgeben
"""
from __future__ import annotations

import argparse
import html as html_lib
import base64
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from fontTools.agl import toUnicode
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
ICS_OUT = ROOT / "docs" / "ergebnisse.ics"

BFV = "https://www.bfv.de"
SERVICE = "https://service.bfv.de/rest"
FONT_URL = "https://app.bfv.de/export.fontface/-/format/ttf/id/{fid}/type/font"
UA = "HadernerErgebnistracker/0.2 (Vereinsprojekt; Prototyp)"
TZ = ZoneInfo("Europe/Berlin")
DIGEST_HOUR = 7  # ab dieser Uhrzeit (lokal) kommt die Spieltag-Übersicht

# Zeitfenster rund um ein Spiel
PRE_KICKOFF = timedelta(minutes=10)      # ab hier wird ein Spiel beobachtet
LIVE_WINDOW = timedelta(minutes=150)     # so lange wird minütlich gepollt
RESULT_WINDOW = timedelta(hours=48)      # so lange warten wir auf ein nachgetragenes Ergebnis
LIVE_POLL_SECONDS = 60
MAX_RUNTIME = timedelta(hours=5, minutes=40)  # GitHub-Limit sind 6 h
CHAIN_UNTIL_HOUR = 22  # bis dahin startet sich der Tracker bei Bedarf selbst neu
CHAIN_FLAG = ROOT / ".chain"

session = requests.Session()
session.headers["User-Agent"] = UA


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def log(*a):
    print(datetime.now(TZ).strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------------------
# Konfiguration & Zustand
# ---------------------------------------------------------------------------

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mannschaften automatisch erkennen
# ---------------------------------------------------------------------------

def discover_teams(club_slug: str, club_id: str) -> list[dict]:
    """Liest von der Vereinsseite alle Mannschaften und deren iCal-Staffel-ID."""
    html = session.get(f"{BFV}/vereine/{club_slug}/{club_id}", timeout=30).text
    teams, seen = [], set()
    for slug, tid in re.findall(r"/mannschaften/([a-z0-9-]+)/([A-Z0-9]{32})", html):
        if tid in seen:
            continue
        seen.add(tid)
        page = session.get(f"{BFV}/mannschaften/{slug}/{tid}", timeout=30).text
        title = re.search(r"<title>([^|<]+)", page)
        name = title.group(1).replace("&nbsp;", " ").strip() if title else slug
        teams.append({"id": tid, "slug": slug, "name": name})
        time.sleep(0.5)
    return teams


def team_label(name: str, cfg: dict) -> str:
    labels = cfg.get("labels", {})
    if name in labels:
        return labels[name]
    short = name.replace(cfg.get("club_name", ""), "").strip(" ()")
    return short or name


# ---------------------------------------------------------------------------
# Spielplan (Spielplan-Liste der Mannschaftsseite, Namen/Zeiten unverschleiert)
# ---------------------------------------------------------------------------

def _clean(fragment: str) -> str:
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html_lib.unescape(fragment)).strip()


def parse_plan(html: str) -> list[dict]:
    out = []
    for block in html.split('class="bfv-spieltag-eintrag"')[1:]:
        mid = re.search(r"ergebnisse/spiel/-/([A-Z0-9]{32})", block)
        dt = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*/\s*(\d{1,2}:\d{2})", block)
        names = re.findall(r'team-name--team[01][^"]*">(.*?)</div>', block, re.S)
        if not (mid and dt and len(names) >= 2):
            continue
        local = datetime.strptime(f"{dt.group(1)} {dt.group(2)}", "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
        region = re.search(r'eintrag__region">(.*?)</div>', block, re.S)
        loc = re.search(r'eintrag__location">(.*?)</div>', block, re.S)
        home, guest = _clean(names[0]), _clean(names[1])
        festival = "kinderfestival" in (home + guest).lower()
        home, guest = (re.sub(r"\s*-\s*Kinderfestival", "", n, flags=re.I) for n in (home, guest))
        out.append({
            "id": mid.group(1),
            "kickoff": local.astimezone(timezone.utc).isoformat(),
            "pairing": f"{home} – {guest}",
            "home_plan": home, "guest_plan": guest,
            "competition": _clean(region.group(1)) if region else "",
            "location": _clean(loc.group(1)) if loc else "",
            "festival_hint": festival,
        })
    return out


def fetch_plan(team_id: str) -> list[dict]:
    today = datetime.now(TZ).date()
    params = {
        "wettbewerbsart": "-1", "spieltyp": "ALLE", "from": "0", "size": "50",
        "fromDate": (today - timedelta(days=2)).strftime("%d.%m.%Y"),
        "toDate": (today + timedelta(days=21)).strftime("%d.%m.%Y"),
    }
    r = session.get(f"{BFV}/partial/mannschaftsprofil/spielplan/{team_id}/alle", params=params, timeout=30)
    r.raise_for_status()
    return parse_plan(r.text)


def is_festival(game: dict, cfg: dict) -> bool:
    if game.get("festival_hint"):
        return True
    return game.get("team_label") in cfg.get("ohne_ergebnis", ["U9", "U8", "U7"])


# ---------------------------------------------------------------------------
# Spielseite lesen und entschlüsseln
# ---------------------------------------------------------------------------

def _balanced(text: str, start: int) -> str:
    """Gibt das JSON-Objekt/-Array zurück, das bei text[start] beginnt."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        c = text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    raise ValueError("unbalanced JSON")


def rsc_payload(html: str) -> str:
    """Setzt die Next.js-Datenblöcke (self.__next_f.push) zu einem Text zusammen."""
    parts = []
    for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            parts.append(arr[1])
    return "".join(parts)


_font_cache: dict[str, dict[int, str]] = {}


def font_map(font_id: str, font_bytes: bytes | None = None) -> dict[int, str]:
    """Codepoint -> echtes Zeichen, abgeleitet aus den Glyphennamen der Schrift."""
    if font_id in _font_cache:
        return _font_cache[font_id]
    if font_bytes is None:
        r = session.get(FONT_URL.format(fid=font_id), timeout=30)
        r.raise_for_status()
        font_bytes = r.content
    cmap = TTFont(io.BytesIO(font_bytes)).getBestCmap()
    mapping = {cp: toUnicode(name) for cp, name in cmap.items()}
    _font_cache[font_id] = mapping
    return mapping


def deobfuscate(value, mapping):
    if isinstance(value, str):
        if value == "$undefined":
            return None
        s = "".join(mapping.get(ord(c), c) for c in value)
        s = s.replace("\u200b", "")
        return re.sub(r"\s+", " ", s).strip()
    if isinstance(value, list):
        return [deobfuscate(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: deobfuscate(v, mapping) for k, v in value.items()}
    return value


def parse_match_page(html: str, match_id: str, font_bytes: bytes | None = None) -> dict:
    payload = rsc_payload(html)
    fm = re.search(r"font-family: font-([a-z0-9]+)", payload) or re.search(r"font-family: font-([a-z0-9]+)", html)
    if not fm:
        raise ValueError("keine Schrift-ID gefunden")
    mapping = font_map(fm.group(1), font_bytes)

    idx = payload.find('{"id":"%s"' % match_id)
    if idx < 0:
        raise ValueError("Spieldaten nicht gefunden")
    match = json.loads(_balanced(payload, idx))
    gi = payload.find('"goals":[', idx)
    goals = json.loads(_balanced(payload, gi + len('"goals":'))) if gi >= 0 else []

    m = deobfuscate(match, mapping)
    goals = deobfuscate(goals, mapping)
    res = m.get("result") or {}
    return {
        "id": match_id,
        "status": m.get("status"),
        "live": bool(match.get("live")),
        "live_minute": m.get("liveMinute"),
        "ticker": (match.get("liveTickerCount") or 0) > 0,
        "home": m["homeTeam"]["name"],
        "home_club": match["homeTeam"].get("clubId"),
        "guest": m["guestTeam"]["name"],
        "guest_club": match["guestTeam"].get("clubId"),
        "result": _score(res.get("text")),
        "halftime": _score((res.get("resultHalfTime") or "").replace(" ", "").strip("()")),
        "goals": sorted(goals, key=lambda g: g.get("goalId", 0)),
        "competition": m.get("competitionName"),
    }


def _score(text: str | None) -> str | None:
    """Nur echte Spielstände (mit Ziffern) zählen – „- : -“ heißt: noch kein Ergebnis."""
    if not text or not re.search(r"\d", text):
        return None
    return re.sub(r"\s+", "", text)


def fetch_match(match_id: str) -> dict:
    r = session.get(f"{BFV}/ergebnisse/spiel/-/{match_id}", timeout=30)
    r.raise_for_status()
    return parse_match_page(r.text, match_id)


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def push(title: str, message: str, tags: str, url: str, priority: str = "default", dry_run: bool = False):
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    log(f"PUSH [{tags}] {title} | {message}")
    if dry_run or not topic:
        if not topic and not dry_run:
            log("Kein NTFY_TOPIC gesetzt – Push übersprungen")
        return
    # JSON-Variante: Umlaute und Emojis sind hier sicher (in HTTP-Headern nicht)
    body = {
        "topic": topic, "title": title, "message": message,
        "tags": [t for t in tags.split(",") if t],
        "priority": {"min": 1, "low": 2, "default": 3, "high": 4, "max": 5}.get(priority, 3),
        "click": url,
    }
    # Spiel-Link: Antippen öffnet FUSSBALL.DE (App, falls installiert), Knopf öffnet die BFV-Seite
    m = re.search(r"/ergebnisse/spiel/-/([A-Z0-9]{32})", url)
    if m:
        body["click"] = f"https://www.fussball.de/spiel/spiel/-/spiel/{m.group(1)}"
        body["actions"] = [{"action": "view", "label": "BFV", "url": url, "clear": False}]
    try:
        r = session.post(server, json=body, timeout=15)
        if r.status_code >= 300:
            log(f"Push abgelehnt ({r.status_code}): {r.text[:200]}")
    except requests.RequestException as e:
        log("Push fehlgeschlagen:", e)


# ---------------------------------------------------------------------------
# Ereignisse erkennen
# ---------------------------------------------------------------------------

def our_side(info: dict, club_id: str) -> str | None:
    if info.get("home_club") == club_id:
        return "home"
    if info.get("guest_club") == club_id:
        return "guest"
    return None


def _verdict(result: str | None, side: str | None) -> str:
    if not (result and side and ":" in result):
        return ""
    try:
        h, a = (int(x) for x in result.split(":"))
    except ValueError:
        return ""
    mine, theirs = (h, a) if side == "home" else (a, h)
    return " ✅ Sieg" if mine > theirs else " ❌ Niederlage" if mine < theirs else " 🤝 Remis"


def local_time(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%H:%M")


def _short(name: str) -> str:
    """Gegnername ohne Altersklasse/Zusätze: 'SV Planegg-Krailling U17 2' -> 'SV Planegg-Krailling'."""
    name = re.sub(r"\s*-\s*Kinderfestival", "", name, flags=re.I)
    name = re.sub(r"\s+(U\d+|[A-G]\d?)(\s+\d+)?$", "", name)
    return re.sub(r"\s+(2|3|4|II|III)$", "", name).strip()


def opponent(game: dict, cfg: dict, home: str | None = None, guest: str | None = None) -> str:
    """'gg. Gegner (H)' bzw. '(A)' aus Haderner Sicht."""
    home = home or game.get("home_plan") or game.get("home") or ""
    guest = guest or game.get("guest_plan") or game.get("guest") or ""
    key = cfg.get("club_key", "Großhadern")
    if key in home and key not in guest:
        return f"gg. {_short(guest)} (H)"
    if key in guest and key not in home:
        return f"gg. {_short(home)} (A)"
    return f"{home} – {guest}"


def ours_first(score: str | None, side: str | None) -> str | None:
    """'1:3' (Heim:Gast) -> '3:1' wenn Hadern Gast ist."""
    if not score or ":" not in score or side != "guest":
        return score
    a, b = score.split(":", 1)
    return f"{b}:{a}"


def verdict_emoji(score: str | None) -> str:
    """Emoji für Ergebnis aus Haderner Sicht ('3:1')."""
    try:
        mine, theirs = (int(x) for x in (score or "").split(":"))
    except ValueError:
        return ""
    return "✅" if mine > theirs else "❌" if mine < theirs else "🤝"


def send_kickoff(game: dict, cfg: dict, dry_run: bool):
    st = game["st"]
    if st.get("kickoff_sent"):
        return
    st["kickoff_sent"] = True
    if not cfg.get("notify", {}).get("kickoff", True):
        return
    title = f"{game['team_label']} · {'Festival' if game.get('festival') else 'Anpfiff'}"
    push(title, opponent(game, cfg), "", f"{BFV}/ergebnisse/spiel/-/{game['id']}", "low", dry_run)


FINAL_STATUSES = {"acknowledged"}  # Ergebnis vom Spielleiter bestätigt (beobachtet)


def process_match(game: dict, info: dict, cfg: dict, dry_run: bool) -> bool:
    """Vergleicht neuen Stand mit gespeichertem, verschickt Pushes. True = Spiel abgeschlossen."""
    st = game["st"]
    label = game["team_label"]
    url = f"{BFV}/ergebnisse/spiel/-/{game['id']}"
    side = our_side(info, cfg["club_id"])
    pairing = opponent(game, cfg, info["home"], info["guest"])
    kickoff = datetime.fromisoformat(game["kickoff"])

    # Status-Verlauf mitschreiben (zum Lernen, welche Werte der BFV nutzt)
    if info.get("status") and (not st.get("statuses") or st["statuses"][-1] != info["status"]):
        st.setdefault("statuses", []).append(info["status"])
        log(f"{label}: Status -> {info['status']}")

    # Absage
    if info.get("status") == "cancelled":
        if not st.get("final_sent"):
            st["final_sent"] = True
            if now_utc() < kickoff + timedelta(hours=3):
                push(f"{label} · abgesagt 🚫", pairing, "", url, "default", dry_run)
        return True

    # Zum ersten Mal gesehen und längst vorbei: still übernehmen, nichts nachholen
    if not st.get("seen"):
        st["seen"] = True
        if not st.get("kickoff_sent") and now_utc() > kickoff + timedelta(minutes=20):
            st["kickoff_sent"] = True
            st["goals"] = [g.get("goalId") for g in info["goals"]]
            game["result"], game["halftime"] = info["result"], info["halftime"]
            if info["result"] and not info["live"]:
                st["whistle_sent"] = st["final_sent"] = True
            return st.get("final_sent", False)

    if info["live"] or now_utc() >= kickoff:
        send_kickoff(game, cfg, dry_run)
    if info["live"]:
        st["was_live"] = True

    known = set(st["goals"])
    for g in info["goals"]:
        gid = g.get("goalId")
        if gid in known:
            continue
        st["goals"].append(gid)
        ours = (g.get("home") and side == "home") or (not g.get("home") and side == "guest")
        minute = g.get("minute") or "?"
        if g.get("addMinute"):
            minute += f"+{g['addMinute']}"
        scorer = re.sub(r"\s*\(11m\)", "", g.get("name") or "")
        kind = {"penalty": " (11m)", "owngoal": " (ET)"}.get(g.get("type"), "")
        score = ours_first(g.get("score"), side)
        if ours:
            title, prio, who = f"{label} · {score} ⚽", "high", f"{scorer}{kind}" if scorer and scorer != "k.A." else "Tor"
        else:
            title, prio, who = f"{label} · {score}", "default", "Gegentor"
        push(title, f"{minute}' {who}", "", url, prio, dry_run)

    game["result"] = info["result"]
    game["halftime"] = info["halftime"]
    game["home"], game["guest"] = info["home"], info["guest"]
    ht = f" · HZ {ours_first(info['halftime'], side)}" if info["halftime"] else ""
    mine = ours_first(info["result"], side)

    # Abpfiff: Ticker war live und ist es nicht mehr
    if st.get("was_live") and not info["live"] and not st.get("whistle_sent"):
        st["whistle_sent"] = True
        st["whistle_result"] = info["result"]
        push(f"{label} · {mine or '?'} {verdict_emoji(mine)}".rstrip(),
             f"{pairing}{ht} · vorläufig", "", url, "default", dry_run)

    # Ergebnis offiziell eingetragen
    over = not info["live"] and now_utc() > kickoff + timedelta(minutes=60)
    official = info["result"] and over and (not st.get("was_live") or info.get("status") in FINAL_STATUSES)
    if official and not st.get("final_sent"):
        st["final_sent"] = True
        note = " · offiziell"
        if st.get("whistle_result") and st["whistle_result"] != info["result"]:
            note = f" · korrigiert (Ticker {ours_first(st['whistle_result'], side)})"
        push(f"{label} · {mine} {verdict_emoji(mine)}".rstrip(),
             f"{pairing}{ht}{note if st.get('was_live') else ''}", "", url, "default", dry_run)
        return True
    return False


# ---------------------------------------------------------------------------
# Spieltags-Übersicht
# ---------------------------------------------------------------------------

def send_digest(cfg: dict, state: dict, dry_run: bool):
    now_local = datetime.now(TZ)
    today = now_local.date().isoformat()
    if state.get("digest_date") == today or now_local.hour < DIGEST_HOUR:
        return
    todays = [g for g in state.get("games", {}).values()
              if datetime.fromisoformat(g["kickoff"]).astimezone(TZ).date().isoformat() == today]
    state["digest_date"] = today
    if not todays:
        return
    lines = []
    for g in sorted(todays, key=lambda x: x["kickoff"]):
        opp = opponent(g, cfg).replace("gg. ", "")
        extra = " 🎪" if g.get("festival") else ""
        lines.append(f"{local_time(g['kickoff'])} {g['team_label']} – {opp}{extra}")
    n = len(todays)
    push(f"📅 {n} {'Spiel' if n == 1 else 'Spiele'} heute", "\n".join(lines),
         "", f"{BFV}/vereine/{cfg['club_slug']}/{cfg['club_id']}", "default", dry_run)


# ---------------------------------------------------------------------------
# Ergebnis-Kalender
# ---------------------------------------------------------------------------

def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def write_ics(games: dict, cfg: dict):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Haderner Ergebnistracker//DE",
        f"X-WR-CALNAME:{_ics_escape(cfg.get('calendar_name', 'Vereinsspiele'))}",
        "X-PUBLISHED-TTL:PT15M", "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
    ]
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    for g in sorted(games.values(), key=lambda x: x["kickoff"]):
        start = datetime.fromisoformat(g["kickoff"])
        pairing = f"{g['home']} – {g['guest']}" if g.get("home") else g["pairing"]
        title = f"{g['team_label']}: {pairing}"
        if g.get("result"):
            title += f" {g['result']}"
        desc = g.get("competition", "")
        if g.get("halftime"):
            desc += f"\nHalbzeit: {g['halftime']}"
        lines += [
            "BEGIN:VEVENT", f"UID:{g['id']}@ergebnistracker", f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{(start + timedelta(minutes=110)).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_ics_escape(title)}", f"LOCATION:{_ics_escape(g.get('location', ''))}",
            f"DESCRIPTION:{_ics_escape(desc)}", f"URL:{BFV}/ergebnisse/spiel/-/{g['id']}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ICS_OUT.parent.mkdir(parents=True, exist_ok=True)
    ICS_OUT.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def refresh_schedule(cfg: dict, state: dict):
    today = now_utc().date().isoformat()
    if state.get("teams_date") != today or not state.get("teams"):
        try:
            state["teams"] = discover_teams(cfg["club_slug"], cfg["club_id"])
            state["teams_date"] = today
            log(f"{len(state['teams'])} Mannschaften erkannt")
        except requests.RequestException as e:
            log("Mannschaften konnten nicht geladen werden:", e)
    games = state.setdefault("games", {})
    for team in state.get("teams", []):
        try:
            plan = fetch_plan(team["id"])
        except requests.RequestException as e:
            log(f"Spielplan {team['name']} nicht ladbar:", e)
            continue
        for ev in plan:
            if "SPIELFREI" in ev["pairing"].upper():
                continue
            g = games.setdefault(ev["id"], {})
            g.update(ev)
            g["team"] = team["name"]
            g["team_label"] = team_label(team["name"], cfg)
            g["festival"] = is_festival(g, cfg)
            g.setdefault("st", {"goals": []})
        time.sleep(0.3)
    cutoff = now_utc() - timedelta(days=60)
    for gid in [k for k, g in games.items() if datetime.fromisoformat(g["kickoff"]) < cutoff]:
        del games[gid]


def one_pass(cfg: dict, state: dict, dry_run: bool) -> datetime | None:
    """Prüft alle fälligen Spiele. Gibt zurück, wann als Nächstes etwas zu prüfen ist (oder None)."""
    now = now_utc()
    next_due: datetime | None = None

    def due(t: datetime):
        nonlocal next_due
        next_due = t if next_due is None else min(next_due, t)

    for g in state.get("games", {}).values():
        g.setdefault("st", {"goals": []})
        st = g["st"]
        kickoff = datetime.fromisoformat(g["kickoff"])
        if st.get("final_sent") or now > kickoff + RESULT_WINDOW:
            continue
        if g.get("festival"):
            # Festivals: nur Anstoß-Erinnerung, kein Ergebnis
            if now > kickoff + timedelta(minutes=20):
                st["kickoff_sent"] = True  # längst vorbei: nicht nachholen
            if now >= kickoff:
                send_kickoff(g, cfg, dry_run)
                st["final_sent"] = True
            else:
                due(kickoff)
            continue
        if now < kickoff - PRE_KICKOFF:
            due(kickoff - PRE_KICKOFF)
            continue
        in_live = now <= kickoff + LIVE_WINDOW
        last = datetime.fromisoformat(g["checked"]) if g.get("checked") else None
        interval = timedelta(seconds=LIVE_POLL_SECONDS) if (st.get("was_live") or st.get("ticker")) \
            else timedelta(minutes=5) if in_live else timedelta(minutes=20)
        if last and now - last < interval and not (now >= kickoff and not st.get("kickoff_sent")):
            due(last + interval)
            continue
        try:
            info = fetch_match(g["id"])
        except Exception as e:  # Seite kaputt/umgebaut: nicht abbrechen
            log(f"{g['team_label']} {g['pairing']}: Fehler {e}")
            if now >= kickoff:
                send_kickoff(g, cfg, dry_run)
            due(now + timedelta(minutes=5))
            continue
        g["checked"] = now.isoformat()
        if info["ticker"] or info["live"]:
            st["ticker"] = True
        process_match(g, info, cfg, dry_run)
        if not st.get("final_sent"):
            interval = timedelta(seconds=LIVE_POLL_SECONDS) if (st.get("was_live") or st.get("ticker")) \
                else timedelta(minutes=5) if in_live else timedelta(minutes=20)
            nxt = now + interval
            if now < kickoff:
                nxt = min(nxt, kickoff)  # Anstoß pünktlich melden
            due(nxt)
        log(f"{g['team_label']}: {info['home']} – {info['guest']} {info['result'] or '-:-'}"
            f" [{info.get('status')}]{' TICKER' if st.get('ticker') else ''}"
            f"{' LIVE ' + str(info['live_minute'] or '') if info['live'] else ''}")
        time.sleep(1)
    return next_due


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="aktiv bleiben, solange Spiele laufen")
    ap.add_argument("--dry-run", action="store_true", help="keine Pushes verschicken")
    args = ap.parse_args()

    cfg = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    started = now_utc()

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and os.environ.get("CHAINED") != "true":
        push("Tracker · Test ✅", "Manueller Start – Verbindung steht.",
             "", f"{BFV}/vereine/{cfg['club_slug']}/{cfg['club_id']}", "low", args.dry_run)

    refresh_schedule(cfg, state)
    send_digest(cfg, state, args.dry_run)
    deadline = started + MAX_RUNTIME
    chain_until = datetime.now(TZ).replace(hour=CHAIN_UNTIL_HOUR, minute=0, second=0, microsecond=0)
    while True:
        next_due = one_pass(cfg, state, args.dry_run)
        save_json(STATE_PATH, state)
        write_ics(state.get("games", {}), cfg)
        if not args.watch or next_due is None:
            break
        if next_due >= deadline:
            # Laufzeit reicht nicht: Staffelübergabe an einen neuen Lauf, wenn heute noch etwas ansteht
            if next_due <= chain_until:
                CHAIN_FLAG.write_text(next_due.isoformat())
                log(f"Übergabe an neuen Lauf (nächste Prüfung {local_time(next_due.isoformat())})")
            break
        wait = max(20, (next_due - now_utc()).total_seconds())
        if wait > 120:
            log(f"Warte bis {local_time(next_due.isoformat())}")
        time.sleep(wait)
    log("fertig")


if __name__ == "__main__":
    main()
