"""Pytest configuration and fixtures.

Provides test fixtures for the Flask application. The app is stateless
(no database); external services (Google Docs, Gemini) are mocked per test.
"""
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner

from app import create_app


@pytest.fixture
def app() -> Iterator[Flask]:
    """Create application configured for testing."""
    flask_app = create_app('testing')
    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client for making HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app: Flask) -> FlaskCliRunner:
    """Create CLI runner for testing Flask commands."""
    return app.test_cli_runner()
