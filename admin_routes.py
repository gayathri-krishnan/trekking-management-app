from datetime import date

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from decorators import role_required
from extensions import db
from models import Booking, Trek, User


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
            "Search staff and trekkers by name, email, or ID. "
            "Trek searching is already available on the "
            "Manage Treks page."
        ),
        active_page="search",
        planned_milestone="Milestone 7",
    )