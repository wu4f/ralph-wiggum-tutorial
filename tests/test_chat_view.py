"""Route tests for pages_bp and chat_bp (external services patched)."""
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.services.chat_service import ChatAnswer, HistoryTurn, Source
from app.services.google_docs import DocTab


@pytest.fixture
def tabs() -> list[DocTab]:
    return [
        DocTab(tab_id='t1', title='Home', slug='home', content='# Welcome'),
        DocTab(tab_id='t2', title='About', slug='about', content='About us'),
    ]


@pytest.fixture
def answer_mock(app: Flask) -> MagicMock:
    """Stub ChatService.answer; the real instance is kept (views type-check it)."""
    mock = MagicMock(return_value=ChatAnswer(
        answer='Hello there',
        sources=[Source(title='Home', url='http://localhost/home')],
    ))
    app.extensions['chat_service'].answer = mock
    return mock


@pytest.fixture
def client(app: Flask, tabs: list[DocTab], answer_mock: MagicMock) -> FlaskClient:
    """Test client with content_cache.get_tabs stubbed to fixed tabs."""
    app.extensions['content_cache'].get_tabs = MagicMock(return_value=tabs)
    return app.test_client()


def test_index_redirects_to_first_tab(client: FlaskClient) -> None:
    res = client.get('/')
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/home')


def test_page_renders_tab_content(client: FlaskClient) -> None:
    res = client.get('/home')
    assert res.status_code == 200
    assert b'Home' in res.data
    assert b'<h1>' in res.data


def test_page_unknown_slug_returns_404(client: FlaskClient) -> None:
    res = client.get('/does-not-exist')
    assert res.status_code == 404


def test_chat_page_hides_floating_widget(client: FlaskClient) -> None:
    res = client.get('/chat')
    assert res.status_code == 200
    assert b'data-island="chat-page"' in res.data
    assert b'data-island="chat-widget"' not in res.data


def test_api_chat_returns_answer_and_sources(client: FlaskClient) -> None:
    res = client.post('/api/chat', json={'question': 'What is this?'})
    assert res.status_code == 200
    body = res.get_json()
    assert body['answer'] == 'Hello there'
    assert body['sources'] == [
        {'title': 'Home', 'url': 'http://localhost/home'}
    ]


def test_api_chat_passes_history(
    client: FlaskClient, answer_mock: MagicMock
) -> None:
    history = [
        {'role': 'user', 'content': 'Hi'},
        {'role': 'assistant', 'content': 'Hello'},
    ]
    res = client.post('/api/chat',
                      json={'question': 'Follow up', 'history': history})
    assert res.status_code == 200
    _, kwargs = answer_mock.call_args
    assert kwargs['history'] == [
        HistoryTurn(role='user', content='Hi'),
        HistoryTurn(role='assistant', content='Hello'),
    ]


def test_api_chat_empty_body_returns_400(client: FlaskClient) -> None:
    res = client.post('/api/chat', json={})
    assert res.status_code == 400


def test_api_chat_oversized_question_returns_400(client: FlaskClient) -> None:
    res = client.post('/api/chat', json={'question': 'x' * 2001})
    assert res.status_code == 400


def test_api_chat_malformed_history_returns_400(client: FlaskClient) -> None:
    res = client.post('/api/chat',
                      json={'question': 'hi', 'history': [{'role': 'user'}]})
    assert res.status_code == 400


def test_api_chat_service_failure_returns_502(
    client: FlaskClient, answer_mock: MagicMock
) -> None:
    answer_mock.side_effect = RuntimeError('gemini down')
    res = client.post('/api/chat', json={'question': 'hi'})
    assert res.status_code == 502
