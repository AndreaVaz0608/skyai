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
from app.services.astrology_service import get_astrological_signs
from app.services.numerology_service import get_numerology
from app.models import Payment

import re

current_year = datetime.utcnow().year       # ← defina ANTES do prompt

# (opcional) import OpenAI somente dentro das funções que usam

# ── CONFIGURAÇÕES ──────────────────────────────────────────────────────
user_bp = Blueprint("user", __name__, template_folder="../templates")

# 🔹 Página para o usuário preencher seus dados astrais
@user_bp.route('/preencher-dados', methods=['GET', 'POST'])
def preencher_dados():
    if 'user_id' not in session:
        flash("Inicia sesión para continuar.", "error")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        user_id = session['user_id']

        # 🔍 Captura e normaliza campos
        full_name = request.form.get('full_name', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        birth_time = request.form.get('birth_time', '').strip()
        birth_city = request.form.get('birth_city', '').strip()
        birth_country = request.form.get('birth_country', '').strip()

        # ✅ Validação básica
        missing_fields = []
        if not full_name: missing_fields.append("Full name")
        if not birth_date_str: missing_fields.append("Birth date")
        if not birth_time: missing_fields.append("Birth time")
        if not birth_city: missing_fields.append("City")
        if not birth_country: missing_fields.append("Country")

        if missing_fields:
            flash(f"Por favor completa los siguientes campos: {', '.join(missing_fields)}.", "error")
            return render_template("user_data.html")

        # 💾 Guarda dados na sessão para uso após pagamento
        session['pending_data'] = {
            'user_id': user_id,
            'full_name': full_name,
            'birth_date': birth_date_str,
            'birth_time': birth_time,
            'birth_city': birth_city,
            'birth_country': birth_country
        }
        session.modified = True

        current_app.logger.info(
            f"[PRENCHER_DADOS] User {user_id} data saved to session. Redirecting to Stripe..."
        )

        # 🔗 Redireciona para o checkout Stripe (link fixo do produto)
        return redirect("https://buy.stripe.com/bJefZg96w76eaLn0zj5AQ09")

    # 👉 Renderiza formulário caso GET
    return render_template('user_data.html')

@user_bp.route("/processando-relatorio")
def processando_relatorio():
    # ─── Segurança ────────────────────────────────────────────────
    if "user_id" not in session:
        flash("Inicia sesión para ver tu informe.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id           = session["user_id"]
    sessao_id_param   = request.args.get("sessao_id")
    pago              = request.args.get("paid") == "true"
    stripe_session_id = request.args.get("session_id")

    pending = session.get("pending_data")

    # ------------------------------------------------------------------
    # CENÁRIO A · Já existe sessão criada (refresh/polling)
    # ------------------------------------------------------------------
    if not pending and sessao_id_param:
        sessao = TestSession.query.filter_by(id=sessao_id_param, user_id=user_id).first()

        if not sessao:
            flash("Sesión no encontrada.", "warning")
            return redirect(url_for("auth_views.dashboard"))

        # Ainda processando → permanece na tela de loading
        if sessao.ai_result is None:
            return render_template(
                "carregando.html",
                sessao_id=sessao.id,
                pago=pago,
            )

        # Já pronto → vai direto ao relatório
        return redirect(url_for("user.gerar_relatorio", sessao_id=sessao.id))

    # ------------------------------------------------------------------
    # CENÁRIO B · Primeira chamada após pagamento (pending_data presente)
    # ------------------------------------------------------------------
    if not pending:
        # Sem dados pendentes e sem sessao_id ⇒ fallback seguro
        return redirect(url_for("auth_views.dashboard"))

    try:
        # 1️⃣ Confirma pagamento  (mantém igual ao seu código)
        if pago:
            pay_q = Payment.query
            if stripe_session_id:
                pay_q = pay_q.filter_by(stripe_session_id=stripe_session_id)
            else:
                pay_q = pay_q.filter_by(user_id=user_id)

            payment = pay_q.first()
            if not payment:
                flash("El pago aún no se ha confirmado. Espera unos segundos y actualiza.", "warning")
                return render_template("carregando.html", sessao_id=None, pago=False)

        # 2️⃣ Cria TestSession apenas uma vez
        new_sessao = TestSession(
            user_id       = user_id,
            full_name     = pending["full_name"],
            birth_date    = pending["birth_date"],
            birth_time    = pending["birth_time"],
            birth_city    = pending["birth_city"],
            birth_country = pending["birth_country"],
        )
        db.session.add(new_sessao)
        db.session.commit()

        # Limpa dados pendentes
        session.pop("pending_data", None)
        session.modified = True

        # 3️⃣ Dispara geração em background
        threading.Thread(
            target=gerar_relatorio_background,
            args=(current_app._get_current_object(), new_sessao.id),
            daemon=True,
        ).start()

        return render_template(
            "carregando.html",
            sessao_id=new_sessao.id,
            pago=pago,
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[PROCESSANDO ERROR] {e}")
        flash("Error inesperado al generar tu informe. Inténtalo de nuevo.", "danger")
        return redirect(url_for("auth_views.dashboard"))

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
        flash("Inicia sesión para ver el informe.", "error")
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
        flash("No se encontró ninguna sesión.", "warning")
        return redirect(url_for("user.preencher_dados"))

    # Relatório ainda não finalizado?
    if not sessao.ai_result:
        flash("La generación del informe aún está en curso.", "warning")
        return redirect(url_for("user.processando_relatorio", sessao_id=sessao.id))

    # ─── Converte/normaliza o campo ai_result ───────────────────────────
    if isinstance(sessao.ai_result, str):
        try:
            ai_data = json.loads(sessao.ai_result)  # JSON válido
        except Exception as e:
            current_app.logger.error(f"[RELATORIO JSON ERROR] {e}")
            ai_data = {}                            # texto bruto
    elif isinstance(sessao.ai_result, dict):
        ai_data = sessao.ai_result                  # já é dict
    else:
        ai_data = {}

    # 🔹 Limpeza das quebras de linha escapadas
    if isinstance(ai_data.get("texto"), str):
        # converte \n, \\n, \\\\n … em quebras reais
        ai_data["texto"] = re.sub(r'(?:\\)+n', '\n', ai_data["texto"])

    # ─── Fallback: se continuamos SEM texto estruturado ────────────────
    if not ai_data.get("texto"):
        texto_fallback = (
            sessao.ai_result
            if isinstance(sessao.ai_result, str)
            else json.dumps(sessao.ai_result, ensure_ascii=False, indent=2)
        )
        return render_template(
            "relatorio_bruto.html",
            nome=user_name,
            texto=texto_fallback,
            sessao_id=sessao.id,
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
        nome=user_name,
        resultado=resultado_dict,
        sessao_id=sessao.id,
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
# 🔹 Rota — /relatorio/pdf  (gera PDF com o MESMO conteúdo já tratado)
# ---------------------------------------------------------------------------
@user_bp.route("/relatorio/pdf")
def relatorio_pdf():
    if "user_id" not in session:
        flash("Debes iniciar sesión para descargar el PDF.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id   = session["user_id"]
    sessao_id = request.args.get("sessao_id")

    # ─── Recupera a sessão escolhida (ou a mais recente) ────────────────────
    sessao = (
        TestSession.query.filter_by(id=sessao_id, user_id=user_id).first()
        if sessao_id
        else TestSession.query.filter_by(user_id=user_id)
                              .order_by(TestSession.created_at.desc())
                              .first()
    )
    if not sessao:
        flash("No se encontró ninguna sesión para generar el PDF.", "warning")
        return redirect(url_for("user.preencher_dados"))

    if not sessao.ai_result:
        flash("El informe aún se está generando. Intenta de nuevo pronto.", "warning")
        return redirect(url_for("user.processando_relatorio", sessao_id=sessao.id))

    # ─── Converte/normaliza o campo ai_result ───────────────────────────
    if isinstance(sessao.ai_result, str):
        try:
            ai_data = json.loads(sessao.ai_result)          # JSON válido
        except Exception as e:
            current_app.logger.error(f"[RELATORIO JSON ERROR] {e}")
            ai_data = {}                                    # texto bruto
    elif isinstance(sessao.ai_result, dict):
        ai_data = sessao.ai_result
    else:
        ai_data = {}

    # 🔹 Limpa quebras de linha escapadas
    if isinstance(ai_data.get("texto"), str):
        ai_data["texto"] = re.sub(r'(?:\\)+n', '\n', ai_data["texto"])

    # ─── Monta dicionário final (mesma estrutura da view HTML) ───────────
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

    # ─── Gera HTML e converte em PDF ─────────────────────────────────────
    html = render_template(
        "relatorio.html",
        nome=session.get("user_name", "User"),
        resultado=resultado_dict,
        sessao_id=sessao.id,
        pdf_mode=True         # se o template usar flag para ocultar botões
    )

    try:
        pdf_bytes = asyncio.run(html_to_pdf_bytes(html))
    except Exception as e:
        current_app.logger.error(f"[PDF GENERATION ERROR] {e}")
        flash("Error al generar el PDF. Intenta más tarde.", "danger")
        return redirect(url_for("user.gerar_relatorio", sessao_id=sessao.id))

    # ─── Envia arquivo ao usuário ───────────────────────────────────────
    response = make_response(pdf_bytes)
    response.headers["Content-Type"]        = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=skyai_report_{sessao.id}.pdf"
    )
    return response

# ---------------------------------------------------------------------------
# 🔹 /compatibility/pdf  –  gera PDF do resultado de compatibilidade
# ---------------------------------------------------------------------------
@user_bp.route("/compatibility/pdf")
def compatibility_pdf():
    if "user_id" not in session:
        flash("Debes iniciar sesión para descargar el PDF.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id   = session["user_id"]
    sessao_id = request.args.get("match_id")        # usaremos o id do GuruQuestion

    # Recupera o registro salvo na geração do relatório
    match = (
        GuruQuestion.query
        .filter_by(id=sessao_id, user_id=user_id)
        .first()
    )
    if not match:
        flash("No se encontró el resultado de compatibilidad.", "warning")
        return redirect(url_for("auth_views.dashboard"))

    # Separar nomes (estavam no ‘question’)
    try:
        title_names = match.question.replace("Compatibility ", "").split(" × ")
        name_1, name_2 = title_names if len(title_names) == 2 else ("Persona 1", "Persona 2")
    except Exception:
        name_1, name_2 = ("Persona 1", "Persona 2")

    # Renderiza o MESMO template usado na tela, porém para PDF
    html = render_template(
        "compatibility_result.html",
        result = match.answer,
        name_1 = name_1,
        name_2 = name_2,
        pdf_mode = True                      # flag opcional p/ esconder botões
    )

    try:
        pdf_bytes = asyncio.run(html_to_pdf_bytes(html))
    except Exception as e:
        current_app.logger.error(f"[PDF COMPAT ERROR] {e}")
        flash("Error al generar el PDF. Intenta más tarde.", "danger")
        return redirect(url_for("auth_views.dashboard"))

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=compatibility_{match.id}.pdf"
    )
    return response

@user_bp.route('/select-product', methods=['GET', 'POST'])
def select_product():
    if 'user_id' not in session:
        flash("Inicia sesión para continuar.", "error")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        selected_plan = request.form.get('plan')
        if selected_plan:
            user = User.query.get(session['user_id'])
            user.plan = selected_plan
            db.session.commit()
            session['user_plan'] = selected_plan

            flash(f"¡Seleccionaste el plan {selected_plan}!", "success")
            return redirect(url_for('user.preencher_dados'))
        else:
            flash("Ningún plan seleccionado.", "warning")

    return render_template('products.html')

@user_bp.route("/compatibility", methods=["GET", "POST"])
def compatibility():
    # ─────────── Requer login ───────────
    if "user_id" not in session:
        flash("Inicia sesión para continuar.", "error")
        return redirect(url_for("auth_views.login_view"))

    user = User.query.get(session["user_id"])

    # ─────────── Bloqueio se já usado ───────────
    if user.compatibility_used:
        flash("Ya usaste tu prueba de Compatibilidad. Compra nuevamente para desbloquear una nueva.", "info")
        return redirect(url_for("auth_views.dashboard"))

    # ─────────── Mostra formulário (GET) ─────────
    if request.method == "GET":
        return render_template("compatibility.html")

    # ─────────── POST: valida campos ────────────
    name_1            = request.form.get("name_1")
    birth_1           = request.form.get("birth_1")
    birth_time_1      = request.form.get("birth_time_1")
    birth_city_1      = request.form.get("birth_city_1")
    birth_country_1   = request.form.get("birth_country_1")

    name_2            = request.form.get("name_2")
    birth_2           = request.form.get("birth_2")
    birth_time_2      = request.form.get("birth_time_2")
    birth_city_2      = request.form.get("birth_city_2")
    birth_country_2   = request.form.get("birth_country_2")

    if not all([
        name_1, birth_1, birth_time_1, birth_city_1, birth_country_1,
        name_2, birth_2, birth_time_2, birth_city_2, birth_country_2
    ]):
        flash("Por favor, completa todos los campos para ambas personas.", "warning")
        return render_template("compatibility.html")

    try:
        # ── Calcula astrologia / numerologia ──
        from app.services.astrology_service import get_astrological_signs
        from app.services.numerology_service import get_numerology

        astro_1 = get_astrological_signs(birth_1, birth_time_1, birth_city_1, birth_country_1)
        if isinstance(astro_1, tuple):
            astro_1 = {"positions": {"SUN": {"sign": astro_1[0]},
                                      "MOON": {"sign": astro_1[1]},
                                      "ASC": {"sign": astro_1[2]}}}
        num_1   = get_numerology(name_1, birth_1)

        astro_2 = get_astrological_signs(birth_2, birth_time_2, birth_city_2, birth_country_2)
        if isinstance(astro_2, tuple):
            astro_2 = {"positions": {"SUN": {"sign": astro_2[0]},
                                      "MOON": {"sign": astro_2[1]},
                                      "ASC": {"sign": astro_2[2]}}}
        num_2   = get_numerology(name_2, birth_2)

        # ── Gera análise via OpenAI ──
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""
Eres el Guru SkyAI, experto en compatibilidad astrológica y numerológica.
Responde **exclusivamente en español de México (es-MX)**. **No saludes**; entrega SOLO el informe.

Devuelve el análisis con estas secciones tituladas con emoji (enfoque en presente y futuro):

💞 Panorama general  
🌞 Dinámica de signos solares  
🌙 Conexión emocional (Luna)  
⬆️ Energía del Ascendente  
🔢 Resonancia numerológica  
❤️ Fortalezas de la relación  
⚠️ Desafíos potenciales  
✨ Recomendaciones prácticas  

PERSONA A  
• Nombre………..: {name_1}  
• Sol………..…: {astro_1['positions']['SUN']['sign']}  
• Luna………..…: {astro_1['positions']['MOON']['sign']}  
• Ascendente…: {astro_1['positions']['ASC']['sign']}  
• Número de Camino de Vida: {num_1['life_path']}  
• Número de Anhelo del Alma: {num_1['soul_urge']}  
• Número de Expresión: {num_1['expression']}

PERSONA B  
• Nombre………..: {name_2}  
• Sol………..…: {astro_2['positions']['SUN']['sign']}  
• Luna………..…: {astro_2['positions']['MOON']['sign']}  
• Ascendente…: {astro_2['positions']['ASC']['sign']}  
• Número de Camino de Vida: {num_2['life_path']}  
• Número de Anhelo del Alma: {num_2['soul_urge']}  
• Número de Expresión: {num_2['expression']}

Escribe 400–600 palabras.  
→ Sé directo, claro y totalmente anclado en los datos anteriores.  
→ Habla solo de tendencias presentes y potenciales futuras; evita referencias al pasado salvo que se te pida explícitamente.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres el Guru SkyAI, maestro en compatibilidad. Responde en español de México (es-MX)."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=1300
        )

        result_text = response.choices[0].message.content.strip()

               # ─────────── Salva resultado e marca uso ───────────
        match = GuruQuestion(
            user_id = user.id,
            question = f"Compatibility {name_1} × {name_2}",
            answer   = result_text
        )
        db.session.add(match)

        user.compatibility_used = True      # bloqueia novo teste grátis
        db.session.commit()                 # grava e gera match.id

        return render_template(
            "compatibility_result.html",
            result   = result_text,
            name_1   = name_1,
            name_2   = name_2,
            match_id = match.id              # ← usado pelo botão PDF
        )

    except Exception as e:
        current_app.logger.error(f"[COMPATIBILITY ERROR] {e}")
        flash("Lo sentimos, no pudimos generar tu lectura de compatibilidad en este momento.", "danger")
        return render_template("compatibility.html")

@user_bp.route("/ask-guru", methods=["POST"])
def ask_guru():
    # ─────────── Requer login ───────────
    if "user_id" not in session:
        flash("Inicia sesión para preguntarle al Guru SkyAI.", "error")
        return redirect(url_for("auth_views.login_view"))

    user = User.query.get(session["user_id"])

    # ─────────── Limite de 4 perguntas ───────────
    if user.guru_questions_used >= 4:
        flash("Has alcanzado tu límite de 4 preguntas para el Guru SkyAI. Compra nuevamente para restablecerlo.", "info")
        return redirect(url_for("auth_views.dashboard"))

    # ─────────── Validação da pergunta ───────────
    question = request.form.get("question", "").strip()
    if len(question) < 5:
        flash("Ingresa una pregunta válida.", "warning")
        return redirect(url_for("auth_views.dashboard"))

    # ─────────── Garante que o usuário tem mapa gerado ─────────
    last_session = (TestSession.query
                    .filter_by(user_id=user.id)
                    .filter(TestSession.ai_result.isnot(None))
                    .order_by(TestSession.created_at.desc())
                    .first())
    if not last_session:
        flash("Primero genera una carta natal para que el Guru pueda darte una respuesta personalizada.", "info")
        return redirect(url_for("user.preencher_dados"))

    # Extrai dados do último mapa
    data = json.loads(last_session.ai_result) if isinstance(last_session.ai_result, str) else last_session.ai_result
    sun  = data.get("sun_sign", "unknown")
    moon = data.get("moon_sign", "unknown")
    asc  = data.get("ascendant", "unknown")
    life = data.get("life_path", "unknown")
    soul = data.get("soul_urge", "unknown")
    expr = data.get("expression", "unknown")

    # ─────────── Monta prompt para OpenAI ───────────
    prompt = f"""
Eres el Guru SkyAI — un asesor pragmático que DEBE fundamentar CADA respuesta en los datos natales del usuario y, si está disponible, en el pronóstico de **12 meses** más reciente entregado por SkyAI.

Año actual: {current_year}.  
✦ Nunca hagas referencia a años de calendario *anteriores* a {current_year} a menos que el usuario lo pida explícitamente.  
✦ Cuando menciones periodos futuros, sé explícito: p. ej., “feb–mar {current_year + 1}”.

PREGUNTA del usuario:
\"\"\"{question}\"\"\"

CONTEXTO del usuario:
- Signo solar: {sun}
- Signo lunar: {moon}
- Ascendente: {asc}
- Número de Camino de Vida: {life}
- Número de Anhelo del Alma: {soul}
- Número de Expresión: {expr}

REGLAS
1. Empieza con una oración que responda directamente.
2. Luego explica **por qué** — cita al menos un indicador natal O el pronóstico de 12 meses
   (p. ej., “Júpiter cuadratura Saturno en feb {current_year + 1}”).
3. Termina con una recomendación concreta que pueda aplicar en 7 días.
4. Sin saludos ni relleno.
"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres el Guru SkyAI, el asesor cósmico claro y práctico. Responde en español de México (es-MX)."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.65,
            max_tokens=700
        )

        answer = response.choices[0].message.content.strip()

        # ─────────── Salva pergunta + incrementa uso ───────────
        db.session.add(GuruQuestion(user_id=user.id, question=question, answer=answer))
        user.guru_questions_used += 1
        db.session.commit()

        flash("✨ El Guru SkyAI ha respondido tu pregunta. ¡Ve la respuesta abajo en tu panel!", "success")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[GURU SKY ERROR] {e}")
        flash("Lo sentimos, el Guru SkyAI no pudo responder tu pregunta en este momento.", "danger")

    return redirect(url_for("auth_views.dashboard"))
