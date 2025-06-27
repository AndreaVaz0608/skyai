import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

from app.config import Config  # ✅ Importa a config customizada

load_dotenv()
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-fallback')

    # ✅ Carrega todas configurações centralizadas
    app.config.from_object(Config)

    db.init_app(app)

    # Blueprints
    from app.routes.user import user_bp
    app.register_blueprint(user_bp)

    return app
