# app/services/perfil_service.py
"""
Geração de relatório Sky.AI com astrologia e numerologia.
Inclui logging do prompt e controle de erros.
"""

import os
import json
import re
from datetime import datetime
import io
import traceback

from flask import current_app
from openai import OpenAI

from app.services.astrology_service import get_astrological_data
from app.services.numerology_service import get_numerology


def generate_skyai_prompt(user_data: dict) -> str:
    full_name      = user_data.get("full_name", "User")
    birth_date_raw = user_data.get("birth_date", "")
    birth_time     = user_data.get("birth_time", "")
    birth_city     = user_data.get("birth_city", "")
    birth_country  = user_data.get("birth_country", "")

    # ── 1. Data de nascimento ────────────────────────────────────────────────
    try:
        birth_date_obj = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
    except ValueError:
        birth_date_obj = datetime.strptime(birth_date_raw, "%d/%m/%Y").date()

    birth_date_iso = birth_date_obj.isoformat()
    display_date   = birth_date_obj.strftime("%m/%d/%Y")

    # ── 1.1 Data atual para referência dinâmica no forecast ──────────────────
    today = datetime.today()
    current_month = today.strftime("%B")
    current_year = today.strftime("%Y")
    current_date_text = f"{current_month} {current_year}"

    # ── 2. Astrologia ────────────────────────────────────────────────────────
    try:
        astro = get_astrological_data(
            birth_date_iso,
            birth_time,
            birth_city,
            birth_country,
        )
    except Exception as e:
        buf = io.StringIO()
        traceback.print_exc(file=buf)
        current_app.logger.error(f"[Astrology ERROR] {e}\n{buf.getvalue()}")
        raise RuntimeError("Falha ao calcular signos astrológicos; verifique logs.") from e

    if astro.get("error"):
        current_app.logger.error(f"[Astrology ERROR] {astro.get('error')}")
        raise RuntimeError("Falha ao calcular signos astrológicos; verifique logs.")

    # ── 3. Signos principais ────────────────────────────────────────────────
    positions = astro.get("positions", {})

    def fmt_sign(body_key: str, default="None") -> str:
        data = positions.get(body_key)
        return f"{data['sign']} ({data['degree']}°)" if data else default

    sun_sign  = fmt_sign("SUN")
    moon_sign = fmt_sign("MOON")
    asc_sign  = fmt_sign("ASC")

    # ── 4. Numerologia ──────────────────────────────────────────────────────
    nume = get_numerology(full_name, birth_date_iso)
    if nume.get("error"):
        current_app.logger.error(f"[Numerology ERROR] {nume.get('error')}")
        raise RuntimeError("Falha ao calcular numerologia; verifique logs.")

    # ── 5. Aspectos astrológicos ────────────────────────────────────────────
    aspects = astro.get("aspects", [])

    def find_aspect(b1: str, b2: str) -> str:
        for a in aspects:
            if ((a["body1"] == b1 and a["body2"] == b2) or
                (a["body1"] == b2 and a["body2"] == b1)):
                return f"{a['aspect']} (orb: {a['orb']}°, angle: {a['angle']}°)"
        return "No significant aspect"

    aspect_sun_moon = find_aspect("SUN", "MOON")
    aspect_moon_asc = find_aspect("MOON", "ASC")

    aspectos_detalhados = "\n".join(
        f"  - {a['body1']} {a['aspect']} {a['body2']} "
        f"(orb: {a['orb']}°, angle: {a['angle']}°)"
        for a in aspects
    )

    # ── 6. Prompt final para a IA ───────────────────────────────────────────
    preamble = (
        "Usa estos valores precomputados para todas las interpretaciones:\n"
        f"- Signo Solar: {sun_sign}\n"
        f"- Signo Lunar: {moon_sign}\n"
        f"- Ascendente: {asc_sign}\n"
        f"- Aspecto Sol–Luna: {aspect_sun_moon}\n"
        f"- Aspecto Luna–Ascendente: {aspect_moon_asc}\n"
        f"- Número de Camino de Vida: {nume['life_path']}\n"
        f"- Número de Anhelo del Alma: {nume['soul_urge']}\n"
        f"- Número de Expresión: {nume['expression']}\n"
        f"- Aspectos de la carta natal:\n{aspectos_detalhados}\n"
    )

    body = f"""
Eres SkyAI — un/a astrólogo(a) y numerólogo(a) de élite que escribe en **español claro y motivador**.

Genera un informe profundamente PERSONAL y accionable para {full_name},
nacido(a) el {display_date} a las {birth_time} en {birth_city}, {birth_country}.
Basar **todas** las interpretaciones **solo** en los valores precomputados de arriba.

• Las proyecciones deben incluir fechas **desde hoy en adelante** (hoy = {current_date_text}).  
• **No** incluyas referencias a años pasados.  
• Usa referencias mensuales o trimestrales: “octubre de 2025”, “T4 2025”, “inicios de 2026”.  
• Todo marco temporal debe ayudar a tomar decisiones reales.

💡 ESTILO  
• Lenguaje motivador, sin jerga complicada.  
• 2–4 párrafos cortos por sección, con una línea en blanco entre párrafos.  
• Cita grados/orbes entre paréntesis, p. ej.: “Sol ♓ 25° opuesto a Luna ♍ 28° (orbe 2°)”.  
• En las proyecciones, incluye rangos aproximados (“feb–mar 2026”).  
• Cierra **cada** sección con una frase imperativa y práctica (“Empieza…”, “Evita…”, “Registra…”).

📑 SECCIONES OBLIGATORIAS (usa **exactamente** estos títulos, cada uno empezando con `##`):
1. ## 🌞 Sol, 🌙 Luna y ⬆️ Ascendente  
2. ## 🩹 Temas Astrológicos Clave  
3. ## 🔢 Numerología Clave  
4. ## 💖 Relaciones y Emociones  
5. ## 🎯 Carrera y Propósito  
6. ## 🔮 Perspectiva a 12 Meses  
7. ## ✨ Plan de Acción de 30 Días — Tu Prescripción Cósmica Personal

Esta última sección es la más valiosa.  
Entrega un plan de 30 días con 2–4 acciones simples y poderosas.  
Frases breves, específicas y prácticas.  
Cada sugerencia en una línea nueva, tono imperativo.

Cierra con una línea inspiradora que recuerde al usuario su propio poder.

➡️ FORMATO DE SALIDA  
Devuelve **solo** un objeto JSON puro — sin bloques Markdown ni texto adicional.  
Dentro del campo "texto", ESCAPA cada salto de línea como `\\n`. Ejemplo:

{{
  "sun_sign": "Pisces",
  "moon_sign": "Virgo",
  "ascendant": "Aquarius",
  "life_path": "{nume['life_path']}",
  "soul_urge": "{nume['soul_urge']}",
  "expression": "{nume['expression']}",
  "texto": "## 🌞 Sol, 🌙 Luna y ⬆️ Ascendente\\n\
Tu Sol en Piscis...\\n\\n\
## 🩹 Temas Astrológicos Clave\\n\
..."
}}

❌ No añadas saludos, despedidas ni notas de proceso.  
✅ Entrega únicamente el JSON anterior.
"""

    return f"{preamble}\n{body}"


