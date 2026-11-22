import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); import tracker as t
t.STATE_PATH = R/"tests/state_day.json"; t.ICS_OUT = R/"tests/erg_day.ics"; t.CHAIN_FLAG = R/"tests/.chain"
if t.CHAIN_FLAG.exists(): t.CHAIN_FLAG.unlink()
clock = [datetime(2026, 11, 8, 9, 40, tzinfo=timezone.utc)]  # 10:40 lokal
t.now_utc = lambda: clock[0]
class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None): return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
t.datetime = FakeDT
fetches = []
def sleep(s): clock[0] += timedelta(seconds=s)
t.time.sleep = sleep
CLUB = "00ES8GNHBS00000SVV0AG08LVUPGND5I"
def iso(h, m): return datetime(2026, 11, 8, h, m, tzinfo=timezone.utc).isoformat()
games = {
 "FEST": {"id":"FEST","kickoff":iso(10,0),"team_label":"U9","pairing":"A – U9","festival":True},
 "NOTICK": {"id":"NOTICK","kickoff":iso(10,0),"team_label":"U10 2","pairing":"BSC – U10 2"},
 "TICK": {"id":"TICK","kickoff":iso(13,0),"team_label":"1. Mannschaft","pairing":"TSV – Helios"},
 "U17": {"id":"U17","kickoff":iso(14,0),"team_label":"U17","pairing":"Planegg – U17"},
}
def fetch(mid):
    fetches.append((clock[0].astimezone(t.TZ).strftime("%H:%M"), mid))
    k = datetime.fromisoformat(games[mid]["kickoff"]); m = (clock[0]-k).total_seconds()/60
    base = dict(id=mid, home="Heim", guest="Gast", home_club=CLUB, guest_club="X", halftime=None, goals=[], live_minute=None, competition="")
    if mid == "TICK":
        live = 0 <= m < 95
        goals = [dict(goalId=1, minute="23", score="1:0", home=True, type="regular", name="Max")] if m >= 23 else []
        return dict(base, live=live, ticker=m >= -5, goals=goals, result=("1:0" if m >= 23 else ("0:0" if m >= 0 else None)),
                    status="acknowledged" if m > 200 else ("live" if live else "planned"))
    res = "3:1" if m > 140 else None
    return dict(base, live=False, ticker=False, result=res, status="finished" if res else "planned")
t.fetch_match = fetch
state = {"games": {k: dict(v, st={"goals": []}) for k, v in games.items()}}
cfg = json.loads((R/"config.json").read_text())
t.load_json = lambda p, d: state if p == t.STATE_PATH else cfg
t.refresh_schedule = lambda c, s: None
t.send_digest = lambda c, s, d: None
sys.argv = ["x", "--watch", "--dry-run"]
t.main()
print("Lauf-Ende:", clock[0].astimezone(t.TZ).strftime("%H:%M"), "| .chain:", t.CHAIN_FLAG.read_text() if t.CHAIN_FLAG.exists() else "-")
from collections import Counter
print("Abrufe je Spiel:", Counter(m for _, m in fetches))
print("NOTICK-Abrufe:", [x for x, m in fetches if m == "NOTICK"][:8], "...")
