from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user


def role_required(*allowed_roles):

    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def approved_staff_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if current_user.role != "staff":
            abort(403)

        if not current_user.is_approved:
            flash(
                "Your staff account is waiting for admin approval.",
                "warning",
            )

            return redirect(url_for("auth.pending_approval"))

        return view_function(*args, **kwargs)

    return wrapped_view