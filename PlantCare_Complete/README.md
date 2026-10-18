# PlantCare Reminder — Complete starter app

A responsive Flask + SQLAlchemy plant-care web app with:
- Account registration and login (hashed passwords)
- Personal plant lists (users only see their own plants)
- Add, edit, delete plants
- Watering frequency, last-watered date, next watering date
- Mark a plant as watered
- Fertilizer date and notes
- Dashboard with due/overdue watering reminders
- Installable Progressive Web App (PWA) on supported phones
- SQLite locally; PostgreSQL recommended for internet hosting

## 1. Run on Windows locally

1. Install Python 3.11 or newer from https://www.python.org/downloads/ and select **Add Python to PATH**.
2. Extract this folder to Desktop, for example `C:\Users\YourName\Desktop\PlantCare_Complete`.
3. Open Command Prompt and enter the folder:
   `cd %USERPROFILE%\Desktop\PlantCare_Complete`
4. Create a virtual environment:
   `py -m venv .venv`
5. Activate it:
   `.venv\Scripts\activate`
6. Install packages:
   `py -m pip install -r requirements.txt`
7. Set a secret key for this terminal session:
   `set SECRET_KEY=replace-this-with-a-long-random-secret`
8. Start the app:
   `py app.py`
9. Open `http://127.0.0.1:5000`

Keep the terminal window open while running locally. Do not use the development server for a public production deployment.

## 2. Make it available on every phone, anywhere

Your laptop must not be the server for an always-available public app. Deploy it to a hosting service.

### Recommended route
- Create a GitHub account/repository and upload the files in this folder.
- Create a PostgreSQL database with your host (for example Render's managed PostgreSQL, or another provider).
- Deploy the repository as a Python web service.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Set environment variables:
  - `SECRET_KEY`: a long random secret (never publish it)
  - `DATABASE_URL`: your hosted PostgreSQL connection URL
- Open the public HTTPS URL provided by the host.

If the host provides a PostgreSQL URL starting with `postgres://`, the app normalizes it. Do not rely on temporary local disk or SQLite on an ephemeral hosting plan; the database may be lost when the instance restarts/redeploys. Use persistent PostgreSQL for real users. Free host plans can sleep or have limits; check current provider pricing and terms.

## 3. Install it like an app on Android

1. Open your deployed **HTTPS** website in Chrome on Android.
2. Use the browser menu (⋮) and choose **Install app** or **Add to Home screen**.
3. Confirm. It will appear on your home screen and open in an app-like window.

This is a PWA (installable web app), not a native APK. It works across phones and shares the same online account/database. The first page shell may be cached, but plant data and login require internet.

## 4. Important notifications note

The app displays watering due/overdue reminders when you open it and can request browser notification permission. Ordinary browser notifications cannot reliably wake a closed app at a future time by themselves. True push notifications while the app is closed require a push service and extra server configuration; that is not included in this starter.

## 5. Before public launch

- Set a unique, long `SECRET_KEY`.
- Use HTTPS (the host should provide it).
- Use a persistent PostgreSQL database and keep backups.
- Never share secrets or database credentials in public repositories.
- Test account registration, login, plant creation, edit, delete, and mark-watered actions.
