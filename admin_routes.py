from datetime import date

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from decorators import role_required
from extensions import db
from models import Booking, Trek, User, BookingEvent


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


TREK_DIFFICULTIES = (
    "Easy",
    "Moderate",
    "Hard",
)

TREK_STATUSES = (
    "Pending",
    "Approved",
    "Open",
    "Closed",
    "Ongoing",
    "Completed",
)

TREK_SCOPES = (
    "active",
    "archived",
    "all",
)
STAFF_STATUS_FILTERS = (
    "all",
    "pending",
    "approved",
    "blacklisted",
)

TREKKER_STATUS_FILTERS = (
    "all",
    "active",
    "blacklisted",
)

TREK_FORM_FIELDS = (
    "name",
    "location",
    "difficulty",
    "duration_days",
    "total_slots",
    "available_slots",
    "assigned_staff_id",
    "status",
    "start_date",
    "end_date",
    "description",
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


def _normalize_text(value: str) -> str:

    return " ".join(value.split())


def _parse_integer(
    raw_value: str,
    field_label: str,
    errors: list[str],
    minimum: int,
):

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        errors.append(
            f"{field_label} must be a whole number."
        )
        return None

    if value < minimum:
        errors.append(
            f"{field_label} must be at least {minimum}."
        )
        return None

    return value


def _parse_date(
    raw_value: str,
    field_label: str,
    errors: list[str],
):

    try:
        return date.fromisoformat(raw_value)
    except (TypeError, ValueError):
        errors.append(
            f"{field_label} must contain a valid date."
        )
        return None


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


def _staff_options(current_staff_id=None):

    staff_members = db.session.execute(
        db.select(User)
        .where(
            User.role == "staff",
            User.is_approved.is_(True),
            User.is_blacklisted.is_(False),
        )
        .order_by(
            User.full_name.asc(),
            User.id.asc(),
        )
    ).scalars().all()

    if current_staff_id is not None:
        current_staff_is_present = any(
            staff.id == current_staff_id
            for staff in staff_members
        )

        if not current_staff_is_present:
            current_staff = db.session.get(
                User,
                current_staff_id,
            )

            if (
                current_staff is not None
                and current_staff.role == "staff"
            ):
                staff_members.append(current_staff)

    return sorted(
        staff_members,
        key=lambda staff: (
            staff.full_name.lower(),
            staff.id,
        ),
    )


def _form_data_for_trek(trek=None):

    if request.method == "POST":
        return {
            field_name: request.form.get(
                field_name,
                "",
            )
            for field_name in TREK_FORM_FIELDS
        }

    if trek is None:
        return {
            "name": "",
            "location": "",
            "difficulty": "Easy",
            "duration_days": "1",
            "total_slots": "10",
            "available_slots": "10",
            "assigned_staff_id": "",
            "status": "Pending",
            "start_date": "",
            "end_date": "",
            "description": "",
        }

    return {
        "name": trek.name,
        "location": trek.location,
        "difficulty": trek.difficulty,
        "duration_days": str(trek.duration_days),
        "total_slots": str(trek.total_slots),
        "available_slots": str(trek.available_slots),
        "assigned_staff_id": (
            str(trek.assigned_staff_id)
            if trek.assigned_staff_id is not None
            else ""
        ),
        "status": trek.status,
        "start_date": trek.start_date.isoformat(),
        "end_date": trek.end_date.isoformat(),
        "description": trek.description,
    }


def _validate_trek_form(existing_trek=None):

    errors = []

    name = _normalize_text(
        request.form.get("name", "")
    )

    location = _normalize_text(
        request.form.get("location", "")
    )

    difficulty = request.form.get(
        "difficulty",
        "",
    ).strip()

    status = request.form.get(
        "status",
        "",
    ).strip()

    description = request.form.get(
        "description",
        "",
    ).strip()

    if not 2 <= len(name) <= 150:
        errors.append(
            "Trek name must contain between 2 and "
            "150 characters."
        )

    if not 2 <= len(location) <= 150:
        errors.append(
            "Location must contain between 2 and "
            "150 characters."
        )

    if difficulty not in TREK_DIFFICULTIES:
        errors.append(
            "Choose a valid difficulty."
        )

    if status not in TREK_STATUSES:
        errors.append(
            "Choose a valid trek status."
        )

    if len(description) > 2000:
        errors.append(
            "Description cannot exceed 2000 characters."
        )

    duration_days = _parse_integer(
        request.form.get(
            "duration_days",
            "",
        ),
        "Duration",
        errors,
        minimum=1,
    )

    total_slots = _parse_integer(
        request.form.get(
            "total_slots",
            "",
        ),
        "Total slots",
        errors,
        minimum=1,
    )

    available_slots = _parse_integer(
        request.form.get(
            "available_slots",
            "",
        ),
        "Available slots",
        errors,
        minimum=0,
    )

    start_date = _parse_date(
        request.form.get(
            "start_date",
            "",
        ),
        "Start date",
        errors,
    )

    end_date = _parse_date(
        request.form.get(
            "end_date",
            "",
        ),
        "End date",
        errors,
    )

    if (
        start_date is not None
        and end_date is not None
        and end_date < start_date
    ):
        errors.append(
            "End date cannot be earlier than start date."
        )

    assigned_staff_id = None

    raw_staff_id = request.form.get(
        "assigned_staff_id",
        "",
    ).strip()

    if raw_staff_id:
        try:
            assigned_staff_id = int(raw_staff_id)
        except ValueError:
            errors.append(
                "Choose a valid staff member."
            )
        else:
            selected_staff = db.session.get(
                User,
                assigned_staff_id,
            )

            if (
                selected_staff is None
                or selected_staff.role != "staff"
            ):
                errors.append(
                    "The selected account is not a staff member."
                )

            elif not selected_staff.is_approved:
                errors.append(
                    "Only approved staff can be assigned "
                    "to a trek."
                )

            elif selected_staff.is_blacklisted:
                errors.append(
                    "A blacklisted staff member cannot be "
                    "assigned to a trek."
                )

    active_bookings = 0

    if existing_trek is not None:
        active_bookings = _active_booking_count(
            existing_trek.id
        )

    if (
        total_slots is not None
        and total_slots < active_bookings
    ):
        errors.append(
            "Total slots cannot be lower than the number "
            f"of active bookings ({active_bookings})."
        )

    if (
        total_slots is not None
        and available_slots is not None
    ):
        maximum_available = (
            total_slots - active_bookings
        )

        if available_slots > maximum_available:
            errors.append(
                "Available slots cannot exceed total slots "
                "minus active bookings. The maximum allowed "
                f"value is {maximum_available}."
            )

    if errors:
        return None, errors

    validated_data = {
        "name": name,
        "location": location,
        "difficulty": difficulty,
        "duration_days": duration_days,
        "total_slots": total_slots,
        "available_slots": available_slots,
        "assigned_staff_id": assigned_staff_id,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "description": description,
    }

    return validated_data, []


def _render_trek_form(
    trek=None,
    errors=None,
):

    current_staff_id = (
        trek.assigned_staff_id
        if trek is not None
        else None
    )

    active_bookings = (
        _active_booking_count(trek.id)
        if trek is not None
        else 0
    )

    return render_template(
        "admin/treks/form.html",
        active_page="treks",
        trek=trek,
        errors=errors or [],
        form_data=_form_data_for_trek(trek),
        difficulties=TREK_DIFFICULTIES,
        statuses=TREK_STATUSES,
        staff_options=_staff_options(
            current_staff_id
        ),
        active_booking_count=active_bookings,
    )


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():

    total_treks = db.session.scalar(
        db.select(
            func.count(Trek.id)
        ).where(
            Trek.is_archived.is_(False)
        )
    ) or 0

    total_users = db.session.scalar(
        db.select(
            func.count(User.id)
        ).where(
            User.role == "trekker"
        )
    ) or 0

    total_staff = db.session.scalar(
        db.select(
            func.count(User.id)
        ).where(
            User.role == "staff"
        )
    ) or 0

    total_bookings = db.session.scalar(
        db.select(
            func.count(Booking.id)
        )
    ) or 0

    recent_bookings = db.session.execute(
        db.select(Booking)
        .options(
            joinedload(Booking.trekker),
            joinedload(Booking.trek),
        )
        .order_by(
            Booking.booking_date.desc(),
            Booking.id.desc(),
        )
        .limit(5)
    ).scalars().all()

    return render_template(
        "admin/dashboard.html",
        active_page="dashboard",
        total_treks=total_treks,
        total_users=total_users,
        total_staff=total_staff,
        total_bookings=total_bookings,
        recent_bookings=recent_bookings,
    )


@admin_bp.route("/treks")
@login_required
@role_required("admin")
def manage_treks():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    difficulty_filter = request.args.get(
        "difficulty",
        "",
    ).strip()

    status_filter = request.args.get(
        "status",
        "",
    ).strip()

    scope = request.args.get(
        "scope",
        "active",
    ).strip().lower()

    if difficulty_filter not in TREK_DIFFICULTIES:
        difficulty_filter = ""

    if status_filter not in TREK_STATUSES:
        status_filter = ""

    if scope not in TREK_SCOPES:
        scope = "active"

    statement = (
        db.select(Trek)
        .options(
            joinedload(Trek.assigned_staff)
        )
    )

    if scope == "active":
        statement = statement.where(
            Trek.is_archived.is_(False)
        )

    elif scope == "archived":
        statement = statement.where(
            Trek.is_archived.is_(True)
        )

    if search_text:
        search_pattern = f"%{search_text}%"

        search_conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            search_conditions.append(
                Trek.id == int(possible_id)
            )

        statement = statement.where(
            or_(*search_conditions)
        )

    if difficulty_filter:
        statement = statement.where(
            Trek.difficulty == difficulty_filter
        )

    if status_filter:
        statement = statement.where(
            Trek.status == status_filter
        )

    statement = statement.order_by(
        Trek.is_archived.asc(),
        Trek.start_date.desc(),
        Trek.id.desc(),
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
        "admin/treks/list.html",
        active_page="treks",
        treks=pagination.items,
        pagination=pagination,
        search_text=search_text,
        difficulty_filter=difficulty_filter,
        status_filter=status_filter,
        scope=scope,
        difficulties=TREK_DIFFICULTIES,
        statuses=TREK_STATUSES,
    )


@admin_bp.route(
    "/treks/new",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def create_trek():

    if request.method == "POST":
        validated_data, errors = (
            _validate_trek_form()
        )

        if not errors:
            trek = Trek(**validated_data)

            try:
                db.session.add(trek)
                db.session.commit()

            except IntegrityError:
                db.session.rollback()

                errors = [
                    "The trek could not be saved because "
                    "one or more values violated a database rule."
                ]

            else:
                flash(
                    f'Trek "{trek.name}" was created successfully.',
                    "success",
                )

                return redirect(
                    url_for("admin.manage_treks")
                )

        return _render_trek_form(
            errors=errors
        )

    return _render_trek_form()


@admin_bp.route(
    "/treks/<int:trek_id>/edit",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def edit_trek(trek_id):

    trek = db.get_or_404(
        Trek,
        trek_id,
        description="The requested trek does not exist.",
    )

    if trek.is_archived:
        flash(
            "Restore this trek before editing it.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.manage_treks",
                scope="archived",
            )
        )

    if request.method == "POST":
        validated_data, errors = (
            _validate_trek_form(
                existing_trek=trek
            )
        )

        if not errors:
            for field_name, value in (
                validated_data.items()
            ):
                setattr(
                    trek,
                    field_name,
                    value,
                )

            try:
                db.session.commit()

            except IntegrityError:
                db.session.rollback()

                errors = [
                    "The changes could not be saved because "
                    "one or more values violated a database rule."
                ]

            else:
                flash(
                    f'Trek "{trek.name}" was updated successfully.',
                    "success",
                )

                return redirect(
                    url_for("admin.manage_treks")
                )

        return _render_trek_form(
            trek=trek,
            errors=errors,
        )

    return _render_trek_form(
        trek=trek
    )


@admin_bp.route(
    "/treks/<int:trek_id>/archive",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def archive_trek(trek_id):

    trek = db.get_or_404(
        Trek,
        trek_id,
        description="The requested trek does not exist.",
    )

    if trek.is_archived:
        flash(
            "That trek is already archived.",
            "info",
        )

        return redirect(
            url_for(
                "admin.manage_treks",
                scope="archived",
            )
        )

    active_bookings = _active_booking_count(
        trek.id
    )

    can_archive = (
        active_bookings == 0
        and trek.status != "Ongoing"
    )

    if request.method == "POST":
        if active_bookings > 0:
            flash(
                "This trek cannot be archived while it has "
                f"{active_bookings} active booking(s).",
                "danger",
            )

            return redirect(
                url_for("admin.manage_treks")
            )

        if trek.status == "Ongoing":
            flash(
                "An ongoing trek cannot be archived. "
                "Complete or close it first.",
                "danger",
            )

            return redirect(
                url_for("admin.manage_treks")
            )

        trek.is_archived = True

        if trek.status != "Completed":
            trek.status = "Closed"

        db.session.commit()

        flash(
            f'Trek "{trek.name}" was archived.',
            "success",
        )

        return redirect(
            url_for(
                "admin.manage_treks",
                scope="archived",
            )
        )

    return render_template(
        "admin/treks/confirm_archive.html",
        active_page="treks",
        trek=trek,
        active_booking_count=active_bookings,
        can_archive=can_archive,
    )


@admin_bp.route(
    "/treks/<int:trek_id>/restore",
    methods=["POST"],
)
@login_required
@role_required("admin")
def restore_trek(trek_id):

    trek = db.get_or_404(
        Trek,
        trek_id,
        description="The requested trek does not exist.",
    )

    if not trek.is_archived:
        flash(
            "That trek is already active.",
            "info",
        )

        return redirect(
            url_for("admin.manage_treks")
        )

    trek.is_archived = False

    db.session.commit()

    flash(
        f'Trek "{trek.name}" was restored. '
        "Review its status and slots before reopening it.",
        "success",
    )

    return redirect(
        url_for("admin.manage_treks")
    )


def _get_role_account_or_404(
    account_id: int,
    expected_role: str,
):

    account = db.get_or_404(
        User,
        account_id,
        description="The requested account does not exist.",
    )

    if account.role != expected_role:
        abort(
            404,
            description="The requested account does not exist.",
        )

    return account


def _account_search_expression(search_text: str):

    search_pattern = f"%{search_text}%"

    conditions = [
        User.full_name.ilike(search_pattern),
        User.email.ilike(search_pattern),
        User.phone.ilike(search_pattern),
    ]

    possible_id = search_text.removeprefix("#")

    if possible_id.isdigit():
        conditions.append(
            User.id == int(possible_id)
        )

    return or_(*conditions)


def _staff_assignments_for_status_change(
    staff_id: int,
):

    assignments = db.session.execute(
        db.select(Trek)
        .where(
            Trek.assigned_staff_id == staff_id,
            Trek.is_archived.is_(False),
            Trek.status != "Completed",
        )
        .order_by(
            Trek.start_date.asc(),
            Trek.id.asc(),
        )
    ).scalars().all()

    ongoing_assignments = [
        trek
        for trek in assignments
        if trek.status == "Ongoing"
    ]

    return assignments, ongoing_assignments


def _unassign_treks(
    assignments: list[Trek],
) -> int:

    for trek in assignments:
        trek.assigned_staff_id = None

    return len(assignments)


def _booking_counts_for_user(
    user_id: int,
):

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
            Booking.user_id == user_id
        )
        .group_by(
            Booking.status
        )
    ).all()

    for status, count in rows:
        counts[status] = count
        counts["Total"] += count

    return counts
def _all_booking_counts():

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
        .group_by(
            Booking.status
        )
    ).all()

    for status, count in rows:
        counts[status] = count
        counts["Total"] += count

    return counts


