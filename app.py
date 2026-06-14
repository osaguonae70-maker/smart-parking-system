import os
import random
import re
import string
import ipaddress
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, send_from_directory
from flask_login import LoginManager, login_required, current_user
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
try:
    from flask_cors import CORS
except Exception:
    CORS = None
from models import db, User, Slot, Payment, VehicleRegistry
from auth import auth as auth_blueprint
from werkzeug.security import generate_password_hash
import pandas as pd
from io import BytesIO
from functools import wraps
from sqlalchemy import text, case

if load_dotenv is not None:
    load_dotenv()


def normalize_database_url(database_url):
    if not database_url:
        return None

    normalized = database_url.strip()
    if normalized.startswith('postgres://'):
        return normalized.replace('postgres://', 'postgresql+psycopg://', 1)
    if normalized.startswith('postgresql://') and not normalized.startswith('postgresql+psycopg://'):
        return normalized.replace('postgresql://', 'postgresql+psycopg://', 1)
    return normalized


app = Flask(__name__)

database_url = normalize_database_url(os.environ.get('DATABASE_URL'))
if not database_url:
    database_url = 'sqlite:///parking.db'

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if not database_url.startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

db.init_app(app)
portal_origin_env = os.environ.get('PORTAL_ORIGIN', '').strip()
portal_origins = '*'
if portal_origin_env:
    portal_origins = [o.strip() for o in portal_origin_env.split(',') if o.strip()]
if CORS is not None:
    CORS(app, resources={r"/api/*": {"origins": portal_origins}})

admin_local_only = os.environ.get('ADMIN_LOCAL_ONLY', '0').strip() not in {'0', 'false', 'False', 'no', 'No'}

def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr

def is_private_or_loopback_ip(value):
    try:
        ip = ipaddress.ip_address(value)
    except Exception:
        return False
    return ip.is_private or ip.is_loopback

@app.before_request
def restrict_admin_to_local_network():
    if not admin_local_only:
        return

    path = request.path or ''
    is_admin_path = (
        path.startswith('/admin') or
        path.startswith('/admin-login') or
        path.startswith('/api/admin')
    )
    if not is_admin_path:
        return

    client_ip = get_client_ip()
    if not client_ip:
        return
    if client_ip and is_private_or_loopback_ip(client_ip):
        return

    abort(403)

login_manager = LoginManager()
login_manager.login_view = 'auth.admin_login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

DEFAULT_CAMERAS_COUNT = 8
MAINTENANCE_SENSOR_MONTHLY = 500.00
MAINTENANCE_CAMERA_MONTHLY = 1500.00
MAINTENANCE_MISC_MONTHLY = 5000.00
PARKING_RATE_PER_HOUR = 200.00
TOTAL_PARKING_SPACES = 50
SIMULATION_SPACE_COUNT = 20
REAL_USER_SPACE_COUNT = 30
SIMULATION_REFRESH_SECONDS = 3

PAYMENT_METHODS = [
    {'key': 'card_payment', 'label': 'Card Payment'},
    {'key': 'bank_transfer', 'label': 'Bank Transfer'},
    {'key': 'crypto', 'label': 'Crypto'},
]

NIGERIAN_REGISTRATION_CODES = [
    {'code': 'ABJ', 'local_government': 'Abuja Municipal', 'state': 'Federal Capital Territory'},
    {'code': 'KSF', 'local_government': 'Keffi', 'state': 'Nasarawa'},
    {'code': 'LND', 'local_government': 'Lagos Mainland', 'state': 'Lagos'},
    {'code': 'KJA', 'local_government': 'Kajuru', 'state': 'Kaduna'},
    {'code': 'KTU', 'local_government': 'Kano Municipal', 'state': 'Kano'},
    {'code': 'NSR', 'local_government': 'Nasarawa', 'state': 'Nasarawa'},
]

NIGERIAN_VEHICLE_MODELS = [
    'Toyota Corolla',
    'Toyota Camry',
    'Toyota Highlander',
    'Toyota Sienna',
    'Lexus RX350',
    'Lexus ES350',
    'Honda Accord',
    'Honda Civic',
    'Hyundai Elantra',
    'Kia Sportage',
    'Mercedes-Benz C300',
    'Mercedes-Benz GLK',
    'BMW X5',
    'Peugeot 406',
]

NIGERIAN_VEHICLE_COLORS = [
    'Black',
    'White',
    'Silver',
    'Gray',
    'Blue',
    'Red',
    'Green',
]

SIMULATED_SLOTS = set()
SIMULATED_SLOT_VEHICLES = {}
SIMULATED_SLOT_LIMIT = SIMULATION_SPACE_COUNT
REAL_USER_SLOT_START = SIMULATED_SLOT_LIMIT + 1
REAL_USER_SLOT_END = TOTAL_PARKING_SPACES
SIMULATION_SLOT_IDS = set(range(1, SIMULATION_SPACE_COUNT + 1))
REAL_USER_SLOT_IDS = set(range(REAL_USER_SLOT_START, REAL_USER_SLOT_END + 1))

def get_payment_method_label(method_key):
    for m in PAYMENT_METHODS:
        if m['key'] == method_key:
            return m['label']
    return method_key

def random_payment_method_key():
    return random.choice(PAYMENT_METHODS)['key']

def is_valid_payment_method_key(method_key):
    return any(m['key'] == method_key for m in PAYMENT_METHODS)

def is_simulation_slot_id(slot_id):
    try:
        return int(slot_id) in SIMULATION_SLOT_IDS
    except (TypeError, ValueError):
        return False

def is_real_user_slot_id(slot_id):
    try:
        return int(slot_id) in REAL_USER_SLOT_IDS
    except (TypeError, ValueError):
        return False

def get_slot_zone(slot_id):
    if is_simulation_slot_id(slot_id):
        return 'simulation'
    if is_real_user_slot_id(slot_id):
        return 'real_user'
    return 'unknown'

def get_slot_zone_label(slot_id):
    zone = get_slot_zone(slot_id)
    if zone == 'simulation':
        return 'Simulation'
    if zone == 'real_user':
        return 'Real User'
    return 'Unknown'

