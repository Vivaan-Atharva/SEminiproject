"""Command-line helpers, run with `flask --app cms <command>`."""

import click

from cms.extensions import db
from cms.seed import DEMO_PASSWORD, seed_demo_data


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create any missing database tables."""
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="This deletes ALL local data. Continue?")
    def reset_db():
        """Drop and recreate every table (local development only)."""
        db.drop_all()
        db.create_all()
        click.echo("Database reset.")

    @app.cli.command("seed")
    def seed():
        """Add demo users and change requests."""
        result = seed_demo_data()
        click.echo(
            f"Added {result['users_added']} users and "
            f"{result['change_requests_added']} change requests. "
            f"Demo password: {DEMO_PASSWORD}"
        )
