# create_tables.py

from app import db
from app.models import User  # Importe os modelos diretamente aqui
from app import create_app

app = create_app()

with app.app_context():
    print(f"[DB CHECK] URI ativa: {app.config['SQLALCHEMY_DATABASE_URI']}")
    db.drop_all()   # Opcional: remove todas as tabelas (cuidado!)
    db.create_all()
    print("✅ Tabelas criadas com sucesso no banco de dados.")
