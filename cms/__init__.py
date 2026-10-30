"""Change Management Software (CMS) - Flask application factory."""

from pathlib import Path

from flask import Flask, render_template

from cms.config import Config
from cms.extensions import db


def create_app(config_object=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    # Default to a SQLite file inside the instance/ folder (ignored by Git).
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        db_path = Path(app.instance_path) / "cms.db"
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path.as_posix()}"

    db.init_app(app)

    from cms import models  # noqa: F401  (registers the tables)
    from cms.routes.main import bp as main_bp

    app.register_blueprint(main_bp)

    from cms.cli import register_cli

    register_cli(app)

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    with app.app_context():
        db.create_all()

    return app
