from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), default='admin')

class VehicleRegistry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(30), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    local_government = db.Column(db.String(60), nullable=False)
    state_of_registration = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'plate_number': self.plate_number,
            'model': self.model,
            'color': self.color,
            'year': self.year,
            'local_government': self.local_government,
            'state_of_registration': self.state_of_registration,
        }

class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle = db.Column(db.String(20), nullable=True)
    entry_time = db.Column(db.DateTime, nullable=True)

    @property
    def is_simulation_slot(self):
        return self.id <= 20

    @property
    def zone(self):
        return 'simulation' if self.is_simulation_slot else 'real_user'

    @property
    def zone_label(self):
        return 'Simulation' if self.is_simulation_slot else 'Real User'

    @property
    def slot_number(self):
        return self.id if self.is_simulation_slot else self.id - 20

    @property
    def slot_label(self):
        prefix = 'S' if self.is_simulation_slot else 'R'
        return f'{prefix}{self.slot_number}'

    def to_dict(self):
        return {
            'id': self.id,
            'slot_label': self.slot_label,
            'slot_number': self.slot_number,
            'zone': self.zone,
            'zone_label': self.zone_label,
            'vehicle': self.vehicle,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'is_occupied': self.vehicle is not None
        }

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False, default='card_payment')
    slot_id = db.Column(db.Integer, nullable=True)
    parked_at = db.Column(db.DateTime, nullable=True)
    exited_at = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'vehicle': self.vehicle,
            'amount': self.amount,
            'slot_id': self.slot_id,
            'parked_at': self.parked_at.isoformat() if self.parked_at else None,
            'exited_at': self.exited_at.isoformat() if self.exited_at else None,
            'duration_minutes': self.duration_minutes,
            'payment_method': self.payment_method,
            'timestamp': self.timestamp.isoformat()
        }