def generate_report_via_ai(user_data: dict) -> dict:
    try:
        prompt = generate_skyai_prompt(user_data)

        inst = current_app.instance_path
        os.makedirs(inst, exist_ok=True)
        log_path = os.path.join(inst, "prompt_log_skyai.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- {datetime.utcnow().isoformat()} Prompt ---\n")
            f.write(prompt)
            f.write("\n--- End Prompt ---\n")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")

        # Idioma configurável (default: es)
        LANG = os.getenv("REPORT_LANG", "es").lower()
        system_msg = (
            "Eres SkyAI, astrólogo(a) y numerólogo(a) profesional. "
            "RESPONDE SIEMPRE en español latino neutro, con tono claro, cálido y accionable. "
            "Si el usuario escribe en otro idioma, traduce y responde en español."
            if LANG.startswith("es")
            else "You are SkyAI, astrologer and numerologist. Always answer in the requested language."
        )

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.85,
            max_tokens=2200,
        )

        raw_output = response.choices[0].message.content.strip()

        # ── Registrar saída bruta ────────────────────────────────────────────
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("--- RAW OUTPUT ---\n")
            f.write(raw_output + "\n")
            f.write("--- End RAW ---\n")

        # ── Limpeza: remove cercas ``` e isola o JSON puro ───────────────────
        clean_output = re.sub(r"```(?:\w+)?\s*|```", "", raw_output).strip()

        if '"texto"' in clean_output:
            def _escape_block(match):
                body = match.group(2)
                body = body.replace('\\', '\\\\')   # escapa barras
                body = body.replace('"', r'\"')     # escapa aspas
                body = body.replace('\n', r'\n')    # escapa quebras de linha
                return f'{match.group(1)}{body}{match.group(3)}'

            clean_output = re.sub(
                r'("texto"\s*:\s*")([\s\S]*?)("(?=\s*[},]))',
                _escape_block,
                clean_output,
                flags=re.S
            )

        if not clean_output.lstrip().startswith("{"):
            start = clean_output.find("{")
            end = clean_output.rfind("}")
            if start != -1 and end != -1 and end > start:
                clean_output = clean_output[start: end + 1]

        result_text = clean_output

        # ── Parse JSON ───────────────────────────────────────────────────────
        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError:
            current_app.logger.warning("[AI WARNING] Response was not JSON. Saving raw text.")
            return {
                "erro": None,
                "texto": result_text,
                "sun_sign": None,
                "moon_sign": None,
                "ascendant": None,
                "life_path": None,
                "soul_urge": None,
                "expression": None,
            }

        # ── Correção para duplicação do plano 30 dias (EN/ES) ───────────────
        texto = parsed.get("texto", "") or ""
        if texto.count("30-Day Action Plan") > 1 or texto.count("Plan de Acción de 30 Días") > 1:
            partes = texto.split("## ")
            visto = False
            filtradas = []
            for parte in partes:
                if "30-Day Action Plan" in parte or "Plan de Acción de 30 Días" in parte:
                    if not visto:
                        filtradas.append(parte)
                        visto = True
                else:
                    filtradas.append(parte)
            texto = "## ".join(filtradas)

        return {
            "erro": None,
            "texto": texto,
            "sun_sign": parsed.get("sun_sign"),
            "moon_sign": parsed.get("moon_sign"),
            "ascendant": parsed.get("ascendant"),
            "life_path": parsed.get("life_path"),
            "soul_urge": parsed.get("soul_urge"),
            "expression": parsed.get("expression"),
        }

    except Exception as e:
        current_app.logger.error(f"[AI ERROR] {e}")
        return {
            "erro": str(e),
            "texto": "Lo sentimos, no pudimos generar el informe en este momento.",
            "sun_sign": None,
            "moon_sign": None,
            "ascendant": None,
            "life_path": None,
            "soul_urge": None,
            "expression": None,
        }
