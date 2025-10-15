from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from models import db, User, Patient, Doctor, Appointment
from datetime import datetime, date, time, timedelta
from sqlalchemy import select, func, or_, update
from sqlalchemy.orm import joinedload
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hospital.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Specialization options
SPECIALIZATIONS = [
    "Cardiology", "Dermatology", "Neurology", "Pediatrics", 
    "Orthopedics", "Ophthalmology", "Gynecology", "Psychiatry"
]

# Country codes with flags
COUNTRY_CODES = [
    {"code": "+264", "name": "Namibia", "flag": "🇳🇦"},
    {"code": "+27", "name": "South Africa", "flag": "🇿🇦"},
    {"code": "+263", "name": "Zimbabwe", "flag": "🇿🇼"},
    {"code": "+267", "name": "Botswana", "flag": "🇧🇼"},
    {"code": "+260", "name": "Zambia", "flag": "🇿🇲"},
    {"code": "+258", "name": "Mozambique", "flag": "🇲🇿"},
    {"code": "+256", "name": "Uganda", "flag": "🇺🇬"},
    {"code": "+254", "name": "Kenya", "flag": "🇰🇪"},
    {"code": "+255", "name": "Tanzania", "flag": "🇹🇿"},
    {"code": "+234", "name": "Nigeria", "flag": "🇳🇬"},
]

# Helper functions
def generate_id(prefix, last_id):
    """Generate ID in format P001, D001, A001"""
    if last_id:
        number = int(last_id[1:]) + 1
    else:
        number = 1
    return f"{prefix}{number:03d}"

def validate_phone_number(phone_number):
    """Validate phone number: 7-15 digits only"""
    if not phone_number:
        return False
    
    clean_number = re.sub(r'[^\d]', '', phone_number)
    
    if len(clean_number) < 7 or len(clean_number) > 15:
        return False
    
    if not re.match(r'^\d+$', clean_number):
        return False
    
    return True

def validate_country_code(country_code):
    """Validate country code format - must be one of the predefined codes"""
    if not country_code:
        return False
    
    valid_codes = [country['code'] for country in COUNTRY_CODES]
    return country_code in valid_codes

def format_phone_number(phone_number):
    """Format phone number for storage"""
    if not phone_number:
        return ""
    
    clean_number = re.sub(r'[^\d]', '', phone_number)
    return clean_number

def is_doctor_available(doctor_id, appt_date, appt_time, duration, exclude_appt_id=None):
    """Check if doctor is available at given time (prevent double booking)"""
    appt_datetime = datetime.strptime(f"{appt_date} {appt_time}", "%Y-%m-%d %H:%M")
    appt_end = appt_datetime + timedelta(minutes=duration)
    
    with db.session() as session_db:
        stmt = select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date == appt_date
        )
        appointments = session_db.execute(stmt).scalars().all()
    
    for appointment in appointments:
        if exclude_appt_id and appointment.id == exclude_appt_id:
            continue
            
        existing_start = datetime.strptime(f"{appointment.date} {appointment.time}", "%Y-%m-%d %H:%M")
        existing_end = existing_start + timedelta(minutes=appointment.duration)
        
        if (appt_datetime < existing_end and appt_end > existing_start):
            return False
    
    return True


def is_patient_available(patient_id, appt_date, appt_time, duration, exclude_appt_id=None):
    """Check if patient is available at given time (prevent double booking for same patient)"""
    appt_datetime = datetime.strptime(f"{appt_date} {appt_time}", "%Y-%m-%d %H:%M")
    appt_end = appt_datetime + timedelta(minutes=duration)

    with db.session() as session_db:
        stmt = select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.date == appt_date
        ).limit(100)
        appointments = session_db.execute(stmt).scalars().all()

    for appointment in appointments:
        if exclude_appt_id and appointment.id == exclude_appt_id:
            continue

        existing_start = datetime.strptime(f"{appointment.date} {appointment.time}", "%Y-%m-%d %H:%M")
        existing_end = existing_start + timedelta(minutes=appointment.duration)

        if (appt_datetime < existing_end and appt_end > existing_start):
            return False

    return True