@admin_bp.route("/staff")
@login_required
@role_required("admin")
def manage_staff():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    status_filter = request.args.get(
        "status",
        "all",
    ).strip().lower()

    if status_filter not in STAFF_STATUS_FILTERS:
        status_filter = "all"

    statement = (
        db.select(User)
        .where(
            User.role == "staff"
        )
        .options(
            selectinload(User.assigned_treks)
        )
    )

    if search_text:
        statement = statement.where(
            _account_search_expression(search_text)
        )

    if status_filter == "pending":
        statement = statement.where(
            User.is_approved.is_(False),
            User.is_blacklisted.is_(False),
        )

    elif status_filter == "approved":
        statement = statement.where(
            User.is_approved.is_(True),
            User.is_blacklisted.is_(False),
        )

    elif status_filter == "blacklisted":
        statement = statement.where(
            User.is_blacklisted.is_(True)
        )

    statement = statement.order_by(
        User.created_at.desc(),
        User.id.desc(),
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

    total_staff = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "staff"
            )
        )
        or 0
    )

    pending_staff = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "staff",
                User.is_approved.is_(False),
                User.is_blacklisted.is_(False),
            )
        )
        or 0
    )

    approved_staff = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "staff",
                User.is_approved.is_(True),
                User.is_blacklisted.is_(False),
            )
        )
        or 0
    )

    blacklisted_staff = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "staff",
                User.is_blacklisted.is_(True),
            )
        )
        or 0
    )

    return render_template(
        "admin/accounts/staff_list.html",
        active_page="staff",
        staff_members=pagination.items,
        pagination=pagination,
        search_text=search_text,
        status_filter=status_filter,
        total_staff=total_staff,
        pending_staff=pending_staff,
        approved_staff=approved_staff,
        blacklisted_staff=blacklisted_staff,
    )