def get_slot_number(slot_id):
    slot_id_int = int(slot_id)
    return slot_id_int if is_simulation_slot_id(slot_id_int) else slot_id_int - SIMULATION_SPACE_COUNT

def get_slot_label(slot_id):
    if slot_id is None:
        return None
    slot_number = get_slot_number(slot_id)
    return f"S{slot_number}" if is_simulation_slot_id(slot_id) else f"R{slot_number}"

def format_duration(seconds):
    try:
        seconds_int = int(seconds)
    except Exception:
        seconds_int = 0

    if seconds_int < 0:
        seconds_int = 0

    minutes = seconds_int // 60
    hours = minutes // 60
    days = hours // 24
    rem_hours = hours % 24
    rem_minutes = minutes % 60

    if days > 0:
        text = f"{days}d {rem_hours}h {rem_minutes}m"
    elif hours > 0:
        text = f"{hours}h {rem_minutes}m"
    else:
        text = f"{minutes}m"

    return {
        'seconds': seconds_int,
        'minutes': int(minutes),
        'hours': float(seconds_int) / 3600,
        'text': text,
    }

def format_duration_from_minutes(minutes):
    try:
        minutes_int = int(minutes)
    except Exception:
        minutes_int = 0
    return format_duration(minutes_int * 60)

def infer_registration_state(plate_number):
    plate = (plate_number or '').strip().upper()
    prefix = plate.split('-', 1)[0]
    for item in NIGERIAN_REGISTRATION_CODES:
        if item['code'] == prefix:
            return item['state']
    return 'Custom Entry'

def infer_local_government(plate_number):
    plate = (plate_number or '').strip().upper()
    prefix = plate.split('-', 1)[0]
    for item in NIGERIAN_REGISTRATION_CODES:
        if item['code'] == prefix:
            return item['local_government']
    return 'Custom Entry'

def is_nigerian_plate_number(plate_number):
    codes = '|'.join(item['code'] for item in NIGERIAN_REGISTRATION_CODES)
    return bool(re.match(rf'^({codes})-\d{{3}}[A-Z]{{2}}$', (plate_number or '').strip().upper()))

def generate_vehicle_number():
    registration = random.choice(NIGERIAN_REGISTRATION_CODES)
    digits = ''.join(random.choices(string.digits, k=3))
    suffix = ''.join(random.choices(string.ascii_uppercase, k=2))
    return f"{registration['code']}-{digits}{suffix}"

def generate_unique_vehicle_number(max_attempts=20):
    for _ in range(max_attempts):
        candidate = generate_vehicle_number()
        if Slot.query.filter_by(vehicle=candidate).first() is None and VehicleRegistry.query.filter_by(plate_number=candidate).first() is None:
            return candidate
    return generate_vehicle_number()

def create_vehicle_registry_record(plate_number):
    record = VehicleRegistry(
        plate_number=plate_number,
        model=random.choice(NIGERIAN_VEHICLE_MODELS),
        color=random.choice(NIGERIAN_VEHICLE_COLORS),
        year=random.randint(2016, 2024),
        local_government=infer_local_government(plate_number),
        state_of_registration=infer_registration_state(plate_number)
    )
    db.session.add(record)
    db.session.flush()
    return record

def get_vehicle_registry(plate_number):
    normalized_plate = (plate_number or '').strip().upper()
    if not normalized_plate:
        return None
    return VehicleRegistry.query.filter_by(plate_number=normalized_plate).first()

def get_or_create_vehicle_registry(plate_number):
    normalized_plate = (plate_number or '').strip().upper()
    if not normalized_plate:
        return None

    record = get_vehicle_registry(normalized_plate)
    if record:
        return record

    return create_vehicle_registry_record(normalized_plate)

def backfill_vehicle_registry():
    plates = set()
    for slot in Slot.query.filter(Slot.vehicle != None).all():
        if slot.vehicle:
            plates.add(slot.vehicle.strip().upper())
    for payment in Payment.query.filter(Payment.vehicle != None).all():
        if payment.vehicle:
            plates.add(payment.vehicle.strip().upper())

    created = False
    for plate in sorted(plates):
        if not get_vehicle_registry(plate):
            create_vehicle_registry_record(plate)
            created = True

    if created:
        db.session.commit()

def sync_vehicle_registry_metadata():
    changed = False
    for record in VehicleRegistry.query.all():
        expected_state = infer_registration_state(record.plate_number)
        expected_local_government = infer_local_government(record.plate_number)
        if record.state_of_registration != expected_state:
            record.state_of_registration = expected_state
            changed = True
        if getattr(record, 'local_government', None) != expected_local_government:
            record.local_government = expected_local_government
            changed = True

    if changed:
        db.session.commit()

def summarize_registry_group(rows, label_key):
    return [
        {
            label_key: row[0],
            'count': int(row[1] or 0),
        }
        for row in rows
    ]

def get_vehicle_registry_analytics():
    total_registered = VehicleRegistry.query.count()
    mapped_prefix_count = VehicleRegistry.query.filter(
        db.or_(*[VehicleRegistry.plate_number.like(f"{item['code']}-%") for item in NIGERIAN_REGISTRATION_CODES])
    ).count() if NIGERIAN_REGISTRATION_CODES else 0

    by_state_rows = db.session.query(
        VehicleRegistry.state_of_registration,
        db.func.count(VehicleRegistry.id)
    ).filter(
        VehicleRegistry.state_of_registration != 'Custom Entry'
    ).group_by(
        VehicleRegistry.state_of_registration
    ).order_by(
        db.func.count(VehicleRegistry.id).desc(),
        VehicleRegistry.state_of_registration.asc()
    ).limit(5).all()

    by_lga_rows = db.session.query(
        VehicleRegistry.local_government,
        db.func.count(VehicleRegistry.id)
    ).filter(
        VehicleRegistry.local_government != 'Custom Entry'
    ).group_by(
        VehicleRegistry.local_government
    ).order_by(
        db.func.count(VehicleRegistry.id).desc(),
        VehicleRegistry.local_government.asc()
    ).limit(5).all()

    by_model_rows = db.session.query(
        VehicleRegistry.model,
        db.func.count(VehicleRegistry.id)
    ).group_by(
        VehicleRegistry.model
    ).order_by(
        db.func.count(VehicleRegistry.id).desc(),
        VehicleRegistry.model.asc()
    ).limit(5).all()

    by_color_rows = db.session.query(
        VehicleRegistry.color,
        db.func.count(VehicleRegistry.id)
    ).group_by(
        VehicleRegistry.color
    ).order_by(
        db.func.count(VehicleRegistry.id).desc(),
        VehicleRegistry.color.asc()
    ).limit(5).all()

    return {
        'total_registered': int(total_registered),
        'mapped_prefix_count': int(mapped_prefix_count),
        'mapped_prefix_rate': round((mapped_prefix_count / total_registered) * 100, 2) if total_registered else 0.0,
        'top_states': summarize_registry_group(by_state_rows, 'state'),
        'top_local_governments': summarize_registry_group(by_lga_rows, 'local_government'),
        'top_models': summarize_registry_group(by_model_rows, 'model'),
        'top_colors': summarize_registry_group(by_color_rows, 'color'),
    }

