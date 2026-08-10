from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from decorators import approved_staff_required
from extensions import db
from models import Booking, Trek, User, BookingEvent


staff_bp = Blueprint(
    "staff",
    __name__,
    url_prefix="/staff",
)


STAFF_TREK_SCOPES = (
    "active",
    "completed",
    "all",
)

PARTICIPANT_STATUS_FILTERS = (
    "all",
    "Booked",
    "Cancelled",
    "Completed",
)


def _render_placeholder(
    page_title: str,
    description: str,
    active_page: str,
    planned_milestone: str,
):

    return render_template(
        "shared/placeholder.html",
        page_title=page_title,
        description=description,
        active_page=active_page,
        planned_milestone=planned_milestone,
    )


def _assigned_trek_or_404(trek_id: int):

    trek = db.session.scalar(
        db.select(Trek).where(
            Trek.id == trek_id,
            Trek.assigned_staff_id == current_user.id,
        )
    )

    if trek is None:
        abort(
            404,
            description=(
                "The requested Trek does not exist or is not "
                "assigned to your Staff account."
            ),
        )

    return trek


def _active_booking_count(trek_id: int) -> int:

    return (
        db.session.scalar(
            db.select(
                func.count(Booking.id)
            ).where(
                Booking.trek_id == trek_id,
                Booking.status == "Booked",
            )
        )
        or 0
    )


def _booking_counts_for_trek(trek_id: int):

    counts = {
        "Booked": 0,
        "Cancelled": 0,
        "Completed": 0,
        "Total": 0,
    }

    rows = db.session.execute(
        db.select(
            Booking.status,
            func.count(Booking.id),
        )
        .where(
            Booking.trek_id == trek_id
        )
        .group_by(
            Booking.status
        )
    ).all()

    for status, count in rows:
        counts[status] = count
        counts["Total"] += count

    return counts


def _active_booking_counts_for_treks(treks):

    trek_ids = [
        trek.id
        for trek in treks
    ]

    if not trek_ids:
        return {}

    rows = db.session.execute(
        db.select(
            Booking.trek_id,
            func.count(Booking.id),
        )
        .where(
            Booking.trek_id.in_(trek_ids),
            Booking.status == "Booked",
        )
        .group_by(
            Booking.trek_id
        )
    ).all()

    return {
        trek_id: count
        for trek_id, count in rows
    }


def _status_options_for_trek(trek):


    transitions = {
        "Pending": (
            "Pending",
        ),
        "Approved": (
            "Approved",
            "Open",
            "Closed",
        ),
        "Open": (
            "Open",
            "Closed",
        ),
        "Closed": (
            "Closed",
            "Open",
        ),
        "Ongoing": (
            "Ongoing",
        ),
        "Completed": (
            "Completed",
        ),
    }

    return transitions.get(
        trek.status,
        (trek.status,),
    )


@staff_bp.route("/dashboard")
@login_required
@approved_staff_required
def dashboard():

    assigned_treks_count = (
        db.session.scalar(
            db.select(
                func.count(Trek.id)
            ).where(
                Trek.assigned_staff_id == current_user.id,
                Trek.is_archived.is_(False),
                Trek.status != "Completed",
            )
        )
        or 0
    )

    open_treks_count = (
        db.session.scalar(
            db.select(
                func.count(Trek.id)
            ).where(
                Trek.assigned_staff_id == current_user.id,
                Trek.is_archived.is_(False),
                Trek.status == "Open",
            )
        )
        or 0
    )

    active_participants_count = (
        db.session.scalar(
            db.select(
                func.count(Booking.id)
            )
            .join(
                Trek,
                Booking.trek_id == Trek.id,
            )
            .where(
                Trek.assigned_staff_id == current_user.id,
                Trek.is_archived.is_(False),
                Booking.status == "Booked",
            )
        )
        or 0
    )

    upcoming_treks = db.session.execute(
        db.select(Trek)
        .where(
            Trek.assigned_staff_id == current_user.id,
            Trek.is_archived.is_(False),
            Trek.status != "Completed",
        )
        .order_by(
            Trek.start_date.asc(),
            Trek.id.asc(),
        )
        .limit(5)
    ).scalars().all()

    active_booking_counts = (
        _active_booking_counts_for_treks(
            upcoming_treks
        )
    )

    return render_template(
        "staff/dashboard.html",
        active_page="dashboard",
        assigned_treks_count=assigned_treks_count,
        open_treks_count=open_treks_count,
        active_participants_count=(
            active_participants_count
        ),
        upcoming_treks=upcoming_treks,
        active_booking_counts=active_booking_counts,
    )


