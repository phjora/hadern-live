"""Donnerstag: ein Spiel um 18:00, erster Lauf 07:05. Wie viele Läufe entstehen bis zum Ergebnis?"""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); import tracker as t
t.STATE_PATH = R/"tests/state_wd.json"; t.ICS_OUT = R/"tests/erg_wd.ics"; t.CHAIN_FLAG = R/"tests/.chain_wd"
clock = [datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)]  # 07:05 lokal
t.now_utc = lambda: clock[0]
class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None): return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
t.datetime = FakeDT
t.time.sleep = lambda s: clock.__setitem__(0, clock[0] + timedelta(seconds=s))
CLUB = "00ES8GNHBS00000SVV0AG08LVUPGND5I"
K = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)  # 18:00 lokal
RESULT_AFTER = int(sys.argv[1]) if len(sys.argv) > 1 else 100  # Minuten nach Anpfiff
def fetch(mid):
    m = (clock[0]-K).total_seconds()/60
    res = "2:1" if m > RESULT_AFTER else None
    return dict(id=mid, home="TSV Großhadern U15", guest="TSV Gräfelfing U15", home_club=CLUB, guest_club="X", halftime=None,
                goals=[], live_minute=None, competition="", live=False, ticker=False, result=res,
                status="acknowledged" if res else "scheduled")
t.fetch_match = fetch
state = {"games": {"G": {"id":"G","kickoff":K.isoformat(),"team_label":"U15","pairing":"TSV Großhadern U15 – TSV Gräfelfing U15",
                         "home_plan":"TSV Großhadern U15","guest_plan":"TSV Gräfelfing U15","st":{"goals":[]}}}}
cfg = json.loads((R/"config.json").read_text())
t.load_json = lambda p, d: state if p == t.STATE_PATH else cfg
t.refresh_schedule = lambda c, s: None

sys.argv = ["x", "--watch", "--dry-run"]
runs = 0
while True:
    runs += 1
    if t.CHAIN_FLAG.exists(): t.CHAIN_FLAG.unlink()
    start = clock[0].astimezone(t.TZ).strftime("%a %H:%M")
    t.main()
    print(f"== Lauf {runs}: {start} – {clock[0].astimezone(t.TZ).strftime('%a %H:%M')}, Übergabe: {t.CHAIN_FLAG.exists()}")
    if not t.CHAIN_FLAG.exists() or runs > 30: break
    clock[0] += timedelta(seconds=40)  # Startzeit des nächsten Laufs
print("Läufe:", runs)
