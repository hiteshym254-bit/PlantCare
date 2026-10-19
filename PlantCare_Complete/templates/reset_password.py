
from getpass import getpass
from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    username = input("Enter your existing username: ").strip().lower()
    user = User.query.filter_by(username=username).first()

    if user is None:
        print("Username not found in this database.")
    else:
        new_password = getpass("Enter your new password: ")
        confirm_password = getpass("Confirm your new password: ")

        if len(new_password) < 8:
            print("Password must be at least 8 characters.")
        elif new_password != confirm_password:
            print("Passwords do not match.")
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            print("Password changed successfully!")
