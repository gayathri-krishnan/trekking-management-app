from flask import Blueprint, render_template
from flask_login import login_required

from decorators import role_required


trekker_bp = Blueprint(
    "trekker",
    __name__,
    url_prefix="/trekker",
)


def _render_placeholder(
    page_title: str,
    description: str,
    active_page: str,
    planned_milestone: str,
):
    """
    Render a temporary page for a trekker feature that will be
    implemented in a later milestone.
    """

    return render_template(
        "shared/placeholder.html",
        page_title=page_title,
        description=description,
        active_page=active_page,
        planned_milestone=planned_milestone,
    )


@trekker_bp.route("/dashboard")
@login_required
@role_required("trekker")
def dashboard():
    return render_template(
        "trekker/dashboard.html",
        active_page="dashboard",
    )


@trekker_bp.route("/treks")
@login_required
@role_required("trekker")
def browse_treks():
    return _render_placeholder(
        page_title="Browse Treks",
        description=(
            "View approved and open treks and filter them by "
            "difficulty and location."
        ),
        active_page="treks",
        planned_milestone="Milestone 9",
    )


@trekker_bp.route("/bookings")
@login_required
@role_required("trekker")
def my_bookings():
    return _render_placeholder(
        page_title="My Bookings",
        description=(
            "View current bookings, booking status, trek "
            "dates, and cancellation options."
        ),
        active_page="bookings",
        planned_milestone="Milestone 10",
    )


@trekker_bp.route("/history")
@login_required
@role_required("trekker")
def history():
    return _render_placeholder(
        page_title="Trekking History",
        description=(
            "View completed and historical trekking activity "
            "for the current user."
        ),
        active_page="history",
        planned_milestone="Milestone 11",
    )


@trekker_bp.route("/profile")
@login_required
@role_required("trekker")
def profile():
    return _render_placeholder(
        page_title="My Profile",
        description=(
            "View and update the current trekker's name, "
            "email, and contact information."
        ),
        active_page="profile",
        planned_milestone="Milestone 12",
    )