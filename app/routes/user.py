# ── IMPORTS ───────────────────────────────────────────────────────────
import os, json, threading, asyncio
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app, make_response
)
from sqlalchemy import func
from pyppeteer import launch

from app.main import db
from app.models import User, TestSession, GuruQuestion
from app.services.perfil_service import (
    generate_report_via_ai as generate_skyai_report_via_ai
)
from app.services.astrology_service import get_astrological_data
from app.services.numerology_service import get_numerology

# (opcional) import OpenAI somente dentro das funções que usam

# ── CONFIGURAÇÕES ──────────────────────────────────────────────────────
user_bp = Blueprint("user", __name__, template_folder="../templates")

# 🔹 Página para o usuário preencher seus dados astrais
@user_bp.route('/preencher-dados', methods=['GET', 'POST'])
def preencher_dados():
    if 'user_id' not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        user_id = session['user_id']

        # Captura e normaliza campos
        full_name = request.form.get('full_name', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        birth_time = request.form.get('birth_time', '').strip()
        birth_city = request.form.get('birth_city', '').strip()
        birth_country = request.form.get('birth_country', '').strip()

        # Validação
        missing_fields = []
        if not full_name: missing_fields.append("Full name")
        if not birth_date_str: missing_fields.append("Birth date")
        if not birth_time: missing_fields.append("Birth time")
        if not birth_city: missing_fields.append("City")
        if not birth_country: missing_fields.append("Country")

        if missing_fields:
            flash(f"Please complete the following fields: {', '.join(missing_fields)}.", "error")
            return render_template("user_data.html")

        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format. Please use the date picker.", "error")
            return render_template("user_data.html")

        try:
            test_session = TestSession(
                user_id=user_id,
                full_name=full_name,
                birth_date=birth_date,
                birth_time=birth_time,
                birth_city=birth_city,
                birth_country=birth_country
            )
            db.session.add(test_session)
            db.session.commit()
            session.modified = True

            return redirect(url_for('user.processando_relatorio', sessao_id=test_session.id))

        except Exception as e:
            current_app.logger.error(f"[USER DATA ERROR] Failed to save test session: {e}")
            db.session.rollback()
            flash("Something went wrong while saving your data. Please try again.", "danger")
            return render_template("user_data.html")

    return render_template('user_data.html')

# 🔹 Página de carregamento enquanto gera o relatório
@user_bp.route('/processando-relatorio')
def processando_relatorio():
    if 'user_id' not in session:
        flash("Please log in to view your report.", "error")
        return redirect(url_for('auth_views.login_view'))

    sessao_id = request.args.get('sessao_id')

    threading.Thread(target=gerar_relatorio_background, args=(current_app._get_current_object(), sessao_id)).start()

    return render_template("carregando.html", sessao_id=sessao_id)

# 🔹 Função de geração do relatório em background
def gerar_relatorio_background(app, sessao_id):
    with app.app_context():
        try:
            sessao = TestSession.query.get(sessao_id)
            if not sessao:
                current_app.logger.error(f"[BACKGROUND] Sessão {sessao_id} não encontrada.")
                return

            dados = {
                "full_name": sessao.full_name,
                "birth_date": sessao.birth_date.strftime("%Y-%m-%d"),
                "birth_time": sessao.birth_time,
                "birth_city": sessao.birth_city,
                "birth_country": sessao.birth_country,
            }

            current_app.logger.info(f"[BACKGROUND] Gerando relatório para sessão {sessao_id}")
            resultado = generate_skyai_report_via_ai(dados)

            # Se a IA indicou erro ➜ aborta
            if resultado.get("erro"):
                current_app.logger.error(f"[AI ❌] {resultado['erro']}")
                return

            # Grava somente se o JSON está completo (sun_sign presente)
            if resultado.get("sun_sign"):
                sessao.ai_result  = json.dumps(resultado, ensure_ascii=False)
                sessao.sun_sign   = resultado["sun_sign"]
                sessao.moon_sign  = resultado["moon_sign"]
                sessao.ascendant  = resultado["ascendant"]
                sessao.life_path  = resultado["life_path"]
                sessao.soul_urge  = resultado["soul_urge"]
                sessao.expression = resultado["expression"]
                db.session.commit()
                current_app.logger.info(f"[AI ✅] Relatório salvo – sessão {sessao_id}")
            else:
                # JSON inválido ➜ não salva; mantém sessão sem resultado
                current_app.logger.warning(f"[AI ⚠️] JSON inválido; relatório ignorado.")
                db.session.rollback()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"[BACKGROUND EXCEPTION] {e}")


