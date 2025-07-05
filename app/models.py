from datetime import datetime
from app.main import db
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    accepted_terms = db.Column(db.Boolean, default=False)
    accepted_privacy = db.Column(db.Boolean, default=False)
    reset_token = db.Column(db.String(256), nullable=True)

    # Plano simplificado
    plan = db.Column(db.String(20), default='CosmicLife')  # único plano
    is_admin = db.Column(db.Boolean, default=False)

    # Controles mensais
    guru_questions_used = db.Column(db.Integer, default=0)
    compatibility_used = db.Column(db.Boolean, default=False)
    last_reset = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class TestSession(db.Model):
    __tablename__ = 'test_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Dados fornecidos pelo usuário
    full_name = db.Column(db.String(255), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    birth_time = db.Column(db.Time, nullable=True)
    birth_city = db.Column(db.String(100), nullable=True)
    birth_country = db.Column(db.String(100), nullable=True)

    # Dados calculados
    sun_sign = db.Column(db.String(50), nullable=True)
    moon_sign = db.Column(db.String(50), nullable=True)
    ascendant = db.Column(db.String(50), nullable=True)
    life_path = db.Column(db.String(10), nullable=True)
    soul_urge = db.Column(db.String(10), nullable=True)
    expression = db.Column(db.String(10), nullable=True)

    # Resultado final
    ai_result = db.Column(db.Text, nullable=True)


class PromptLog(db.Model):
    __tablename__ = 'prompt_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(255), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<PromptLog {self.id} – {self.user_email} at {self.created_at}>"


class GuruQuestion(db.Model):
    __tablename__ = 'guru_questions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LoveCompatibility(db.Model):
    __tablename__ = 'love_compatibility'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    target_name = db.Column(db.String(100))
    target_birth_date = db.Column(db.Date)
    target_birth_time = db.Column(db.Time)
    target_birth_city = db.Column(db.String(100))
    target_birth_country = db.Column(db.String(100))
    result_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LoveCompatibility {self.id} – User {self.user_id}>"

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_session_id = db.Column(db.String(128), nullable=False, unique=True)
    amount = db.Column(db.Numeric(10, 2), default=Decimal("29.90"))
    status = db.Column(db.String(20), default="paid")  # ex: 'paid'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='payments')

    def __repr__(self):
        return f"<Payment {self.id} – User {self.user_id} – {self.status}>"
    