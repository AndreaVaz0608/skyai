import os
import stripe
from flask import (
    Blueprint, render_template, request, jsonify,
    session, url_for, redirect, current_app
)

# ─────────────────────────────────────────────
# Configuração da chave secreta Stripe
# ─────────────────────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Cria blueprint de pagamentos
payments_bp = Blueprint("payments", __name__, url_prefix="/pay")

# ─────────────────────────────────────────────
# Rota: Cria sessão de checkout Stripe e redireciona
# Aceita GET e POST ➜ funciona com redirect do preencher_dados
# ─────────────────────────────────────────────
@payments_bp.route("/checkout", methods=["GET", "POST"])
def create_checkout():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        checkout = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            customer_email=session.get("user_email"),  # opcional
            line_items=[
                {
                    "price": os.getenv("STRIPE_PRICE_ID"),
                    "quantity": 1
                }
            ],
            # ✅ Após sucesso ➜ volta para rota /processando-relatorio do Flask
            success_url=url_for("user.processando_relatorio", _external=True)
                        + "?paid=true&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("user.home", _external=True),
            metadata={
                "user_id": session["user_id"]
            }
        )

        current_app.logger.info(f"[STRIPE] Created Checkout Session: {checkout.id}")

        return redirect(checkout.url)

    except Exception as e:
        current_app.logger.error(f"[STRIPE ERROR] {e}")
        return jsonify({"error": "stripe"}), 500

# ─────────────────────────────────────────────
# Rota opcional: fallback de "Obrigado"
# (não usada, pois volta direto para processando)
# ─────────────────────────────────────────────
@payments_bp.route("/thank-you")
def thank_you():
    return redirect(url_for("user.home"))
