from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):

    __tablename__ = "users"

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('admin', 'staff', 'trekker')",
            name="ck_users_role",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(255, collation="NOCASE"),
        nullable=False,
        unique=True,
    )

    password_hash = db.Column(
        db.String(512),
        nullable=False,
    )

    phone = db.Column(
        db.String(20),
        nullable=True,
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    is_approved = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    is_blacklisted = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    assigned_treks = db.relationship(
        "Trek",
        back_populates="assigned_staff",
        foreign_keys="Trek.assigned_staff_id",
    )

    bookings = db.relationship(
        "Booking",
        back_populates="trekker",
    )

    def set_password(self, password: str) -> None:
        """Convert a plain password into a secure password hash."""

        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check a plain password against the stored password hash."""

        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        """
        Flask-Login uses this property to determine whether
        the account is active.
        """

        return not self.is_blacklisted

    def __repr__(self) -> str:
        return f"<User {self.id}: {self.email} ({self.role})>"


class Trek(db.Model):
    """Represents one scheduled trekking event."""

    __tablename__ = "treks"

    __table_args__ = (
        db.CheckConstraint(
            "difficulty IN ('Easy', 'Moderate', 'Hard')",
            name="ck_treks_difficulty",
        ),
        db.CheckConstraint(
            (
                "status IN "
                "('Pending', 'Approved', 'Open', 'Closed', "
                "'Ongoing', 'Completed')"
            ),
            name="ck_treks_status",
        ),
        db.CheckConstraint(
            "duration_days > 0",
            name="ck_treks_positive_duration",
        ),
        db.CheckConstraint(
            "total_slots > 0",
            name="ck_treks_positive_total_slots",
        ),
        db.CheckConstraint(
            "available_slots >= 0",
            name="ck_treks_non_negative_available_slots",
        ),
        db.CheckConstraint(
            "available_slots <= total_slots",
            name="ck_treks_available_not_above_total",
        ),
        db.CheckConstraint(
            "end_date >= start_date",
            name="ck_treks_valid_date_range",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    location = db.Column(
        db.String(150),
        nullable=False,
        index=True,
    )

    difficulty = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    duration_days = db.Column(
        db.Integer,
        nullable=False,
    )

    total_slots = db.Column(
        db.Integer,
        nullable=False,
    )

    available_slots = db.Column(
        db.Integer,
        nullable=False,
    )

    assigned_staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
        index=True,
    )

    start_date = db.Column(
        db.Date,
        nullable=False,
    )

    end_date = db.Column(
        db.Date,
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=False,
        default="",
    )

    is_archived = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    assigned_staff = db.relationship(
        "User",
        back_populates="assigned_treks",
        foreign_keys=[assigned_staff_id],
    )

    bookings = db.relationship(
        "Booking",
        back_populates="trek",
    )

    def __repr__(self) -> str:
        return f"<Trek {self.id}: {self.name}>"


class Booking(db.Model):
    """Represents a trekker's booking for a trek."""

    __tablename__ = "bookings"

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('Booked', 'Cancelled', 'Completed')",
            name="ck_bookings_status",
        ),
        db.UniqueConstraint(
            "user_id",
            "trek_id",
            name="uq_bookings_user_trek",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    trek_id = db.Column(
        db.Integer,
        db.ForeignKey("treks.id"),
        nullable=False,
        index=True,
    )

    booking_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Booked",
        index=True,
    )

    cancelled_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    trekker = db.relationship(
        "User",
        back_populates="bookings",
    )

    trek = db.relationship(
        "Trek",
        back_populates="bookings",
    )

    events = db.relationship(
        "BookingEvent",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingEvent.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<Booking {self.id}: "
            f"user={self.user_id}, trek={self.trek_id}>"
        )

class BookingEvent(db.Model):

    __tablename__ = "booking_events"

    __table_args__ = (
        db.CheckConstraint(
            (
                "event_type IN "
                "('Booked', 'Rebooked', 'Cancelled', 'Completed')"
            ),
            name="ck_booking_events_type",
        ),
        db.CheckConstraint(
            (
                "previous_status IS NULL OR "
                "previous_status IN "
                "('Booked', 'Cancelled', 'Completed')"
            ),
            name="ck_booking_events_previous_status",
        ),
        db.CheckConstraint(
            (
                "new_status IN "
                "('Booked', 'Cancelled', 'Completed')"
            ),
            name="ck_booking_events_new_status",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id"),
        nullable=False,
        index=True,
    )

    event_type = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    previous_status = db.Column(
        db.String(20),
        nullable=True,
    )

    new_status = db.Column(
        db.String(20),
        nullable=False,
    )

    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    note = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
    )

    booking = db.relationship(
        "Booking",
        back_populates="events",
    )

    changed_by = db.relationship(
        "User",
        foreign_keys=[changed_by_user_id],
    )

    def __repr__(self) -> str:
        return (
            f"<BookingEvent {self.id}: "
            f"booking={self.booking_id}, "
            f"event={self.event_type}>"
        )