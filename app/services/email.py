# app/services/email.py
from flask_mail import Message
from flask import render_template, current_app
from app.main import mail


def _send_message(msg: Message):
    """
    Envia a mensagem de maneira segura em uma única conexão SMTP.
    Loga erros de autenticação ou configuração ausente.
    """
    try:
        smtp_user = current_app.config.get("MAIL_USERNAME")
        smtp_pass = current_app.config.get("MAIL_PASSWORD")
        if not smtp_user or not smtp_pass:
            raise RuntimeError("MAIL_USERNAME or MAIL_PASSWORD not set")

        with mail.connect() as conn:
            conn.send(msg)
        current_app.logger.info(f"✅ Email '{msg.subject}' sent to {msg.recipients}")

    except Exception as e:
        current_app.logger.error(f"❌ Email send failure ({msg.subject}): {e}")


# ------------------------------------------------------------------
# 1) Welcome e-mail  –– agora com BCC
# ------------------------------------------------------------------
def enviar_email_boas_vindas(user):
    bcc_addr = current_app.config.get("MAIL_BCC")        # e.g. admin@skyai.digital
    msg = Message(
        subject="🌟 Welcome to SkyAI – Your Cosmic Journey Begins!",
        recipients=[user.email],
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        bcc=[bcc_addr] if bcc_addr else None,
    )
    msg.html = render_template("emails/welcome.html", nome=user.name)
    _send_message(msg)


# ------------------------------------------------------------------
# 2) Report-ready e-mail
# ------------------------------------------------------------------
def enviar_email_relatorio(user, sessao_id):
    link = f"https://skyai.digital/relatorio?sessao_id={sessao_id}"

    msg = Message(
        subject="🌌 Your SkyAI Astrological & Numerological Report is Ready!",
        recipients=[user.email],
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
    )
    # se quiser BCC também aqui, adicione bcc=[bcc_addr] no construtor acima
    msg.html = render_template(
        "emails/relatorio_astral.html",
        nome=user.name,
        link=link,
        sun_sign=user.sun_sign,
        moon_sign=user.moon_sign,
        ascendant=user.ascendant,
        life_path=user.life_path,
    )
    _send_message(msg)


# ------------------------------------------------------------------
# 3) Password-recovery e-mail
# ------------------------------------------------------------------
def send_recovery_email(recipient_email, reset_token):
    reset_link = f"https://skyai.digital/reset-password?token={reset_token}"

    msg = Message(
        subject="🔒 Password Recovery Instructions • SkyAI",
        recipients=[recipient_email],
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
    )
    msg.html = render_template(
        "emails/recovery.html",
        link=reset_link,
    )
    _send_message(msg)
