import os
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
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
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
      if not name or not username or not email or not password:
            flash("Please fill in every required field.", "error")
        elif len(name) > 80 or len(username) > 40:
            flash("Name or username is too long.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already registered. Please sign in.", "error")
        else:
            user = User(name=name, username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            flash("Welcome to PlantCare! Add your first plant.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    plants = Plant.query.filter_by(user_id=user.id).order_by(Plant.name.asc()).all()
    due = sorted([p for p in plants if p.days_until_water <= 0], key=lambda p: p.days_until_water)
    upcoming = sorted([p for p in plants if p.days_until_water > 0], key=lambda p: p.days_until_water)[:5]
    return render_template("dashboard.html", plants=plants, due=due, upcoming=upcoming)


def parse_plant_form():
    name = request.form.get("name", "").strip()
    plant_type = request.form.get("plant_type", "").strip()
    frequency_raw = request.form.get("watering_frequency", "3").strip()
    last_raw = request.form.get("last_watered", "").strip()
    fertilizer_raw = request.form.get("fertilizer_date", "").strip()
    sunlight = request.form.get("sunlight", "Indirect sunlight").strip()
    notes = request.form.get("notes", "").strip()

    if not name:
        raise ValueError("Plant name is required.")
    if len(name) > 100 or len(plant_type) > 80:
        raise ValueError("Plant name or type is too long.")
    try:
        frequency = int(frequency_raw)
        if not 1 <= frequency <= 365:
            raise ValueError
    except ValueError:
        raise ValueError("Watering frequency must be between 1 and 365 days.")
    try:
        last_watered = date.fromisoformat(last_raw) if last_raw else date.today()
    except ValueError:
        raise ValueError("Please enter a valid last-watered date.")
    try:
        fertilizer_date = date.fromisoformat(fertilizer_raw) if fertilizer_raw else None
    except ValueError:
        raise ValueError("Please enter a valid fertilizer date.")
    if len(notes) > 3000:
        raise ValueError("Notes must be 3000 characters or fewer.")
    allowed_sun = {"Full sun", "Partial sun", "Indirect sunlight", "Shade"}
    if sunlight not in allowed_sun:
        sunlight = "Indirect sunlight"
    return {
        "name": name, "plant_type": plant_type, "watering_frequency": frequency,
        "last_watered": last_watered, "fertilizer_date": fertilizer_date,
        "sunlight": sunlight, "notes": notes
    }


@app.route("/plants/add", methods=["GET", "POST"])
@login_required
def add_plant():
    if request.method == "POST":
        try:
            plant = Plant(user_id=current_user().id, **parse_plant_form())
            db.session.add(plant)
            db.session.commit()
            flash(f"{plant.name} was added successfully.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("plant_form.html", plant=None, form_title="Add a plant", submit_label="Save plant")


@app.route("/plants/<int:plant_id>/edit", methods=["GET", "POST"])
@login_required
def edit_plant(plant_id):
    plant = Plant.query.filter_by(id=plant_id, user_id=current_user().id).first_or_404()
    if request.method == "POST":
        try:
            for key, value in parse_plant_form().items():
                setattr(plant, key, value)
            db.session.commit()
            flash(f"{plant.name} was updated.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("plant_form.html", plant=plant, form_title="Edit plant", submit_label="Save changes")


@app.route("/plants/<int:plant_id>/water", methods=["POST"])
@login_required
def water_plant(plant_id):
    plant = Plant.query.filter_by(id=plant_id, user_id=current_user().id).first_or_404()
    plant.last_watered = date.today()
    db.session.commit()
    flash(f"{plant.name} marked as watered today.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/plants/<int:plant_id>/delete", methods=["POST"])
@login_required
def delete_plant(plant_id):
    plant = Plant.query.filter_by(id=plant_id, user_id=current_user().id).first_or_404()
    name = plant.name
    db.session.delete(plant)
    db.session.commit()
    flash(f"{name} was deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory("static", "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory("static", "service-worker.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/health")
def health():
    return jsonify(status="ok")



with app.app_context():
    db.create_all()

    user_columns = {
        column["name"]
        for column in inspect(db.engine).get_columns("user")
    }

    with db.engine.begin() as connection:
        if "email" not in user_columns:
            connection.exec_driver_sql(
                'ALTER TABLE "user" ADD COLUMN email VARCHAR(254)'
            )

        connection.exec_driver_sql(
            'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email '
            'ON "user" (email)'
        )



if __name__ == "__main__":
    # Local development only. For public hosting use: gunicorn app:app
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
