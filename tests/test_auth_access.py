def test_home_and_custom_404_page(
    client,
):
    """
    The home page should load and an unknown route should
    return the custom 404 response.
    """

    home_response = client.get(
        "/"
    )

    assert home_response.status_code == 200

    missing_response = client.get(
        "/route-that-does-not-exist"
    )

    assert missing_response.status_code == 404
    assert b"Page Not Found" in missing_response.data


def test_admin_login_reaches_admin_dashboard(
    client,
    auth,
):
    response = auth.login(
        "admin@test.local"
    )

    assert response.status_code == 200
    assert b"Admin Dashboard" in response.data


def test_pending_staff_sees_approval_page(
    client,
    auth,
):
    response = auth.login(
        "pending@test.local"
    )

    assert response.status_code == 200
    assert b"Staff Approval Pending" in response.data


def test_trekker_cannot_access_admin_dashboard(
    client,
    auth,
):
    auth.login(
        "trekker1@test.local"
    )

    response = client.get(
        "/admin/dashboard"
    )

    assert response.status_code == 403
    assert b"Access Denied" in response.data


def test_staff_cannot_open_another_staff_trek(
    app,
    client,
    auth,
):
    auth.login(
        "staff1@test.local"
    )

    other_trek_id = app.config[
        "TEST_IDS"
    ]["other_staff_trek"]

    response = client.get(
        f"/staff/treks/{other_trek_id}"
    )

    assert response.status_code == 404