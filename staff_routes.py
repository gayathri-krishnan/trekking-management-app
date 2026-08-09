from flask import Blueprint, render_template
from flask_login import login_required

from decorators import approved_staff_required


staff_bp = Blueprint(
    "staff",
    __name__,
    url_prefix="/staff",
)


def _render_placeholder(
    page_title: str,
    description: str,
    active_page: str,
    planned_milestone: str,
):
    """
    Render a temporary page for a staff feature that will be
    implemented in a later milestone.
    """

    return render_template(
        "shared/placeholder.html",
        page_title=page_title,
        description=description,
        active_page=active_page,
        planned_milestone=planned_milestone,
    )


@staff_bp.route("/dashboard")
@login_required
@approved_staff_required
def dashboard():
    return render_template(
        "staff/dashboard.html",
        active_page="dashboard",
    )


@staff_bp.route("/treks")
@login_required
@approved_staff_required
def my_treks():
    return _render_placeholder(
        page_title="My Assigned Treks",
        description=(
            "View treks assigned by the administrator and "
            "manage their slots and status."
        ),
        active_page="treks",
        planned_milestone="Milestone 8",
    )


@staff_bp.route("/participants")
@login_required
@approved_staff_required
def participants():
    return _render_placeholder(
        page_title="Participants",
        description=(
            "View users registered for treks assigned to the "
            "current staff member."
        ),
        active_page="participants",
        planned_milestone="Milestone 8",
    )


@staff_bp.route("/profile")
@login_required
@approved_staff_required
def profile():
    return _render_placeholder(
        page_title="Staff Profile",
        description=(
            "View and update the current staff member's "
            "contact information."
        ),
        active_page="profile",
        planned_milestone="Milestone 12",
    )