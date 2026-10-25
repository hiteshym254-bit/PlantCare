import os
import json
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from pywebpush import webpush, WebPushException
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "dev-only-change-this-secret-before-deploying"
)

database_url = os.environ.get("DATABASE_URL", "sqlite:///plantcare.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    database_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = (
    {"pool_pre_ping": True} if not database_url.startswith("sqlite") else {}
)
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    plants = db.relationship(
        "Plant",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )
    name = db.Column(db.String(100), nullable=False)
    plant_type = db.Column(db.String(80), default="", nullable=False)
    watering_frequency = db.Column(db.Integer, default=3, nullable=False)
    last_watered = db.Column(db.Date, nullable=False, default=date.today)
    fertilizer_date = db.Column(db.Date, nullable=True)
    sunlight = db.Column(
        db.String(40),
        default="Indirect sunlight",
        nullable=False
    )
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


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class PushReminderLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )
    reminder_date = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "reminder_date",
            name="uq_push_reminder_log_user_date"
        ),
    )


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


def push_api_user():
    """Return the signed-in user, or None for an unauthenticated API request."""
    return current_user()


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
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not username or not password:
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
            user = User(
                name=name,
                username=username,
                password_hash=generate_password_hash(password)
            )
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
    due = sorted(
        [plant for plant in plants if plant.days_until_water <= 0],
        key=lambda plant: plant.days_until_water
    )
    upcoming = sorted(
        [plant for plant in plants if plant.days_until_water > 0],
        key=lambda plant: plant.days_until_water
    )[:5]
    return render_template(
        "dashboard.html",
        plants=plants,
        due=due,
        upcoming=upcoming
    )


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
        fertilizer_date = (
            date.fromisoformat(fertilizer_raw) if fertilizer_raw else None
        )
    except ValueError:
        raise ValueError("Please enter a valid fertilizer date.")

    if len(notes) > 3000:
        raise ValueError("Notes must be 3000 characters or fewer.")

    allowed_sun = {"Full sun", "Partial sun", "Indirect sunlight", "Shade"}
    if sunlight not in allowed_sun:
        sunlight = "Indirect sunlight"

    return {
        "name": name,
        "plant_type": plant_type,
        "watering_frequency": frequency,
        "last_watered": last_watered,
        "fertilizer_date": fertilizer_date,
        "sunlight": sunlight,
        "notes": notes
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

    return render_template(
        "plant_form.html",
        plant=None,
        form_title="Add a plant",
        submit_label="Save plant"
    )


@app.route("/plants/<int:plant_id>/edit", methods=["GET", "POST"])
@login_required
def edit_plant(plant_id):
    plant = Plant.query.filter_by(
        id=plant_id,
        user_id=current_user().id
    ).first_or_404()

    if request.method == "POST":
        try:
            for key, value in parse_plant_form().items():
                setattr(plant, key, value)
            db.session.commit()
            flash(f"{plant.name} was updated.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")

    return render_template(
        "plant_form.html",
        plant=plant,
        form_title="Edit plant",
        submit_label="Save changes"
    )


@app.route("/plants/<int:plant_id>/water", methods=["POST"])
@login_required
def water_plant(plant_id):
    plant = Plant.query.filter_by(
        id=plant_id,
        user_id=current_user().id
    ).first_or_404()
    plant.last_watered = date.today()
    db.session.commit()
    flash(f"{plant.name} marked as watered today.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/plants/<int:plant_id>/delete", methods=["POST"])
@login_required
def delete_plant(plant_id):
    plant = Plant.query.filter_by(
        id=plant_id,
        user_id=current_user().id
    ).first_or_404()
    name = plant.name
    db.session.delete(plant)
    db.session.commit()
    flash(f"{name} was deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/push/public-key", methods=["GET"])
def push_public_key():
    public_key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    if not public_key:
        return jsonify(error="Push notifications are not configured."), 503
    return jsonify(publicKey=public_key)


@app.route("/api/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    user = push_api_user()
    if not user:
        return jsonify(error="Please sign in first."), 401

    subscription = request.get_json(silent=True)
    if not isinstance(subscription, dict):
        return jsonify(error="A valid subscription is required."), 400

    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")
    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("https://")
        or not isinstance(keys, dict)
        or not isinstance(keys.get("p256dh"), str)
        or not isinstance(keys.get("auth"), str)
    ):
        return jsonify(error="The browser subscription is incomplete."), 400

    try:
        serialized = json.dumps(subscription)
        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()

        if existing:
            existing.user_id = user.id
            existing.subscription_json = serialized
        else:
            db.session.add(
                PushSubscription(
                    user_id=user.id,
                    endpoint=endpoint,
                    subscription_json=serialized
                )
            )

        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not save push subscription")
        return jsonify(error="Could not save the notification subscription."), 500

    return jsonify(success=True, message="Notifications enabled for this device.")


@app.route("/api/push/unsubscribe", methods=["POST"])
@login_required
def push_unsubscribe():
    user = push_api_user()
    if not user:
        return jsonify(error="Please sign in first."), 401

    payload = request.get_json(silent=True) or {}
    endpoint = payload.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        return jsonify(error="A subscription endpoint is required."), 400

    subscription = PushSubscription.query.filter_by(
        endpoint=endpoint,
        user_id=user.id
    ).first()

    if subscription:
        db.session.delete(subscription)
        db.session.commit()

    return jsonify(success=True, message="Notification subscription removed.")


@app.route("/api/push/test", methods=["POST"])
@login_required
def push_test():
    user = push_api_user()
    if not user:
        return jsonify(error="Please sign in first."), 401

    public_key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    subject = os.environ.get("VAPID_CLAIMS_SUBJECT", "").strip()

    if not public_key or not private_key or not subject.startswith("mailto:"):
        return jsonify(error="Push notification server settings are incomplete."), 503

    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    if not subscriptions:
        return jsonify(error="This account has no saved notification subscription yet."), 400

    sent = 0
    expired_ids = []

    notification = {
        "title": "PlantCare 🌿",
        "body": "Your push notifications are working!",
        "url": "/dashboard",
        "tag": "plantcare-test"
    }

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(subscription.subscription_json),
                data=json.dumps(notification, ensure_ascii=False),
                vapid_private_key=private_key,
                vapid_claims={"sub": subject}
            )
            sent += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            app.logger.warning(
                "Push delivery failed for subscription %s (status %s)",
                subscription.id,
                status_code
            )
            if status_code in (404, 410):
                expired_ids.append(subscription.id)
        except (ValueError, TypeError, json.JSONDecodeError):
            app.logger.warning(
                "Stored push subscription %s is invalid",
                subscription.id
            )
            expired_ids.append(subscription.id)

    if expired_ids:
        PushSubscription.query.filter(
            PushSubscription.id.in_(expired_ids)
        ).delete(synchronize_session=False)
        db.session.commit()

    if sent:
        return jsonify(
            success=True,
            sent=sent,
            message="Test push notification sent to the subscribed device(s)."
        )

    return jsonify(
        error="PlantCare could not deliver the test notification. Check Render logs and VAPID settings."
    ), 502


