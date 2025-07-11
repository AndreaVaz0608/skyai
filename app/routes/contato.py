# app/routes/contato.py
import threading
from flask import Blueprint, render_template, request, flash, current_app
from flask_mail import Message
from app.main import mail

contato_views = Blueprint("contato", __name__)

# ────────────────────────────────────────────────────────────────
# helper: envia e-mail em background
# ────────────────────────────────────────────────────────────────
def _send_async_email(app, msg: Message):
    with app.app_context():
        try:
            # usa uma única conexão SMTP
            with mail.connect() as conn:
                conn.send(msg)
            current_app.logger.info("✅ Contact email delivered")
        except Exception as e:
            current_app.logger.error(f"❌ Contact email failure: {e}")


@contato_views.route("/contato", methods=["GET", "POST"])
def contato():
    if request.method == "POST":
        nome      = request.form.get("name")
        email     = request.form.get("email")
        mensagem  = request.form.get("message")

        if not all([nome, email, mensagem]):
            flash("Please fill in all fields.", "warning")
            return render_template("contato.html")

        # monta mensagem
        msg = Message(
            subject="New Contact • SkyAI",
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
            recipients=["skyai@skyai.digital"],
            body=(
                "📩 New contact from SkyAI:\n\n"
                f"Name   : {nome}\n"
                f"Email  : {email}\n\n"
                "Message:\n"
                f"{mensagem}"
            ),
        )

        # dispara em background
        threading.Thread(
            target=_send_async_email,
            args=(current_app._get_current_object(), msg),
            daemon=True,
        ).start()

        return render_template("contato.html", success=True)

    # GET
    return render_template("contato.html")
