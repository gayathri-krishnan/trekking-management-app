from flask import render_template

from extensions import db


def _error_message(
    error,
    fallback: str,
) -> str:
    """
    Use a supplied error description when available.
    """

    description = getattr(
        error,
        "description",
        "",
    )

    if (
        isinstance(description, str)
        and description.strip()
    ):
        return description

    return fallback


def register_error_handlers(app):
    """
    Register application-level error pages.
    """

    @app.errorhandler(400)
    def bad_request(error):
        return (
            render_template(
                "errors/error.html",
                status_code=400,
                title="Bad Request",
                message=_error_message(
                    error,
                    (
                        "The application could not understand "
                        "the submitted request."
                    ),
                ),
            ),
            400,
        )

    @app.errorhandler(403)
    def forbidden(error):
        return (
            render_template(
                "errors/error.html",
                status_code=403,
                title="Access Denied",
                message=_error_message(
                    error,
                    (
                        "Your account does not have permission "
                        "to access this page."
                    ),
                ),
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template(
                "errors/error.html",
                status_code=404,
                title="Page Not Found",
                message=_error_message(
                    error,
                    (
                        "The requested page or record could "
                        "not be found."
                    ),
                ),
            ),
            404,
        )

    @app.errorhandler(405)
    def method_not_allowed(error):
        return (
            render_template(
                "errors/error.html",
                status_code=405,
                title="Method Not Allowed",
                message=(
                    "That request method is not permitted "
                    "for this page."
                ),
            ),
            405,
        )

    @app.errorhandler(500)
    def internal_server_error(error):
        """
        Roll back a failed database transaction before
        rendering the error page.
        """

        try:
            db.session.rollback()
        except Exception:
            pass

        return (
            render_template(
                "errors/error.html",
                status_code=500,
                title="Internal Server Error",
                message=(
                    "The application encountered an unexpected "
                    "problem. Please return to the dashboard "
                    "and try again."
                ),
            ),
            500,
        )