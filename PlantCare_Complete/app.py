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
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
