import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # Chave secreta carregada do .env
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-fallback')

    # Configurações do banco
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///skyai.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Importa e registra os blueprints
    from app.routes.user import user_bp
    app.register_blueprint(user_bp)

    return app
