# app/routes/stripe_webhook.py  (replace the existing file)

import os, stripe
from flask import Blueprint, request, jsonify, current_app
from app.main   import db
from app.models import Payment, User

stripe_webhook_bp = Blueprint("stripe_webhook", __name__, url_prefix="/stripe")

stripe.api_key      = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret     = os.getenv("STRIPE_WEBHOOK_SECRET")


@stripe_webhook_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload     = request.data
    sig_header  = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Signature / payload error → {e}")
        return jsonify(success=False), 400

    # ── Handle successful payments ────────────────────────────────
    if event["type"] == "checkout.session.completed":
        sess               = event["data"]["object"]
        stripe_session_id  = sess["id"]
        amount_total       = sess["amount_total"] / 100      # cents → dollars

        # Works both for Payment Links and “classic” Checkouts
        user_email = (
            sess.get("customer_email")
            or (sess.get("customer_details") or {}).get("email")
        )

        if not user_email:
            current_app.logger.error("[STRIPE WEBHOOK] No e-mail in session")
            return jsonify(success=False), 400

        user = User.query.filter_by(email=user_email).first()
        if not user:
            current_app.logger.error(f"[STRIPE WEBHOOK] No user with e-mail {user_email}")
            return jsonify(success=False), 400

        # Only insert once
        exists = Payment.query.filter_by(stripe_session_id=stripe_session_id).first()
        if exists:
            current_app.logger.info(f"[STRIPE WEBHOOK] Session {stripe_session_id} already saved")
        else:
            db.session.add(
                Payment(
                    user_id=user.id,
                    stripe_session_id=stripe_session_id,
                    amount=amount_total,
                    status="paid",
                )
            )
            db.session.commit()
            current_app.logger.info(
                f"[STRIPE WEBHOOK] ✔ Payment saved for user {user.id} – ${amount_total}"
            )

    return jsonify(success=True), 200