@admin_bp.route("/staff/<int:staff_id>")
@login_required
@role_required("admin")
def staff_detail(staff_id):

    staff = _get_role_account_or_404(
        staff_id,
        "staff",
    )

    assigned_treks = db.session.execute(
        db.select(Trek)
        .where(
            Trek.assigned_staff_id == staff.id
        )
        .order_by(
            Trek.is_archived.asc(),
            Trek.start_date.desc(),
            Trek.id.desc(),
        )
    ).scalars().all()

    active_assignments = [
        trek
        for trek in assigned_treks
        if (
            not trek.is_archived
            and trek.status != "Completed"
        )
    ]

    historical_assignments = [
        trek
        for trek in assigned_treks
        if (
            trek.is_archived
            or trek.status == "Completed"
        )
    ]

    return render_template(
        "admin/accounts/staff_detail.html",
        active_page="staff",
        staff=staff,
        active_assignments=active_assignments,
        historical_assignments=historical_assignments,
    )


@admin_bp.route(
    "/staff/<int:staff_id>/approve",
    methods=["POST"],
)
@login_required
@role_required("admin")
def approve_staff(staff_id):

    staff = _get_role_account_or_404(
        staff_id,
        "staff",
    )

    if staff.is_blacklisted:
        flash(
            "Reactivate this account before approving it.",
            "warning",
        )

    elif staff.is_approved:
        flash(
            "This staff account is already approved.",
            "info",
        )

    else:
        staff.is_approved = True
        db.session.commit()

        flash(
            f"{staff.full_name}'s staff registration was approved.",
            "success",
        )

    return redirect(
        url_for(
            "admin.staff_detail",
            staff_id=staff.id,
        )
    )


