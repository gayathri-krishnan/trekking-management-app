from sqlalchemy import inspect

from app import app
from extensions import db
from models import User

with app.app_context():
    database_path = db.engine.url.database
    table_names = inspect(db.engine).get_table_names()

    admins = db.session.execute(
        db.select(User).where(User.role == "admin")
    ).scalars().all()

    print("Database path:")
    print(database_path)
    print()

    print("Database tables:")
    print(table_names)
    print()

    print("Admin users:")
    print(admins)

    if not admins:
        raise SystemExit("ERROR: The default admin was not created.")

    admin = admins[0]

    print("Admin email:")
    print(admin.email)
    print()
    print("Admin role:")
    print(admin.role)
    print()
    print("Admin approved:")
    print(admin.is_approved)