import os

from flask import Flask, render_template
from extensions import db, login_manager
from models import User
from seed_data import create_default_admin

@login_manager.user_loader
def load_user(user_id: str):
    try:
        numeric_user_id = int(user_id)
    except (ValueError, TypeError):
        return None

    user = db.session.get(User, numeric_user_id)
    if user is None:
        return None
    if user.is_blacklisted:
        return None
    return user

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY= os.environ.get('SECRET_KEY',"dev-key"),
        SQLALCHEMY_DATABASE_URI='sqlite:///trekking.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        ADMIN_EMAIL=os.environ.get('ADMIN_EMAIL', 'admin@trekking.local'),
        ADMIN_PASSWORD=os.environ.get('ADMIN_PASSWORD', 'Admin@123'),
    )

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)

    @app.route('/')
    def home():
        return render_template('home.html')

    with app.app_context():
        db.create_all()

        create_default_admin(
            email=app.config['ADMIN_EMAIL'],
            password=app.config['ADMIN_PASSWORD']
        )

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)