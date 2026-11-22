import base64, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); import tracker as t
S = R / "sample"
cfg = json.loads((R / "config.json").read_text())
t.STATE_PATH = R/"tests/state_v2.json"; t.ICS_OUT = R/"tests/erg_v2.ics"

# 1) Spielplan-Parser
teams = {"u9":"TSV Großhadern U9","h1":"TSV Großhadern","u17":"TSV Großhadern U17","u12":"TSV Großhadern U12","u10":"TSV Großhadern U10"}
state = {"games": {}}
for k, name in teams.items():
    for ev in t.parse_plan((S/f"plan_{k}.html").read_text(encoding="utf-8")):
        g = state["games"].setdefault(ev["id"], {}); g.update(ev)
        g["team_label"] = t.team_label(name, cfg); g["festival"] = t.is_festival(g, cfg); g["st"] = {"goals": []}
for g in sorted(state["games"].values(), key=lambda x: x["kickoff"]):
    print(t.local_time(g["kickoff"]), g["kickoff"][:10], g["team_label"], "|", g["pairing"], "|", g["competition"], "| Festival" if g["festival"] else "")

# 2) Tages-Übersicht (Zeit auf heute 08.11. gesetzt)
print("\n--- Digest")
state["digest_date"] = None
t.send_digest(cfg, state, dry_run=True)
t.send_digest(cfg, state, dry_run=True)  # darf nicht doppelt kommen

# 3) Ticker-Spiel durchspielen (Daten des 2:2 aus Gräfelfing)
html = (S/"match_page.html").read_text(encoding="utf-8"); font = base64.b64decode((S/"match_page_font.b64").read_text())
info = t.parse_match_page(html, "031BSK5S0G000000VS5489BTVUS470OH", font_bytes=font)
g = {"id": info["id"], "kickoff": (t.now_utc()-timedelta(minutes=100)).isoformat(), "team_label": "1. Mannschaft", "pairing": "x", "st": {"goals": []}}
full = info["goals"]
print("\n--- Ticker-Spiel")
for step in range(len(full)+1):
    t.process_match(g, dict(info, live=True, status="live?", goals=full[:step], result=f"{sum(1 for x in full[:step] if x['home'])}:{sum(1 for x in full[:step] if not x['home'])}"), cfg, True)
print("-- Abpfiff (Ticker aus, Status noch nicht bestätigt)")
t.process_match(g, dict(info, live=False, status="played"), cfg, True)
print("-- Spielleiter bestätigt")
t.process_match(g, dict(info, live=False, status="acknowledged"), cfg, True)

# 4) Spiel ohne Ticker
print("\n--- Ohne Ticker")
g2 = {"id": "X", "kickoff": (t.now_utc()-timedelta(minutes=1)).isoformat(), "team_label": "U12", "pairing": "A – B", "st": {"goals": []}}
noinfo = dict(info, live=False, goals=[], result=None, halftime=None, status="planned")
t.process_match(g2, noinfo, cfg, True)                      # Anstoß laut Plan
g2["kickoff"] = (t.now_utc()-timedelta(minutes=120)).isoformat()
t.process_match(g2, noinfo, cfg, True)                      # nichts
t.process_match(g2, dict(noinfo, result="3:1", status="acknowledged"), cfg, True)  # Ergebnis

print("\n--- Altes Spiel zum ersten Mal gesehen (darf nichts pushen)")
g3 = {"id": info["id"], "kickoff": (t.now_utc()-timedelta(days=1)).isoformat(), "team_label": "U19", "pairing": "x", "st": {"goals": []}}
print("fertig:", t.process_match(g3, dict(info, status="acknowledged"), cfg, True))
print("\n--- Absage vor Anstoß")
g4 = {"id": "Y", "kickoff": (t.now_utc()+timedelta(minutes=5)).isoformat(), "team_label": "U12", "pairing": "A – B", "st": {"goals": []}}
t.process_match(g4, dict(info, status="cancelled", live=False, goals=[]), cfg, True)
t.process_match(g4, dict(info, status="cancelled", live=False, goals=[]), cfg, True)
