"""Sonntag, U17 in Planegg nachgestellt: Vereins-Ticker bleibt bei 1:0 stehen, Fanticker läuft weiter."""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); import tracker as t
CLUB = "00ES8GNHBS00000SVV0AG08LVUPGND5I"; MID = "M"
K = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)  # 15:00 lokal
clock = [K - timedelta(minutes=10)]
t.now_utc = lambda: clock[0]
class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None): return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
t.datetime = FakeDT
t.time.sleep = lambda s: None
def page(obj):  # so sieht eine BFV-Seite aus: Daten in self.__next_f.push
    return "<script>self.__next_f.push(" + json.dumps([1, json.dumps(obj, separators=(",", ":"))]) + ")</script>"
# Fanticker-Verlauf (echte Daten vom Sonntag): Minute nach Anpfiff -> Stand
FAN = [(13, "1:0", 11), (48, "2:0", 45), (73, "2:1", 54), (86, "3:1", 67)]
def fan(m):
    ev = [{"typeId": 1, "score": s, "minute": mi} for at, s, mi in FAN if m >= at][::-1]
    over = m >= 102
    return {"id": "FAN", "score": ev[0]["score"] if ev else "0:0", "scoreHalftime": "2:0" if m >= 50 else None,
            "live": not over, "timeplayed": 4800 if over else (2400 if m >= 50 else 0), "duration": 80,
            "actualKickoffSecondHalf": "x" if m >= 60 else None, "events": ev,
            "tickers": [{"id": "GAST"}, {"id": "FAN"}]}
def gast(m):
    return {"id": "GAST", "score": "1:0" if m >= 14 else "0:0", "scoreHalftime": "1:0", "live": True, "timeplayed": 2400,
            "duration": 80, "actualKickoffSecondHalf": None, "events": [{"typeId": 1, "score": "1:0", "minute": 14}] if m >= 14 else [],
            "tickers": [{"id": "GAST"}, {"id": "FAN"}]}
class Resp:
    def __init__(s, text): s.text = text
    def raise_for_status(s): pass
def get(url, **kw):
    m = (clock[0] - K).total_seconds() / 60
    if url.endswith("/liveticker"): return Resp(page({"ticker": gast(m)}))
    if url.endswith("/liveticker/FAN"): return Resp(page({"ticker": fan(m)}))
    return Resp("MATCH")
t.session.get = get
def match_page(html, mid):  # Spielseite: zeigt nur den stehengebliebenen Vereins-Ticker, „live“ bis zur Bestätigung
    m = (clock[0] - K).total_seconds() / 60
    ack = m >= 136
    return dict(id=mid, status="acknowledged" if ack else ("live" if m >= 6 else "scheduled"), live=6 <= m < 136,
                live_minute="40" if m > 45 else str(int(max(m, 0))), ticker=True, ticker_count=2,
                home="SV Planegg-Krailling U17 2", home_club="X", guest="TSV Großhadern U17", guest_club=CLUB,
                result="3:1" if ack else ("1:0" if m >= 14 else ("0:0" if m >= 6 else None)),
                halftime="2:0" if ack else None, goals=[], competition="")
t.parse_match_page = match_page
pushes = []
t.push = lambda title, msg, tags, url, prio="default", dry=False: pushes.append(f"{clock[0].astimezone(t.TZ):%H:%M}  {title}  |  {msg}")
cfg = json.loads((R/"config.json").read_text())
g = {"id": MID, "kickoff": K.isoformat(), "team_label": "U17", "pairing": "SV Planegg-Krailling U17 2 – TSV Großhadern U17",
     "home_plan": "SV Planegg-Krailling U17 2", "guest_plan": "TSV Großhadern U17", "st": {"goals": []}}
state = {"games": {MID: g}}
t.log = lambda *a: print("LOG", *a) if "Ticker" in str(a) else None
while clock[0] < K + timedelta(minutes=150):
    g.pop("checked", None)
    t.one_pass(cfg, state, False)
    clock[0] += timedelta(minutes=1)
print("\n".join(pushes))
exp = ["Anpfiff", "0:1", "0:2", "1:2", "1:3", "1:3 🔴"]
assert len(pushes) == 6 and all(e in p for e, p in zip(exp, pushes)), "unerwartete Pushes"
assert "vorläufig" in pushes[5] and "HZ 0:2" in pushes[5]
print("OK")