@admin_bp.route(
    "/staff/<int:staff_id>/reject",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def reject_staff(staff_id):

    staff = _get_role_account_or_404(
        staff_id,
        "staff",
    )

    if staff.is_approved:
        flash(
            "This account is already approved. Use Blacklist "
            "instead of Reject.",
            "warning",
        )

        return redirect(
            url_for(
                "admin.staff_detail",
                staff_id=staff.id,
            )
        )

    if staff.is_blacklisted:
        flash(
            "This staff registration is already rejected or blocked.",
            "info",
        )

        return redirect(
            url_for(
                "admin.staff_detail",
                staff_id=staff.id,
            )
        )

    assignments, ongoing_assignments = (
        _staff_assignments_for_status_change(
            staff.id
        )
    )

    blocked_reason = None

    if ongoing_assignments:
        blocked_reason = (
            "This registration cannot be rejected because the "
            "staff account is assigned to an ongoing trek."
        )

    if request.method == "POST":
        if blocked_reason:
            flash(
                blocked_reason,
                "danger",
            )

            return redirect(
                url_for(
                    "admin.staff_detail",
                    staff_id=staff.id,
                )
            )

        unassigned_count = _unassign_treks(
            assignments
        )

        staff.is_approved = False
        staff.is_blacklisted = True

        db.session.commit()

        flash(
            f"{staff.full_name}'s registration was rejected. "
            f"{unassigned_count} active trek assignment(s) "
            "were removed.",
            "success",
        )

        return redirect(
            url_for(
                "admin.manage_staff",
                status="blacklisted",
            )
        )

    return render_template(
        "admin/accounts/confirm_action.html",
        active_page="staff",
        page_title="Reject Staff Registration",
        action_label="Reject Registration",
        action_button_class="danger",
        account=staff,
        account_kind="Staff",
        description=(
            "The staff member will not be able to log in. "
            "The registration record will be preserved."
        ),
        warnings=[
            (
                "Non-archived, non-completed Trek assignments "
                "will become unassigned."
            ),
            (
                "Completed and archived Trek records will keep "
                "their historical staff relationship."
            ),
        ],
        affected_treks=assignments,
        blocked_reason=blocked_reason,
        cancel_url=url_for(
            "admin.staff_detail",
            staff_id=staff.id,
        ),
    )


@admin_bp.route(
    "/staff/<int:staff_id>/blacklist",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def blacklist_staff(staff_id):

    staff = _get_role_account_or_404(
        staff_id,
        "staff",
    )

    if staff.is_blacklisted:
        flash(
            "This staff account is already blacklisted.",
            "info",
        )

        return redirect(
            url_for(
                "admin.staff_detail",
                staff_id=staff.id,
            )
        )

    assignments, ongoing_assignments = (
        _staff_assignments_for_status_change(
            staff.id
        )
    )

    blocked_reason = None

    if ongoing_assignments:
        ongoing_names = ", ".join(
            trek.name
            for trek in ongoing_assignments
        )

        blocked_reason = (
            "This staff account cannot be blacklisted while "
            f"assigned to an ongoing trek: {ongoing_names}. "
            "Complete, close, or reassign the trek first."
        )

    if request.method == "POST":
        if blocked_reason:
            flash(
                blocked_reason,
                "danger",
            )

            return redirect(
                url_for(
                    "admin.staff_detail",
                    staff_id=staff.id,
                )
            )

        unassigned_count = _unassign_treks(
            assignments
        )

        staff.is_blacklisted = True

        db.session.commit()

        flash(
            f"{staff.full_name} was blacklisted. "
            f"{unassigned_count} active trek assignment(s) "
            "were removed.",
            "success",
        )

        return redirect(
            url_for(
                "admin.manage_staff",
                status="blacklisted",
            )
        )

    return render_template(
        "admin/accounts/confirm_action.html",
        active_page="staff",
        page_title="Blacklist Staff",
        action_label="Blacklist Staff",
        action_button_class="danger",
        account=staff,
        account_kind="Staff",
        description=(
            "This blocks the staff member from logging in "
            "and managing assigned treks."
        ),
        warnings=[
            (
                "All non-archived, non-completed Trek "
                "assignments listed below will become unassigned."
            ),
            (
                "Historical completed and archived Trek records "
                "will remain connected to this staff account."
            ),
            (
                "Reactivating the account later will not "
                "automatically restore old assignments."
            ),
        ],
        affected_treks=assignments,
        blocked_reason=blocked_reason,
        cancel_url=url_for(
            "admin.staff_detail",
            staff_id=staff.id,
        ),
    )


@admin_bp.route(
    "/staff/<int:staff_id>/reactivate",
    methods=["POST"],
)
@login_required
@role_required("admin")
def reactivate_staff(staff_id):

    staff = _get_role_account_or_404(
        staff_id,
        "staff",
    )

    if not staff.is_blacklisted:
        flash(
            "This staff account is already active.",
            "info",
        )

        return redirect(
            url_for(
                "admin.staff_detail",
                staff_id=staff.id,
            )
        )

    staff.is_blacklisted = False
    db.session.commit()

    if staff.is_approved:
        message = (
            f"{staff.full_name} was reactivated and may "
            "log in again."
        )
    else:
        message = (
            f"{staff.full_name}'s registration was reactivated "
            "and is now waiting for approval."
        )

    flash(
        message,
        "success",
    )

    return redirect(
        url_for(
            "admin.staff_detail",
            staff_id=staff.id,
        )
    )


@admin_bp.route("/users")
@login_required
@role_required("admin")
def manage_users():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    status_filter = request.args.get(
        "status",
        "all",
    ).strip().lower()

    if status_filter not in TREKKER_STATUS_FILTERS:
        status_filter = "all"

    statement = (
        db.select(User)
        .where(
            User.role == "trekker"
        )
        .options(
            selectinload(User.bookings)
        )
    )

    if search_text:
        statement = statement.where(
            _account_search_expression(search_text)
        )

    if status_filter == "active":
        statement = statement.where(
            User.is_blacklisted.is_(False)
        )

    elif status_filter == "blacklisted":
        statement = statement.where(
            User.is_blacklisted.is_(True)
        )

    statement = statement.order_by(
        User.created_at.desc(),
        User.id.desc(),
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

    total_users = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "trekker"
            )
        )
        or 0
    )

    active_users = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "trekker",
                User.is_blacklisted.is_(False),
            )
        )
        or 0
    )

    blacklisted_users = (
        db.session.scalar(
            db.select(
                func.count(User.id)
            ).where(
                User.role == "trekker",
                User.is_blacklisted.is_(True),
            )
        )
        or 0
    )

    return render_template(
        "admin/accounts/user_list.html",
        active_page="users",
        users=pagination.items,
        pagination=pagination,
        search_text=search_text,
        status_filter=status_filter,
        total_users=total_users,
        active_users=active_users,
        blacklisted_users=blacklisted_users,
    )


