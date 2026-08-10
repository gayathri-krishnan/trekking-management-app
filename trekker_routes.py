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
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from decorators import role_required
from extensions import db
from models import Booking, BookingEvent, Trek
from profile_helpers import profile_page

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

BOOKING_STATUS_FILTERS = (
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


def _visible_trek_or_404(trek_id: int):

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


def _owned_booking_or_404(booking_id: int):
    """
    Return a Booking only when it belongs to the currently
    logged-in Trekker.

    A Trekker must not be able to inspect another user's
    booking by changing an ID in the URL.
    """

    booking = db.session.scalar(
        db.select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.user_id == current_user.id,
        )
        .options(
            joinedload(Booking.trek)
        )
    )

    if booking is None:
        abort(
            404,
            description="The requested Booking does not exist.",
        )

    return booking


def _booking_can_be_cancelled(booking: Booking) -> bool:
    """
    Return True only when a current Booked record has not
    started or completed.
    """

    if booking.status != "Booked":
        return False

    if booking.trek is None:
        return False

    if booking.trek.is_archived:
        return False

    if booking.trek.status in {
        "Ongoing",
        "Completed",
    }:
        return False

    return True


def _booking_counts_for_current_user():
    """
    Return booking counts grouped by status for the current
    Trekker.
    """

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
            Booking.user_id == current_user.id
        )
        .group_by(
            Booking.status
        )
    ).all()

    for status, count in rows:
        counts[status] = count
        counts["Total"] += count

    return counts


def _try_take_available_slot(trek_id: int) -> bool:
    """
    Atomically reduce available slots by one.

    The UPDATE succeeds only when the Trek is still Open,
    active, and has at least one available slot.
    """

    result = db.session.execute(
        update(Trek)
        .where(
            Trek.id == trek_id,
            Trek.is_archived.is_(False),
            Trek.status == "Open",
            Trek.available_slots > 0,
        )
        .values(
            available_slots=Trek.available_slots - 1
        )
        .execution_options(
            synchronize_session=False
        )
    )

    return result.rowcount == 1


def _restore_available_slot(trek_id: int) -> None:
    """
    Atomically return one available slot after cancellation.

    The total-slots limit prevents the value from exceeding
    Trek capacity.
    """

    db.session.execute(
        update(Trek)
        .where(
            Trek.id == trek_id,
            Trek.available_slots < Trek.total_slots,
        )
        .values(
            available_slots=Trek.available_slots + 1
        )
        .execution_options(
            synchronize_session=False
        )
    )

@trekker_bp.route("/dashboard")
@login_required
@role_required("trekker")
def dashboard():

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
    Display one Trek and its current booking availability.
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

    can_rebook = (
        existing_booking is not None
        and existing_booking.status == "Cancelled"
        and is_bookable
    )

    return render_template(
        "trekker/treks/detail.html",
        active_page="treks",
        trek=trek,
        existing_booking=existing_booking,
        is_bookable=is_bookable,
        can_rebook=can_rebook,
    )

