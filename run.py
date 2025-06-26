from app.main import create_app
import os

# Instância do Flask para o Gunicorn
app = create_app()

# Execução local (apenas em desenvolvimento)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Fallback para 5000 se não definido
    app.run(host="0.0.0.0", port=port, debug=True)
