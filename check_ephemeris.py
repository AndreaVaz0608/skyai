import os
import math
import sys
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
import swisseph as swe
import requests

load_dotenv()  # ✅ Agora o .env é lido na hora!

# Config path Swiss Ephemeris
EPH_PATH = os.getenv("SWISS_EPHEMERIS_DATA_PATH")
if EPH_PATH:
    swe.set_ephe_path(EPH_PATH)

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

try:
    from timezonefinder import TimezoneFinder
    _TF = TimezoneFinder()

    def get_timezone(lat, lon):
        tz = _TF.timezone_at(lat=lat, lng=lon)
        if tz is None:
            raise ValueError("Timezone not found")
        return tz
except ImportError:
    def get_timezone(lat, lon):
        return os.getenv("DEFAULT_TIMEZONE", "UTC")

def get_coordinates(city, country):
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENCAGE_API_KEY")
    query = f"{city.strip()}, {country.strip()}"
    url = (
        "https://api.opencagedata.com/geocode/v1/json"
        f"?q={query}&key={api_key}&limit=1&language=en"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("results"):
        raise ValueError(f"No results for '{query}'")
    geom = payload["results"][0]["geometry"]
    return {"lat": float(geom["lat"]), "lon": float(geom["lng"])}

def jd_from_utc(dt_utc):
    jd_ut, _ = swe.utc_to_jd(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour,
        dt_utc.minute,
        dt_utc.second + dt_utc.microsecond / 1e6,
        swe.GREG_CAL,
    )
    return jd_ut

def main(args):
    coords = get_coordinates(args.city, args.country)
    tz = get_timezone(coords["lat"], coords["lon"])
    tzinfo = ZoneInfo(tz)

    dt_format = "%Y-%m-%d %H:%M"
    local_dt = datetime.strptime(f"{args.date} {args.time}", dt_format)
    local_dt = local_dt.replace(tzinfo=tzinfo)
    utc_dt = local_dt.astimezone(timezone.utc)
    jd_ut = jd_from_utc(utc_dt)

    sol_pos = swe.calc_ut(jd_ut, swe.SUN)[0][0]
    sol_idx = math.floor((sol_pos + 1e-7) / 30.0) % 12
    sol_degree = sol_pos % 30.0

    print("\n=== EPHEMERIS DEBUG ===")
    print(f"Coordinates : lat={coords['lat']} lon={coords['lon']}")
    print(f"Timezone    : {tz}")
    print(f"Local time  : {local_dt.isoformat()}")
    print(f"UTC time    : {utc_dt.isoformat()}")
    print(f"Julian Day  : {jd_ut}")
    print(f"Sun lon     : {sol_pos:.6f}°")
    print(f"Sun sign    : {SIGNS[sol_idx]}")
    print(f"Degree in sign : {sol_degree:.4f}")
    print("========================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--country", required=True)
    args = parser.parse_args()
    main(args)