@admin_bp.route("/users/<int:user_id>")
@login_required
@role_required("admin")
def user_detail(user_id):

    user = _get_role_account_or_404(
        user_id,
        "trekker",
    )

    bookings = db.session.execute(
        db.select(Booking)
        .where(
            Booking.user_id == user.id
        )
        .options(
            joinedload(Booking.trek)
        )
        .order_by(
            Booking.booking_date.desc(),
            Booking.id.desc(),
        )
    ).scalars().all()

    booking_counts = _booking_counts_for_user(
        user.id
    )

    return render_template(
        "admin/accounts/user_detail.html",
        active_page="users",
        user=user,
        bookings=bookings,
        booking_counts=booking_counts,
    )


@admin_bp.route(
    "/users/<int:user_id>/blacklist",
    methods=["GET", "POST"],
)
@login_required
@role_required("admin")
def blacklist_user(user_id):

    user = _get_role_account_or_404(
        user_id,
        "trekker",
    )

    if user.is_blacklisted:
        flash(
            "This Trekker account is already blacklisted.",
            "info",
        )

        return redirect(
            url_for(
                "admin.user_detail",
                user_id=user.id,
            )
        )

    booking_counts = _booking_counts_for_user(
        user.id
    )

    if request.method == "POST":
        user.is_blacklisted = True
        db.session.commit()

        flash(
            f"{user.full_name} was blacklisted. Existing "
            "booking records were preserved.",
            "success",
        )

        return redirect(
            url_for(
                "admin.manage_users",
                status="blacklisted",
            )
        )

    return render_template(
        "admin/accounts/confirm_action.html",
        active_page="users",
        page_title="Blacklist Trekker",
        action_label="Blacklist Trekker",
        action_button_class="danger",
        account=user,
        account_kind="Trekker",
        description=(
            "The Trekker will no longer be able to log in "
            "or create new bookings."
        ),
        warnings=[
            (
                "Existing bookings and Trek history are "
                "preserved."
            ),
            (
                "This action does not automatically cancel "
                f"the user's {booking_counts['Booked']} "
                "active booking(s)."
            ),
        ],
        affected_treks=[],
        blocked_reason=None,
        cancel_url=url_for(
            "admin.user_detail",
            user_id=user.id,
        ),
    )


