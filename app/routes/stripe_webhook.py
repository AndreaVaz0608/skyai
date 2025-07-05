import os
import stripe
from flask import Blueprint, request, jsonify, current_app
from app.main import db
from app.models import Payment

# 📌 Cria blueprint dedicado
stripe_webhook_bp = Blueprint('stripe_webhook', __name__, url_prefix='/stripe')

# 📌 Chave de verificação do webhook
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")


@stripe_webhook_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')

    try:
        # ✅ Verifica a assinatura
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Invalid payload: {e}")
        return jsonify(success=False), 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.error(f"[STRIPE WEBHOOK] Invalid signature: {e}")
        return jsonify(success=False), 400

    # 📌 Processa eventos de interesse
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata'].get('user_id')
        stripe_session_id = session['id']
        amount_total = session['amount_total'] / 100  # Stripe retorna em centavos

        # ⚡️ Marca pagamento no banco se ainda não existir
        existing = Payment.query.filter_by(stripe_session_id=stripe_session_id).first()
        if existing:
            current_app.logger.info(f"[STRIPE WEBHOOK] Payment já registrado: {stripe_session_id}")
        else:
            payment = Payment(
                user_id=user_id,
                stripe_session_id=stripe_session_id,
                amount=amount_total,
                status='paid'
            )
            db.session.add(payment)
            db.session.commit()
            current_app.logger.info(f"[STRIPE WEBHOOK] Novo pagamento registrado para User {user_id}")

    else:
        current_app.logger.info(f"[STRIPE WEBHOOK] Ignored event: {event['type']}")

    return jsonify(success=True), 200
