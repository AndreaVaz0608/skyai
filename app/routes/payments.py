import os
from flask import (
    Blueprint, redirect, session, jsonify, current_app
)

# ─────────────────────────────────────────────
# Você NÃO usa stripe.api_key aqui porque não cria session dinâmica
# ─────────────────────────────────────────────

payments_bp = Blueprint("payments", __name__, url_prefix="/pay")

# ─────────────────────────────────────────────
# Redireciona para o link fixo do Stripe Checkout
# ─────────────────────────────────────────────
@payments_bp.route("/checkout", methods=["GET", "POST"])
def create_checkout():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    # ⚡️ Apenas log para auditoria
    user_id = session["user_id"]
    current_app.logger.info(f"[PAYMENTS] Redirecting user {user_id} to Stripe fixed link")

    # 🔗 Link fixo gerado no painel do Stripe
    stripe_link = "https://buy.stripe.com/bJefZg96w76eaLn0zj5AQ09"

    return redirect(stripe_link)


# ─────────────────────────────────────────────
# Fallback: tela de obrigado (opcional)
# ─────────────────────────────────────────────
@payments_bp.route("/thank-you")
def thank_you():
    return redirect("/")
