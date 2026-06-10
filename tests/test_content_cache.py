"""Unit tests for ContentCache: TTL caching, Gemini cache lifecycle, fallback."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.content_cache import MIN_CACHE_TOKENS, ContentCache
from app.services.google_docs import DocTab


def _tabs() -> list[DocTab]:
    return [
        DocTab(tab_id='t1', title='Home', slug='home', content='Welcome'),
        DocTab(tab_id='t2', title='About', slug='about', content='About us'),
    ]


def _make_cache(
    token_count: int = 10,
    ttl: int = 900,
    site_base_url: str = '',
) -> tuple[ContentCache, MagicMock, MagicMock]:
    """Build a ContentCache with a mocked Gemini client and docs service."""
    docs_service = MagicMock()
    docs_service.fetch_tabs.return_value = _tabs()

    client = MagicMock()
    client.models.count_tokens.return_value.total_tokens = token_count
    created = MagicMock()
    created.name = 'caches/created-1'
    client.caches.create.return_value = created

    with patch('app.services.content_cache.genai.Client', return_value=client):
        cache = ContentCache(
            docs_service=docs_service,
            gemini_api_key='key',
            ttl_seconds=ttl,
            site_base_url=site_base_url,
        )
    return cache, docs_service, client


def test_get_tabs_caches_within_ttl() -> None:
    cache, docs_service, _ = _make_cache()
    cache.get_tabs('http://localhost/')
    cache.get_tabs('http://localhost/')
    docs_service.fetch_tabs.assert_called_once()


def test_cache_rebuilt_after_ttl_expiry() -> None:
    cache, docs_service, _ = _make_cache(ttl=100)
    cache.get_tabs('http://localhost/')

    future = datetime.now(timezone.utc) + timedelta(seconds=200)
    with patch('app.services.content_cache.datetime') as fake_dt:
        fake_dt.now.return_value = future
        cache.get_tabs('http://localhost/')

    assert docs_service.fetch_tabs.call_count == 2


def test_creates_gemini_cache_when_tokens_meet_minimum() -> None:
    cache, _, client = _make_cache(token_count=MIN_CACHE_TOKENS + 1)
    cache.get_tabs('http://localhost/')
    client.caches.create.assert_called_once()
    assert cache.gemini_cache_name == 'caches/created-1'


def test_inline_fallback_when_below_token_minimum() -> None:
    cache, _, client = _make_cache(token_count=MIN_CACHE_TOKENS - 1)
    cache.get_tabs('http://localhost/')
    client.caches.create.assert_not_called()
    assert cache.gemini_cache_name is None


def test_inline_fallback_when_cache_creation_fails() -> None:
    cache, _, client = _make_cache(token_count=MIN_CACHE_TOKENS + 1)
    client.caches.create.side_effect = RuntimeError('quota exceeded')
    cache.get_tabs('http://localhost/')  # must not raise
    assert cache.gemini_cache_name is None


def test_old_gemini_cache_deleted_on_refresh() -> None:
    cache, _, client = _make_cache(token_count=MIN_CACHE_TOKENS + 1)
    cache.get_tabs('http://localhost/')
    first_name = cache.gemini_cache_name

    cache.invalidate()
    cache.get_tabs('http://localhost/')
    client.caches.delete.assert_called_once_with(name=first_name)


def test_site_base_url_overrides_request_host() -> None:
    cache, _, _ = _make_cache(site_base_url='https://site.example')
    cache.get_tabs('http://internal-host/')
    assert 'https://site.example/home' in cache.context_text
    assert 'http://internal-host' not in cache.context_text


def test_invalidate_forces_refetch() -> None:
    cache, docs_service, _ = _make_cache()
    cache.get_tabs('http://localhost/')
    cache.invalidate()
    cache.get_tabs('http://localhost/')
    assert docs_service.fetch_tabs.call_count == 2
