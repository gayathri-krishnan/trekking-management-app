from sqlalchemy import func

from extensions import db
from models import (
    Booking,
    BookingEvent,
    Trek,
)


def test_booking_reduces_slots_and_duplicate_is_prevented(
    app,
    client,
    auth,
):
    """
    Booking once should consume one slot.

    Submitting the same Booking again should not insert another
    row or consume another slot.
    """

    auth.login(
        "trekker1@test.local"
    )

    ids = app.config[
        "TEST_IDS"
    ]

    trek_id = ids[
        "open_trek"
    ]

    user_id = ids[
        "trekker_one"
    ]

    first_response = client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    assert first_response.status_code == 200
    assert b"Booking Details" in first_response.data

    with app.app_context():
        booking = db.session.scalar(
            db.select(Booking).where(
                Booking.user_id == user_id,
                Booking.trek_id == trek_id,
            )
        )

        assert booking is not None
        assert booking.status == "Booked"

        trek = db.session.get(
            Trek,
            trek_id,
        )

        assert trek.available_slots == 1

        event_types = db.session.execute(
            db.select(
                BookingEvent.event_type
            )
            .where(
                BookingEvent.booking_id
                == booking.id
            )
            .order_by(
                BookingEvent.id
            )
        ).scalars().all()

        assert event_types == [
            "Booked",
        ]

    second_response = client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    assert second_response.status_code == 200

    with app.app_context():
        booking_count = db.session.scalar(
            db.select(
                func.count(Booking.id)
            ).where(
                Booking.user_id == user_id,
                Booking.trek_id == trek_id,
            )
        )

        trek = db.session.get(
            Trek,
            trek_id,
        )

        assert booking_count == 1
        assert trek.available_slots == 1


def test_only_one_user_can_take_the_last_slot(
    app,
):
    """
    Two users submit a Booking for a Trek with one slot.

    Exactly one Booking should succeed.
    """

    first_client = app.test_client()
    second_client = app.test_client()

    first_client.post(
        "/login",
        data={
            "email": "trekker1@test.local",
            "password": "Test@1234",
        },
        follow_redirects=True,
    )

    second_client.post(
        "/login",
        data={
            "email": "trekker2@test.local",
            "password": "Test@1234",
        },
        follow_redirects=True,
    )

    trek_id = app.config[
        "TEST_IDS"
    ]["one_slot_trek"]

    first_client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    second_client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    with app.app_context():
        active_booking_count = (
            db.session.scalar(
                db.select(
                    func.count(Booking.id)
                ).where(
                    Booking.trek_id == trek_id,
                    Booking.status == "Booked",
                )
            )
        )

        trek = db.session.get(
            Trek,
            trek_id,
        )

        assert active_booking_count == 1
        assert trek.available_slots == 0


def test_cancellation_restores_one_slot(
    app,
    client,
    auth,
):
    auth.login(
        "trekker1@test.local"
    )

    ids = app.config[
        "TEST_IDS"
    ]

    trek_id = ids[
        "open_trek"
    ]

    user_id = ids[
        "trekker_one"
    ]

    client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    with app.app_context():
        booking = db.session.scalar(
            db.select(Booking).where(
                Booking.user_id == user_id,
                Booking.trek_id == trek_id,
            )
        )

        booking_id = booking.id

    response = client.post(
        (
            f"/trekker/bookings/"
            f"{booking_id}/cancel"
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        booking = db.session.get(
            Booking,
            booking_id,
        )

        trek = db.session.get(
            Trek,
            trek_id,
        )

        event_types = db.session.execute(
            db.select(
                BookingEvent.event_type
            )
            .where(
                BookingEvent.booking_id
                == booking_id
            )
            .order_by(
                BookingEvent.id
            )
        ).scalars().all()

        assert booking.status == "Cancelled"
        assert booking.cancelled_at is not None
        assert trek.available_slots == 2
        assert event_types == [
            "Booked",
            "Cancelled",
        ]


def test_staff_completion_completes_active_booking(
    app,
    client,
    auth,
):
    """
    Starting and completing an assigned Trek should mark its
    active Booking as Completed and add a completion event.
    """

    ids = app.config[
        "TEST_IDS"
    ]

    trek_id = ids[
        "open_trek"
    ]

    user_id = ids[
        "trekker_one"
    ]

    auth.login(
        "trekker1@test.local"
    )

    client.post(
        f"/trekker/treks/{trek_id}/book",
        follow_redirects=True,
    )

    auth.logout()

    auth.login(
        "staff1@test.local"
    )

    start_response = client.post(
        f"/staff/treks/{trek_id}/start",
        follow_redirects=True,
    )

    assert start_response.status_code == 200

    completion_response = client.post(
        f"/staff/treks/{trek_id}/complete",
        follow_redirects=True,
    )

    assert completion_response.status_code == 200

    with app.app_context():
        trek = db.session.get(
            Trek,
            trek_id,
        )

        booking = db.session.scalar(
            db.select(Booking).where(
                Booking.user_id == user_id,
                Booking.trek_id == trek_id,
            )
        )

        completed_event = db.session.scalar(
            db.select(BookingEvent).where(
                BookingEvent.booking_id
                == booking.id,
                BookingEvent.event_type
                == "Completed",
            )
        )

        assert trek.status == "Completed"
        assert trek.available_slots == 0

        assert booking.status == "Completed"
        assert booking.completed_at is not None

        assert completed_event is not None
        assert (
            completed_event.changed_by_user_id
            == ids["staff_one"]
        )