def migrate_sensor_vehicles():
    sensor_slots = Slot.query.filter(Slot.vehicle.like('SENSOR-%')).all()
    if not sensor_slots:
        return

    changed = False
    for slot in sensor_slots:
        slot.vehicle = generate_unique_vehicle_number()
        get_or_create_vehicle_registry(slot.vehicle)
        changed = True

    if changed:
        db.session.commit()

def is_simulated_slot(slot_id, vehicle=None):
    return is_simulation_slot_id(slot_id)

def calculate_fee(entry_time, exit_time=None):
    if not entry_time:
        return 0.0
    effective_exit_time = exit_time or datetime.utcnow()
    duration_hours = max(0, (effective_exit_time - entry_time).total_seconds()) / 3600
    return round(max(1, duration_hours) * PARKING_RATE_PER_HOUR, 2)

def build_simulation_entry_time(reference_time=None):
    now = reference_time or datetime.utcnow()
    age_minutes = random.randint(60, 300)
    age_seconds = random.randint(0, 59)
    return now - timedelta(minutes=age_minutes, seconds=age_seconds)

def populate_simulation_slot(slot, reference_time=None):
    slot.vehicle = generate_unique_vehicle_number()
    get_or_create_vehicle_registry(slot.vehicle)
    slot.entry_time = build_simulation_entry_time(reference_time)
    SIMULATED_SLOTS.add(slot.id)
    SIMULATED_SLOT_VEHICLES[slot.id] = slot.vehicle
    return slot

def maintain_simulation_occupancy(reference_time=None, commit=True):
    simulation_slots = Slot.query.filter(Slot.id.in_(list(SIMULATION_SLOT_IDS))).order_by(Slot.id).all()
    changed = False
    for slot in simulation_slots:
        if slot.vehicle:
            if not is_nigerian_plate_number(slot.vehicle):
                slot.vehicle = generate_unique_vehicle_number()
                get_or_create_vehicle_registry(slot.vehicle)
                changed = True
            elif not get_vehicle_registry(slot.vehicle):
                get_or_create_vehicle_registry(slot.vehicle)
                changed = True
            SIMULATED_SLOTS.add(slot.id)
            SIMULATED_SLOT_VEHICLES[slot.id] = slot.vehicle
            continue
        populate_simulation_slot(slot, reference_time)
        changed = True

    if changed and commit:
        db.session.commit()

    return changed

def serialize_slot(slot, reference_time=None):
    payload = slot.to_dict()
    now = reference_time or datetime.utcnow()
    duration = None
    current_fee = 0.0
    vehicle_record = get_vehicle_registry(slot.vehicle) if slot.vehicle else None
    if slot.entry_time:
        duration_seconds = max(0, int((now - slot.entry_time).total_seconds()))
        duration = format_duration(duration_seconds)
        current_fee = calculate_fee(slot.entry_time, now)

    payload.update({
        'zone': get_slot_zone(slot.id),
        'zone_label': get_slot_zone_label(slot.id),
        'slot_label': get_slot_label(slot.id),
        'is_simulation_slot': is_simulation_slot_id(slot.id),
        'duration': duration,
        'current_fee': current_fee,
        'plate_number': slot.vehicle,
        'vehicle_record': vehicle_record.to_dict() if vehicle_record else None,
    })
    return payload

def vehicles_parked_today_count():
    today = datetime.utcnow().date()
    active_today = Slot.query.filter(Slot.entry_time != None, db.func.date(Slot.entry_time) == today).count()
    completed_today = Payment.query.filter(Payment.parked_at != None, db.func.date(Payment.parked_at) == today).count()
    return int(active_today + completed_today)

def get_dashboard_metrics():
    simulation_occupied = Slot.query.filter(Slot.id.in_(list(SIMULATION_SLOT_IDS)), Slot.vehicle != None).count()
    real_user_occupied = Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle != None).count()
    total_occupied = simulation_occupied + real_user_occupied
    total_available = TOTAL_PARKING_SPACES - total_occupied

    simulation_revenue = db.session.query(db.func.sum(Payment.amount)).filter(Payment.slot_id.in_(list(SIMULATION_SLOT_IDS))).scalar() or 0
    real_user_revenue = db.session.query(db.func.sum(Payment.amount)).filter(Payment.slot_id.in_(list(REAL_USER_SLOT_IDS))).scalar() or 0
    combined_revenue = db.session.query(db.func.sum(Payment.amount)).scalar() or 0

    return {
        'total_spaces': TOTAL_PARKING_SPACES,
        'simulation_spaces': SIMULATION_SPACE_COUNT,
        'real_user_spaces': REAL_USER_SPACE_COUNT,
        'simulation_occupied': int(simulation_occupied),
        'real_user_occupied': int(real_user_occupied),
        'total_occupied': int(total_occupied),
        'total_parked': int(total_occupied),
        'total_available_spaces': int(total_available),
        'available_slots': int(total_available),
        'simulation_revenue': float(simulation_revenue),
        'real_user_revenue': float(real_user_revenue),
        'combined_revenue': float(combined_revenue),
        'simulation_occupancy_rate': round((simulation_occupied / SIMULATION_SPACE_COUNT) * 100, 2),
        'real_user_occupancy_rate': round((real_user_occupied / REAL_USER_SPACE_COUNT) * 100, 2),
        'total_occupancy_rate': round((total_occupied / TOTAL_PARKING_SPACES) * 100, 2),
        'vehicles_parked_today': vehicles_parked_today_count(),
        'total_revenue': float(combined_revenue),
    }

