# app/main.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from app.config import Config

import logging
import smtplib
import os

# ── Extensões globais ─────────────────────────────────────────
db  = SQLAlchemy()
jwt = JWTManager()
mail = Mail()

# ── Fábrica da aplicação ─────────────────────────────────────
def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # 🔎 Exibe a URI ativa do banco (útil em logs)
    print("[DB CHECK] URI ativa:", app.config['SQLALCHEMY_DATABASE_URI'])

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    # ── Blueprints ------------------------------------------------------
    with app.app_context():
        from app.routes.web      import auth_views
        from app.routes.user     import user_bp
        from app.routes.contato  import contato_views
        from app.routes.payments import payments_bp      # ← NOVO

        app.register_blueprint(auth_views)
        app.register_blueprint(user_bp)
        app.register_blueprint(contato_views)
        app.register_blueprint(payments_bp)              # ← NOVO

    # ── SMTP Debug (somente em modo DEBUG) ------------------------------
    if app.config.get("DEBUG", False):
        mail_logger = logging.getLogger("smtplib")
        mail_logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        mail_logger.addHandler(console_handler)
        smtplib.SMTP.debuglevel = 1

    return app

# ── Exposto ao Gunicorn ───────────────────────────────────────
app = create_app()

# ── Execução local para testes rápidos ------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