@admin_bp.route(
    "/users/<int:user_id>/reactivate",
    methods=["POST"],
)
@login_required
@role_required("admin")
def reactivate_user(user_id):

    user = _get_role_account_or_404(
        user_id,
        "trekker",
    )

    if not user.is_blacklisted:
        flash(
            "This Trekker account is already active.",
            "info",
        )

        return redirect(
            url_for(
                "admin.user_detail",
                user_id=user.id,
            )
        )

    user.is_blacklisted = False
    db.session.commit()

    flash(
        f"{user.full_name} was reactivated and may log in again.",
        "success",
    )

    return redirect(
        url_for(
            "admin.user_detail",
            user_id=user.id,
        )
    )


@admin_bp.route("/bookings")
@login_required
@role_required("admin")
def view_bookings():

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
        .select_from(Booking)
        .join(
            User,
            Booking.user_id == User.id,
        )
        .join(
            Trek,
            Booking.trek_id == Trek.id,
        )
        .options(
            joinedload(Booking.trekker),
            joinedload(Booking.trek),
        )
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
            numeric_id = int(
                possible_id
            )

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
        per_page=12,
        max_per_page=30,
        error_out=False,
    )

    return render_template(
        "admin/bookings/list.html",
        active_page="bookings",
        bookings=pagination.items,
        pagination=pagination,
        booking_counts=_all_booking_counts(),
        search_text=search_text,
        status_filter=status_filter,
        booking_statuses=BOOKING_STATUS_FILTERS,
    )

