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

    try:
        birth_date_obj = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
    except ValueError:
        birth_date_obj = datetime.strptime(birth_date_raw, "%d/%m/%Y").date()

    birth_date_iso = birth_date_obj.isoformat()
    display_date   = birth_date_obj.strftime("%m/%d/%Y")

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

    positions = astro.get("positions", {})

    def fmt_sign(body_key: str, default="None") -> str:
        data = positions.get(body_key)
        return f"{data['sign']} ({data['degree']}°)" if data else default

    sun_sign = fmt_sign("SUN")
    moon_sign = fmt_sign("MOON")
    asc_sign  = fmt_sign("ASC")

    nume = get_numerology(full_name, birth_date_iso)
    if nume.get("error"):
        current_app.logger.error(f"[Numerology ERROR] {nume.get('error')}")
        raise RuntimeError("Falha ao calcular numerologia; verifique logs.")

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
You are the best expert astrologer and numerologist AI ever created. Generate a deeply personalized, professional, warm, and inspiring Astral and Numerological Report for {full_name}, born on {display_date} at {birth_time} in {birth_city}, {birth_country}.  
Ground all interpretations in the validated birth chart and numerological values provided above. Ensure all insights are realistic, practical, and highly assertive (≥ 98% accuracy).  

📜 **Output Rules:**  
- DO NOT include any markdown code blocks or extra explanations.  
- Your entire response must be a single, valid JSON object only — no commentary, no extra text.  
- Format: exactly this → {{
  "sun_sign": "...",
  "moon_sign": "...",
  "ascendant": "...",
  "life_path": "...",
  "soul_urge": "...",
  "expression": "...",
  "texto": "... full report ..."
}}

Inside "texto", deliver a clear, structured narrative covering:
1. 🌞 **Solar Sign**, 🌙 **Lunar Sign**, ⬆️ **Ascendant Sign** — deep but clear explanations.
2. 🩹 **General Astrological Overview** — connect signs to personality and life flow.
3. 🔢 **Numerological Analysis** — life path, soul urge, expression number and how they interact with the chart.
4. 💖 **Relationship & Emotional Profile** — insights on how this person loves, connects, and grows.
5. 🎯 **Career & Purpose Guidance** — practical guidance for aligning actions with essence.
6. 🔮 **12-Month Forecast** — key themes, opportunities, and what to watch out for.
7. ✨ **Practical Growth Tips** — actionable suggestions to align daily life with cosmic guidance.

📚 **Style:**  
Keep language inspiring yet down-to-earth, warm and supportive, motivating the user to live in alignment with their truest self. Always use clear, modern language — avoid clichés.  

Return **JSON only** — no additional commentary.
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
                {"role": "system", "content": "You are SkyAI, expert in astrology and numerology. You must return ONLY pure JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=2200,
        )

        raw_output = response.choices[0].message.content.strip()

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write("--- RAW OUTPUT ---\n")
            f.write(raw_output + "\n")
            f.write("--- End RAW ---\n")

        # Força limpeza de blocos de código se vier errado
        result_text = raw_output.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError:
            current_app.logger.warning("[AI WARNING] Response was not JSON. Saving raw text.")
            return {
                "erro": "IA returned invalid JSON",
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

