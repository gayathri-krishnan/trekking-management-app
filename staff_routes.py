from flask import Blueprint, render_template
from flask_login import login_required

from decorators import approved_staff_required


staff_bp = Blueprint(
    "staff",
    __name__,
    url_prefix="/staff",
)


@staff_bp.route("/dashboard")
@login_required
@approved_staff_required
def dashboard():
    return render_template("staff/dashboard.html")