@trekker_bp.route(
    "/treks/<int:trek_id>/book",
    methods=["POST"],
)
@login_required
@role_required("trekker")
def book_trek(trek_id):
    """
    Create a new Booking or reactivate a cancelled Booking.

    Slot acquisition and Booking changes occur in one
    transaction. If any part fails, all changes are rolled
    back.
    """

    trek = db.session.scalar(
        db.select(Trek).where(
            Trek.id == trek_id,
            Trek.is_archived.is_(False),
        )
    )

    if trek is None:
        abort(
            404,
            description="The requested Trek does not exist.",
        )

    existing_booking = db.session.scalar(
        db.select(Booking).where(
            Booking.user_id == current_user.id,
            Booking.trek_id == trek.id,
        )
    )

    if (
        existing_booking is not None
        and existing_booking.status == "Booked"
    ):
        flash(
            "You have already booked this Trek.",
            "info",
        )

        return redirect(
            url_for(
                "trekker.booking_detail",
                booking_id=existing_booking.id,
            )
        )

    if (
        existing_booking is not None
        and existing_booking.status == "Completed"
    ):
        flash(
            "This Trek is already part of your completed history.",
            "warning",
        )

        return redirect(
            url_for(
                "trekker.booking_detail",
                booking_id=existing_booking.id,
            )
        )

    now = datetime.now()

    try:
        if existing_booking is not None:
            # Claim the Cancelled row. The conditional status
            # prevents two simultaneous rebooking requests from
            # processing the same Booking twice.
            booking_update = db.session.execute(
                update(Booking)
                .where(
                    Booking.id == existing_booking.id,
                    Booking.user_id == current_user.id,
                    Booking.status == "Cancelled",
                )
                .values(
                    status="Booked",
                    booking_date=now,
                    cancelled_at=None,
                    completed_at=None,
                    updated_at=now,
                )
                .execution_options(
                    synchronize_session=False
                )
            )

            if booking_update.rowcount != 1:
                db.session.rollback()

                flash(
                    "That Booking was already changed by another "
                    "request. Please check My Bookings.",
                    "warning",
                )

                return redirect(
                    url_for("trekker.my_bookings")
                )

        slot_was_taken = _try_take_available_slot(
            trek.id
        )

        if not slot_was_taken:
            db.session.rollback()

            latest_trek = db.session.get(
                Trek,
                trek.id,
            )

            if latest_trek is None or latest_trek.is_archived:
                message = (
                    "This Trek is no longer available."
                )

                redirect_url = url_for(
                    "trekker.browse_treks"
                )

            elif latest_trek.status != "Open":
                message = (
                    "This Trek is not currently Open for booking."
                )

                if latest_trek.status in CATALOGUE_STATUSES:
                    redirect_url = url_for(
                        "trekker.trek_detail",
                        trek_id=latest_trek.id,
                    )
                else:
                    redirect_url = url_for(
                        "trekker.browse_treks"
                    )

            else:
                message = (
                    "This Trek is currently full. Another user "
                    "may have booked the final available slot."
                )

                redirect_url = url_for(
                    "trekker.trek_detail",
                    trek_id=latest_trek.id,
                )

            flash(
                message,
                "warning",
            )

            return redirect(
                redirect_url
            )

        if existing_booking is None:
            booking = Booking(
                user_id=current_user.id,
                trek_id=trek.id,
                booking_date=now,
                status="Booked",
            )

            db.session.add(
                booking
            )

            # Flush assigns the new Booking ID while keeping
            # the transaction open.
            db.session.flush()

            booking_id = booking.id
            event_type = "Booked"
            previous_status = None

        else:
            booking_id = existing_booking.id
            event_type = "Rebooked"
            previous_status = "Cancelled"

        event = BookingEvent(
            booking_id=booking_id,
            event_type=event_type,
            previous_status=previous_status,
            new_status="Booked",
            changed_by_user_id=current_user.id,
            note=(
                f'Trek "{trek.name}" booked by the Trekker.'
            ),
        )

        db.session.add(
            event
        )

        db.session.commit()

    except IntegrityError:
        # Rolling back also reverses any slot decrement made
        # earlier in the same transaction.
        db.session.rollback()

        flash(
            "The Booking could not be created. You may already "
            "have a Booking record for this Trek.",
            "danger",
        )

        return redirect(
            url_for(
                "trekker.trek_detail",
                trek_id=trek.id,
            )
        )

    flash(
        f'Your Booking for "{trek.name}" was successful.',
        "success",
    )

    return redirect(
        url_for(
            "trekker.booking_detail",
            booking_id=booking_id,
        )
    )

