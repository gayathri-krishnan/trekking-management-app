import os

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user, login_required

from extensions import db, login_manager
from models import User
from seed_data import create_default_admin
from error_handlers import register_error_handlers

@login_manager.user_loader
def load_user(user_id: str):
    """
    Reload a logged-in user using the ID stored in
    the Flask session.
    """

    try:
        numeric_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    user = db.session.get(
        User,
        numeric_user_id,
    )

    if user is None:
        return None

    if user.is_blacklisted:
        return None

    return user


def create_app():
    """Create and configure the Flask application."""

    app = Flask(
        __name__,
        instance_relative_config=True,
    )

    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "SECRET_KEY",
            "development-key-change-before-final-submission",
        ),
        SQLALCHEMY_DATABASE_URI="sqlite:///trekking.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        ADMIN_EMAIL=os.environ.get(
            "ADMIN_EMAIL",
            "admin@trekking.local",
        ),
        ADMIN_PASSWORD=os.environ.get(
            "ADMIN_PASSWORD",
            "Admin@123",
        ),
    )

    os.makedirs(
        app.instance_path,
        exist_ok=True,
    )

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = (
        "Please log in to access that page."
    )
    login_manager.login_message_category = "warning"

    # Import and register route groups.
    from admin_routes import admin_bp
    from auth_routes import auth_bp
    from staff_routes import staff_bp
    from trekker_routes import trekker_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(trekker_bp)
    register_error_handlers(app)

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        """
        Send a logged-in user to the dashboard matching
        their database role.
        """

        if current_user.role == "admin":
            return redirect(
                url_for("admin.dashboard")
            )

        if current_user.role == "staff":
            if not current_user.is_approved:
                return redirect(
                    url_for("auth.pending_approval")
                )

            return redirect(
                url_for("staff.dashboard")
            )

        if current_user.role == "trekker":
            return redirect(
                url_for("trekker.dashboard")
            )

        abort(403)

    with app.app_context():
        db.create_all()

        create_default_admin(
            email=app.config["ADMIN_EMAIL"],
            password=app.config["ADMIN_PASSWORD"],
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)