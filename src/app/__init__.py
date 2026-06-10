"""Flask application factory and initialization."""
import os

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .config import config
from .logging_config import configure_logging
from .services.chat_service import ChatService
from .services.content_cache import ContentCache
from .services.google_docs import GoogleDocsService


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Uses the application factory pattern for flexibility in testing
    and deployment scenarios.

    Args:
        config_name: Configuration to use ('development', 'testing',
                    'production'). Defaults to FLASK_ENV or 'development'.

    Returns:
        Configured Flask application instance.
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Configure logging before other initialization
    configure_logging(app)

    # Content + chat services (stateless; backed by Google Docs + Gemini).
    docs_service = GoogleDocsService(
        service_account_source=app.config['GOOGLE_SERVICE_ACCOUNT_JSON'],
        doc_id=app.config['GOOGLE_DOC_ID'],
    )
    cache = ContentCache(
        docs_service=docs_service,
        gemini_api_key=app.config['GEMINI_API_KEY'],
        ttl_seconds=app.config['DOCS_CACHE_TTL_SECONDS'],
        site_base_url=app.config['SITE_BASE_URL'],
    )
    app.extensions['content_cache'] = cache
    app.extensions['chat_service'] = ChatService(cache=cache)

    # Per-IP rate limiting for the paid Gemini-backed chat API.
    limiter = Limiter(key_func=get_remote_address, app=app)
    app.extensions['limiter'] = limiter

    # Inject the site navigation tabs into every template render. Must never
    # raise — error pages also extend base.html — and skips work for the JSON
    # API where the nav is not rendered.
    @app.context_processor
    def inject_tabs():  # type: ignore[no-untyped-def]
        if request.path.startswith('/api/'):
            return {'tabs': [], 'hide_widget': True}
        try:
            c = app.extensions.get('content_cache')
            tabs = c.get_tabs(request.host_url) if c is not None else []
        except Exception:
            app.logger.warning('Could not load tabs for nav', exc_info=True)
            tabs = []
        return {'tabs': tabs, 'hide_widget': False}

    # Register error handlers
    from .errors import register_error_handlers
    register_error_handlers(app)

    # Register blueprints
    from .views import register_blueprints
    register_blueprints(app)

    # Apply the configured per-IP limit to the chat API endpoint.
    limiter.limit(app.config['CHAT_RATE_LIMIT'])(
        app.view_functions['chat.ask'])

    return app