@admin_bp.route(
    "/bookings/<int:booking_id>"
)
@login_required
@role_required("admin")
def booking_detail(booking_id):

    booking = db.session.scalar(
        db.select(Booking)
        .where(
            Booking.id == booking_id
        )
        .options(
            joinedload(Booking.trekker),
            joinedload(Booking.trek),
        )
    )

    if booking is None:
        abort(
            404,
            description="The requested Booking does not exist.",
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

    return render_template(
        "admin/bookings/detail.html",
        active_page="bookings",
        booking=booking,
        events=events,
    )

@admin_bp.route("/search")
@login_required
@role_required("admin")
def search():

    search_text = request.args.get(
        "q",
        "",
    ).strip()[:100]

    trek_results = []
    staff_results = []
    user_results = []

    if search_text:
        search_pattern = f"%{search_text}%"

        trek_conditions = [
            Trek.name.ilike(search_pattern),
            Trek.location.ilike(search_pattern),
        ]

        possible_id = search_text.removeprefix("#")

        if possible_id.isdigit():
            trek_conditions.append(
                Trek.id == int(possible_id)
            )

        trek_results = db.session.execute(
            db.select(Trek)
            .where(
                or_(*trek_conditions)
            )
            .options(
                joinedload(Trek.assigned_staff)
            )
            .order_by(
                Trek.is_archived.asc(),
                Trek.start_date.desc(),
                Trek.id.desc(),
            )
            .limit(10)
        ).scalars().all()

        staff_results = db.session.execute(
            db.select(User)
            .where(
                User.role == "staff",
                _account_search_expression(search_text),
            )
            .order_by(
                User.full_name.asc(),
                User.id.asc(),
            )
            .limit(10)
        ).scalars().all()

        user_results = db.session.execute(
            db.select(User)
            .where(
                User.role == "trekker",
                _account_search_expression(search_text),
            )
            .order_by(
                User.full_name.asc(),
                User.id.asc(),
            )
            .limit(10)
        ).scalars().all()

    return render_template(
        "admin/search.html",
        active_page="search",
        search_text=search_text,
        trek_results=trek_results,
        staff_results=staff_results,
        user_results=user_results,
    )
