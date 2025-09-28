# app/routes/web.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.models import User, TestSession, GuruQuestion
from app.main import db
import secrets
from app.services.email import enviar_email_boas_vindas, send_recovery_email
from datetime import datetime
from sqlalchemy import func
import json
from sqlalchemy.exc import SQLAlchemyError
from app.models import User, TestSession, GuruQuestion, Payment


# ⬇️  REMOVIDO:  from app.services.insights_service import get_past_insights

auth_views = Blueprint('auth_views', __name__)

# 🔹 Redirecionamento da raiz para login
@auth_views.route('/')
def home_redirect():
    return redirect(url_for('auth_views.login_view'))

# 🔹 Tela de login
@auth_views.route('/login', methods=['GET', 'POST'])
def login_view():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_plan'] = user.plan
            flash(f"¡Bienvenido(a), {user.name.split()[0]}!", "success")

            return redirect(url_for('auth_views.dashboard'))

        flash("Credenciales inválidas.", "error")
        return redirect(url_for('auth_views.login_view'))

    return render_template('login.html')

# 🔹 Tela de registro
@auth_views.route('/register', methods=['GET', 'POST'])
def register_view():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        accepted_terms = request.form.get("accepted_terms")
        accepted_privacy = request.form.get("accepted_privacy")

        if not all([name, email, password, accepted_terms, accepted_privacy]):
            flash("Todos los campos son obligatorios, incluida la aceptación de términos y privacidad.", "warning")
            return redirect(url_for('auth_views.register_view'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Ese correo ya está en uso. Intenta iniciar sesión o restablecer tu contraseña.", "error")
            return redirect(url_for('auth_views.register_view'))

        try:
            user = User(
                name=name,
                email=email,
                accepted_terms=True,
                accepted_privacy=True,
                plan='CosmicLife'
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_plan'] = user.plan

            try:
                enviar_email_boas_vindas(user)
            except Exception as e:
                current_app.logger.error(f"[EMAIL ERROR] {e}")

            flash(f"¡Registro exitoso, {name.split()[0]}!", "success")
            return redirect(url_for('user.preencher_dados'))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[REGISTER SQL ERROR] {e}")
            flash("Error de base de datos durante el registro. Inténtalo de nuevo más tarde.", "danger")
            return redirect(url_for('auth_views.register_view'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"[REGISTER UNEXPECTED ERROR] {e}")
            flash("Ocurrió un error inesperado. Inténtalo de nuevo más tarde.", "danger")
            return redirect(url_for('auth_views.register_view'))

    return render_template('register.html')

# 🔹 Tela de recuperação de senha
@auth_views.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        if not email:
            flash("Ingresa tu correo electrónico.", "warning")
            return redirect(url_for('auth_views.forgot_password'))

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Correo no encontrado. Verifícalo e inténtalo nuevamente.", "error")
            return redirect(url_for('auth_views.forgot_password'))

        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        db.session.commit()

        send_recovery_email(user.email, reset_token)

        flash("Instrucciones enviadas a tu correo. ¡Revisa tu bandeja de entrada!", "success")
        return redirect(url_for('auth_views.login_view'))

    return render_template('forgot_password.html')

# 🔹 Logout
@auth_views.route('/logout')
def logout():
    session.clear()
    flash("¡Cerraste sesión correctamente!", "info")
    return redirect(url_for('auth_views.login_view'))

# app/routes/web.py  ➜  trecho completo da view dashboard()

@auth_views.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Necesitas iniciar sesión para acceder al panel.", "error")
        return redirect(url_for("auth_views.login_view"))

    user_id = session["user_id"]
    user    = User.query.get(user_id)

    # ─────────────────────────────────────────────────────────────
    # 1. Relatórios recentes (máx. 6)
    # ─────────────────────────────────────────────────────────────
    sessoes = (
        TestSession.query
        .filter_by(user_id=user_id)
        .order_by(TestSession.created_at.desc())
        .limit(6)
        .all()
    )
    ultima_sessao = sessoes[0] if sessoes else None
    total         = len(sessoes)

    # ─────────────────────────────────────────────────────────────
    # 2. Existe pagamento "paid" vinculado ao usuário?
    # ─────────────────────────────────────────────────────────────
    payment_exists = (
        db.session.query(Payment)
        .filter(Payment.user_id == user_id, Payment.status == "paid")
        .first()
    )
    show_pay_banner = payment_exists is None  # mostra “Pay Now” se nunca pagou

    # ─────────────────────────────────────────────────────────────
    # 3. Guru SkyAI – usa créditos do usuário (0‒4)
    # ─────────────────────────────────────────────────────────────
    remaining_questions = 0
    limit_exceeded      = True
    guru_answers        = []

    if payment_exists:
        # Créditos ainda disponíveis?
        remaining_questions = max(0, 4 - user.guru_questions_used)
        limit_exceeded      = remaining_questions == 0

        # Últimas 3 respostas (não precisa filtrar por mês)
        guru_answers = (
            GuruQuestion.query
            .filter_by(user_id=user_id)
            .order_by(GuruQuestion.created_at.desc())
            .limit(3)
            .all()
        )

    # ─────────────────────────────────────────────────────────────
    # 4. Render
    # ─────────────────────────────────────────────────────────────
    return render_template(
    "dashboard.html",
    nome=user.name,
    email=user.email,
    total=total,
    ultima_sessao=ultima_sessao,
    show_pay_banner=show_pay_banner,
    compatibility_used=user.compatibility_used,   # ← essencial
    remaining_questions=remaining_questions,
    limit_exceeded=limit_exceeded,
    guru_answers=guru_answers,
    )

# 🔹 Termos de uso
@auth_views.route('/termos')
def termos():
    return render_template('termos.html')

# 🔹 Resetar senha
@auth_views.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token')
    if not token:
        flash("Token inválido o ausente.", "danger")
        return redirect(url_for('auth_views.login_view'))

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        flash("Enlace de restablecimiento inválido o vencido.", "danger")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not password or not confirm_password:
            flash("Por favor, completa todos los campos.", "warning")
            return redirect(request.url)

        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "warning")
            return redirect(request.url)

        user.set_password(password)
        user.reset_token = None
        db.session.commit()

        flash("¡Contraseña restablecida con éxito! Inicia sesión.", "success")
        return redirect(url_for('auth_views.login_view'))

    return render_template('reset_password.html')
