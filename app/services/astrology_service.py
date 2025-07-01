"""
Serviço de astrologia para Sky.AI
================================

• Cálculo de posições planetárias, ascendente e aspectos globais
  usando **Swiss Ephemeris** (pyswisseph).
• Geocodificação via **OpenCage** e fuso‑horário com **timezonefinder** +
  base oficial *tzdata* (zoneinfo) do Python ≥ 3.9.

Requisitos principais
--------------------
- swisseph (pyswisseph)
- requests
- timezonefinder  (opcional, porém recomendado)
- python ≥ 3.9  (para zoneinfo). Se não houver zoneinfo, cai em `pytz`.

Variáveis de ambiente esperadas
-------------------------------
SWISS_EPHEMERIS_DATA_PATH   → caminho para os arquivos .se1 …
OPENCAGE_API_KEY            → chave de acesso ao serviço OpenCage
DEFAULT_TIMEZONE            → fallback, ex. "UTC" ou "America/Sao_Paulo"
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

import requests
import swisseph as swe

# ── Efemérides ───────────────────────────────────────────
EPH_PATH = os.getenv("SWISS_EPHEMERIS_DATA_PATH")
if EPH_PATH:
    swe.set_ephe_path(EPH_PATH)

# ── Signos ───────────────────────────────────────────────
SIGNS: List[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── Aspectos (grau exato & nome) ─────────────────────────
ASPECTS_LIST = [
    (0, "Conjunction"),
    (60, "Sextile"),
    (90, "Square"),
    (120, "Trine"),
    (150, "Quincunx"),
    (180, "Opposition"),
]

# ── Time‑zone utils ──────────────────────────────────────
DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")

try:
    from zoneinfo import ZoneInfo  # Python ≥ 3.9
except ImportError:  # pragma: no cover — fallback antigo
    try:
        from pytz import timezone as ZoneInfo  # type: ignore
    except ImportError as err:  # pragma: no cover
        sys.exit(
            "✖ Nenhuma biblioteca de timezone disponível. Instale python ≥ 3.9 ou pytz."
        )

try:
    from timezonefinder import TimezoneFinder  # slow import

    _TF = TimezoneFinder()

    def get_timezone(lat: float, lon: float) -> str:
        """Resolve fuso‑horário IANA a partir da latitude/longitude."""
        tz = _TF.timezone_at(lat=lat, lng=lon)
        if tz is None:
            raise ValueError("TimezoneFinder não encontrou fuso para as coordenadas.")
        return tz

except ImportError:

    def get_timezone(lat: float, lon: float) -> str:  # type: ignore[override]
        """Versão fallback: retorna DEFAULT_TZ e avisa."""
        print("[WARN] TimezoneFinder não instalado – usando DEFAULT_TIMEZONE!", file=sys.stderr)
        return DEFAULT_TZ

# ── Geocodificação via OpenCage ───────────────────────────


def get_coordinates(city: str, country: str) -> Dict[str, float]:
    """Obtém latitude/longitude com OpenCage. Lança Erro se nada encontrado."""

    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        raise RuntimeError("OPENCAGE_API_KEY não configurada.")

    query = f"{city.strip()}, {country.strip()}"
    url = (
        "https://api.opencagedata.com/geocode/v1/json"
        f"?q={query}&key={api_key}&limit=1&language=en"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("results"):
        raise ValueError(f"Sem resultados de geocodificação para '{query}'.")

    geom = payload["results"][0]["geometry"]
    return {"lat": float(geom["lat"]), "lon": float(geom["lng"])}


# ── Funções auxiliares de aspectos ───────────────────────

def _angle_distance(a: float, b: float) -> float:
    """Retorna a distância mínima entre dois ângulos (0‑180°)."""

    diff = abs(a - b) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


def is_aspect(angle: float, target: float, orb_max: float) -> bool:
    return _angle_distance(angle, target) <= orb_max


def calc_orb(angle: float, target: float) -> float:
    return _angle_distance(angle, target)


# ── Conversões de tempo ──────────────────────────────────


def jd_from_utc(dt_utc: datetime) -> float:
    """Converte datetime **UTC** → Julian Day UT via helper nativo."""
    jd_ut, _jd_tt = swe.utc_to_jd(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour,
        dt_utc.minute,
        dt_utc.second + dt_utc.microsecond / 1e6,
        swe.GREG_CAL,
    )
    return jd_ut


# ── Função principal ─────────────────────────────────────


def get_astrological_data(
    birth_date: str,
    birth_time: str,
    birth_city: str,
    birth_country: str,
    debug: bool = False,
) -> Dict[str, object]:
    """Cálculo completo (posições, aspectos, ascendente).

    Args:
        birth_date: "AAAA-MM-DD".
        birth_time: "HH:MM" ou "HH:MM:SS" no horário **local** da cidade.
        birth_city: Cidade de nascimento.
        birth_country: País de nascimento.
        debug: Imprime detalhes de conversão tempo/JD se `True`.
    """

    # 1) Coordenadas & fuso‑horário ---------------------------------------
    coords = get_coordinates(birth_city, birth_country)

    try:
        tz_str = get_timezone(coords["lat"], coords["lon"])
    except ValueError:
        tz_str = DEFAULT_TZ  # fallback explícito

    tzinfo = ZoneInfo(tz_str)

    # 2) Monta datetime local ---------------------------------------------
    dt_format = "%Y-%m-%d %H:%M:%S" if len(birth_time.split(":")) == 3 else "%Y-%m-%d %H:%M"
    naive_local = datetime.strptime(f"{birth_date} {birth_time}", dt_format)

    # Detecta horário de verão ambíguo
    try:
        local_dt = naive_local.replace(tzinfo=tzinfo)
    except Exception as e:  # zoneinfo não gera ambíguo; pytz sim
        raise ValueError(f"Falha ao aplicar timezone ({tz_str}): {e}")

    # 3) Converte para UTC e JD -------------------------------------------
    utc_dt = local_dt.astimezone(timezone.utc)
    jd_ut = jd_from_utc(utc_dt)

    # 4) Posições planetárias ---------------------------------------------
    bodies = {
        "SUN": swe.SUN,
        "MOON": swe.MOON,
        "MERCURY": swe.MERCURY,
        "VENUS": swe.VENUS,
        "MARS": swe.MARS,
        "JUPITER": swe.JUPITER,
        "SATURN": swe.SATURN,
        "URANUS": swe.URANUS,
        "NEPTUNE": swe.NEPTUNE,
        "PLUTO": swe.PLUTO,
    }

    positions: Dict[str, Dict[str, float | str]] = {}

    for name, code in bodies.items():
        lon, lat, dist, _ = swe.calc_ut(jd_ut, code)[0]
        lon = float(lon)
        sign_idx = math.floor((lon + 1e-7) / 30.0) % 12  # epsilon evita erro cusp.
        positions[name] = {
            "longitude": round(lon, 6),
            "sign": SIGNS[sign_idx],
            "degree": round(lon % 30.0, 4),
        }
        if debug:
            print(f"[DEBUG] {name:7}: {positions[name]}")

    # 5) Ascendente --------------------------------------------------------
    house_cusps, ascmc = swe.houses(jd_ut, coords["lat"], coords["lon"])
    asc_lon = float(ascmc[0])  # 0 = ASC
    asc_idx = math.floor((asc_lon + 1e-7) / 30.0) % 12
    positions["ASC"] = {
        "longitude": round(asc_lon, 6),
        "sign": SIGNS[asc_idx],
        "degree": round(asc_lon % 30.0, 4),
    }
    if debug:
        print(f"[DEBUG] ASC    : {positions['ASC']}")

    # 6) Aspectos ----------------------------------------------------------
    aspects: List[Dict[str, object]] = []
    keys = list(positions.keys())
    for i, body1 in enumerate(keys):
        for body2 in keys[i + 1 :]:
            a_lon = positions[body1]["longitude"]  # type: ignore[index]
            b_lon = positions[body2]["longitude"]  # type: ignore[index]
            angle = _angle_distance(a_lon, b_lon)
            for target, asp_name in ASPECTS_LIST:
                if is_aspect(angle, target, orb_max=6):
                    aspects.append(
                        {
                            "body1": body1,
                            "body2": body2,
                            "aspect": asp_name,
                            "angle": round(angle, 2),
                            "orb": round(calc_orb(angle, target), 2),
                        }
                    )

    # 7) Debug geral -------------------------------------------------------
    if debug:
        print("==== DEBUG ASTRAL ====")
        print(f"Local datetime: {local_dt.isoformat()}")
        print(f"UTC datetime:   {utc_dt.isoformat()}")
        print(f"Timezone used:  {tz_str}")
        print(f"JD_UT:          {jd_ut}")
        print("======================")

    return {
        "positions": positions,
        "aspects": aspects,
        "coords": coords,
        "timezone": tz_str,
        "jd_ut": jd_ut,
    }

# ---- alias de compatibilidade ---------------------------------
def get_astrological_signs(*args, **kwargs):
    """Mantido para código legado — devolve 4 valores esperados."""
    data = get_astrological_data(*args, **kwargs)
    sun_sign  = data["positions"]["SUN"]["sign"]
    moon_sign = data["positions"]["MOON"]["sign"]
    asc_sign  = data["positions"]["ASC"]["sign"]
    aspects   = data["aspects"]
    return sun_sign, moon_sign, asc_sign, aspects

# ── Execução rápida via CLI ---------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calcula mapa astral básico.")
    parser.add_argument("date", help="Data de nascimento AAAA-MM-DD")
    parser.add_argument("time", help="Hora local HH:MM ou HH:MM:SS")
    parser.add_argument("city", help="Cidade")
    parser.add_argument("country", help="País")
    parser.add_argument("--debug", action="store_true", help="Exibe debug detalhado")

    args = parser.parse_args()

    result = get_astrological_data(
        args.date,
        args.time,
        args.city,
        args.country,
        debug=args.debug,
    )

    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
