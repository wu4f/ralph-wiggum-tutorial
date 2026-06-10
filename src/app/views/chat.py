"""Chat page and the Gemini-backed chat API."""
from flask import Blueprint, current_app, jsonify, render_template, request
from pydantic import TypeAdapter, ValidationError

from ..services.chat_service import ChatService, HistoryTurn

chat_bp = Blueprint('chat', __name__)

_MAX_HISTORY = 20
_MAX_QUESTION_CHARS = 2000
_history_adapter = TypeAdapter(list[HistoryTurn])


def _get_chat_service() -> ChatService:
    svc = current_app.extensions.get('chat_service')
    if not isinstance(svc, ChatService):
        raise RuntimeError('ChatService is not configured.')
    return svc


@chat_bp.route('/chat')
def chat_page():  # type: ignore[no-untyped-def]
    return render_template('chat.html')


@chat_bp.route('/api/chat', methods=['POST'])
def ask():  # type: ignore[no-untyped-def]
    body = request.get_json(silent=True) or {}
    question = (body.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'question is required'}), 400
    if len(question) > _MAX_QUESTION_CHARS:
        return jsonify({'error': 'question too long'}), 400

    try:
        history = _history_adapter.validate_python(
            (body.get('history') or [])[-_MAX_HISTORY:]
        )
    except ValidationError:
        return jsonify({'error': 'invalid history'}), 400

    try:
        result = _get_chat_service().answer(
            question, request.host_url, history=history)
    except Exception:
        current_app.logger.exception('Chat failed')
        return jsonify({'error': 'chat service unavailable'}), 502
    return jsonify({'answer': result.answer,
                    'sources': [s.model_dump() for s in result.sources]})
