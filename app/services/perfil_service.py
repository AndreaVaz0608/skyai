# app/services/perfil_service.py
"""
Geração de relatório Sky.AI com astrologia e numerologia.
Inclui logging do prompt e controle de erros.
"""
import os
import json
import re                # ← novo
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
You are SkyAI — an elite professional astrologer + numerologist writing in clear, engaging English.

Generate a deeply PERSONAL, actionable report for {full_name},
born on {display_date} at {birth_time} in {birth_city}, {birth_country}.
Base every insight ONLY on the pre-computed values above.

• Forecasts must include dates ONLY from the present onward (today = {current_date_text}).  
• DO NOT include any references to past years.  
• Dates should be monthly or quarterly, e.g., “October 2025”, “Q4 2025”, or “early 2026”.  
• All time references must be helpful and relevant to real decision-making.

💡 STYLE
• Motivating, jargon-free language.  
• 2–4 short paragraphs per section, blank line between paragraphs.  
• Quote aspect degrees/orbs in parentheses, e.g. “Sun ♓ 25° opposite Moon ♍ 28° (orb 2°)”.  
• Forecasts must include approximate dates (“Feb–Mar 2026”).  
• End each section with one imperative takeaway (“Start a 5-minute grounding routine…”).

📑 REQUIRED SECTIONS (use these titles **exactly**, each starting with `##`):
1. ## 🌞 Sun, 🌙 Moon & ⬆️ Ascendant  
2. ## 🩹 Core Astrological Themes  
3. ## 🔢 Key Numerology  
4. ## 💖 Relationships & Emotions  
5. ## 🎯 Career & Purpose  
6. ## 🔮 12-Month Outlook  
7. ## ✨ Exclusive 30-Day Action Plan — Your Personalized Cosmic Prescription

This is the most valuable section.  
Provide a clear, motivating 30-day roadmap with 2–4 simple, powerful actions.  
Use short sentences. Be specific and practical.  
Start each suggestion on a new line, and use imperative tone (e.g., “Start your day with...”, “Avoid...”, “Track...”)

Close this section with one inspiring line that reminds the user of their power.

This must be the most actionable and easy-to-remember part of the report.

➡️ OUTPUT FORMAT  
Return **only** a pure JSON object — no Markdown fences, no extra text.  
Inside the "texto" field, ESCAPE every line break as `\\n`. Example:

{{
  "sun_sign": "Pisces",
  "moon_sign": "Virgo",
  "ascendant": "Aquarius",
  "life_path": "{nume['life_path']}",
  "soul_urge": "{nume['soul_urge']}",
  "expression": "{nume['expression']}",
  "texto": "## 🌞 Sun, 🌙 Moon & ⬆️ Ascendant\\n\
Your Pisces Sun...\\n\\n\
## 🩹 Core Astrological Themes\\n\
..."
}}

❌ Do NOT add greetings, sign-offs, or process notes.
✅ Deliver only the JSON object above.
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

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are SkyAI, expert in astrology and numerology."},
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
        clean_output = re.sub(r"```(?:\\w+)?\s*|```", "", raw_output).strip()

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
                clean_output = clean_output[start : end + 1]

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

        # ── Correção para remover duplicação do plano 30 dias ────────────────
        texto = parsed.get("texto", "")
        if texto.count("30-Day Action Plan") > 1:
            partes = texto.split("## ")
            plano_visto = False
            partes_filtradas = []

            for parte in partes:
                if "30-Day Action Plan" in parte:
                    if not plano_visto:
                        partes_filtradas.append(parte)
                        plano_visto = True
                else:
                    partes_filtradas.append(parte)

            texto = "## ".join(partes_filtradas)

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
            "texto": "Sorry, couldn’t generate report at this time.",
            "sun_sign": None,
            "moon_sign": None,
            "ascendant": None,
            "life_path": None,
            "soul_urge": None,
            "expression": None,
        }
    