import pytest

from cms import create_app
from cms.config import TestConfig
from cms.extensions import db


@pytest.fixture
def app():
    """A fresh app with an empty in-memory database for every test."""
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded(app):
    """The app with demo users and change requests loaded."""
    from cms.seed import seed_demo_data

    seed_demo_data()
    return app