def get_time_slots():
    """Generate time slots for appointments"""
    times = []
    for hour in range(8, 18):
        for minute in [0, 30]:
            times.append(f"{hour:02d}:{minute:02d}")
    return times

def is_admin():
    """Check if current user is admin"""
    if 'user_id' not in session:
        return False
    
    with db.session() as session_db:
        stmt = select(User).where(User.id == session['user_id'])
        user = session_db.execute(stmt).scalar_one_or_none()
        return user and user.is_admin

# Create admin user if not exists
def create_admin_user():
    with app.app_context():
        with db.session() as session_db:
            # Create admin user
            stmt = select(User).where(User.username == 'admin')
            admin = session_db.execute(stmt).scalar_one_or_none()
            if not admin:
                admin = User(username='admin', is_admin=True)
                admin.set_password('admin123')
                session_db.add(admin)
            
            # Create regular user
            stmt = select(User).where(User.username == 'user')
            user = session_db.execute(stmt).scalar_one_or_none()
            if not user:
                user = User(username='user', is_admin=False)
                user.set_password('user123')
                session_db.add(user)
            
            session_db.commit()

# Login required decorator
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not is_admin():
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/check_availability', methods=['POST'])
@login_required
def check_availability():
    """AJAX endpoint to check doctor and patient availability for a given date/time/duration.

    Expects JSON or form-data with: doctor_id, patient_id, date, time, duration
    Returns JSON: { doctor_available: bool, patient_available: bool }
    """
    data = request.get_json(silent=True) or request.form
    doctor_id = data.get('doctor_id')
    patient_id = data.get('patient_id')
    date_str = data.get('date')
    time_str = data.get('time')
    duration = data.get('duration')

    # Basic validation
    if not date_str or not time_str:
        return jsonify({'error': 'missing_date_or_time', 'message': 'Date and time are required'}), 400

    try:
        dur = int(duration) if duration is not None else 30
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_duration', 'message': 'Duration must be an integer'}), 400

    doctor_ok = True
    patient_ok = True

    # If doctor_id provided, check doctor availability
    if doctor_id:
        try:
            doctor_ok = is_doctor_available(doctor_id, date_str, time_str, dur)
        except Exception:
            # On parsing errors, consider not available
            doctor_ok = False

    # If patient_id provided, check patient availability
    if patient_id:
        try:
            patient_ok = is_patient_available(patient_id, date_str, time_str, dur)
        except Exception:
            patient_ok = False

    return jsonify({'doctor_available': doctor_ok, 'patient_available': patient_ok})

@app.route('/')
def index():
    # Redirect to login if not authenticated
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get current user
    with db.session() as session_db:
        stmt = select(User).where(User.id == session['user_id'])
        user = session_db.execute(stmt).scalar_one_or_none()
        
        if not user:
            session.pop('user_id', None)
            flash('User not found. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Get all patients and doctors for counts
        patients_count = session_db.execute(select(func.count(Patient.id))).scalar()
        doctors_count = session_db.execute(select(func.count(Doctor.id))).scalar()
        
        # Get today's date string for filtering
        today = date.today().strftime("%Y-%m-%d")
        
        # Get today's appointments with eager loading
        stmt = select(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor)
        ).where(Appointment.date == today)
        today_appointments = session_db.execute(stmt).scalars().all()
        
        # Get upcoming appointments (today and future) with eager loading
        stmt = select(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor)
        ).where(
            Appointment.date >= today
        ).order_by(Appointment.date, Appointment.time).limit(10)
        upcoming_appointments = session_db.execute(stmt).scalars().all()
    
    return render_template('dashboard.html', 
                         username=user.username, 
                         patients_count=patients_count,
                         doctors_count=doctors_count,
                         today_appointments=today_appointments,
                         appointments=upcoming_appointments,
                         is_admin=is_admin())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with db.session() as session_db:
            stmt = select(User).where(User.username == username)
            user = session_db.execute(stmt).scalar_one_or_none()
            
            if user and user.check_password(password):
                session['user_id'] = user.id
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# User management routes
@app.route('/users')
@admin_required
def users():
    with db.session() as session_db:
        stmt = select(User)
        users = session_db.execute(stmt).scalars().all()
    return render_template('users.html', users=users)

