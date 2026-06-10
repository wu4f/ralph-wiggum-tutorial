"""Views (routes) package.

Blueprint registration for all application routes.
Each view module defines a Blueprint with its routes.
"""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application.

    Args:
        app: Flask application instance
    """
    from .chat import chat_bp
    from .pages import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(chat_bp)
