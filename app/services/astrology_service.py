"""
Serviço de astrologia para Sky.AI: cálculo mundial de signos, graus e aspectos
com Swiss Ephemeris (pyswisseph) + TimezoneFinder + OpenCage.
"""

import os
import requests
import swisseph as swe
import pytz
from datetime import datetime

# ── Configura efemérides ────────────────────────────────
eph_path = os.getenv('SWISS_EPHEMERIS_DATA_PATH')
if eph_path:
    swe.set_ephe_path(eph_path)

# ── Lista de signos ──────────────────────────────────────
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# ── Aspectos principais ─────────────────────────────────
ASPECTS_LIST = [
    (0, "Conjunction"),
    (60, "Sextile"),
    (90, "Square"),
    (120, "Trine"),
    (150, "Quincunx"),
    (180, "Opposition")
]

# ── Fallback TimezoneFinder ─────────────────────────────
try:
    from timezonefinder import TimezoneFinder
    _tf = TimezoneFinder()
    def get_timezone(lat: float, lon: float) -> str:
        tz = _tf.timezone_at(lat=lat, lng=lon)
        return tz or os.getenv('DEFAULT_TIMEZONE', 'UTC')
except ImportError:
    def get_timezone(lat: float, lon: float) -> str:
        return os.getenv('DEFAULT_TIMEZONE', 'UTC')

# ── Busca coordenadas via OpenCage ──────────────────────
def get_coordinates(city: str, country: str) -> dict:
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        raise RuntimeError("OPENCAGE_API_KEY is not set.")
    query = f"{city.strip()}, {country.strip()}"
    url = f"https://api.opencagedata.com/geocode/v1/json?q={query}&key={api_key}&limit=1&language=en"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if not data.get('results'):
        raise ValueError(f"No geocoding results for {query}")
    geom = data['results'][0]['geometry']
    return {"lat": float(geom['lat']), "lon": float(geom['lng'])}

# ── Verifica se ângulo configura aspecto ────────────────
def is_aspect(angle: float, target: float, orb_max: float) -> bool:
    diff = abs(angle - target)
    if diff > 180:
        diff = 360 - diff
    return diff <= orb_max

# ── Calcula orbe exato ──────────────────────────────────
def calc_orb(angle: float, target: float) -> float:
    diff = abs(angle - target)
    if diff > 180:
        diff = 360 - diff
    return diff

# ── Função principal ────────────────────────────────────
def get_astrological_signs(
    birth_date: str,
    birth_time: str,
    birth_city: str,
    birth_country: str
) -> dict:
    """
    Retorna:
      - positions: corpos com longitude, signo e grau
      - aspects: lista de aspectos
      - coords, timezone, jd_ut para debug
    """
    try:
        # 🔹 Busca coordenadas e timezone mundial
        coords = get_coordinates(birth_city, birth_country)
        tz_str = get_timezone(coords['lat'], coords['lon'])
        tz = pytz.timezone(tz_str)

        # 🔹 Local datetime → UTC → Julian Day
        try:
            naive = datetime.strptime(f"{birth_date} {birth_time}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            naive = datetime.strptime(f"{birth_date} {birth_time}", "%Y-%m-%d %H:%M")
        local_dt = tz.localize(naive)
        utc_dt = local_dt.astimezone(pytz.utc)

        jd_ut = swe.julday(
            utc_dt.year, utc_dt.month, utc_dt.day,
            utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
        )

        print(f"[DEBUG] Local: {local_dt.isoformat()} | UTC: {utc_dt.isoformat()} | TZ: {tz_str} | JD_UT: {jd_ut}")

        # 🔹 Planetas principais
        bodies = {
            'SUN': swe.SUN, 'MOON': swe.MOON, 'MERCURY': swe.MERCURY,
            'VENUS': swe.VENUS, 'MARS': swe.MARS, 'JUPITER': swe.JUPITER,
            'SATURN': swe.SATURN, 'URANUS': swe.URANUS,
            'NEPTUNE': swe.NEPTUNE, 'PLUTO': swe.PLUTO
        }

        positions = {}
        for name, code in bodies.items():
            data = swe.calc_ut(jd_ut, code)
            lon = float(data[0][0])
            sign_idx = int(lon // 30) % 12
            positions[name] = {
                'longitude': round(lon, 4),
                'sign': SIGNS[sign_idx],
                'degree': round(lon % 30, 2)
            }
            print(f"[DEBUG] {name}: {positions[name]}")

        # 🔹 Ascendente
        asc_data = swe.houses(jd_ut, coords['lat'], coords['lon'])[0]
        asc_lon = float(asc_data[0])
        asc_idx = int(asc_lon // 30) % 12
        positions['ASC'] = {
            'longitude': round(asc_lon, 4),
            'sign': SIGNS[asc_idx],
            'degree': round(asc_lon % 30, 2)
        }
        print(f"[DEBUG] ASC: {positions['ASC']}")

        # 🔹 Aspectos
        aspects = []
        keys = list(positions.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a_lon = positions[keys[i]]['longitude']
                b_lon = positions[keys[j]]['longitude']
                angle = abs(a_lon - b_lon)
                if angle > 180:
                    angle = 360 - angle
                for target, asp_name in ASPECTS_LIST:
                    if is_aspect(angle, target, orb_max=6):
                        aspects.append({
                            'body1': keys[i],
                            'body2': keys[j],
                            'aspect': asp_name,
                            'angle': round(angle, 2),
                            'orb': round(calc_orb(angle, target), 2)
                        })

        return {
            'positions': positions,
            'aspects': aspects,
            'coords': coords,
            'timezone': tz_str,
            'jd_ut': jd_ut
        }

    except Exception as e:
        print(f"[Astrology ERROR] {e}")
        return {'error': str(e), 'positions': {}, 'aspects': []}
