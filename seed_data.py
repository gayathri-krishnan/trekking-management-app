from extensions import db
from models import User

def create_default_admin(email: str, password: str):
    normalised_email = email.lower().strip()
    if not normalised_email:
        raise RuntimeError('The default admin email cannot be empty.')
    if not password:
        raise RuntimeError('The default admin password cannot be empty.')

    existing_admin = db.session.scalar(db.select(User).where(User.role == "admin"))

    if existing_admin is not None:
        return existing_admin

    existing_email_owner = db.session.scalar(db.select(User).where(User.email == normalised_email))
    if existing_email_owner is not None:
        raise RuntimeError('The default admin email belongs to another account.')

    admin = User(
        full_name = "System Administrator",
        email=normalised_email,
        role="admin",
        is_approved=True,
        is_blacklisted=False,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    print(f"Default admin created: {admin.email}")
    return admin