# 🔹 Tela para visualizar o relatório
@user_bp.route("/relatorio")
def gerar_relatorio():

    # ─── Permissão ──────────────────────────────────────────────────────
    if "user_id" not in session:
        flash("Please log in to view the report.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id   = session["user_id"]
    user_name = session.get("user_name", "User")
    sessao_id = request.args.get("sessao_id")

    # ─── Recupera a sessão escolhida (ou a mais recente) ────────────────
    sessao = (
        TestSession.query.filter_by(id=sessao_id, user_id=user_id).first()
        if sessao_id
        else TestSession.query.filter_by(user_id=user_id)
                              .order_by(TestSession.created_at.desc())
                              .first()
    )

    if not sessao:
        flash("No session found.", "warning")
        return redirect(url_for("user.preencher_dados"))

    # Ainda não terminou
    if not sessao.ai_result:
        flash("Report generation is still in progress.", "warning")
        return redirect(url_for("user.processando_relatorio", sessao_id=sessao.id))

    # ─── Converte/normaliza o campo ai_result ───────────────────────────
    if isinstance(sessao.ai_result, str):
        try:
            ai_data = json.loads(sessao.ai_result)            # JSON válido
        except Exception as e:
            current_app.logger.error(f"[RELATORIO JSON ERROR] {e}")
            ai_data = {}                                      # texto bruto
    elif isinstance(sessao.ai_result, dict):
        ai_data = sessao.ai_result                            # já é dict
    else:
        ai_data = {}

    # Se não veio JSON OU não há texto ⇒ exibe página “bruta”
    if not ai_data.get("texto"):
        texto_fallback = (
            sessao.ai_result
            if isinstance(sessao.ai_result, str)
            else json.dumps(sessao.ai_result, ensure_ascii=False, indent=2)
        )
        return render_template(
            "relatorio_bruto.html",
            nome   = user_name,
            texto  = texto_fallback,
            sessao_id = sessao.id,
        )

    # ─── Monta dicionário final para o template bonito ──────────────────
    resultado_dict = {
        "nome"        : sessao.full_name,
        "birth_date"  : sessao.birth_date.strftime("%d/%m/%Y") if sessao.birth_date else None,
        "birth_time"  : sessao.birth_time,
        "birth_city"  : sessao.birth_city,
        "birth_country": sessao.birth_country,
        "sun_sign"    : ai_data.get("sun_sign",   sessao.sun_sign),
        "moon_sign"   : ai_data.get("moon_sign",  sessao.moon_sign),
        "ascendant"   : ai_data.get("ascendant",  sessao.ascendant),
        "life_path"   : ai_data.get("life_path",  sessao.life_path),
        "soul_urge"   : ai_data.get("soul_urge",  sessao.soul_urge),
        "expression"  : ai_data.get("expression", sessao.expression),
        "texto"       : ai_data.get("texto"),
    }

    # ─── Renderiza a versão formatada ───────────────────────────────────
    return render_template(
        "relatorio.html",
        nome      = user_name,
        resultado = resultado_dict,
        sessao_id = sessao.id,
    )

# ---------------------------------------------------------------------------
# 🔹 Exporta o relatório como PDF — gerado diretamente do HTML via Pyppeteer
# ---------------------------------------------------------------------------
import asyncio
from pyppeteer import launch

# ---------------------------------------------------------------------------
# 🔹 Helper — HTML → PDF (Pyppeteer 2.x)
# ---------------------------------------------------------------------------
async def html_to_pdf_bytes(html: str) -> bytes:
    """Converte HTML em bytes PDF usando Chromium headless (A4, sem margens)."""
    browser = await launch(
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        headless=True,
    )
    page = await browser.newPage()

    # injeta o HTML
    await page.setContent(html)

    # pausa simples p/ assets carregarem
    await asyncio.sleep(0.5)   # 0,5 s

    pdf_bytes = await page.pdf(
        format="A4",
        printBackground=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )
    await browser.close()
    return pdf_bytes

# ---------------------------------------------------------------------------
# 🔹 Rota — /relatorio/pdf (mantém o restante igual)
# ---------------------------------------------------------------------------
@user_bp.route("/relatorio/pdf")
def relatorio_pdf():
    if "user_id" not in session:
        flash("You must be logged in to download the PDF.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id   = session["user_id"]
    sessao_id = request.args.get("sessao_id")

    sessao = (
        TestSession.query.filter_by(id=sessao_id, user_id=user_id).first()
        if sessao_id else
        TestSession.query.filter_by(user_id=user_id)
                         .order_by(TestSession.created_at.desc())
                         .first()
    )
    if not sessao:
        flash("No session found to generate the PDF.", "warning")
        return redirect(url_for("user.preencher_dados"))

    if not sessao.ai_result:
        flash("Report is still being generated.", "warning")
        return redirect(url_for("user.processando_relatorio", sessao_id=sessao.id))

    # constrói o dicionário e renderiza o HTML exatamente como antes ...
    ai_data = json.loads(sessao.ai_result) if isinstance(sessao.ai_result, str) else sessao.ai_result
    resultado_dict = {
        "nome": sessao.full_name,
        "birth_date": sessao.birth_date.strftime("%d/%m/%Y") if sessao.birth_date else None,
        "birth_time": sessao.birth_time,
        "birth_city": sessao.birth_city,
        "birth_country": sessao.birth_country,
        "sun_sign":   ai_data.get("sun_sign",   sessao.sun_sign),
        "moon_sign":  ai_data.get("moon_sign",  sessao.moon_sign),
        "ascendant":  ai_data.get("ascendant",  sessao.ascendant),
        "life_path":  ai_data.get("life_path",  sessao.life_path),
        "soul_urge":  ai_data.get("soul_urge",  sessao.soul_urge),
        "expression": ai_data.get("expression", sessao.expression),
        "texto":      ai_data.get("texto"),
    }

    html = render_template(
        "relatorio.html",
        nome=session.get("user_name", "User"),
        resultado=resultado_dict,
        sessao_id=sessao.id,
    )

    try:
        pdf_bytes = asyncio.run(html_to_pdf_bytes(html))
    except Exception as e:
        current_app.logger.error(f"[PDF GENERATION ERROR] {e}")
        flash("Error generating PDF. Please try later.", "danger")
        return redirect(url_for("user.gerar_relatorio", sessao_id=sessao.id))

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=skyai_report_{sessao.id}.pdf"
    )
    return response

    # ─── Constrói o MESMO dicionário usado na tela bonita ────────────────────
    ai_data = json.loads(sessao.ai_result) if isinstance(sessao.ai_result, str) else sessao.ai_result

    resultado_dict = {
        "nome"        : sessao.full_name,
        "birth_date"  : sessao.birth_date.strftime("%d/%m/%Y") if sessao.birth_date else None,
        "birth_time"  : sessao.birth_time,
        "birth_city"  : sessao.birth_city,
        "birth_country": sessao.birth_country,
        "sun_sign"    : ai_data.get("sun_sign",   sessao.sun_sign),
        "moon_sign"   : ai_data.get("moon_sign",  sessao.moon_sign),
        "ascendant"   : ai_data.get("ascendant",  sessao.ascendant),
        "life_path"   : ai_data.get("life_path",  sessao.life_path),
        "soul_urge"   : ai_data.get("soul_urge",  sessao.soul_urge),
        "expression"  : ai_data.get("expression", sessao.expression),
        "texto"       : ai_data.get("texto"),
    }

    # ─── Renderiza o HTML em string e converte em PDF ─────────────────────────
    html = render_template(
        "relatorio.html",
        nome=session.get("user_name", "User"),
        resultado=resultado_dict,
        sessao_id=sessao.id,
    )

    try:
        pdf_bytes = asyncio.run(html_to_pdf_bytes(html))
    except Exception as e:
        current_app.logger.error(f"[PDF GENERATION ERROR] {e}")
        flash("Error generating PDF. Please try later.", "danger")
        return redirect(url_for("user.gerar_relatorio", sessao_id=sessao.id))

    # ─── Resposta: devolve o arquivo ao usuário ───────────────────────────────
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=skyai_report_{sessao.id}.pdf"
    return response

@user_bp.route('/select-product', methods=['GET', 'POST'])
def select_product():
    if 'user_id' not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        selected_plan = request.form.get('plan')
        if selected_plan:
            user = User.query.get(session['user_id'])
            user.plan = selected_plan
            db.session.commit()
            session['user_plan'] = selected_plan

            flash(f"You selected the {selected_plan} plan!", "success")
            return redirect(url_for('user.preencher_dados'))
        else:
            flash("No plan selected.", "warning")

    return render_template('products.html')

@user_bp.route('/compatibility', methods=['GET', 'POST'])
def compatibility():
    if 'user_id' not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        name_1 = request.form.get("name_1", "").strip()
        birth_1 = request.form.get("birth_1", "").strip()
        birth_time_1 = request.form.get("birth_time_1", "").strip()
        birth_city_1 = request.form.get("birth_city_1", "").strip()
        birth_country_1 = request.form.get("birth_country_1", "").strip()

        name_2 = request.form.get("name_2", "").strip()
        birth_2 = request.form.get("birth_2", "").strip()
        birth_time_2 = request.form.get("birth_time_2", "").strip()
        birth_city_2 = request.form.get("birth_city_2", "").strip()
        birth_country_2 = request.form.get("birth_country_2", "").strip()

        if not all([
            name_1, birth_1, birth_time_1, birth_city_1, birth_country_1,
            name_2, birth_2, birth_time_2, birth_city_2, birth_country_2
        ]):
            flash("Please fill in all fields for both people.", "warning")
            return render_template("compatibility.html")

        try:
            # 🔹 Importa serviços reais para garantir precisão
            from app.services.astrology_service import get_astrological_data
            from app.services.numerology_service import get_numerology

            # 🔹 Cálculo real — Pessoa 1
            astro_1 = get_astrological_signs(birth_1, birth_time_1, birth_city_1, birth_country_1)
            num_1 = get_numerology(name_1, birth_1)

            # 🔹 Cálculo real — Pessoa 2
            astro_2 = get_astrological_signs(birth_2, birth_time_2, birth_city_2, birth_country_2)
            num_2 = get_numerology(name_2, birth_2)

            # 🔹 Prompt blindado com dados reais
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            client = OpenAI(api_key=api_key)

            prompt = f"""
You are **Guru SkyAI**, a world-class expert in relationship compatibility, modern astrology, and Pythagorean numerology.

Your mission is to produce a **premium, clear, deeply insightful** compatibility report for two people.  
Your analysis must feel like it was crafted by a high-level human advisor: **logical, honest, practical and free of generic clichés**.  
No poetic fluff, no vague metaphors, no spiritual mysticism — just concrete, human language and empathetic but **realistic** insights.

---

## 🌍 REAL DATA (DO NOT CHANGE, DO NOT GUESS)

👤 **Person 1**:
- Full Name: {{name_1}}
- Sun Sign: {{sun_1}}  _(from Swiss Ephemeris)_
- Moon Sign: {{moon_1}}
- Ascendant: {{asc_1}}
- Life Path: {{life_1}}  _(Pythagorean)_
- Soul Urge: {{soul_1}}
- Expression: {{expression_1}}

👤 **Person 2**:
- Full Name: {{name_2}}
- Sun Sign: {{sun_2}}
- Moon Sign: {{moon_2}}
- Ascendant: {{asc_2}}
- Life Path: {{life_2}}
- Soul Urge: {{soul_2}}
- Expression: {{expression_2}}

> ⚠️ These facts are **FINAL**. You must NOT recalculate or deduce new signs or numbers. You must not reinterpret them. Use exactly what is provided.

---

## 🪐 **STRUCTURE**

Your premium report must include **5 clear, numbered sections**:

1️⃣ **Compatibility Level**  
Rate the overall compatibility as **High, Medium, or Low**, with 1–2 sentences explaining why.

2️⃣ **Astrological Alignment**  
Analyze the dynamics between their **Sun, Moon, and Ascendant signs**:
   - What works naturally?
   - What conflicts may appear?
   - What is unique about this pair?

3️⃣ **Numerology Match**  
Discuss how their **Life Path, Soul Urge, and Expression numbers** interact:
   - Do the numbers reinforce each other or create tension?
   - How do their values and life goals align?

4️⃣ **Emotional Dynamics**  
Describe the emotional and communication style:
   - How do they express affection?
   - Where can misunderstandings arise?
   - What emotional needs must be respected?

5️⃣ **Practical Advice & Final Reflection**  
Offer concrete, realistic advice:
   - What should each person be mindful of?
   - What are the relationship’s greatest strengths?
   - When might they need to reconsider or adjust course?

---

## 📝 **TONE & STYLE**

- Use clear, warm, respectful language — never cold or robotic.
- Speak as if you were a trusted human advisor with real-life experience.
- Avoid generic phrases like “you may feel” — be direct and credible.
- Keep the text easy to read, with short paragraphs and lists where helpful.
- No process explanations. Deliver the final analysis only.

---

## 🚫 **ABSOLUTE RULES**

✅ Only use the provided signs and numbers.  
✅ Do not recalculate.  
✅ Do not add or hallucinate extra birth details.  
✅ No mysticism, no poetic fluff.  
✅ Always close with a short, encouraging final insight.

"""

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are Guru SkyAI, master of compatibility."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.85,
                max_tokens=1300
            )

            result_text = response.choices[0].message.content.strip()

            return render_template(
                "compatibility_result.html",
                result=result_text,
                name_1=name_1,
                name_2=name_2
            )

        except Exception as e:
            current_app.logger.error(f"[COMPATIBILITY ERROR] {e}")
            flash("Sorry, we couldn't generate your compatibility reading right now.", "danger")
            return render_template("compatibility.html")

    return render_template("compatibility.html")