@app.before_request
def maintain_simulation_zone():
    path = request.path or ''
    if path.startswith('/static/'):
        return
    maintain_simulation_occupancy()

def get_revenue_series(days=7):
    if days < 1:
        days = 1

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)
    start_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    rows = db.session.query(
        db.func.date(Payment.timestamp).label('d'),
        db.func.sum(Payment.amount).label('amt'),
    ).filter(
        Payment.timestamp >= start_dt
    ).group_by(
        db.func.date(Payment.timestamp)
    ).all()

    by_day = {row.d: float(row.amt or 0) for row in rows}
    series = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        series.append({'date': d, 'amount': by_day.get(d, 0.0)})
    return series

def create_payment_record(vehicle, amount, payment_method, exit_time, entry_time=None, slot_id=None):
    duration_minutes = None
    if entry_time:
        duration_seconds = max(0, int((exit_time - entry_time).total_seconds()))
        duration_minutes = max(0, duration_seconds // 60)

    payment = Payment(
        vehicle=vehicle,
        amount=amount,
        payment_method=payment_method,
        slot_id=slot_id,
        parked_at=entry_time,
        exited_at=exit_time,
        duration_minutes=duration_minutes,
        timestamp=exit_time
    )
    db.session.add(payment)
    return payment

def checkout_slot(slot, payment_method=None, exit_time=None, refill_simulation=False, commit=True):
    if not slot or not slot.vehicle or not slot.entry_time:
        return None

    resolved_payment_method = payment_method or random_payment_method_key()
    if not is_valid_payment_method_key(resolved_payment_method):
        resolved_payment_method = 'card_payment'

    resolved_exit_time = exit_time or datetime.utcnow()
    fee = calculate_fee(slot.entry_time, resolved_exit_time)
    duration = format_duration((resolved_exit_time - slot.entry_time).total_seconds())
    released_vehicle = slot.vehicle
    released_entry_time = slot.entry_time
    slot_id = slot.id

    create_payment_record(
        vehicle=released_vehicle,
        amount=fee,
        payment_method=resolved_payment_method,
        exit_time=resolved_exit_time,
        entry_time=released_entry_time,
        slot_id=slot_id
    )

    slot.vehicle = None
    slot.entry_time = None
    SIMULATED_SLOTS.discard(slot_id)
    SIMULATED_SLOT_VEHICLES.pop(slot_id, None)

    replacement = None
    if refill_simulation and is_simulation_slot_id(slot_id):
        replacement = populate_simulation_slot(slot, resolved_exit_time)

    if commit:
        db.session.commit()

    return {
        'slot_id': slot_id,
        'slot_label': get_slot_label(slot_id),
        'vehicle': released_vehicle,
        'entry_time': released_entry_time,
        'exit_time': resolved_exit_time,
        'fee': fee,
        'duration': duration,
        'payment_method': resolved_payment_method,
        'payment_method_label': get_payment_method_label(resolved_payment_method),
        'replacement_vehicle': replacement.vehicle if replacement else None,
        'replacement_entry_time': replacement.entry_time.isoformat() if replacement and replacement.entry_time else None,
    }

def get_maintenance_figures():
    sensors_count = Slot.query.count()
    cameras_count = DEFAULT_CAMERAS_COUNT
    sensors_monthly = round(sensors_count * MAINTENANCE_SENSOR_MONTHLY, 2)
    cameras_monthly = round(cameras_count * MAINTENANCE_CAMERA_MONTHLY, 2)
    misc_monthly = round(MAINTENANCE_MISC_MONTHLY, 2)
    total_monthly = round(sensors_monthly + cameras_monthly + misc_monthly, 2)
    total_weekly = round(total_monthly / 4, 2)
    total_yearly = round(total_monthly * 12, 2)

    return {
        'sensors_count': sensors_count,
        'cameras_count': cameras_count,
        'sensors_monthly': sensors_monthly,
        'cameras_monthly': cameras_monthly,
        'misc_monthly': misc_monthly,
        'total_monthly': total_monthly,
        'total_weekly': total_weekly,
        'total_yearly': total_yearly,
    }

def get_recent_parking_history(limit=20):
    rows = Payment.query.order_by(Payment.timestamp.desc()).limit(limit).all()
    history = []
    for row in rows:
        duration = format_duration_from_minutes(row.duration_minutes) if row.duration_minutes is not None else None
        slot_label = get_slot_label(row.slot_id) if row.slot_id else None
        vehicle_record = get_vehicle_registry(row.vehicle) if row.vehicle else None
        history.append({
            'id': row.id,
            'vehicle': row.vehicle,
            'slot_id': row.slot_id,
            'slot_label': slot_label,
            'zone': get_slot_zone(row.slot_id) if row.slot_id else None,
            'zone_label': get_slot_zone_label(row.slot_id) if row.slot_id else None,
            'amount': float(row.amount or 0),
            'payment_method': row.payment_method,
            'payment_method_label': get_payment_method_label(row.payment_method),
            'parked_at': row.parked_at.isoformat() if row.parked_at else None,
            'exited_at': row.exited_at.isoformat() if row.exited_at else (row.timestamp.isoformat() if row.timestamp else None),
            'duration': duration,
            'timestamp': row.timestamp.isoformat() if row.timestamp else None,
            'vehicle_record': vehicle_record.to_dict() if vehicle_record else None,
        })
    return history

def get_payment_methods_today():
    today = datetime.utcnow().date()
    rows = db.session.query(
        Payment.payment_method.label('method'),
        db.func.count(Payment.id).label('count'),
        db.func.sum(Payment.amount).label('amount'),
    ).filter(
        db.func.date(Payment.timestamp) == today
    ).group_by(
        Payment.payment_method
    ).all()

    by_method = {row.method: {'count': int(row.count), 'amount': float(row.amount or 0)} for row in rows}
    result = []
    for m in PAYMENT_METHODS:
        stats = by_method.get(m['key'], {'count': 0, 'amount': 0.0})
        result.append({'key': m['key'], 'label': m['label'], **stats})
    return result

def get_revenue_history(view='daily', day=None, month=None, year=None, limit=31):
    allowed_views = {'daily', 'monthly', 'yearly'}
    selected_view = view if view in allowed_views else 'daily'

    query = Payment.query
    active_filter_label = 'All records'
    selected_day = (day or '').strip()
    selected_month = (month or '').strip()
    selected_year = (year or '').strip()

    if selected_view == 'daily':
        period_expr = db.func.date(Payment.timestamp)
        if selected_day:
            try:
                parsed_day = datetime.strptime(selected_day, '%Y-%m-%d').date()
                selected_day = parsed_day.isoformat()
                query = query.filter(db.func.date(Payment.timestamp) == selected_day)
                active_filter_label = parsed_day.strftime('%d %b %Y')
            except ValueError:
                selected_day = ''
    elif selected_view == 'monthly':
        period_expr = db.func.strftime('%Y-%m', Payment.timestamp)
        if selected_month:
            try:
                parsed_month = datetime.strptime(selected_month, '%Y-%m')
                selected_month = parsed_month.strftime('%Y-%m')
                query = query.filter(db.func.strftime('%Y-%m', Payment.timestamp) == selected_month)
                active_filter_label = parsed_month.strftime('%B %Y')
            except ValueError:
                selected_month = ''
    else:
        period_expr = db.func.strftime('%Y', Payment.timestamp)
        if selected_year:
            if selected_year.isdigit() and len(selected_year) == 4:
                query = query.filter(db.func.strftime('%Y', Payment.timestamp) == selected_year)
                active_filter_label = selected_year
            else:
                selected_year = ''

    rows = query.with_entities(
        period_expr.label('period_key'),
        db.func.count(Payment.id).label('transactions'),
        db.func.sum(Payment.amount).label('total_amount'),
        db.func.sum(case((Payment.payment_method == 'card_payment', Payment.amount), else_=0)).label('card_amount'),
        db.func.sum(case((Payment.payment_method == 'bank_transfer', Payment.amount), else_=0)).label('bank_transfer_amount'),
        db.func.sum(case((Payment.payment_method == 'crypto', Payment.amount), else_=0)).label('crypto_amount'),
    ).group_by(
        period_expr
    ).order_by(
        period_expr.desc()
    )

    if not (selected_day or selected_month or selected_year):
        rows = rows.limit(limit)

    history_rows = []
    summary = {
        'total_amount': 0.0,
        'card_amount': 0.0,
        'bank_transfer_amount': 0.0,
        'crypto_amount': 0.0,
        'transactions': 0,
    }

    for row in rows.all():
        period_key = row.period_key or '-'
        if selected_view == 'daily':
            try:
                period_label = datetime.strptime(period_key, '%Y-%m-%d').strftime('%d %b %Y')
            except ValueError:
                period_label = period_key
        elif selected_view == 'monthly':
            try:
                period_label = datetime.strptime(period_key, '%Y-%m').strftime('%B %Y')
            except ValueError:
                period_label = period_key
        else:
            period_label = period_key

        entry = {
            'period_key': period_key,
            'period_label': period_label,
            'transactions': int(row.transactions or 0),
            'total_amount': float(row.total_amount or 0),
            'card_amount': float(row.card_amount or 0),
            'bank_transfer_amount': float(row.bank_transfer_amount or 0),
            'crypto_amount': float(row.crypto_amount or 0),
        }
        history_rows.append(entry)
        summary['transactions'] += entry['transactions']
        summary['total_amount'] += entry['total_amount']
        summary['card_amount'] += entry['card_amount']
        summary['bank_transfer_amount'] += entry['bank_transfer_amount']
        summary['crypto_amount'] += entry['crypto_amount']

    return {
        'rows': history_rows,
        'summary': summary,
        'filters': {
            'view': selected_view,
            'day': selected_day,
            'month': selected_month,
            'year': selected_year,
            'active_filter_label': active_filter_label,
        }
    }

def get_revenue_periods():
    now = datetime.utcnow()
    today = now.date()
    start_of_today = datetime(today.year, today.month, today.day)
    start_of_week = start_of_today - timedelta(days=start_of_today.weekday())
    start_of_month = start_of_today.replace(day=1)
    start_of_year = start_of_today.replace(month=1, day=1)

    daily = db.session.query(db.func.sum(Payment.amount)).filter(Payment.timestamp >= start_of_today).scalar() or 0
    weekly = db.session.query(db.func.sum(Payment.amount)).filter(Payment.timestamp >= start_of_week).scalar() or 0
    monthly = db.session.query(db.func.sum(Payment.amount)).filter(Payment.timestamp >= start_of_month).scalar() or 0
    yearly = db.session.query(db.func.sum(Payment.amount)).filter(Payment.timestamp >= start_of_year).scalar() or 0

    return {
        'daily': float(daily),
        'weekly': float(weekly),
        'monthly': float(monthly),
        'yearly': float(yearly),
    }

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(403)
def access_denied(error):
    return render_template('403.html'), 403

# Create Blueprint for main routes
from flask import Blueprint
main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('landing.html')

@main.route('/portal')
def portal():
    available_slots = Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle == None).count()
    return render_template(
        'index.html',
        available_slots=available_slots,
        total_real_user_spaces=REAL_USER_SPACE_COUNT,
        refresh_seconds=SIMULATION_REFRESH_SECONDS
    )

