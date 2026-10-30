"""Sign-in and sign-out pages (CMS-2)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from cms.services.auth_service import authenticate, is_safe_redirect

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        user = authenticate(email, password)
        if user is None:
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email.strip()), 401

        login_user(user)
        flash(f"Signed in as {user.name} ({user.role}).", "success")
        next_page = request.args.get("next")
        return redirect(next_page if is_safe_redirect(next_page) else url_for("main.index"))

    return render_template("auth/login.html", email="")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("auth.login"))
