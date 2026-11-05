"""Single ET clock for every tab and the recorder."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def ms_to_et(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, ET)


def recording_window(n: datetime | None = None) -> bool:
    """True while SPX options trade or are about to: Sun 19:00 ET -> Fri 16:20 ET,
    skipping the daily 16:20-19:00 maintenance gap. Outside it the recorder keeps
    its connection but writes no snapshots (closed market = no pointless rows)."""
    n = n or now_et()
    wd, t = n.weekday(), n.time()
    if wd == 5:                      # Saturday
        return False
    if wd == 6:                      # Sunday
        return t >= time(19, 0)
    if time(16, 20) < t < time(19, 0):
        return False
    if wd == 4 and t > time(16, 20):  # Friday evening
        return False
    return True


def session_minute(n: datetime | None = None) -> float:
    """Minutes since 09:30 ET today; negative overnight."""
    n = n or now_et()
    return (n.hour * 60 + n.minute + n.second / 60) - 570
