from flask import Blueprint, render_template
from flask_login import login_required

from decorators import role_required


trekker_bp = Blueprint(
    "trekker",
    __name__,
    url_prefix="/trekker",
)


@trekker_bp.route("/dashboard")
@login_required
@role_required("trekker")
def dashboard():
    return render_template("trekker/dashboard.html")