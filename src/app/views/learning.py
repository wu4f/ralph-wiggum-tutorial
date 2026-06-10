"""Learning routes for repository execution-flow visualization quizzes."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from ..services.analysis_store import AnalysisSnapshot, AnalysisStore
from ..services.repository_analysis import (
    RepositoryAnalysisError,
    analyze_repository,
    score_flow,
)

learning_bp = Blueprint('learning', __name__)


def _get_snapshot_store() -> AnalysisStore:
    store = current_app.extensions.get('analysis_store')
    if not isinstance(store, AnalysisStore):
        raise RuntimeError('Analysis store is not configured.')
    return store


def _learner_snapshot_response(snapshot: AnalysisSnapshot) -> dict[str, Any]:
    analysis = dict(snapshot.learner_payload)
    analysis['analysisId'] = snapshot.analysis_id
    analysis['expiresAt'] = snapshot.expires_at.isoformat()
    return analysis


@learning_bp.route('/', methods=['GET'])
@learning_bp.route('/learn', methods=['GET'])
def index() -> str:
    """Render the execution-flow visualization homepage shell."""
    return render_template('learning.html')


@learning_bp.route('/api/learning/analyses', methods=['POST'])
def create_analysis() -> tuple[Any, int]:
    """Create a fresh repository analysis snapshot."""
    payload = request.get_json(silent=True) or {}
    repository_url = payload.get('repositoryUrl')
    if not isinstance(repository_url, str) or not repository_url.strip():
        abort(400, description='repositoryUrl is required.')

    try:
        learner_payload, answer_keys = analyze_repository(repository_url)
    except RepositoryAnalysisError as error:
        abort(400, description=str(error))

    snapshot = _get_snapshot_store().save(learner_payload, answer_keys)
    return jsonify(_learner_snapshot_response(snapshot)), 201


@learning_bp.route('/api/learning/analyses/<analysis_id>', methods=['GET'])
def get_analysis(analysis_id: str) -> Any:
    """Return a previously created short-lived analysis snapshot."""
    snapshot = _get_snapshot_store().get(analysis_id)
    if snapshot is None:
        abort(404, description='The analysis could not be found or has expired.')
    return jsonify(_learner_snapshot_response(snapshot))


@learning_bp.route('/api/learning/analyses/<analysis_id>/score', methods=['POST'])
def score_analysis(analysis_id: str) -> Any:
    """Score a student's ordered execution-flow answer."""
    snapshot = _get_snapshot_store().get(analysis_id)
    if snapshot is None:
        abort(404, description='The analysis could not be found or has expired.')

    payload = request.get_json(silent=True) or {}
    flow_id = payload.get('flowId')
    ordered_step_ids = payload.get('orderedStepIds')
    if not isinstance(flow_id, str):
        abort(400, description='flowId is required.')
    if not isinstance(ordered_step_ids, list) or not all(
        isinstance(step_id, str) for step_id in ordered_step_ids
    ):
        abort(400, description='orderedStepIds must be a list of strings.')

    try:
        result = score_flow(snapshot.answer_keys, flow_id, ordered_step_ids)
    except RepositoryAnalysisError as error:
        abort(400, description=str(error))
    return jsonify(result)
