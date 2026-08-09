from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import User


auth_bp = Blueprint("auth", __name__)


def normalize_name(value: str) -> str:

    return " ".join(value.split())


def looks_like_email(value: str) -> bool:

    if not value or len(value) > 255:
        return False

    if any(character.isspace() for character in value):
        return False

    local_part, separator, domain_part = value.partition("@")

    if not local_part or not separator or not domain_part:
        return False

    if "@" in domain_part:
        return False

    return True


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = normalize_name(
            request.form.get("full_name", "")
        )

        email = request.form.get(
            "email",
            "",
        ).strip().lower()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        role = request.form.get(
            "role",
            "",
        ).strip().lower()

        password = request.form.get(
            "password",
            "",
        )

        confirm_password = request.form.get(
            "confirm_password",
            "",
        )

        errors = []

        if not 2 <= len(full_name) <= 100:
            errors.append(
                "Full name must contain between 2 and 100 characters."
            )

        if not looks_like_email(email):
            errors.append(
                "Enter a valid email address."
            )

        if not 7 <= len(phone) <= 20:
            errors.append(
                "Phone number must contain between 7 and 20 characters."
            )

        if role not in {"staff", "trekker"}:
            errors.append(
                "Choose either Trek Staff or Trekker."
            )

        if not 8 <= len(password) <= 128:
            errors.append(
                "Password must contain between 8 and 128 characters."
            )

        if password != confirm_password:
            errors.append(
                "Password and confirmation password do not match."
            )

        if errors:
            for error in errors:
                flash(error, "danger")

            return render_template("auth/register.html")

        existing_user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if existing_user is not None:
            flash(
                "An account with that email already exists.",
                "danger",
            )

            return render_template("auth/register.html")

        user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            role=role,
            is_approved=(role == "trekker"),
            is_blacklisted=False,
        )

        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()

        except IntegrityError:
            db.session.rollback()

            flash(
                "The account could not be created because that "
                "email is already registered.",
                "danger",
            )

            return render_template("auth/register.html")

        if role == "staff":
            flash(
                "Registration completed. An admin must approve "
                "your staff account before you can access the "
                "staff dashboard.",
                "info",
            )
        else:
            flash(
                "Registration completed. You can now log in.",
                "success",
            )

        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get(
            "email",
            "",
        ).strip().lower()

        password = request.form.get(
            "password",
            "",
        )

        remember = request.form.get("remember") == "yes"

        if not email or not password:
            flash(
                "Email and password are required.",
                "danger",
            )

            return render_template("auth/login.html")

        user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if user is None or not user.check_password(password):
            flash(
                "Invalid email or password.",
                "danger",
            )

            return render_template("auth/login.html")

        if user.is_blacklisted:
            flash(
                "This account has been blocked. Contact the administrator.",
                "danger",
            )

            return render_template("auth/login.html")

        login_user(
            user,
            remember=remember,
        )

        flash(
            f"Welcome, {user.full_name}.",
            "success",
        )

        if user.role == "staff" and not user.is_approved:
            flash(
                "Your staff account is still waiting for "
                "admin approval.",
                "warning",
            )

            return redirect(
                url_for("auth.pending_approval")
            )

        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/pending-approval")
@login_required
def pending_approval():

    if current_user.role != "staff":
        return redirect(url_for("dashboard"))

    if current_user.is_approved:
        return redirect(
            url_for("staff.dashboard")
        )

    return render_template(
        "auth/pending_approval.html"
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():

    user_name = current_user.full_name

    logout_user()

    flash(
        f"{user_name}, you have been logged out.",
        "success",
    )

    return redirect(url_for("home"))