"""Unit tests for GoogleDocsService (service-account auth, nested tabs, slugs)."""
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.google_docs import (
    DocTab,
    GoogleDocsService,
    GoogleDocsServiceError,
    _safe_slug,
)


def _paragraph(text: str) -> dict[str, Any]:
    return {'paragraph': {'elements': [{'textRun': {'content': text}}]}}


def _fake_document() -> dict[str, Any]:
    """A doc with two top-level tabs; 'About' has a nested child tab 'Team'."""
    return {
        'tabs': [
            {
                'tabProperties': {'title': 'Home', 'tabId': 't1'},
                'documentTab': {
                    'body': {'content': [_paragraph('Welcome home')]}
                },
                'childTabs': [],
            },
            {
                'tabProperties': {'title': 'About', 'tabId': 't2'},
                'documentTab': {
                    'body': {'content': [_paragraph('About us')]}
                },
                'childTabs': [
                    {
                        'tabProperties': {'title': 'Team', 'tabId': 't3'},
                        'documentTab': {
                            'body': {'content': [_paragraph('Our team')]}
                        },
                    }
                ],
            },
        ]
    }


def _build_returning(document: dict[str, Any]) -> MagicMock:
    service = MagicMock()
    service.documents().get().execute.return_value = document
    return service


def test_fetch_tabs_returns_parent_and_child_tabs() -> None:
    creds = MagicMock()
    with patch('app.services.google_docs.service_account.Credentials'
               '.from_service_account_info', return_value=creds), \
         patch('app.services.google_docs.build',
               return_value=_build_returning(_fake_document())):
        svc = GoogleDocsService('{"type": "service_account"}', 'doc-id')
        tabs = svc.fetch_tabs()

    assert [t.title for t in tabs] == ['Home', 'About', 'Team']
    assert [t.slug for t in tabs] == ['home', 'about', 'team']
    assert all(isinstance(t, DocTab) for t in tabs)
    assert tabs[0].content == 'Welcome home'
    assert tabs[2].content == 'Our team'


def test_fetch_tabs_reads_credentials_from_file() -> None:
    creds = MagicMock()
    with patch('app.services.google_docs.os.path.isfile', return_value=True), \
         patch('app.services.google_docs.service_account.Credentials'
               '.from_service_account_file', return_value=creds) as from_file, \
         patch('app.services.google_docs.build',
               return_value=_build_returning(_fake_document())):
        svc = GoogleDocsService('/path/to/key.json', 'doc-id')
        tabs = svc.fetch_tabs()

    from_file.assert_called_once()
    assert tabs[0].title == 'Home'


def test_fetch_tabs_raises_when_credentials_missing() -> None:
    svc = GoogleDocsService('', 'doc-id')
    with pytest.raises(GoogleDocsServiceError):
        svc.fetch_tabs()


def test_fetch_tabs_raises_on_invalid_json_source() -> None:
    svc = GoogleDocsService('{not valid json', 'doc-id')
    with pytest.raises(GoogleDocsServiceError):
        svc.fetch_tabs()


def test_fetch_tabs_wraps_api_errors() -> None:
    creds = MagicMock()
    with patch('app.services.google_docs.service_account.Credentials'
               '.from_service_account_info', return_value=creds), \
         patch('app.services.google_docs.build',
               side_effect=RuntimeError('boom')):
        svc = GoogleDocsService('{"type": "service_account"}', 'doc-id')
        with pytest.raises(GoogleDocsServiceError):
            svc.fetch_tabs()


def test_safe_slug_handles_special_chars_and_spaces() -> None:
    assert _safe_slug('Hello, World!', 0, set()) == 'hello-world'


def test_safe_slug_deduplicates_collisions() -> None:
    seen: set[str] = set()
    assert _safe_slug('About', 0, seen) == 'about'
    assert _safe_slug('About', 1, seen) == 'about-1'
    assert _safe_slug('About', 2, seen) == 'about-2'


def test_safe_slug_empty_or_punctuation_title() -> None:
    assert _safe_slug('', 0, set()) == 'page-1'
    assert _safe_slug('!!!', 4, set()) == 'page-5'


def test_safe_slug_reserved_words() -> None:
    assert _safe_slug('Chat', 0, set()) == 'chat-page'
    assert _safe_slug('API', 0, set()) == 'api-page'