@main.route('/service-worker.js')
def service_worker():
    return send_from_directory(app.static_folder, 'service-worker.js', mimetype='application/javascript')

@main.route('/park', methods=['POST'])
def park():
    vehicle_number = request.form.get('vehicle_number')
    if not vehicle_number:
        flash('Vehicle number is required')
        return redirect(url_for('main.portal'))

    # Normalize vehicle number: remove whitespace and make uppercase
    vehicle_number = vehicle_number.strip().upper()

    # Check if vehicle already parked
    existing_slot = Slot.query.filter_by(vehicle=vehicle_number).first()
    if existing_slot:
        flash(f'Vehicle {vehicle_number} is already parked at Slot {get_slot_label(existing_slot.id)}')
        return redirect(url_for('main.portal'))

    # Assign next available slot
    slot = Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle == None).order_by(Slot.id).first()
    if not slot:
        flash('No parking slots available!')
        return redirect(url_for('main.portal'))

    slot.vehicle = vehicle_number
    get_or_create_vehicle_registry(vehicle_number)
    slot.entry_time = datetime.utcnow()
    db.session.commit()

    flash(f'Vehicle {vehicle_number} parked at Slot {get_slot_label(slot.id)} at {slot.entry_time.strftime("%Y-%m-%d %H:%M:%S")}')
    return render_template(
        'index.html',
        parked_slot=get_slot_label(slot.id),
        vehicle_number=vehicle_number,
        parked_entry_time=slot.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
        available_slots=Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle == None).count(),
        total_real_user_spaces=REAL_USER_SPACE_COUNT,
        refresh_seconds=SIMULATION_REFRESH_SECONDS
    )

