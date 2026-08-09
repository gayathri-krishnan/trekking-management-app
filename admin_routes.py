from flask import Blueprint, render_template
from flask_login import login_required

from decorators import role_required


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


def _render_placeholder(
    page_title: str,
    description: str,
    active_page: str,
    planned_milestone: str,
):
    """
    Render a temporary page for an admin feature that will be
    implemented in a later milestone.
    """

    return render_template(
        "shared/placeholder.html",
        page_title=page_title,
        description=description,
        active_page=active_page,
        planned_milestone=planned_milestone,
    )


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        active_page="dashboard",
    )


@admin_bp.route("/treks")
@login_required
@role_required("admin")
def manage_treks():
    return _render_placeholder(
        page_title="Manage Treks",
        description=(
            "Create, edit, archive, search, and assign staff "
            "members to treks."
        ),
        active_page="treks",
        planned_milestone="Milestone 6",
    )


@admin_bp.route("/staff")
@login_required
@role_required("admin")
def manage_staff():
    return _render_placeholder(
        page_title="Manage Staff",
        description=(
            "Review staff registrations, approve staff, and "
            "blacklist or reactivate staff accounts."
        ),
        active_page="staff",
        planned_milestone="Milestone 7",
    )


@admin_bp.route("/users")
@login_required
@role_required("admin")
def manage_users():
    return _render_placeholder(
        page_title="Manage Users",
        description=(
            "View registered trekkers and manage their "
            "account status."
        ),
        active_page="users",
        planned_milestone="Milestone 7",
    )


@admin_bp.route("/bookings")
@login_required
@role_required("admin")
def view_bookings():
    return _render_placeholder(
        page_title="All Bookings",
        description=(
            "View active, cancelled, completed, and historical "
            "trek bookings."
        ),
        active_page="bookings",
        planned_milestone="Milestone 10",
    )


@admin_bp.route("/search")
@login_required
@role_required("admin")
def search():
    return _render_placeholder(
        page_title="Search",
        description=(
            "Search treks, staff members, and trekkers by "
            "name, email, or ID."
        ),
        active_page="search",
        planned_milestone="Milestones 6 and 7",
    )