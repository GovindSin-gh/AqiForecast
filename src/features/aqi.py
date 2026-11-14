"""US AQI from PM2.5 (ug/m3).

CHECK BEFORE TRUSTING: breakpoints below are the EPA table as revised in 2024.
Open-Meteo's own us_aqi may use a different table. Compare a few values and
edit BREAKPOINTS if they differ. This is the only place the table lives.
"""
BREAKPOINTS = [  # (pm_low, pm_high, aqi_low, aqi_high)
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500)]
NAMES = ["Good", "Moderate", "Unhealthy for sensitive groups",
         "Unhealthy", "Very unhealthy", "Hazardous"]
PM25_UPPER = [b[1] for b in BREAKPOINTS[:-1]]   # category edges in ug/m3


def pm25_to_aqi(pm: float) -> int:
    pm = int(max(0.0, float(pm)) * 10) / 10      # EPA truncates to 0.1
    for lo, hi, a_lo, a_hi in BREAKPOINTS:
        if pm <= hi:
            return round((a_hi - a_lo) / (hi - lo) * (pm - lo) + a_lo)
    return 500


def category(aqi: float) -> str:
    for name, top in zip(NAMES, (50, 100, 150, 200, 300)):
        if aqi <= top:
            return name
    return NAMES[-1]