@main.route('/api/park', methods=['POST'])
def api_park():
    data = request.get_json(silent=True) or {}
    vehicle_number = (data.get('vehicle_number') or '').strip().upper()
    if not vehicle_number:
        return jsonify({'error': 'Vehicle number required'}), 400

    existing_slot = Slot.query.filter_by(vehicle=vehicle_number).first()
    if existing_slot:
        return jsonify({'error': f'Vehicle {vehicle_number} is already parked', 'slot_id': existing_slot.id, 'slot_label': get_slot_label(existing_slot.id)}), 409

    slot = Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle == None).order_by(Slot.id).first()
    if not slot:
        return jsonify({'error': 'No parking slots available'}), 409

    slot.vehicle = vehicle_number
    get_or_create_vehicle_registry(vehicle_number)
    slot.entry_time = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'vehicle': vehicle_number,
        'slot_id': slot.id,
        'slot_label': get_slot_label(slot.id),
        'entry_time': slot.entry_time.isoformat(),
        'duration': format_duration(0),
        'available_slots': Slot.query.filter(Slot.id.in_(list(REAL_USER_SLOT_IDS)), Slot.vehicle == None).count()
    })

@main.route('/api/process-exit', methods=['POST'])
def process_exit():
    # This endpoint is called after manual data entry to show fee
    vehicle_number = request.json.get('vehicle_number')
    if not vehicle_number:
        return jsonify({'error': 'Vehicle number required'}), 400
        
    # Normalize lookup
    vehicle_number = vehicle_number.strip().upper()
    slot = Slot.query.filter_by(vehicle=vehicle_number).first()
    
    if not slot:
        return jsonify({'error': f'Vehicle {vehicle_number} not found in any active slot'}), 404

    if is_simulation_slot_id(slot.id):
        return jsonify({'error': 'Simulation vehicles are managed automatically and cannot checkout from the user portal.'}), 403

    if not slot.entry_time:
        return jsonify({'error': 'Entry time missing for this vehicle'}), 400

    exit_time = datetime.utcnow()
    duration_seconds = (exit_time - slot.entry_time).total_seconds()
    fee = calculate_fee(slot.entry_time, exit_time)
    duration_obj = format_duration(duration_seconds)
    
    return jsonify({
        'vehicle': vehicle_number,
        'slot_id': slot.id,
        'slot_label': get_slot_label(slot.id),
        'entry_time': slot.entry_time.isoformat(),
        'exit_time': exit_time.isoformat(),
        'duration': duration_obj,
        'fee': fee
    })

@main.route('/api/pay-and-release', methods=['POST'])
def api_pay_and_release():
    data = request.get_json(silent=True) or {}
    vehicle_number = (data.get('vehicle_number') or '').strip().upper()
    payment_method = data.get('payment_method') or 'card_payment'

    if not vehicle_number:
        return jsonify({'error': 'Vehicle number required'}), 400

    if not is_valid_payment_method_key(payment_method):
        payment_method = 'card_payment'

    slot = Slot.query.filter_by(vehicle=vehicle_number).first()
    if not slot:
        return jsonify({'error': f'Vehicle {vehicle_number} not found in any active slot'}), 404

    if is_simulation_slot_id(slot.id):
        return jsonify({'error': 'Simulation vehicles are managed automatically and cannot checkout from the user portal.'}), 403

    exit_time = datetime.utcnow()
    if not slot.entry_time:
        return jsonify({'error': 'Entry time missing for this vehicle'}), 400

    checkout = checkout_slot(slot, payment_method=payment_method, exit_time=exit_time, refill_simulation=False, commit=True)

    return jsonify({
        'status': 'success',
        'vehicle': vehicle_number,
        'slot_id': checkout['slot_id'],
        'slot_label': checkout['slot_label'],
        'amount': checkout['fee'],
        'entry_time': checkout['entry_time'].isoformat() if checkout['entry_time'] else None,
        'exit_time': checkout['exit_time'].isoformat(),
        'duration': checkout['duration'],
        'payment_method': checkout['payment_method'],
        'payment_method_label': checkout['payment_method_label'],
        'released': True
    })

