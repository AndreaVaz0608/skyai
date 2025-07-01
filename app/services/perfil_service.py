# app/services/perfil_service.py
"""
Geração de relatório Sky.AI com astrologia e numerologia.
Inclui logging do prompt e controle de erros.
"""
import os
import json
from datetime import datetime
import io
import traceback
from flask import current_app
from openai import OpenAI
from app.services.astrology_service import get_astrological_data
from app.services.numerology_service import get_numerology

def generate_skyai_prompt(user_data: dict) -> str:
    full_name     = user_data.get("full_name", "User")
    birth_date_raw = user_data.get("birth_date", "")
    birth_time     = user_data.get("birth_time", "")
    birth_city     = user_data.get("birth_city", "")
    birth_country  = user_data.get("birth_country", "")

    # ── 1. Data de nascimento em ISO e formato de exibição ───────────────────────
    try:
        birth_date_obj = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
    except ValueError:
        birth_date_obj = datetime.strptime(birth_date_raw, "%d/%m/%Y").date()

    birth_date_iso = birth_date_obj.isoformat()
    display_date   = birth_date_obj.strftime("%m/%d/%Y")

    # ── 2. Astrologia – captura robusta de exceções ──────────────────────────────
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
        raise RuntimeError(
            "Falha ao calcular signos astrológicos; verifique logs."
        ) from e

    if astro.get("error"):
        current_app.logger.error(f"[Astrology ERROR] {astro.get('error')}")
        raise RuntimeError("Falha ao calcular signos astrológicos; verifique logs.")

    # ── 3. Signos principais ─────────────────────────────────────────────────────
    positions = astro.get("positions", {})

    def fmt_sign(body_key: str, default="None") -> str:
        data = positions.get(body_key)
        return f"{data['sign']} ({data['degree']}°)" if data else default

    sun_sign = fmt_sign("SUN")
    moon_sign = fmt_sign("MOON")
    asc_sign  = fmt_sign("ASC")

    # ── 4. Numerologia ───────────────────────────────────────────────────────────
    nume = get_numerology(full_name, birth_date_iso)
    if nume.get("error"):
        current_app.logger.error(f"[Numerology ERROR] {nume.get('error')}")
        raise RuntimeError("Falha ao calcular numerologia; verifique logs.")

    # ── 5. Aspectos astrológicos ─────────────────────────────────────────────────
    aspects = astro.get("aspects", [])

    def find_aspect(b1: str, b2: str) -> str:
        for a in aspects:
            if (
                (a["body1"] == b1 and a["body2"] == b2)
                or (a["body1"] == b2 and a["body2"] == b1)
            ):
                return f"{a['aspect']} (orb: {a['orb']}°, angle: {a['angle']}°)"
        return "No significant aspect"

    aspect_sun_moon = find_aspect("SUN", "MOON")
    aspect_moon_asc = find_aspect("MOON", "ASC")

    aspectos_detalhados = "\n".join(
        [
            f"  - {a['body1']} {a['aspect']} {a['body2']} (orb: {a['orb']}°, angle: {a['angle']}°)"
            for a in aspects
        ]
    )

    # ── 6. Prompt final para a IA ────────────────────────────────────────────────
    preamble = (
        "Use these precomputed values for all interpretations:\n"
        f"- Solar Sign: {sun_sign}\n"
        f"- Lunar Sign: {moon_sign}\n"
        f"- Ascendant: {asc_sign}\n"
        f"- Aspect Sun–Moon: {aspect_sun_moon}\n"
        f"- Aspect Moon–Ascendant: {aspect_moon_asc}\n"
        f"- Life Path Number: {nume['life_path']}\n"
        f"- Soul Urge Number: {nume['soul_urge']}\n"
        f"- Expression Number: {nume['expression']}\n"
        f"- Natal Chart Aspects:\n{aspectos_detalhados}\n"
    )

    body = f"""
You are the best expert astrologer and numerologist AI. Generate a deeply personalized, professional, and inspiring Astral and Numerological Report for {full_name}, born on {display_date} at {birth_time} in {birth_city}, {birth_country}. Ensure overall assertiveness ≥ 98% by grounding all interpretations in the precomputed values above.

Include the following sections, each with its emoji-enhanced title:

🌟 Full Name: {full_name}
🗅️ Date of Birth: {display_date}
🕰️ Time of Birth: {birth_time}
🌍 City of Birth: {birth_city}
🌎 Country of Birth: {birth_country}

The report must include:

1. 🌞 Solar Sign, 🌙 Lunar Sign, and ⬆️ Ascendant Sign interpretation (Triad of Personality).
2. 🩹 General Astrological Overview  
   - Major personality strengths & shadow challenges, based on key natal aspects (e.g., Sun–Moon, Moon–Ascendant, ruler transits).

3. 🔢 Numerological Analysis  
   - Life Path Number ({nume['life_path']}): life purpose themes.  
   - Soul Urge Number ({nume['soul_urge']}): inner motivations.  
   - Expression Number ({nume['expression']}): talents and outward expression.

4. 💖 Relationship & Emotional Profile  
   - Attachment style, compatibility patterns, Venus–Mars aspects.

5. 🎯 Career & Purpose Guidance  
   - Ideal vocations, timing windows (Saturn returns, Jupiter transits), vocational strengths.

6. 🔮 12-Month Forecast  
   - Upcoming planetary transits (e.g., Jupiter, Saturn, Uranus), major numerological cycles, concrete trend highlights.

7. ✨ Practical Growth Tips  
   - Actionable rituals, timing suggestions (lunar phases), personalized affirmations.

📜 Style Requirements:  
- Use concise, motivating, jargon-free language.  
- Cite ephemeris degrees and numerology formula references in parentheses.  
- Make each section feel uniquely tailored to {full_name}.  
- ONLY deliver the final report—no meta-commentary or process explanation.

🖚 OUTPUT FORMAT  
You must return a JSON object with this structure (no markdown or explanation):

{{
  "sun_sign": "<your parsed sun_sign>",
  "moon_sign": "<your parsed moon_sign>",
  "ascendant": "<your parsed ascendant>",
  "life_path": "<your parsed life_path>",
  "soul_urge": "<your parsed soul_urge>",
  "expression": "<your parsed expression>",
  "texto": "<Markdown formatted full report using ## section headings.>"
}}
"""

    return f"{preamble}\n{body}"

def generate_report_via_ai(user_data: dict) -> dict:
    try:
        prompt = generate_skyai_prompt(user_data)

        inst = current_app.instance_path
        os.makedirs(inst, exist_ok=True)
        log_path = os.path.join(inst, 'prompt_log_skyai.txt')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n--- {datetime.utcnow().isoformat()} Prompt ---\n")
            f.write(prompt)
            f.write("\n--- End Prompt ---\n")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are SkyAI, expert in astrology and numerology."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=2200,
        )

        raw_output = response.choices[0].message.content.strip()
        result_text = raw_output.replace("```json", "").replace("```", "").strip()

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

        return {
            "erro": None,
            "texto": parsed.get("texto", ""),
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
            "texto": "Sorry, couldn’t generate report at this time.",
            "sun_sign": None,
            "moon_sign": None,
            "ascendant": None,
            "life_path": None,
            "soul_urge": None,
            "expression": None,
        }