@app.route("/api/push/send-daily-reminders", methods=["POST"])
def send_daily_push_reminders():
    # This route is intended for a scheduler, not for browser visits.
    # The secret must be configured in Render and in the scheduled workflow.
    configured_secret = os.environ.get("PLANTCARE_CRON_SECRET", "").strip()
    provided_authorization = request.headers.get("Authorization", "")

    if not configured_secret:
        return jsonify(error="Daily reminders are not configured."), 503

    expected_authorization = "Bearer " + configured_secret
    if not secrets.compare_digest(provided_authorization, expected_authorization):
        return jsonify(error="Unauthorized."), 401

    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    subject = os.environ.get("VAPID_CLAIMS_SUBJECT", "").strip()
    if not private_key or not subject.startswith("mailto:"):
        return jsonify(error="Push notification server settings are incomplete."), 503

    today = date.today()
    due_by_user = {}

    # Evaluate due dates using the same rule as the dashboard.
    for plant in Plant.query.all():
        if plant.days_until_water <= 0:
            due_by_user.setdefault(plant.user_id, []).append(plant)

    users_notified = 0
    subscriptions_sent = 0
    users_without_subscriptions = 0
    already_sent_today = 0
    failed_subscriptions = 0
    expired_subscription_ids = []

    for user_id, due_plants in due_by_user.items():
        already_logged = PushReminderLog.query.filter_by(
            user_id=user_id,
            reminder_date=today
        ).first()

        # Avoid sending repeated daily reminders to the same account/date.
        if already_logged:
            already_sent_today += 1
            continue

        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        if not subscriptions:
            users_without_subscriptions += 1
            continue

        due_plants.sort(key=lambda plant: (plant.days_until_water, plant.name.lower()))
        names = [plant.name for plant in due_plants]
        if len(names) == 1:
            if due_plants[0].days_until_water < 0:
                body = names[0] + " is overdue for watering."
            else:
                body = names[0] + " needs watering today."
        else:
            visible_names = ", ".join(names[:3])
            extra_count = len(names) - 3
            if extra_count > 0:
                visible_names += ", and " + str(extra_count) + " more"
            body = str(len(names)) + " plants need watering: " + visible_names + "."

        notification = {
            "title": "PlantCare watering reminder 🌿",
            "body": body,
            "url": "/dashboard",
            "tag": "plantcare-watering-" + today.isoformat()
        }

        sent_for_user = 0
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info=json.loads(subscription.subscription_json),
                    data=json.dumps(notification, ensure_ascii=False),
                    vapid_private_key=private_key,
                    vapid_claims={"sub": subject}
                )
                sent_for_user += 1
                subscriptions_sent += 1
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                failed_subscriptions += 1
                app.logger.warning(
                    "Daily push failed for subscription %s (status %s)",
                    subscription.id,
                    status_code
                )
                if status_code in (404, 410):
                    expired_subscription_ids.append(subscription.id)
            except (ValueError, TypeError, json.JSONDecodeError):
                failed_subscriptions += 1
                expired_subscription_ids.append(subscription.id)
                app.logger.warning(
                    "Stored push subscription %s is invalid",
                    subscription.id
                )

        # Record only if at least one device accepted the push, allowing a later
        # scheduler retry if every subscription failed.
        if sent_for_user:
            db.session.add(
                PushReminderLog(
                    user_id=user_id,
                    reminder_date=today
                )
            )
            db.session.commit()
            users_notified += 1

    if expired_subscription_ids:
        PushSubscription.query.filter(
            PushSubscription.id.in_(set(expired_subscription_ids))
        ).delete(synchronize_session=False)
        db.session.commit()

    return jsonify(
        success=True,
        date=today.isoformat(),
        users_notified=users_notified,
        subscriptions_sent=subscriptions_sent,
        users_without_subscriptions=users_without_subscriptions,
        already_sent_today=already_sent_today,
        failed_subscriptions=failed_subscriptions
    )


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(
        "static",
        "manifest.webmanifest",
        mimetype="application/manifest+json"
    )


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(
        "static",
        "service-worker.js",
        mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/health")
def health():
    return jsonify(status="ok")


with app.app_context():
    # Creates missing tables (including push_subscription) without dropping
    # or replacing existing User or Plant tables.
    db.create_all()


if __name__ == "__main__":
    # Local development only. For public hosting use: gunicorn app:app
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000))
    )
