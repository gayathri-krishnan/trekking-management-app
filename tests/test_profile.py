from extensions import db
from models import User


def test_trekker_can_update_profile_without_changing_role(
    app,
    client,
    auth,
):
    auth.login(
        "trekker1@test.local"
    )

    user_id = app.config[
        "TEST_IDS"
    ]["trekker_one"]

    response = client.post(
        "/trekker/profile",
        data={
            "full_name": (
                "Updated Trekker Name"
            ),
            "email": (
                "updated.trekker@test.local"
            ),
            "phone": (
                "+91 98765 43210"
            ),

            # A malicious extra field must be ignored.
            "role": "admin",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Your profile was updated successfully."
        in response.data
    )

    with app.app_context():
        user = db.session.get(
            User,
            user_id,
        )

        assert (
            user.full_name
            == "Updated Trekker Name"
        )

        assert (
            user.email
            == "updated.trekker@test.local"
        )

        assert (
            user.phone
            == "+91 98765 43210"
        )

        assert user.role == "trekker"
        assert user.is_approved is True
        assert user.is_blacklisted is False


def test_duplicate_profile_email_is_rejected(
    app,
    client,
    auth,
):
    auth.login(
        "trekker1@test.local"
    )

    user_id = app.config[
        "TEST_IDS"
    ]["trekker_one"]

    response = client.post(
        "/trekker/profile",
        data={
            "full_name": "Test Trekker One",
            "email": "staff1@test.local",
            "phone": "9876543210",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    assert (
        b"Another account already uses that "
        b"email address."
        in response.data
    )

    with app.app_context():
        user = db.session.get(
            User,
            user_id,
        )

        assert (
            user.email
            == "trekker1@test.local"
        )


def test_approved_staff_can_update_profile(
    app,
    client,
    auth,
):
    auth.login(
        "staff1@test.local"
    )

    staff_id = app.config[
        "TEST_IDS"
    ]["staff_one"]

    response = client.post(
        "/staff/profile",
        data={
            "full_name": "Updated Staff Guide",
            "email": "updated.staff@test.local",
            "phone": "(080) 1234-5678",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    assert (
        b"Your profile was updated successfully."
        in response.data
    )

    with app.app_context():
        staff = db.session.get(
            User,
            staff_id,
        )

        assert (
            staff.full_name
            == "Updated Staff Guide"
        )

        assert (
            staff.email
            == "updated.staff@test.local"
        )

        assert staff.role == "staff"
        assert staff.is_approved is True
        assert staff.is_blacklisted is False