@user_bp.route('/ask-guru', methods=['POST'])
def ask_guru():
    if "user_id" not in session:
        flash("Please log in to ask Guru SkyAI.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id  = session["user_id"]
    question = request.form.get("question", "").strip()

    if len(question) < 5:
        flash("Please enter a valid question.", "warning")
        return redirect(url_for("auth_views.dashboard"))

    # ▸ 1. pega a última sessão com resultado válido
    last_session = (TestSession.query
                    .filter_by(user_id=user_id)
                    .filter(TestSession.ai_result.isnot(None))
                    .order_by(TestSession.created_at.desc())
                    .first())

    if not last_session:
        flash("Generate an astral map first so the Guru can give you a personalised answer.", "info")
        return redirect(url_for("user.preencher_dados"))

    # ▸ 2. extrai dados essenciais
    data = json.loads(last_session.ai_result) if isinstance(last_session.ai_result, str) else last_session.ai_result
    sun  = data.get("sun_sign",   "unknown")
    moon = data.get("moon_sign",  "unknown")
    asc  = data.get("ascendant",  "unknown")
    life = data.get("life_path",  "unknown")
    soul = data.get("soul_urge",  "unknown")
    expr = data.get("expression", "unknown")

    # ▸ 3. monta prompt com contexto
    prompt = f"""
You are Guru SkyAI, an objective advisor who uses the client's own natal chart
and numerology to give specific guidance – no mysticism or metaphors.

User QUESTION:
\"\"\"{question}\"\"\"

User CONTEXT:
- Sun sign: {sun}
- Moon sign: {moon}
- Ascendant: {asc}
- Life-Path number: {life}
- Soul-Urge number: {soul}
- Expression number: {expr}

RULES:
• Be clear, practical and direct.
• Reference only the info above (do not create data).
• Conclude with a concrete recommendation.
"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Guru SkyAI, the clear and practical cosmic advisor."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.65,
            max_tokens=700
        )

        answer = response.choices[0].message.content.strip()

        # ▸ 4. salvar pergunta + resposta
        new_q = GuruQuestion(user_id=user_id, question=question, answer=answer)
        db.session.add(new_q)
        db.session.commit()

        flash("✨ Guru SkyAI has answered your question. See the response below in your dashboard!", "success")

    except Exception as e:
        current_app.logger.error(f"[GURU SKY ERROR] {e}")
        flash("Sorry, Guru SkyAI couldn't answer your question right now.", "danger")

    return redirect(url_for("auth_views.dashboard"))

@user_bp.route("/")
def home():
    if 'user_id' in session:
        return redirect(url_for('user.preencher_dados'))
    else:
        return redirect('/login')  # <- substitui o url_for aqui
