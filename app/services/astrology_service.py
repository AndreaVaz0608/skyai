# app/services/astrology_service.py
"""
Serviço de astrologia para Sky.AI: cálculo de signos, graus e aspectos com precisão elevada usando Swiss Ephemeris (pyswisseph).
"""

import os
import requests
import swisseph as swe
import pytz
from datetime import datetime

# Configurar path dos efemérides (use variável de ambiente ou padrão do pacote)
eph_path = os.getenv('SWISS_EPHEMERIS_DATA_PATH')
if eph_path:
    swe.set_ephe_path(eph_path)

# Lista de aspectos principais (ângulos em graus)
ASPECTS_LIST = [
    (0,   "Conjunction"),
    (60,  "Sextile"),
    (90,  "Square"),
    (120, "Trine"),
    (150, "Quincunx"),
    (180, "Opposition")
]

# Signos astrológicos em ordem
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Fallback de timezonefinder
try:
    from timezonefinder import TimezoneFinder
    _tf = TimezoneFinder()
    def get_timezone(lat: float, lon: float) -> str:
        tz = _tf.timezone_at(lat=lat, lng=lon)
        return tz or os.getenv('DEFAULT_TIMEZONE', 'UTC')
except ImportError:
    def get_timezone(lat: float, lon: float) -> str:
        return os.getenv('DEFAULT_TIMEZONE', 'UTC')

# Busca coordenadas via OpenCage API
def get_coordinates(city: str, country: str) -> dict:
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        raise RuntimeError("OPENCAGE_API_KEY is not set.")
    query = f"{city.strip()}, {country.strip()}"
    url = (
        f"https://api.opencagedata.com/geocode/v1/json?q={query}"
        f"&key={api_key}&limit=1&language=en"
    )
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if not data.get('results'):
        raise ValueError(f"No geocoding results for {query}")
    geom = data['results'][0]['geometry']
    return {"lat": float(geom['lat']), "lon": float(geom['lng'])}

# Verifica se ângulo configura aspecto dentro do orbe
def is_aspect(angle: float, target: float, orb_max: float) -> bool:
    diff = abs(angle - target)
    if diff > 180:
        diff = 360 - diff
    return diff <= orb_max

# Calcula orbe exato
def calc_orb(angle: float, target: float) -> float:
    diff = abs(angle - target)
    if diff > 180:
        diff = 360 - diff
    return diff

# Função principal: retorna posições e aspectos
def get_astrological_signs(
    birth_date: str,
    birth_time: str,
    birth_city: str,
    birth_country: str
) -> dict:
    """
    Retorna:
      - positions: dict de corpos com longitude, signo e grau
      - aspects: lista de aspectos entre os corpos
    """
    try:
        # Geolocalização e timezone
        coords = get_coordinates(birth_city, birth_country)
        tz_str = get_timezone(coords['lat'], coords['lon'])
        tz = pytz.timezone(tz_str)

        # Parsing data/hora local
        try:
            naive = datetime.strptime(f"{birth_date} {birth_time}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            naive = datetime.strptime(f"{birth_date} {birth_time}", "%Y-%m-%d %H:%M")
        local_dt = tz.localize(naive)
        utc_dt = local_dt.astimezone(pytz.utc)

        # Cálculo de Julian Day (UT)
        jd_ut = swe.julday(
            utc_dt.year, utc_dt.month, utc_dt.day,
            utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
        )

        print(f"[DEBUG] DateTime UTC: {utc_dt.isoformat()} | JD_UT: {jd_ut}")
        print(f"[DEBUG] Coords: {coords} | TZ: {tz_str}")

        # Posições planetárias
        bodies = {
            'SUN': swe.SUN, 'MOON': swe.MOON, 'MERCURY': swe.MERCURY,
            'VENUS': swe.VENUS, 'MARS': swe.MARS, 'JUPITER': swe.JUPITER,
            'SATURN': swe.SATURN, 'URANUS': swe.URANUS,
            'NEPTUNE': swe.NEPTUNE, 'PLUTO': swe.PLUTO
        }

        positions = {}
        for name, code in bodies.items():
            data = swe.calc_ut(jd_ut, code)
            lon = float(data[0][0])  # ✅ Correção definitiva
            sign_idx = int(lon // 30) % 12
            positions[name] = {
                'longitude': round(lon, 4),
                'sign': SIGNS[sign_idx],
                'degree': round(lon % 30, 2)
            }
            print(f"[DEBUG] {name} → lon: {lon:.4f}, sign: {SIGNS[sign_idx]}, deg: {lon % 30:.2f}")

        # Ascendente
        asc_data = swe.houses(jd_ut, coords['lat'], coords['lon'])[0]
        asc_lon = float(asc_data[0])
        asc_idx = int(asc_lon // 30) % 12
        positions['ASC'] = {
            'longitude': round(asc_lon, 4),
            'sign': SIGNS[asc_idx],
            'degree': round(asc_lon % 30, 2)
        }
        print(f"[DEBUG] ASC → lon: {asc_lon:.4f}, sign: {SIGNS[asc_idx]}, deg: {asc_lon % 30:.2f}")

        # Cálculo de aspectos
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

        return {'positions': positions, 'aspects': aspects}

    except Exception as e:
        print(f"[Astrology ERROR] {e}")
        return {'error': str(e), 'positions': {}, 'aspects': []}


# ✅ Teste local: apenas para debug manual
if __name__ == "__main__":
    test_result = get_astrological_signs(
        birth_date="1991-03-25",
        birth_time="08:15",
        birth_city="São Paulo",
        birth_country="Brazil"
    )

    if "error" in test_result:
        print("[TEST FAILED]", test_result["error"])
    else:
        print("\n✅ [TEST PASSED] Astro Profile:")
        for name, data in test_result["positions"].items():
            print(f"→ {name}: {data['sign']} {data['degree']}° (lon: {data['longitude']})")

        print("\n📐 Aspects:")
        for asp in test_result["aspects"]:
            print(f"{asp['body1']} {asp['aspect']} {asp['body2']} | {asp['angle']}° (orb: {asp['orb']}°)")
