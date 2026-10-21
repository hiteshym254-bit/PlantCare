import os
from datetime import date, datetime, timedelta
import smtplib
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-before-deploying")
database_url = os.environ.get("DATABASE_URL", "sqlite:///plantcare.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True} if not database_url.startswith("sqlite") else {}
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    plants = db.relationship("Plant", backref="owner", lazy=True, cascade="all, delete-orphan")


class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    plant_type = db.Column(db.String(80), default="", nullable=False)
    watering_frequency = db.Column(db.Integer, default=3, nullable=False)
    last_watered = db.Column(db.Date, nullable=False, default=date.today)
    fertilizer_date = db.Column(db.Date, nullable=True)
    sunlight = db.Column(db.String(40), default="Indirect sunlight", nullable=False)
    notes = db.Column(db.Text, default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def next_watering(self):
        return self.last_watered + timedelta(days=self.watering_frequency)

    @property
    def days_until_water(self):
        return (self.next_watering - date.today()).days

    @property
    def watering_status(self):
        delta = self.days_until_water
        if delta < 0:
            return "Overdue"
        if delta == 0:
            return "Due today"
        if delta == 1:
            return "Tomorrow"
        return f"In {delta} days"


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {"logged_in_user": current_user(), "today": date.today()}


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
