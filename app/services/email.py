# app/services/email.py

from flask_mail import Message
from flask import render_template, current_app
from app.main import mail

# 🔹 Email de boas-vindas
def enviar_email_boas_vindas(user):
    try:
        msg = Message(
            subject="🌟 Welcome to SkyAI - Your Journey to the Stars Begins!",
            recipients=[user.email],
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        msg.html = render_template("emails/welcome.html", nome=user.name)
        mail.send(msg)
        current_app.logger.info(f"✅ Welcome email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"❌ Error sending welcome email to {user.email}: {e}")

# 🔹 Email avisando que o Relatório Astral está pronto
def enviar_email_relatorio(user, sessao_id):
    try:
        link_relatorio = f"https://skyai.digital/relatorio?sessao_id={sessao_id}"  # 🔥 Atualizar conforme URL real

        msg = Message(
            subject="🌌 Your SkyAI Astrological and Numerological Report is Ready!",
            recipients=[user.email],
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )

        msg.html = render_template(
            "emails/relatorio_astral.html",
            nome=user.name,
            link=link_relatorio
        )

        mail.send(msg)
        current_app.logger.info(f"✅ Report email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"❌ Error sending report email to {user.email}: {e}")

# 🔹 Email de recuperação de senha
def send_recovery_email(recipient_email, reset_token):
    try:
        reset_link = f"https://skyai.digital/reset-password?token={reset_token}"  # 🔥 Atualizar conforme domínio

        msg = Message(
            subject="🔒 Password Recovery Instructions • SkyAI",
            recipients=[recipient_email],
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )

        msg.html = f"""
        <h2>Hello!</h2>
        <p>You requested to reset your password for your SkyAI account.</p>
        <p>Click the link below to set a new password:</p>
        <p><a href="{reset_link}" style="color: #4A90E2; font-weight: bold;">Reset My Password</a></p>
        <br>
        <p>If you did not request a password reset, please ignore this message.</p>
        <p>Thank you,<br>The SkyAI Team</p>
        """

        mail.send(msg)
        current_app.logger.info(f"✅ Recovery email sent to {recipient_email}")
    except Exception as e:
        current_app.logger.error(f"❌ Error sending recovery email to {recipient_email}: {e}")
