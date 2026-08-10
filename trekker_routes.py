from flask import (
    Blueprint,
    abort,
    render_template,
    request,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from decorators import role_required
from extensions import db
from models import Booking, Trek


trekker_bp = Blueprint(
    "trekker",
    __name__,
    url_prefix="/trekker",
)


CATALOGUE_STATUSES = (
    "Approved",
    "Open",
)

TREK_DIFFICULTIES = (
    "Easy",
    "Moderate",
    "Hard",
)

TREK_STATUS_FILTERS = (
    "all",
    "Approved",
    "Open",
)


def _render_placeholder(
    page_title: str,
    description: str,
    active_page: str,
    planned_milestone: str,
):
    """
    Render a temporary Trekker page for functionality that
    will be implemented in a later milestone.
    """

    return render_template(
        "shared/placeholder.html",
        page_title=page_title,
        description=description,
        active_page=active_page,
        planned_milestone=planned_milestone,
    )


def _visible_trek_or_404(trek_id: int):
    """
    Return a Trek only when it is visible in the Trekker
    catalogue.

    Trekkers may view only non-archived Approved or Open
    Treks.
    """

    trek = db.session.scalar(
        db.select(Trek)
        .where(
            Trek.id == trek_id,
            Trek.is_archived.is_(False),
            Trek.status.in_(CATALOGUE_STATUSES),
        )
        .options(
            joinedload(Trek.assigned_staff)
        )
    )

    if trek is None:
        abort(
            404,
            description=(
                "The requested Trek does not exist or is not "
                "currently visible to Trekkers."
            ),
        )

    return trek


@trekker_bp.route("/dashboard")
@login_required
@role_required("trekker")
def dashboard():
    """
    Display live Trek and booking statistics for the current
    Trekker.
    """

    available_treks_count = (
        db.session.scalar(
            db.select(
                func.count(Trek.id)
            ).where(
                Trek.is_archived.is_(False),
                Trek.status == "Open",
                Trek.available_slots > 0,
            )
        )
        or 0
    )

    active_bookings_count = (
        db.session.scalar(
            db.select(
                func.count(Booking.id)
            ).where(
                Booking.user_id == current_user.id,
                Booking.status == "Booked",
            )
        )
        or 0
    )

    completed_treks_count = (
        db.session.scalar(
            db.select(
                func.count(Booking.id)
            ).where(
                Booking.user_id == current_user.id,
                Booking.status == "Completed",
            )
        )
        or 0
    )

    featured_treks = db.session.execute(
        db.select(Trek)
        .where(
            Trek.is_archived.is_(False),
            Trek.status == "Open",
            Trek.available_slots > 0,
        )
        .options(
            joinedload(Trek.assigned_staff)
        )
        .order_by(
            Trek.start_date.asc(),
            Trek.id.asc(),
        )
        .limit(4)
    ).scalars().all()

    active_bookings = db.session.execute(
        db.select(Booking)
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .where(
            Booking.user_id == current_user.id,
            Booking.status == "Booked",
        )
        .options(
            joinedload(Booking.trek)
        )
        .order_by(
            Trek.start_date.asc(),
            Booking.id.asc(),
        )
        .limit(5)
    ).scalars().all()

    return render_template(
        "trekker/dashboard.html",
        active_page="dashboard",
        available_treks_count=available_treks_count,
        active_bookings_count=active_bookings_count,
        completed_treks_count=completed_treks_count,
        featured_treks=featured_treks,
        active_bookings=active_bookings,
    )


@trekker_bp.route("/treks")
@login_required
@role_required("trekker")
def browse_treks():
    """
    Display the searchable and filterable Trek catalogue.
    """

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    difficulty_filter = request.args.get(
        "difficulty",
        "",
    ).strip()

    location_filter = request.args.get(
        "location",
        "",
    ).strip()

    status_filter = request.args.get(
        "status",
        "all",
    ).strip()

    if difficulty_filter not in TREK_DIFFICULTIES:
        difficulty_filter = ""

    if status_filter not in TREK_STATUS_FILTERS:
        status_filter = "all"

    location_options = db.session.execute(
        db.select(Trek.location)
        .where(
            Trek.is_archived.is_(False),
            Trek.status.in_(CATALOGUE_STATUSES),
        )
        .distinct()
        .order_by(
            Trek.location.asc()
        )
    ).scalars().all()

    if location_filter not in location_options:
        location_filter = ""

    statement = (
        db.select(Trek)
        .where(
            Trek.is_archived.is_(False),
            Trek.status.in_(CATALOGUE_STATUSES),
        )
        .options(
            joinedload(Trek.assigned_staff)
        )
    )

    if search_text:
        search_pattern = f"%{search_text}%"

        conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
            Trek.description.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            conditions.append(
                Trek.id == int(possible_id)
            )

        statement = statement.where(
            or_(*conditions)
        )

    if difficulty_filter:
        statement = statement.where(
            Trek.difficulty == difficulty_filter
        )

    if location_filter:
        statement = statement.where(
            Trek.location == location_filter
        )

    if status_filter != "all":
        statement = statement.where(
            Trek.status == status_filter
        )

    statement = statement.order_by(
        Trek.start_date.asc(),
        Trek.id.asc(),
    )

    page_number = request.args.get(
        "page",
        1,
        type=int,
    )

    if page_number is None or page_number < 1:
        page_number = 1

    pagination = db.paginate(
        statement,
        page=page_number,
        per_page=8,
        max_per_page=20,
        error_out=False,
    )

    return render_template(
        "trekker/treks/list.html",
        active_page="treks",
        treks=pagination.items,
        pagination=pagination,
        search_text=search_text,
        difficulty_filter=difficulty_filter,
        location_filter=location_filter,
        status_filter=status_filter,
        difficulties=TREK_DIFFICULTIES,
        location_options=location_options,
    )


@trekker_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("trekker")
def trek_detail(trek_id):
    """
    Display one Trek that is visible to Trekkers.
    """

    trek = _visible_trek_or_404(
        trek_id
    )

    existing_booking = db.session.scalar(
        db.select(Booking).where(
            Booking.user_id == current_user.id,
            Booking.trek_id == trek.id,
        )
    )

    is_bookable = (
        trek.status == "Open"
        and trek.available_slots > 0
    )

    return render_template(
        "trekker/treks/detail.html",
        active_page="treks",
        trek=trek,
        existing_booking=existing_booking,
        is_bookable=is_bookable,
    )


@trekker_bp.route("/bookings")
@login_required
@role_required("trekker")
def my_bookings():
    return _render_placeholder(
        page_title="My Bookings",
        description=(
            "View active bookings, booking status, Trek dates, "
            "and cancellation options."
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
            "View completed and historical Trek activity for "
            "the current Trekker."
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
            "View and update the current Trekker's name, "
            "email, and contact information."
        ),
        active_page="profile",
        planned_milestone="Milestone 12",
    )