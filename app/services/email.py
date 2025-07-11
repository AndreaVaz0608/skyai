# app/services/email.py
import smtplib, threading
from flask_mail import Message
from flask import render_template, current_app
from app.main import mail


# ------------------------------------------------------------------
# helper: envia e-mail dentro de uma thread
# ------------------------------------------------------------------
def _async_send(app, msg: Message):
    with app.app_context():
        try:
            # timeout de 10 s na conexão SMTP
            with mail.connect(host=mail.server,
                              port=mail.port,
                              timeout=10) as conn:
                conn.send(msg)
            current_app.logger.info(
                f"✅ Email '{msg.subject}' sent to {msg.recipients}"
            )
        except (smtplib.SMTPException, OSError) as e:
            current_app.logger.error(
                f"❌ Email send failure ({msg.subject}): {e}"
            )


def _queue_email(msg: Message):
    threading.Thread(
        target=_async_send,
        args=(current_app._get_current_object(), msg),
        daemon=True,
    ).start()


# ------------------------------------------------------------------
# 1) Welcome e-mail  –– com BCC opcional
# ------------------------------------------------------------------
def enviar_email_boas_vindas(user):
    bcc_addr = current_app.config.get("MAIL_BCC")
    msg = Message(
        subject="🌟 Welcome to SkyAI – Your Cosmic Journey Begins!",
        recipients=[user.email],
        bcc=[bcc_addr] if bcc_addr else None,
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
    )
    msg.html = render_template("emails/welcome.html", nome=user.name)
    _queue_email(msg)


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
    msg.html = render_template(
        "emails/relatorio_astral.html",
        nome=user.name,
        link=link,
        sun_sign=user.sun_sign,
        moon_sign=user.moon_sign,
        ascendant=user.ascendant,
        life_path=user.life_path,
    )
    _queue_email(msg)


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
    msg.html = render_template("emails/recovery.html", link=reset_link)
    _queue_email(msg)
