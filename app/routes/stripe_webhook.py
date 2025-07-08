# app/routes/stripe_webhook.py
import os
import stripe
from flask import Blueprint, request, jsonify, current_app

from app.main   import db
from app.models import Payment, User

stripe_webhook_bp = Blueprint("stripe_webhook", __name__, url_prefix="/stripe")

stripe.api_key  = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")


@stripe_webhook_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")    # header exato

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Signature/payload error → {e}")
        return jsonify(success=False), 400

    # ── Apenas checkout.session.completed nos interessa ────────────────────
    if event["type"] == "checkout.session.completed":
        sess              = event["data"]["object"]
        stripe_session_id = sess["id"]
        amount_total      = (sess.get("amount_total") or 0) / 100  # cents → USD

        # 1) Pega e-mail direto
        user_email = sess.get("customer_email")

        # 2) Fallback: customer_details.email
        if not user_email:
            user_email = (sess.get("customer_details") or {}).get("email")

        # 3) Último esforço: consulta Customer
        if not user_email and sess.get("customer"):
            try:
                cust = stripe.Customer.retrieve(sess["customer"])
                user_email = cust.get("email")
            except Exception as e:
                current_app.logger.error(f"[STRIPE WEBHOOK] Customer lookup failed: {e}")

        if not user_email:
            current_app.logger.error("[STRIPE WEBHOOK] Checkout session missing e-mail")
            return jsonify(success=False), 400

        user = User.query.filter_by(email=user_email.lower()).first()
        if not user:
            current_app.logger.error(f"[STRIPE WEBHOOK] No user with e-mail {user_email}")
            return jsonify(success=False), 400

        # Idempotência — só processa se ainda não existir
        if Payment.query.filter_by(stripe_session_id=stripe_session_id).first():
            current_app.logger.info(f"[STRIPE WEBHOOK] Session {stripe_session_id} already stored")
        else:
            # ❶ Insere pagamento
            db.session.add(
                Payment(
                    user_id=user.id,
                    stripe_session_id=stripe_session_id,
                    amount=amount_total,
                    status="paid",
                )
            )

            # ❷ Reseta créditos de uso
            user.reset_credits()

            db.session.commit()
            current_app.logger.info(
                f"[STRIPE WEBHOOK] ✔ Payment saved & credits reset – user {user.id} – ${amount_total}"
            )

    return jsonify(success=True), 200  # ignora outros eventos
