# app/main.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from app.config import Config

import logging
import smtplib

# Initialize global extensions
db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    # 🔹 Registrar Blueprints DENTRO do contexto da app
    with app.app_context():
        from app.routes.web import auth_views
        app.register_blueprint(auth_views)

        from app.routes.user import user_bp
        app.register_blueprint(user_bp)

        from app.routes.contato import contato_views
        app.register_blueprint(contato_views)

    # 🔹 DEBUG SMTP (somente se FLASK_DEBUG = 1)
    if app.config.get("DEBUG", False):
        mail_logger = logging.getLogger("smtplib")
        mail_logger.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        mail_logger.addHandler(console_handler)

        smtplib.SMTP.debuglevel = 1

    return app

# Execução local (somente para testes manuais)
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