@main.route('/pay-and-release', methods=['POST'])
def pay_and_release():
    vehicle_number = request.form.get('vehicle_number')
    fee = float(request.form.get('fee'))
    payment_method = request.form.get('payment_method') or 'card_payment'
    
    if not vehicle_number:
        flash('Vehicle number required')
        return redirect(url_for('main.portal'))

    # Normalize lookup
    vehicle_number = vehicle_number.strip().upper()
    slot = Slot.query.filter_by(vehicle=vehicle_number).first()
    if not slot:
        flash(f'Error: Vehicle {vehicle_number} no longer found in system')
        return redirect(url_for('main.portal'))

    if is_simulation_slot_id(slot.id):
        flash('Simulation vehicles are managed automatically and cannot checkout from the user portal.')
        return redirect(url_for('main.portal'))

    if not is_valid_payment_method_key(payment_method):
        payment_method = 'card_payment'
        
    checkout = checkout_slot(slot, payment_method=payment_method, exit_time=datetime.utcnow(), refill_simulation=False, commit=True)

    if checkout['duration']:
        flash(f'Payment of ₦{checkout["fee"]:.2f} successful via {checkout["payment_method_label"]}. Parking duration: {checkout["duration"]["text"]}. Vehicle {vehicle_number} released from {checkout["slot_label"]}.')
    else:
        flash(f'Payment of ₦{checkout["fee"]:.2f} successful via {checkout["payment_method_label"]}. Vehicle {vehicle_number} released from {checkout["slot_label"]}.')
    return redirect(url_for('main.portal'))

@main.route('/admin')
@login_required
@admin_required
def admin():
    context = build_admin_view_context(include_slots=True)
    context['admin_page'] = 'dashboard'
    return render_template('admin.html', **context)

@main.route('/admin/revenue')
@login_required
@admin_required
def admin_revenue():
    context = build_admin_view_context(include_slots=False)
    context['admin_page'] = 'revenue'
    revenue_history = get_revenue_history(
        view=request.args.get('view', 'daily'),
        day=request.args.get('day', ''),
        month=request.args.get('month', ''),
        year=request.args.get('year', '')
    )
    context['revenue_history'] = revenue_history['rows']
    context['revenue_history_summary'] = revenue_history['summary']
    context['revenue_history_filters'] = revenue_history['filters']
    return render_template('admin.html', **context)

@main.route('/admin/chart')
@login_required
@admin_required
def admin_chart():
    context = build_admin_view_context(include_slots=False)
    context['admin_page'] = 'chart'
    return render_template('admin.html', **context)

@main.route('/admin/maintenance')
@login_required
@admin_required
def admin_maintenance():
    context = build_admin_view_context(include_slots=False)
    context['admin_page'] = 'maintenance'
    return render_template('admin.html', **context)

@main.route('/admin/history')
@login_required
@admin_required
def admin_history():
    context = build_admin_view_context(include_slots=False)
    context['admin_page'] = 'history'
    return render_template('admin.html', **context)

def build_admin_view_context(include_slots: bool):
    migrate_sensor_vehicles()
    maintain_simulation_occupancy()
    sync_vehicle_registry_metadata()
    now = datetime.utcnow()
    context = {}
    if include_slots:
        context['slots'] = [serialize_slot(slot, now) for slot in Slot.query.order_by(Slot.id).all()]

    revenue_periods = get_revenue_periods()
    dashboard_metrics = get_dashboard_metrics()

    context.update(dashboard_metrics)
    context['daily_revenue'] = revenue_periods['daily']
    context['weekly_revenue'] = revenue_periods['weekly']
    context['monthly_revenue'] = revenue_periods['monthly']
    context['yearly_revenue'] = revenue_periods['yearly']
    context['revenue_series'] = get_revenue_series(7)
    context['maintenance'] = get_maintenance_figures()
    context['payment_methods_today'] = get_payment_methods_today()
    context['parking_history'] = get_recent_parking_history(20)
    context['vehicle_registry_analytics'] = get_vehicle_registry_analytics()
    context['refresh_seconds'] = SIMULATION_REFRESH_SECONDS
    return context

@main.route('/admin/manual-action', methods=['POST'])
@login_required
@admin_required
def admin_manual():
    action = request.form.get('action')
    slot_id = request.form.get('slot_id')
    slot = Slot.query.get(slot_id)
    
    if not slot:
        flash('Invalid slot ID')
        return redirect(url_for('main.admin'))
        
    if action == 'release':
        vehicle = slot.vehicle
        entry_time = slot.entry_time
        if vehicle and entry_time:
            payment_method = request.form.get('payment_method') or 'bank_transfer'
            if not is_valid_payment_method_key(payment_method):
                payment_method = 'bank_transfer'
            checkout = checkout_slot(
                slot,
                payment_method=payment_method,
                exit_time=datetime.utcnow(),
                refill_simulation=is_simulation_slot_id(slot.id),
                commit=True
            )
            if is_simulation_slot_id(slot.id):
                message = f'{checkout["slot_label"]} released. Revenue added: ₦{checkout["fee"]:.2f} ({checkout["payment_method_label"]}). New simulation vehicle {checkout["replacement_vehicle"]} assigned immediately.'
            else:
                message = f'{checkout["slot_label"]} manually released. Revenue added: ₦{checkout["fee"]:.2f} ({checkout["payment_method_label"]}).'
        else:
            if is_simulation_slot_id(slot.id):
                populate_simulation_slot(slot)
                db.session.commit()
                message = f'{get_slot_label(slot.id)} was empty and has been repopulated with simulation vehicle {slot.vehicle}.'
            else:
                message = f'{get_slot_label(slot.id)} manually released.'
    elif action == 'park':
        vehicle = request.form.get('vehicle')
        if not vehicle:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Vehicle number required'}), 400
            flash('Vehicle number required')
            return redirect(url_for('main.admin'))
        else:
            if is_simulation_slot_id(slot.id):
                error_message = f'{get_slot_label(slot.id)} is reserved for simulation only.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': error_message}), 400
                flash(error_message)
                return redirect(url_for('main.admin'))
            vehicle = vehicle.strip().upper()
            slot.vehicle = vehicle
            get_or_create_vehicle_registry(vehicle)
            slot.entry_time = datetime.utcnow()
            db.session.commit()
            message = f'Vehicle {vehicle} manually assigned to {get_slot_label(slot.id)}.'
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Invalid action'}), 400
        flash('Invalid action')
        return redirect(url_for('main.admin'))
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'message': message})
            
    flash(message)
    return redirect(url_for('main.admin'))

@main.route('/api/slots')
def get_slots():
    maintain_simulation_occupancy()
    slots = Slot.query.order_by(Slot.id).all()
    return jsonify([serialize_slot(slot) for slot in slots])

