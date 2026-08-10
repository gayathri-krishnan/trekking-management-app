from datetime import date

import pytest

from app import create_app
from extensions import db
from models import Trek, User


TEST_PASSWORD = "Test@1234"


def _create_user(
    *,
    full_name: str,
    email: str,
    role: str,
    is_approved: bool,
):
    """
    Create a test account with a hashed test password.
    """

    user = User(
        full_name=full_name,
        email=email,
        phone="9876543210",
        role=role,
        is_approved=is_approved,
        is_blacklisted=False,
    )

    user.set_password(
        TEST_PASSWORD
    )

    return user


@pytest.fixture()
def app(tmp_path):
    """
    Create a new Flask application and a temporary SQLite
    database for each test.

    The real instance/trekking.db file is never used.
    """

    database_path = (
        tmp_path
        / "trekking-test.db"
    )

    test_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "automated-test-secret-key",
            "SQLALCHEMY_DATABASE_URI": (
                f"sqlite:///{database_path.as_posix()}"
            ),
            "SEED_DEFAULT_ADMIN": False,

            # This is harmless when Flask-WTF is not installed.
            # It also keeps tests working if CSRF is added later.
            "WTF_CSRF_ENABLED": False,
        }
    )

    with test_app.app_context():
        # Ensure each test begins with a completely clean
        # temporary database.
        db.drop_all()
        db.create_all()

        admin = _create_user(
            full_name="Test Administrator",
            email="admin@test.local",
            role="admin",
            is_approved=True,
        )

        staff_one = _create_user(
            full_name="Approved Staff One",
            email="staff1@test.local",
            role="staff",
            is_approved=True,
        )

        staff_two = _create_user(
            full_name="Approved Staff Two",
            email="staff2@test.local",
            role="staff",
            is_approved=True,
        )

        pending_staff = _create_user(
            full_name="Pending Staff",
            email="pending@test.local",
            role="staff",
            is_approved=False,
        )

        trekker_one = _create_user(
            full_name="Test Trekker One",
            email="trekker1@test.local",
            role="trekker",
            is_approved=True,
        )

        trekker_two = _create_user(
            full_name="Test Trekker Two",
            email="trekker2@test.local",
            role="trekker",
            is_approved=True,
        )

        db.session.add_all(
            [
                admin,
                staff_one,
                staff_two,
                pending_staff,
                trekker_one,
                trekker_two,
            ]
        )

        # IDs are assigned before we create Trek foreign keys.
        db.session.flush()

        open_trek = Trek(
            name="Automated Open Trek",
            location="Karnataka",
            difficulty="Easy",
            duration_days=1,
            total_slots=2,
            available_slots=2,
            assigned_staff_id=staff_one.id,
            status="Open",
            start_date=date(
                2030,
                1,
                10,
            ),
            end_date=date(
                2030,
                1,
                10,
            ),
            description=(
                "An Open Trek used by automated tests."
            ),
            is_archived=False,
        )

        one_slot_trek = Trek(
            name="Last Slot Trek",
            location="Kerala",
            difficulty="Moderate",
            duration_days=2,
            total_slots=1,
            available_slots=1,
            assigned_staff_id=staff_one.id,
            status="Open",
            start_date=date(
                2030,
                2,
                10,
            ),
            end_date=date(
                2030,
                2,
                11,
            ),
            description=(
                "A one-slot Trek used to test "
                "overbooking protection."
            ),
            is_archived=False,
        )

        other_staff_trek = Trek(
            name="Other Staff Trek",
            location="Himachal Pradesh",
            difficulty="Hard",
            duration_days=3,
            total_slots=8,
            available_slots=8,
            assigned_staff_id=staff_two.id,
            status="Open",
            start_date=date(
                2030,
                3,
                10,
            ),
            end_date=date(
                2030,
                3,
                12,
            ),
            description=(
                "A Trek assigned to a different Staff account."
            ),
            is_archived=False,
        )

        db.session.add_all(
            [
                open_trek,
                one_slot_trek,
                other_staff_trek,
            ]
        )

        db.session.commit()

        # Store IDs for tests without relying on a particular
        # SQLite-generated number.
        test_app.config["TEST_IDS"] = {
            "admin": admin.id,
            "staff_one": staff_one.id,
            "staff_two": staff_two.id,
            "pending_staff": pending_staff.id,
            "trekker_one": trekker_one.id,
            "trekker_two": trekker_two.id,
            "open_trek": open_trek.id,
            "one_slot_trek": one_slot_trek.id,
            "other_staff_trek": other_staff_trek.id,
        }

    yield test_app

    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """
    Return Flask's simulated browser client.
    """

    return app.test_client()


class AuthActions:
    """
    Reusable login and logout actions for tests.
    """

    def __init__(self, client):
        self.client = client

    def login(
        self,
        email: str,
        password: str = TEST_PASSWORD,
        follow_redirects: bool = True,
    ):
        return self.client.post(
            "/login",
            data={
                "email": email,
                "password": password,
            },
            follow_redirects=follow_redirects,
        )

    def logout(
        self,
        follow_redirects: bool = True,
    ):
        return self.client.post(
            "/logout",
            follow_redirects=follow_redirects,
        )


@pytest.fixture()
def auth(client):
    return AuthActions(
        client
    )