@trekker_bp.route("/bookings")
@login_required
@role_required("trekker")
def my_bookings():
    """
    List, search, filter, and paginate the current Trekker's
    Booking records.
    """

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    status_filter = request.args.get(
        "status",
        "all",
    ).strip()

    if status_filter not in BOOKING_STATUS_FILTERS:
        status_filter = "all"

    statement = (
        db.select(Booking)
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .where(
            Booking.user_id == current_user.id
        )
        .options(
            joinedload(Booking.trek)
        )
    )

    if search_text:
        search_pattern = f"%{search_text}%"

        conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            numeric_id = int(
                possible_id
            )

            conditions.extend(
                [
                    Booking.id == numeric_id,
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

    cancellable_booking_ids = {
        booking.id
        for booking in pagination.items
        if _booking_can_be_cancelled(booking)
    }

    return render_template(
        "trekker/bookings/list.html",
        active_page="bookings",
        bookings=pagination.items,
        pagination=pagination,
        booking_counts=(
            _booking_counts_for_current_user()
        ),
        cancellable_booking_ids=(
            cancellable_booking_ids
        ),
        search_text=search_text,
        status_filter=status_filter,
        booking_statuses=BOOKING_STATUS_FILTERS,
    )

@trekker_bp.route(
    "/bookings/<int:booking_id>"
)
@login_required
@role_required("trekker")
def booking_detail(booking_id):
    """
    Display one Booking and its complete event history.
    """

    booking = _owned_booking_or_404(
        booking_id
    )

    events = db.session.execute(
        db.select(BookingEvent)
        .where(
            BookingEvent.booking_id == booking.id
        )
        .options(
            joinedload(BookingEvent.changed_by)
        )
        .order_by(
            BookingEvent.created_at.asc(),
            BookingEvent.id.asc(),
        )
    ).scalars().all()

    trek_visible = (
        booking.trek is not None
        and not booking.trek.is_archived
        and booking.trek.status in CATALOGUE_STATUSES
    )

    return render_template(
        "trekker/bookings/detail.html",
        active_page="bookings",
        booking=booking,
        events=events,
        can_cancel=(
            _booking_can_be_cancelled(booking)
        ),
        trek_visible=trek_visible,
    )

@trekker_bp.route(
    "/bookings/<int:booking_id>/cancel",
    methods=["GET", "POST"],
)
@login_required
@role_required("trekker")
def cancel_booking(booking_id):
    """
    Confirm and cancel one owned active Booking.
    """

    booking = _owned_booking_or_404(
        booking_id
    )

    if not _booking_can_be_cancelled(booking):
        flash(
            "This Booking can no longer be cancelled.",
            "warning",
        )

        return redirect(
            url_for(
                "trekker.booking_detail",
                booking_id=booking.id,
            )
        )

    if request.method == "POST":
        now = datetime.now()

        try:
            booking_update = db.session.execute(
                update(Booking)
                .where(
                    Booking.id == booking.id,
                    Booking.user_id == current_user.id,
                    Booking.status == "Booked",
                )
                .values(
                    status="Cancelled",
                    cancelled_at=now,
                    updated_at=now,
                )
                .execution_options(
                    synchronize_session=False
                )
            )

            if booking_update.rowcount != 1:
                db.session.rollback()

                flash(
                    "This Booking was already changed by another "
                    "request.",
                    "warning",
                )

                return redirect(
                    url_for(
                        "trekker.booking_detail",
                        booking_id=booking.id,
                    )
                )

            _restore_available_slot(
                booking.trek_id
            )

            event = BookingEvent(
                booking_id=booking.id,
                event_type="Cancelled",
                previous_status="Booked",
                new_status="Cancelled",
                changed_by_user_id=current_user.id,
                note=(
                    f'Booking for "{booking.trek.name}" '
                    "cancelled by the Trekker."
                ),
            )

            db.session.add(
                event
            )

            db.session.commit()

        except IntegrityError:
            db.session.rollback()

            flash(
                "The Booking could not be cancelled because "
                "the database rejected the change.",
                "danger",
            )

            return redirect(
                url_for(
                    "trekker.booking_detail",
                    booking_id=booking.id,
                )
            )

        flash(
            f'Your Booking for "{booking.trek.name}" '
            "was cancelled.",
            "success",
        )

        return redirect(
            url_for(
                "trekker.my_bookings",
                status="Cancelled",
            )
        )

    return render_template(
        "trekker/bookings/confirm_cancel.html",
        active_page="bookings",
        booking=booking,
    )

@trekker_bp.route("/history")
@login_required
@role_required("trekker")
def history():
    """
    Display completed Trek history for the current Trekker.
    """

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    difficulty_filter = request.args.get(
        "difficulty",
        "",
    ).strip()

    year_filter = request.args.get(
        "year",
        "",
    ).strip()

    if difficulty_filter not in TREK_DIFFICULTIES:
        difficulty_filter = ""

    year_expression = func.strftime(
        "%Y",
        Trek.end_date,
    )

    year_options = db.session.execute(
        db.select(
            year_expression
        )
        .select_from(Booking)
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .where(
            Booking.user_id == current_user.id,
            Booking.status == "Completed",
        )
        .distinct()
        .order_by(
            year_expression.desc()
        )
    ).scalars().all()

    year_options = [
        year
        for year in year_options
        if year
    ]

    if year_filter not in year_options:
        year_filter = ""

    statement = (
        db.select(Booking)
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .where(
            Booking.user_id == current_user.id,
            Booking.status == "Completed",
        )
        .options(
            joinedload(Booking.trek)
        )
    )

    if search_text:
        search_pattern = f"%{search_text}%"

        conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            numeric_id = int(
                possible_id
            )

            conditions.extend(
                [
                    Booking.id == numeric_id,
                    Trek.id == numeric_id,
                ]
            )

        statement = statement.where(
            or_(*conditions)
        )

    if difficulty_filter:
        statement = statement.where(
            Trek.difficulty == difficulty_filter
        )

    if year_filter:
        statement = statement.where(
            year_expression == year_filter
        )

    statement = statement.order_by(
        Trek.end_date.desc(),
        Booking.completed_at.desc(),
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

    total_completed = (
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

    total_days = (
        db.session.scalar(
            db.select(
                func.sum(Trek.duration_days)
            )
            .select_from(Booking)
            .join(
                Trek,
                Booking.trek_id == Trek.id,
            )
            .where(
                Booking.user_id == current_user.id,
                Booking.status == "Completed",
            )
        )
        or 0
    )

    unique_locations = (
        db.session.scalar(
            db.select(
                func.count(
                    func.distinct(Trek.location)
                )
            )
            .select_from(Booking)
            .join(
                Trek,
                Booking.trek_id == Trek.id,
            )
            .where(
                Booking.user_id == current_user.id,
                Booking.status == "Completed",
            )
        )
        or 0
    )

    return render_template(
        "trekker/history.html",
        active_page="history",
        bookings=pagination.items,
        pagination=pagination,
        total_completed=total_completed,
        total_days=total_days,
        unique_locations=unique_locations,
        search_text=search_text,
        difficulty_filter=difficulty_filter,
        year_filter=year_filter,
        difficulties=TREK_DIFFICULTIES,
        year_options=year_options,
    )


@trekker_bp.route(
    "/profile",
    methods=["GET", "POST"],
)
@login_required
@role_required("trekker")
def profile():
    """
    Display and update the current Trekker's profile.
    """

    return profile_page(
        role_title="Trekker",
        profile_endpoint="trekker.profile",
    )