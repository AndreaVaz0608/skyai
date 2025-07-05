import os
import stripe
from flask import Blueprint, request, jsonify, current_app
from app.main import db
from app.models import Payment, User

# 📌 Cria blueprint dedicado para webhook
stripe_webhook_bp = Blueprint('stripe_webhook', __name__, url_prefix='/stripe')

# 📌 Chaves do Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

@stripe_webhook_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')

    try:
        # ✅ Verifica assinatura
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Invalid payload: {e}")
        return jsonify(success=False), 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Invalid signature: {e}")
        return jsonify(success=False), 400

    # 📌 Processa evento de pagamento concluído
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        # ⚡️ Link fixo NÃO tem metadata, usa customer_email
        user_email = session.get('customer_email')
        stripe_session_id = session['id']
        amount_total = session['amount_total'] / 100

        if not user_email:
            current_app.logger.error(f"[STRIPE WEBHOOK] No customer_email found.")
            return jsonify(success=False), 400

        user = User.query.filter_by(email=user_email).first()
        if not user:
            current_app.logger.error(f"[STRIPE WEBHOOK] No user found for email: {user_email}")
            return jsonify(success=False), 400

        # ⚡️ Só registra se não existir
        existing = Payment.query.filter_by(stripe_session_id=stripe_session_id).first()
        if existing:
            current_app.logger.info(f"[STRIPE WEBHOOK] Payment já registrado: {stripe_session_id}")
        else:
            payment = Payment(
                user_id=user.id,
                stripe_session_id=stripe_session_id,
                amount=amount_total,
                status='paid'
            )
            db.session.add(payment)
            db.session.commit()
            current_app.logger.info(f"[STRIPE WEBHOOK] ✔️ Novo pagamento registrado para user {user.id} ({user_email})")

    else:
        current_app.logger.info(f"[STRIPE WEBHOOK] Ignored event: {event['type']}")

    return jsonify(success=True), 200
