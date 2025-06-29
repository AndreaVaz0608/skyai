from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.models import User, TestSession, GuruQuestion
from app.main import db
import secrets
from app.services.email import enviar_email_boas_vindas, send_recovery_email
from datetime import datetime
from sqlalchemy import func
import json
from sqlalchemy.exc import SQLAlchemyError
from app.services.insights_service import get_past_insights

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
            flash(f"Welcome, {user.name.split()[0]}!", "success")

            return redirect(url_for('auth_views.dashboard'))

        flash("Invalid credentials", "error")
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
            flash("All fields are required, including terms and privacy agreement.", "warning")
            return redirect(url_for('auth_views.register_view'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email is already in use. Try logging in or resetting your password.", "error")
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

            flash(f"Registration successful, {name.split()[0]}!", "success")
            return redirect(url_for('user.preencher_dados'))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[REGISTER SQL ERROR] {e}")
            flash("Database error during registration. Please try again later.", "danger")
            return redirect(url_for('auth_views.register_view'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"[REGISTER UNEXPECTED ERROR] {e}")
            flash("An unexpected error occurred. Please try again later.", "danger")
            return redirect(url_for('auth_views.register_view'))

    return render_template('register.html')

# 🔹 Tela de recuperação de senha
@auth_views.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        if not email:
            flash("Please enter your email address.", "warning")
            return redirect(url_for('auth_views.forgot_password'))

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Email not found. Please check and try again.", "error")
            return redirect(url_for('auth_views.forgot_password'))

        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        db.session.commit()

        send_recovery_email(user.email, reset_token)

        flash("Instructions sent to your email. Check your inbox!", "success")
        return redirect(url_for('auth_views.login_view'))

    return render_template('forgot_password.html')

# 🔹 Logout
@auth_views.route('/logout')
def logout():
    session.clear()
    flash("You have successfully logged out!", "info")
    return redirect(url_for('auth_views.login_view'))

# 🔹 Dashboard com contagem de perguntas ao Guru
# 🔹 Dashboard com contagem de perguntas ao Guru
@auth_views.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("You need to log in to access the dashboard.", "error")
        return redirect(url_for('auth_views.login_view'))

    user_id = session['user_id']
    user = User.query.get(user_id)

    # ▶ relatórios recentes (para o card “Your last reports”)
    sessoes = (TestSession.query
               .filter_by(user_id=user_id)
               .order_by(TestSession.created_at.desc())
               .limit(6)
               .all())
    ultima_sessao = sessoes[0] if sessoes else None
    total         = len(sessoes)

    # ▶ NOVO: key insights prontos p/ exibição
    insights = get_past_insights(user_id)   # ← serviço criado em insights_service.py

    # 🔮 contagem de perguntas do Guru neste mês
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used_questions = db.session.query(func.count()).select_from(GuruQuestion).filter(
        GuruQuestion.user_id == user_id,
        GuruQuestion.created_at >= start_of_month
    ).scalar()
    remaining_questions = max(0, 4 - used_questions)

    # 🔮 últimas respostas do Guru
    guru_answers = (GuruQuestion.query
                    .filter_by(user_id=user_id)
                    .order_by(GuruQuestion.created_at.desc())
                    .limit(3)
                    .all())

    return render_template(
        "dashboard.html",
        nome=user.name,
        email=user.email,
        sessoes=sessoes,
        total=total,
        ultima_sessao=ultima_sessao,
        remaining_questions=remaining_questions,
        guru_answers=guru_answers,
        insights=insights               # ← passa para o template
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
        flash("Invalid or missing token.", "danger")
        return redirect(url_for('auth_views.login_view'))

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for('auth_views.login_view'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not password or not confirm_password:
            flash("Please fill in all fields.", "warning")
            return redirect(request.url)

        if password != confirm_password:
            flash("Passwords do not match.", "warning")
            return redirect(request.url)

        user.set_password(password)
        user.reset_token = None
        db.session.commit()

        flash("Password successfully reset! Please log in.", "success")
        return redirect(url_for('auth_views.login_view'))

    return render_template('reset_password.html')
