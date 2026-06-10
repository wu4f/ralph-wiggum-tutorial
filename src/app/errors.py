"""Error handlers for the application.

Provides consistent error responses across the application.
Returns JSON for API requests (Accept: application/json) and HTML for browsers.
"""
from flask import Flask, request, render_template, jsonify
from werkzeug.exceptions import HTTPException
import logging

logger = logging.getLogger(__name__)


def wants_json_response() -> bool:
    """Check if the client prefers JSON response over HTML."""
    return (
        request.accept_mimetypes.best_match(['application/json', 'text/html'])
        == 'application/json'
    )


def register_error_handlers(app: Flask) -> None:
    """Register error handlers on the Flask application.

    Args:
        app: Flask application instance
    """

    @app.errorhandler(400)
    def bad_request_error(error: HTTPException):  # type: ignore[no-untyped-def]
        """Handle 400 Bad Request errors."""
        logger.warning(f"Bad request: {error.description}")
        if wants_json_response():
            return jsonify(error="Bad Request", message=str(error.description)), 400
        return render_template('errors/400.html', error=error), 400

    @app.errorhandler(404)
    def not_found_error(error: HTTPException):  # type: ignore[no-untyped-def]
        """Handle 404 Not Found errors."""
        logger.warning(f"Not found: {request.path}")
        if wants_json_response():
            return jsonify(error="Not Found", message=str(error.description)), 404
        return render_template('errors/404.html', error=error), 404

    @app.errorhandler(500)
    def internal_error(error: HTTPException):  # type: ignore[no-untyped-def]
        """Handle 500 Internal Server errors."""
        logger.error(f"Internal error: {error}", exc_info=True)
        if wants_json_response():
            return jsonify(error="Internal Server Error", message="An unexpected error occurred"), 500
        return render_template('errors/500.html', error=error), 500

    @app.errorhandler(Exception)
    def handle_exception(error: Exception):  # type: ignore[no-untyped-def]
        """Handle uncaught exceptions."""
        logger.error(f"Unhandled exception: {error}", exc_info=True)
        if wants_json_response():
            return jsonify(error="Internal Server Error", message="An unexpected error occurred"), 500
        return render_template('errors/500.html', error=error), 500
