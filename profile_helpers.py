from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import User


PHONE_ALLOWED_CHARACTERS = set(
    "0123456789+ -()"
)


def _normalize_name(value: str) -> str:
    """
    Remove leading and trailing spaces and replace repeated
    internal spaces with one space.
    """

    return " ".join(
        (value or "").split()
    )


def _normalize_email(value: str) -> str:
    """
    Store email addresses without surrounding spaces and
    using lowercase letters.
    """

    return (
        value or ""
    ).strip().lower()


def _normalize_phone(value: str) -> str:
    """
    Remove surrounding spaces and repeated internal spaces.
    """

    return " ".join(
        (value or "").strip().split()
    )


def _is_valid_email(value: str) -> bool:
    """
    Perform a practical backend email validation check.
    """

    if not value or len(value) > 255:
        return False

    if any(
        character.isspace()
        for character in value
    ):
        return False

    if value.count("@") != 1:
        return False

    local_part, domain_part = value.split(
        "@",
        1,
    )

    if not local_part or not domain_part:
        return False

    if (
        local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
    ):
        return False

    if (
        domain_part.startswith(".")
        or domain_part.endswith(".")
        or domain_part.startswith("-")
        or domain_part.endswith("-")
        or ".." in domain_part
    ):
        return False

    return True


def _is_valid_phone(value: str) -> bool:
    """
    Accept digits and common phone-number separators.

    The number must contain between 7 and 15 digits.
    """

    if not 7 <= len(value) <= 20:
        return False

    if any(
        character not in PHONE_ALLOWED_CHARACTERS
        for character in value
    ):
        return False

    digit_count = sum(
        character.isdigit()
        for character in value
    )

    return 7 <= digit_count <= 15


def profile_page(
    *,
    role_title: str,
    profile_endpoint: str,
):
    """
    Display and update the profile of the currently logged-in
    Trekker or Staff member.

    Only these fields are accepted:
    - full_name
    - email
    - phone
    """

    errors = []

    if request.method == "POST":
        full_name = _normalize_name(
            request.form.get(
                "full_name",
                "",
            )
        )

        email = _normalize_email(
            request.form.get(
                "email",
                "",
            )
        )

        phone = _normalize_phone(
            request.form.get(
                "phone",
                "",
            )
        )

        form_data = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
        }

        if not 2 <= len(full_name) <= 100:
            errors.append(
                "Full name must contain between 2 and "
                "100 characters."
            )

        email_is_valid = _is_valid_email(
            email
        )

        if not email_is_valid:
            errors.append(
                "Enter a valid email address."
            )

        if not _is_valid_phone(phone):
            errors.append(
                "Enter a valid phone number containing "
                "between 7 and 15 digits."
            )

        if email_is_valid:
            existing_email_owner = (
                db.session.scalar(
                    db.select(User).where(
                        User.email == email,
                        User.id != current_user.id,
                    )
                )
            )

            if existing_email_owner is not None:
                errors.append(
                    "Another account already uses that "
                    "email address."
                )

        if not errors:
            current_user.full_name = full_name
            current_user.email = email
            current_user.phone = phone

            try:
                db.session.commit()

            except IntegrityError:
                db.session.rollback()

                errors.append(
                    "The profile could not be saved. "
                    "The email address may already be in use."
                )

            else:
                flash(
                    "Your profile was updated successfully.",
                    "success",
                )

                return redirect(
                    url_for(
                        profile_endpoint
                    )
                )

    else:
        form_data = {
            "full_name": current_user.full_name,
            "email": current_user.email,
            "phone": current_user.phone or "",
        }

    return render_template(
        "shared/profile.html",
        active_page="profile",
        role_title=role_title,
        profile_endpoint=profile_endpoint,
        form_data=form_data,
        errors=errors,
    )