@app.route('/add_user', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        
        with db.session() as session_db:
            stmt = select(User).where(User.username == username)
            existing_user = session_db.execute(stmt).scalar_one_or_none()
            
            if existing_user:
                flash('Username already exists', 'error')
                return render_template('add_user.html')
            
            new_user = User(username=username, is_admin=is_admin)
            new_user.set_password(password)
            
            session_db.add(new_user)
            session_db.commit()
            flash(f'User {username} created successfully', 'success')
            return redirect(url_for('users'))
    
    return render_template('add_user.html')

@app.route('/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    with db.session() as session_db:
        stmt = select(User).where(User.id == user_id)
        user = session_db.execute(stmt).scalar_one_or_none()
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('users'))
        
        if user.username == 'admin':
            flash('Cannot delete admin user', 'error')
            return redirect(url_for('users'))
        
        session_db.delete(user)
        session_db.commit()
        flash('User deleted successfully', 'success')
        return redirect(url_for('users'))

# Patient routes
@app.route('/patients')
@login_required
def patients():
    search_query = request.args.get('search', '')
    
    with db.session() as session_db:
        if search_query:
            stmt = select(Patient).where(
                or_(
                    Patient.name.ilike(f'%{search_query}%'),
                    Patient.surname.ilike(f'%{search_query}%'),
                    Patient.email.ilike(f'%{search_query}%'),
                    Patient.id.ilike(f'%{search_query}%'),
                    Patient.contact_number.ilike(f'%{search_query}%')
                )
            )
        else:
            stmt = select(Patient)
        
        patients = session_db.execute(stmt).scalars().all()
    
    return render_template('patients.html', patients=patients, search_query=search_query, is_admin=is_admin())

@app.route('/view_patient/<string:patient_id>')
@login_required
def view_patient(patient_id):
    with db.session() as session_db:
        stmt = select(Patient).where(Patient.id == patient_id)
        patient = session_db.execute(stmt).scalar_one_or_none()
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients'))
        
        # Prepare appointments lists (all, upcoming, past) with eager loading
        today = date.today().strftime("%Y-%m-%d")

        # All appointments for this patient (newest first)
        stmt = select(Appointment).options(
            joinedload(Appointment.doctor)
        ).where(
            Appointment.patient_id == patient_id
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        all_appointments = session_db.execute(stmt).scalars().all()

        # Upcoming (today and future) - newest first
        stmt = select(Appointment).options(
            joinedload(Appointment.doctor)
        ).where(
            Appointment.patient_id == patient_id,
            Appointment.date >= today
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        upcoming_appointments = session_db.execute(stmt).scalars().all()

        # Past (before today) - newest first
        stmt = select(Appointment).options(
            joinedload(Appointment.doctor)
        ).where(
            Appointment.patient_id == patient_id,
            Appointment.date < today
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        past_appointments = session_db.execute(stmt).scalars().all()
    
    return render_template('view_patient.html', patient=patient, appointments=all_appointments, upcoming_appointments=upcoming_appointments, past_appointments=past_appointments, is_admin=is_admin())

@app.route('/edit_patient/<string:patient_id>', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    with db.session() as session_db:
        stmt = select(Patient).where(Patient.id == patient_id)
        patient = session_db.execute(stmt).scalar_one_or_none()
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients'))
        
        if request.method == 'POST':
            patient.name = request.form['name']
            patient.surname = request.form['surname']
            patient.date_of_birth = request.form['date_of_birth']
            patient.gender = request.form['gender']
            patient.email = request.form['email']
            patient.country_code = request.form['country_code']
            contact_number = request.form['contact_number']
            
            # Validate phone number
            if not validate_phone_number(contact_number):
                flash('Phone number must contain 7-15 digits only (e.g., 812345678)', 'error')
                return render_template('edit_patient.html', patient=patient, country_codes=COUNTRY_CODES)
            
            patient.contact_number = format_phone_number(contact_number)
            
            # Validate date of birth
            dob = datetime.strptime(patient.date_of_birth, '%Y-%m-%d').date()
            if dob > date.today():
                flash('Date of birth cannot be in the future', 'error')
                return render_template('edit_patient.html', patient=patient, country_codes=COUNTRY_CODES)
            
            session_db.commit()
            flash('Patient updated successfully', 'success')
            return redirect(url_for('view_patient', patient_id=patient.id))
    
    return render_template('edit_patient.html', patient=patient, country_codes=COUNTRY_CODES)

@app.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        date_of_birth = request.form['date_of_birth']
        gender = request.form['gender']
        email = request.form['email']
        country_code = request.form['country_code']
        contact_number = request.form['contact_number']
        
        if not validate_country_code(country_code):
            flash('Please select a valid country code', 'error')
            return render_template('add_patient.html', country_codes=COUNTRY_CODES)
        
        if not validate_phone_number(contact_number):
            flash('Phone number must contain 7-15 digits only (e.g., 812345678)', 'error')
            return render_template('add_patient.html', country_codes=COUNTRY_CODES)
        
        formatted_number = format_phone_number(contact_number)
        
        dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
        if dob > date.today():
            flash('Date of birth cannot be in the future', 'error')
            return render_template('add_patient.html', country_codes=COUNTRY_CODES)
        
        with db.session() as session_db:
            # Get last patient ID (limit to 1 to avoid MultipleResultsFound)
            stmt = select(Patient).order_by(Patient.id.desc()).limit(1)
            last_patient = session_db.execute(stmt).scalars().first()
            patient_id = generate_id('P', last_patient.id if last_patient else None)
            
            new_patient = Patient(
                id=patient_id,
                name=name, 
                surname=surname, 
                date_of_birth=date_of_birth,
                gender=gender,
                email=email,
                country_code=country_code,
                contact_number=formatted_number
            )
            
            session_db.add(new_patient)
            session_db.commit()
            flash(f'Patient {patient_id} added successfully', 'success')
            return redirect(url_for('patients'))
    
    return render_template('add_patient.html', country_codes=COUNTRY_CODES)

@app.route('/delete_patient/<string:patient_id>')
@admin_required
def delete_patient(patient_id):
    with db.session() as session_db:
        stmt = select(Patient).where(Patient.id == patient_id)
        patient = session_db.execute(stmt).scalar_one_or_none()
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients'))
        
        # First delete all appointments for this patient
        stmt = select(Appointment).where(Appointment.patient_id == patient_id)
        appointments = session_db.execute(stmt).scalars().all()
        
        for appointment in appointments:
            session_db.delete(appointment)
        
        # Then delete the patient
        session_db.delete(patient)
        session_db.commit()
        flash('Patient and their appointments deleted successfully', 'success')
        return redirect(url_for('patients'))

# Doctor routes
@app.route('/doctors')
@login_required
def doctors():
    search_query = request.args.get('search', '')
    
    with db.session() as session_db:
        if search_query:
            stmt = select(Doctor).where(
                or_(
                    Doctor.name.ilike(f'%{search_query}%'),
                    Doctor.surname.ilike(f'%{search_query}%'),
                    Doctor.specialization.ilike(f'%{search_query}%'),
                    Doctor.email.ilike(f'%{search_query}%'),
                    Doctor.id.ilike(f'%{search_query}%'),
                    Doctor.contact_number.ilike(f'%{search_query}%')
                )
            )
        else:
            stmt = select(Doctor)
        
        doctors = session_db.execute(stmt).scalars().all()
    
    return render_template('doctors.html', doctors=doctors, search_query=search_query, specializations=SPECIALIZATIONS, is_admin=is_admin())

@app.route('/view_doctor/<string:doctor_id>')
@login_required
def view_doctor(doctor_id):
    with db.session() as session_db:
        stmt = select(Doctor).where(Doctor.id == doctor_id)
        doctor = session_db.execute(stmt).scalar_one_or_none()
        
        if not doctor:
            flash('Doctor not found', 'error')
            return redirect(url_for('doctors'))
        
        # Prepare appointments lists (all, upcoming, past) with eager loading
        today = date.today().strftime("%Y-%m-%d")

        # All appointments for this doctor (newest first)
        stmt = select(Appointment).options(
            joinedload(Appointment.patient)
        ).where(
            Appointment.doctor_id == doctor_id
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        all_appointments = session_db.execute(stmt).scalars().all()

        # Upcoming (today and future) - newest first
        stmt = select(Appointment).options(
            joinedload(Appointment.patient)
        ).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date >= today
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        upcoming_appointments = session_db.execute(stmt).scalars().all()

        # Past (before today) - newest first
        stmt = select(Appointment).options(
            joinedload(Appointment.patient)
        ).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date < today
        ).order_by(Appointment.date.desc(), Appointment.time.desc())
        past_appointments = session_db.execute(stmt).scalars().all()
    
    return render_template('view_doctor.html', doctor=doctor, appointments=all_appointments, upcoming_appointments=upcoming_appointments, past_appointments=past_appointments, is_admin=is_admin())

@app.route('/edit_doctor/<string:doctor_id>', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    with db.session() as session_db:
        stmt = select(Doctor).where(Doctor.id == doctor_id)
        doctor = session_db.execute(stmt).scalar_one_or_none()
        
        if not doctor:
            flash('Doctor not found', 'error')
            return redirect(url_for('doctors'))
        
        if request.method == 'POST':
            doctor.name = request.form['name']
            doctor.surname = request.form['surname']
            doctor.specialization = request.form['specialization']
            doctor.email = request.form['email']
            doctor.country_code = request.form['country_code']
            contact_number = request.form['contact_number']
            
            if not validate_phone_number(contact_number):
                flash('Phone number must contain 7-15 digits only (e.g., 812345678)', 'error')
                return render_template('edit_doctor.html', doctor=doctor, specializations=SPECIALIZATIONS, country_codes=COUNTRY_CODES)
            
            doctor.contact_number = format_phone_number(contact_number)
            
            session_db.commit()
            flash('Doctor updated successfully', 'success')
            return redirect(url_for('view_doctor', doctor_id=doctor.id))
    
    return render_template('edit_doctor.html', doctor=doctor, specializations=SPECIALIZATIONS, country_codes=COUNTRY_CODES)

@app.route('/add_doctor', methods=['GET', 'POST'])
@login_required
def add_doctor():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        specialization = request.form['specialization']
        email = request.form['email']
        country_code = request.form['country_code']
        contact_number = request.form['contact_number']
        
        if not validate_country_code(country_code):
            flash('Please select a valid country code', 'error')
            return render_template('add_doctor.html', specializations=SPECIALIZATIONS, country_codes=COUNTRY_CODES)
        
        if not validate_phone_number(contact_number):
            flash('Phone number must contain 7-15 digits only (e.g., 812345678)', 'error')
            return render_template('add_doctor.html', specializations=SPECIALIZATIONS, country_codes=COUNTRY_CODES)
        
        formatted_number = format_phone_number(contact_number)
        
        with db.session() as session_db:
            # Get last doctor ID (limit to 1 to avoid MultipleResultsFound)
            stmt = select(Doctor).order_by(Doctor.id.desc()).limit(1)
            last_doctor = session_db.execute(stmt).scalars().first()
            doctor_id = generate_id('D', last_doctor.id if last_doctor else None)
            
            new_doctor = Doctor(
                id=doctor_id,
                name=name, 
                surname=surname, 
                specialization=specialization,
                email=email,
                country_code=country_code,
                contact_number=formatted_number
            )
            
            session_db.add(new_doctor)
            session_db.commit()
            flash(f'Doctor {doctor_id} added successfully', 'success')
            return redirect(url_for('doctors'))
    
    return render_template('add_doctor.html', specializations=SPECIALIZATIONS, country_codes=COUNTRY_CODES)

@app.route('/delete_doctor/<string:doctor_id>')
@admin_required
def delete_doctor(doctor_id):
    with db.session() as session_db:
        stmt = select(Doctor).where(Doctor.id == doctor_id)
        doctor = session_db.execute(stmt).scalar_one_or_none()
        
        if not doctor:
            flash('Doctor not found', 'error')
            return redirect(url_for('doctors'))
        
        # First delete all appointments for this doctor
        stmt = select(Appointment).where(Appointment.doctor_id == doctor_id)
        appointments = session_db.execute(stmt).scalars().all()
        
        for appointment in appointments:
            session_db.delete(appointment)
        
        # Then delete the doctor
        session_db.delete(doctor)
        session_db.commit()
        flash('Doctor and their appointments deleted successfully', 'success')
        return redirect(url_for('doctors'))

# Appointment routes
@app.route('/appointments')
@login_required
def appointments():
    search_query = request.args.get('search', '')
    
    with db.session() as session_db:
        if search_query:
            stmt = select(Appointment).options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor)
            ).join(Patient).join(Doctor).where(
                or_(
                    Patient.name.ilike(f'%{search_query}%'),
                    Patient.surname.ilike(f'%{search_query}%'),
                    Doctor.name.ilike(f'%{search_query}%'),
                    Doctor.surname.ilike(f'%{search_query}%'),
                    Appointment.diagnosis.ilike(f'%{search_query}%'),
                    Appointment.id.ilike(f'%{search_query}%')
                )
            )
        else:
            stmt = select(Appointment).options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor)
            )
        
        appointments = session_db.execute(stmt).scalars().all()
    
    return render_template('appointments.html', appointments=appointments, search_query=search_query)

@app.route('/add_appointment', methods=['GET', 'POST'])
@login_required
def add_appointment():
    with db.session() as session_db:
        stmt = select(Patient)
        patients = session_db.execute(stmt).scalars().all()
        
        stmt = select(Doctor)
        doctors = session_db.execute(stmt).scalars().all()
    
    time_slots = get_time_slots()
    
    if request.method == 'POST':
        date_str = request.form['date']
        time_str = request.form['time']
        duration = int(request.form['duration'])
        diagnosis = request.form['diagnosis']
        patient_id = request.form['patient_id']
        doctor_id = request.form['doctor_id']
        
        with db.session() as session_db:
            stmt = select(Patient).where(Patient.id == patient_id)
            patient = session_db.execute(stmt).scalar_one_or_none()
            
            stmt = select(Doctor).where(Doctor.id == doctor_id)
            doctor = session_db.execute(stmt).scalar_one_or_none()
            
            if not patient:
                flash('Selected patient does not exist', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            if not doctor:
                flash('Selected doctor does not exist', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if appointment_date < date.today():
                flash('Cannot book appointments in the past', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            if duration <= 0 or duration > 240:
                flash('Duration must be between 1 and 240 minutes', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            if not re.match(r'^\d{2}:\d{2}$', time_str):
                flash('Time must be in HH:MM format', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            if not is_doctor_available(doctor_id, date_str, time_str, duration):
                flash('Doctor is not available at this time. Please choose another time.', 'error')
                return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)
            
            # Get last appointment ID (limit to 1 to avoid MultipleResultsFound)
            stmt = select(Appointment).order_by(Appointment.id.desc()).limit(1)
            last_appointment = session_db.execute(stmt).scalars().first()
            appointment_id = generate_id('A', last_appointment.id if last_appointment else None)
            
            new_appointment = Appointment(
                id=appointment_id,
                date=date_str,
                time=time_str,
                duration=duration,
                diagnosis=diagnosis,
                patient_id=patient_id,
                doctor_id=doctor_id
            )
            
            session_db.add(new_appointment)
            session_db.commit()
            flash(f'Appointment {appointment_id} booked successfully', 'success')
            return redirect(url_for('appointments'))
    
    return render_template('add_appointment.html', patients=patients, doctors=doctors, time_slots=time_slots)

@app.route('/delete_appointment/<string:appointment_id>')
@login_required
def delete_appointment(appointment_id):
    with db.session() as session_db:
        stmt = select(Appointment).where(Appointment.id == appointment_id)
        appointment = session_db.execute(stmt).scalar_one_or_none()
        
        if not appointment:
            flash('Appointment not found', 'error')
            return redirect(url_for('appointments'))
        session_db.delete(appointment)
        session_db.commit()
        flash('Appointment deleted successfully', 'success')
        return redirect(url_for('appointments'))


@app.route('/edit_appointment/<string:appointment_id>', methods=['GET', 'POST'])
@login_required
def edit_appointment(appointment_id):
    with db.session() as session_db:
        stmt = select(Appointment).where(Appointment.id == appointment_id)
        appt = session_db.execute(stmt).scalar_one_or_none()

        if not appt:
            flash('Appointment not found', 'error')
            return redirect(url_for('appointments'))

        # Load patients and doctors for select lists
        patients = session_db.execute(select(Patient)).scalars().all()
        doctors = session_db.execute(select(Doctor)).scalars().all()

        if request.method == 'POST':
            date_str = request.form['date']
            time_str = request.form['time']
            duration = int(request.form['duration'])
            diagnosis = request.form['diagnosis']
            patient_id = request.form['patient_id']
            doctor_id = request.form['doctor_id']

            # Basic validation
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if appointment_date < date.today():
                flash('Cannot set appointment date in the past', 'error')
                return render_template('edit_appointment.html', appt=appt, patients=patients, doctors=doctors, time_slots=get_time_slots())

            if duration <= 0 or duration > 240:
                flash('Duration must be between 1 and 240 minutes', 'error')
                return render_template('edit_appointment.html', appt=appt, patients=patients, doctors=doctors, time_slots=get_time_slots())

            if not is_doctor_available(doctor_id, date_str, time_str, duration, exclude_appt_id=appointment_id):
                flash('Doctor is not available at this time', 'error')
                return render_template('edit_appointment.html', appt=appt, patients=patients, doctors=doctors, time_slots=get_time_slots())

            if not is_patient_available(patient_id, date_str, time_str, duration, exclude_appt_id=appointment_id):
                flash('Patient is not available at this time', 'error')
                return render_template('edit_appointment.html', appt=appt, patients=patients, doctors=doctors, time_slots=get_time_slots())

            # Save changes using a direct UPDATE to avoid session attachment issues
            stmt_upd = update(Appointment).where(Appointment.id == appointment_id).values(
                date=date_str,
                time=time_str,
                duration=duration,
                diagnosis=diagnosis,
                patient_id=patient_id,
                doctor_id=doctor_id
            )
            session_db.execute(stmt_upd)
            session_db.commit()
            flash(f'Appointment {appointment_id} updated successfully', 'success')
            return redirect(url_for('appointments'))

    return render_template('edit_appointment.html', appt=appt, patients=patients, doctors=doctors, time_slots=get_time_slots())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin_user()
    app.run(host='0.0.0.0',port='5000',debug=True)