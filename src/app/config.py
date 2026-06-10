"""Application configuration classes.

Configuration is loaded from environment variables with sensible defaults.
Each environment (development, testing, production) has its own class.
"""
import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Config:
    """Base configuration with shared settings."""

    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-me')

    # Google Docs source document and service-account credential.
    GOOGLE_DOC_ID = os.environ.get('GOOGLE_DOC_ID', '')
    # Path to a service-account JSON key file, OR the raw JSON itself.
    GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')

    # Gemini API key for the chat service.
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # How long parsed Google Doc content is cached before re-fetching.
    DOCS_CACHE_TTL_SECONDS = int(os.environ.get('DOCS_CACHE_TTL_SECONDS', '900'))

    # Absolute base URL for building page links in chat sources. Falls back to
    # the request host when empty.
    SITE_BASE_URL = os.environ.get('SITE_BASE_URL', '')

    # Per-IP rate limit applied to the chat API.
    CHAT_RATE_LIMIT = os.environ.get('CHAT_RATE_LIMIT', '20 per minute')

    # Vite dev server URL for template asset loading
    VITE_DEV_SERVER = os.environ.get('VITE_DEV_SERVER', 'http://localhost:5173')


class DevelopmentConfig(Config):
    """Development configuration with debug enabled."""

    DEBUG = True
    # In development, load assets from Vite dev server
    VITE_DEV_MODE = True


class TestingConfig(Config):
    """Testing configuration; all external services are mocked."""

    TESTING = True
    DEBUG = True
    VITE_DEV_MODE = False
    GOOGLE_DOC_ID = 'test-doc-id'
    GOOGLE_SERVICE_ACCOUNT_JSON = ''   # tests mock the service entirely
    GEMINI_API_KEY = 'test-gemini-key'
    DOCS_CACHE_TTL_SECONDS = 9999
    SITE_BASE_URL = 'http://localhost'
    CHAT_RATE_LIMIT = '1000 per minute'   # effectively disabled in tests
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration with strict security settings."""

    DEBUG = False
    # In production, load assets from built manifest
    VITE_DEV_MODE = False

    # Ensure critical settings are configured
    @classmethod
    def init_app(cls, app):  # type: ignore[no-untyped-def]
        """Production-specific initialization."""
        if not os.environ.get('FLASK_SECRET_KEY'):
            raise ValueError("FLASK_SECRET_KEY must be set in production")


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
