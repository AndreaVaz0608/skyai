# app/routes/contato.py

from flask import Blueprint, render_template, request, flash, current_app
from flask_mail import Message
from app.main import mail

contato_views = Blueprint('contato', __name__)

@contato_views.route('/contato', methods=['GET', 'POST'])
def contato():
    if request.method == 'POST':
        nome = request.form.get('name')
        email = request.form.get('email')
        mensagem = request.form.get('message')

        try:
            msg = Message(
                subject="New Contact - SkyAI",  # 🔥 Atualizado para SkyAI
                sender=current_app.config['MAIL_DEFAULT_SENDER'],
                recipients=["skyai@skyai.digital"],  # 🔄 (opcional trocar se tiver e-mail novo)
                body=f"📩 New contact from SkyAI:\n\n"
                     f"Name: {nome}\n"
                     f"Email: {email}\n\n"
                     f"Message:\n{mensagem}"
            )

            mail.send(msg)
            return render_template('contato.html', success=True)

        except Exception as e:
            print("Erro ao enviar e-mail:", e)
            flash("Oops! Something went wrong. Please try again later.", "error")

    return render_template('contato.html')
