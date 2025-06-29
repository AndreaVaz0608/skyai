# app/routes/payments.py
import os
import stripe
from flask import (
    Blueprint, request, jsonify,
    session, url_for, redirect, current_app
)

# ────────────────────────────────────────────────────────────
# Config Stripe
# ────────────────────────────────────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

payments_bp = Blueprint("payments", __name__, url_prefix="/pay")

# ────────────────────────────────────────────────────────────
# Rota: cria sessão de checkout e redireciona o usuário
# ────────────────────────────────────────────────────────────
@payments_bp.route("/checkout", methods=["POST"])
def create_checkout():
    if "user_id" not in session:
        return jsonify({"error": "not authenticated"}), 401

    try:
        checkout = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            customer_email=session.get("user_email"),  # opcional
            line_items=[{
                "price": os.getenv("STRIPE_PRICE_ID"),
                "quantity": 1,
            }],
            success_url=url_for("payments.thank_you", _external=True)
                        + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("auth_views.dashboard", _external=True),
            metadata={"user_id": session["user_id"]},
        )
        # Para single-page apps: devolve URL; aqui redirecionamos direto
        return redirect(checkout.url)
    except Exception as e:
        current_app.logger.error(f"[STRIPE ERROR] {e}")
        return jsonify({"error": "stripe"}), 500

# ────────────────────────────────────────────────────────────
# Rota: tela de “obrigado” após pagamento
# ────────────────────────────────────────────────────────────
@payments_bp.route("/thank-you")
def thank_you():
    session_id = request.args.get("session_id")
    if not session_id:
        return redirect(url_for("auth_views.dashboard"))

    # (opcional) confirmar pagamento via Stripe API:
    # checkout = stripe.checkout.Session.retrieve(session_id)

    return render_template("thank_you.html")
