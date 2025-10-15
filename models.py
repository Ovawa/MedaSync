from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time
import re

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Patient(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(10))
    email = db.Column(db.String(120))
    country_code = db.Column(db.String(10), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    appointments = db.relationship('Appointment', backref='patient', lazy=True)

class Doctor(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(50))
    email = db.Column(db.String(120))
    country_code = db.Column(db.String(10), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    appointments = db.relationship('Appointment', backref='doctor', lazy=True)

class Appointment(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    duration = db.Column(db.Integer, nullable=False, default=30)
    diagnosis = db.Column(db.Text)
    patient_id = db.Column(db.String(4), db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.String(4), db.ForeignKey('doctor.id'), nullable=False)