@main.route('/api/admin-stats')
@login_required
@admin_required
def admin_stats():
    migrate_sensor_vehicles()
    maintain_simulation_occupancy()
    sync_vehicle_registry_metadata()
    dashboard_metrics = get_dashboard_metrics()

    revenue_periods = get_revenue_periods()
    slots = Slot.query.order_by(Slot.id).all()
    revenue_series = get_revenue_series(7)
    maintenance = get_maintenance_figures()
    payment_methods_today = get_payment_methods_today()
    return jsonify({
        **dashboard_metrics,
        'daily_revenue': revenue_periods['daily'],
        'weekly_revenue': revenue_periods['weekly'],
        'monthly_revenue': revenue_periods['monthly'],
        'yearly_revenue': revenue_periods['yearly'],
        'revenue_series': revenue_series,
        'maintenance': maintenance,
        'payment_methods_today': payment_methods_today,
        'parking_history': get_recent_parking_history(20),
        'vehicle_registry_analytics': get_vehicle_registry_analytics(),
        'refresh_seconds': SIMULATION_REFRESH_SECONDS,
        'slots': [serialize_slot(slot) for slot in slots]
    })

@main.route('/sensor-update', methods=['POST'])
def sensor_update():
    data = request.get_json()
    slot_id = data.get('slot_id')
    occupied = data.get('occupied')
    slot = Slot.query.get(slot_id)
    if not slot:
        return jsonify({'status': 'ok', 'event': 'ignored', 'reason': 'invalid_slot'})

    slot_id_int = slot.id

    if occupied:
        if slot_id_int not in SIMULATION_SLOT_IDS:
            return jsonify({'status': 'ok', 'event': 'ignored', 'slot_id': slot_id_int, 'reason': 'reserved_for_real_users'})
        if slot.vehicle is None:
            populate_simulation_slot(slot)
            db.session.commit()
            return jsonify({'status': 'ok', 'event': 'parked', 'slot_id': slot_id_int, 'slot_label': get_slot_label(slot_id_int), 'vehicle': slot.vehicle})
        return jsonify({'status': 'ok', 'event': 'ignored', 'slot_id': slot_id_int, 'reason': 'already_occupied', 'vehicle': slot.vehicle})

    if slot.vehicle is None:
        return jsonify({'status': 'ok', 'event': 'ignored', 'slot_id': slot_id_int, 'reason': 'already_available'})

    if not is_simulated_slot(slot_id_int, slot.vehicle):
        return jsonify({'status': 'ok', 'event': 'ignored', 'slot_id': slot_id_int, 'reason': 'manual_vehicle', 'vehicle': slot.vehicle})

    checkout = checkout_slot(slot, payment_method=random_payment_method_key(), exit_time=datetime.utcnow(), refill_simulation=True, commit=True)
    return jsonify({
        'status': 'ok',
        'event': 'released_and_replaced',
        'slot_id': slot_id_int,
        'slot_label': checkout['slot_label'],
        'vehicle': checkout['vehicle'],
        'replacement_vehicle': checkout['replacement_vehicle']
    })

app.register_blueprint(auth_blueprint)
app.register_blueprint(main)

def init_db():
    with app.app_context():
        db.create_all()
        if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
            try:
                columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(payment)")).fetchall()]
                if 'payment_method' not in columns:
                    db.session.execute(text("ALTER TABLE payment ADD COLUMN payment_method VARCHAR(20)"))
                if 'slot_id' not in columns:
                    db.session.execute(text("ALTER TABLE payment ADD COLUMN slot_id INTEGER"))
                if 'parked_at' not in columns:
                    db.session.execute(text("ALTER TABLE payment ADD COLUMN parked_at DATETIME"))
                if 'exited_at' not in columns:
                    db.session.execute(text("ALTER TABLE payment ADD COLUMN exited_at DATETIME"))
                if 'duration_minutes' not in columns:
                    db.session.execute(text("ALTER TABLE payment ADD COLUMN duration_minutes INTEGER"))
                db.session.execute(text("UPDATE payment SET payment_method = 'card_payment' WHERE payment_method IS NULL OR payment_method = ''"))
                db.session.execute(text("UPDATE payment SET exited_at = timestamp WHERE exited_at IS NULL"))
                db.session.commit()
            except Exception:
                db.session.rollback()
            try:
                vehicle_registry_exists = db.session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='vehicle_registry'")
                ).fetchone() is not None
                if vehicle_registry_exists:
                    registry_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(vehicle_registry)")).fetchall()]
                    if 'local_government' not in registry_columns:
                        db.session.execute(text("ALTER TABLE vehicle_registry ADD COLUMN local_government VARCHAR(60)"))
                        db.session.execute(text("UPDATE vehicle_registry SET local_government = 'Custom Entry' WHERE local_government IS NULL OR local_government = ''"))
                        db.session.commit()
            except Exception:
                db.session.rollback()
        if Slot.query.count() == 0:
            for i in range(1, 51):
                db.session.add(Slot(id=i))
            db.session.commit()
        if User.query.filter_by(role='admin').count() == 0:
            admin = User(
                username='admin',
                email='admin@nsuk.edu.ng',
                password=generate_password_hash('admin123', method='pbkdf2:sha256'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: admin@nsuk.edu.ng / admin123")
        maintain_simulation_occupancy()
        backfill_vehicle_registry()
        sync_vehicle_registry_metadata()
        start_of_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        has_historical_payment = Payment.query.filter(Payment.timestamp < start_of_today).first() is not None
        has_seed_payment = Payment.query.filter(Payment.vehicle == 'HIST-SEED').first() is not None
        if not has_historical_payment and not has_seed_payment:
            db.session.add(Payment(
                vehicle='HIST-SEED',
                amount=15000.00,
                timestamp=start_of_today - timedelta(days=7),
                payment_method='bank_transfer'
            ))
            db.session.commit()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
    if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_db()
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port_raw = os.environ.get('FLASK_PORT', os.environ.get('PORT', '5000'))
    try:
        port = int(port_raw)
    except Exception:
        port = 5000
    app.run(host=host, port=port, debug=debug)