@staff_bp.route("/treks")
@login_required
@approved_staff_required
def my_treks():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    scope = request.args.get(
        "scope",
        "active",
    ).strip().lower()

    if scope not in STAFF_TREK_SCOPES:
        scope = "active"

    statement = db.select(Trek).where(
        Trek.assigned_staff_id == current_user.id
    )

    if scope == "active":
        statement = statement.where(
            Trek.is_archived.is_(False),
            Trek.status != "Completed",
        )

    elif scope == "completed":
        statement = statement.where(
            Trek.status == "Completed"
        )

    if search_text:
        search_pattern = f"%{search_text}%"

        conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            conditions.append(
                Trek.id == int(possible_id)
            )

        statement = statement.where(
            or_(*conditions)
        )

    statement = statement.order_by(
        Trek.is_archived.asc(),
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

    active_booking_counts = (
        _active_booking_counts_for_treks(
            pagination.items
        )
    )

    return render_template(
        "staff/treks/list.html",
        active_page="treks",
        treks=pagination.items,
        pagination=pagination,
        active_booking_counts=active_booking_counts,
        search_text=search_text,
        scope=scope,
    )


@staff_bp.route("/treks/<int:trek_id>")
@login_required
@approved_staff_required
def trek_detail(trek_id):

    trek = _assigned_trek_or_404(
        trek_id
    )

    booking_counts = _booking_counts_for_trek(
        trek.id
    )

    maximum_available_slots = max(
        trek.total_slots - booking_counts["Booked"],
        0,
    )

    recent_bookings = db.session.execute(
        db.select(Booking)
        .where(
            Booking.trek_id == trek.id
        )
        .options(
            selectinload(Booking.trekker)
        )
        .order_by(
            Booking.booking_date.desc(),
            Booking.id.desc(),
        )
        .limit(5)
    ).scalars().all()

    can_update = (
        not trek.is_archived
        and trek.status
        not in {
            "Ongoing",
            "Completed",
        }
    )

    can_start = (
        not trek.is_archived
        and trek.status == "Open"
    )

    can_complete = (
        not trek.is_archived
        and trek.status == "Ongoing"
    )

    return render_template(
        "staff/treks/detail.html",
        active_page="treks",
        trek=trek,
        booking_counts=booking_counts,
        maximum_available_slots=(
            maximum_available_slots
        ),
        status_options=(
            _status_options_for_trek(trek)
        ),
        recent_bookings=recent_bookings,
        can_update=can_update,
        can_start=can_start,
        can_complete=can_complete,
    )


@staff_bp.route(
    "/treks/<int:trek_id>/update",
    methods=["POST"],
)
@login_required
@approved_staff_required
def update_trek(trek_id):

    trek = _assigned_trek_or_404(
        trek_id
    )

    if trek.is_archived:
        flash(
            "An archived Trek cannot be updated.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    if trek.status in {
        "Ongoing",
        "Completed",
    }:
        flash(
            "Slots and normal status cannot be changed after "
            "the Trek has started.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    errors = []

    raw_available_slots = request.form.get(
        "available_slots",
        "",
    ).strip()

    try:
        available_slots = int(
            raw_available_slots
        )
    except ValueError:
        available_slots = None

        errors.append(
            "Available slots must be a whole number."
        )

    active_bookings = _active_booking_count(
        trek.id
    )

    maximum_available_slots = max(
        trek.total_slots - active_bookings,
        0,
    )

    if available_slots is not None:
        if available_slots < 0:
            errors.append(
                "Available slots cannot be negative."
            )

        elif available_slots > maximum_available_slots:
            errors.append(
                "Available slots cannot exceed total capacity "
                "minus active bookings. The maximum allowed "
                f"value is {maximum_available_slots}."
            )

    new_status = request.form.get(
        "status",
        "",
    ).strip()

    allowed_statuses = _status_options_for_trek(
        trek
    )

    if new_status not in allowed_statuses:
        errors.append(
            "That Trek status change is not permitted."
        )

    if errors:
        for error in errors:
            flash(
                error,
                "danger",
            )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    trek.available_slots = available_slots
    trek.status = new_status

    try:
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        flash(
            "The changes could not be saved because they "
            "violated a database rule.",
            "danger",
        )

    else:
        flash(
            f'Trek "{trek.name}" was updated successfully.',
            "success",
        )

    return redirect(
        url_for(
            "staff.trek_detail",
            trek_id=trek.id,
        )
    )


@staff_bp.route(
    "/treks/<int:trek_id>/start",
    methods=["GET", "POST"],
)
@login_required
@approved_staff_required
def start_trek(trek_id):

    trek = _assigned_trek_or_404(
        trek_id
    )

    if trek.is_archived:
        flash(
            "An archived Trek cannot be started.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    if trek.status != "Open":
        flash(
            "Only an Open Trek can be marked as started.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    active_booking_count = (
        _active_booking_count(trek.id)
    )

    if request.method == "POST":
        trek.status = "Ongoing"

        # No new bookings should be accepted after the Trek starts.
        trek.available_slots = 0

        db.session.commit()

        flash(
            f'Trek "{trek.name}" is now Ongoing.',
            "success",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    return render_template(
        "staff/treks/confirm_status.html",
        active_page="treks",
        trek=trek,
        page_title="Start Trek",
        action_name="start",
        active_booking_count=active_booking_count,
    )


@staff_bp.route(
    "/treks/<int:trek_id>/complete",
    methods=["GET", "POST"],
)
@login_required
@approved_staff_required
def complete_trek(trek_id):

    trek = _assigned_trek_or_404(
        trek_id
    )

    if trek.is_archived:
        flash(
            "An archived Trek cannot be completed.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    if trek.status != "Ongoing":
        flash(
            "Only an Ongoing Trek can be marked as completed.",
            "warning",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    active_bookings = db.session.execute(
        db.select(Booking).where(
            Booking.trek_id == trek.id,
            Booking.status == "Booked",
        )
    ).scalars().all()

    if request.method == "POST":
        completed_at = datetime.now()

        trek.status = "Completed"
        trek.available_slots = 0

        for booking in active_bookings:
            previous_status = booking.status

            booking.status = "Completed"
            booking.completed_at = completed_at

            event = BookingEvent(
                booking=booking,
                event_type="Completed",
                previous_status=previous_status,
                new_status="Completed",
                changed_by_user_id=current_user.id,
                note=(
                    f'Trek "{trek.name}" completed by the '
                    "assigned Staff member."
                ),
            )

            db.session.add(
                event
            )

        db.session.commit()

        flash(
            f'Trek "{trek.name}" was completed. '
            f"{len(active_bookings)} booking record(s) "
            "were moved to Completed.",
            "success",
        )

        return redirect(
            url_for(
                "staff.trek_detail",
                trek_id=trek.id,
            )
        )

    return render_template(
        "staff/treks/confirm_status.html",
        active_page="treks",
        trek=trek,
        page_title="Complete Trek",
        action_name="complete",
        active_booking_count=len(active_bookings),
    )


@staff_bp.route("/participants")
@login_required
@approved_staff_required
def participants():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    status_filter = request.args.get(
        "status",
        "all",
    ).strip()

    if status_filter not in PARTICIPANT_STATUS_FILTERS:
        status_filter = "all"

    trek_filter = request.args.get(
        "trek_id",
        type=int,
    )

    selected_trek = None

    statement = (
        db.select(Booking)
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .join(
            User,
            Booking.user_id == User.id,
        )
        .where(
            Trek.assigned_staff_id == current_user.id
        )
        .options(
            selectinload(Booking.trek),
            selectinload(Booking.trekker),
        )
    )

    if trek_filter is not None:
        selected_trek = _assigned_trek_or_404(
            trek_filter
        )

        statement = statement.where(
            Booking.trek_id == selected_trek.id
        )

    if search_text:
        search_pattern = f"%{search_text}%"

        conditions = [
            User.full_name.ilike(search_pattern),
            User.email.ilike(search_pattern),
            User.phone.ilike(search_pattern),
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            numeric_id = int(possible_id)

            conditions.extend(
                [
                    Booking.id == numeric_id,
                    User.id == numeric_id,
                    Trek.id == numeric_id,
                ]
            )

        statement = statement.where(
            or_(*conditions)
        )

    if status_filter != "all":
        statement = statement.where(
            Booking.status == status_filter
        )

    statement = statement.order_by(
        Booking.booking_date.desc(),
        Booking.id.desc(),
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
        per_page=10,
        max_per_page=20,
        error_out=False,
    )

    assigned_treks = db.session.execute(
        db.select(Trek)
        .where(
            Trek.assigned_staff_id == current_user.id
        )
        .order_by(
            Trek.start_date.desc(),
            Trek.id.desc(),
        )
    ).scalars().all()

    return render_template(
        "staff/participants.html",
        active_page="participants",
        bookings=pagination.items,
        pagination=pagination,
        assigned_treks=assigned_treks,
        selected_trek=selected_trek,
        trek_filter=trek_filter,
        search_text=search_text,
        status_filter=status_filter,
        participant_statuses=(
            PARTICIPANT_STATUS_FILTERS
        ),
    )


@staff_bp.route(
    "/treks/<int:trek_id>/participants"
)
@login_required
@approved_staff_required
def trek_participants(trek_id):

    trek = _assigned_trek_or_404(
        trek_id
    )

    return redirect(
        url_for(
            "staff.participants",
            trek_id=trek.id,
        )
    )


@staff_bp.route("/profile")
@login_required
@approved_staff_required
def profile():
    return _render_placeholder(
        page_title="Staff Profile",
        description=(
            "View and update the current Staff member's "
            "contact information."
        ),
        active_page="profile",
        planned_milestone="Milestone 12",
    )