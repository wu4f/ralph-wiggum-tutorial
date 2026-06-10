"""Unit tests for execution-flow analysis and scoring."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.analysis_store import AnalysisSnapshot, AnalysisStore
from app.services.repository_analysis import analyze_repository, score_flow


BUGGY_FIXTURE_URL = 'https://github.com/copilot-fixtures/code-tour-buggy-portal'


def test_analysis_detects_request_flow_with_ordered_steps() -> None:
    learner_payload, answer_keys = analyze_repository(BUGGY_FIXTURE_URL)

    assert learner_payload['flowsAvailable'] is True
    assert learner_payload['flows']
    flow = learner_payload['flows'][0]

    # Steps presented to the learner are sorted by path, not execution order.
    presented_paths = [step['path'] for step in flow['steps']]
    assert presented_paths == sorted(presented_paths)

    # The canonical order starts at the Flask view and ends at the island.
    correct = answer_keys['flows'][flow['id']]['orderedStepIds']
    assert correct[0] == 'file:src/app/views/dashboard.py'
    assert correct[-1] == 'file:frontend/src/islands/dashboard/index.tsx'


def test_graph_edges_are_undirected_pairs() -> None:
    learner_payload, _ = analyze_repository(BUGGY_FIXTURE_URL)
    graph = learner_payload['graph']

    step_ids = {node['id'] for node in graph['nodes']}
    for edge in graph['edges']:
        assert edge['sourceId'] in step_ids
        assert edge['targetId'] in step_ids


def test_scoring_rewards_correct_order_and_penalizes_wrong_order() -> None:
    learner_payload, answer_keys = analyze_repository(BUGGY_FIXTURE_URL)
    flow = learner_payload['flows'][0]
    correct = answer_keys['flows'][flow['id']]['orderedStepIds']

    perfect = score_flow(answer_keys, flow['id'], correct)
    assert perfect['isCorrect'] is True
    assert perfect['score'] == perfect['maxScore']
    assert [step['id'] for step in perfect['correctOrder']] == correct

    reversed_result = score_flow(answer_keys, flow['id'], list(reversed(correct)))
    assert reversed_result['isCorrect'] is False
    assert reversed_result['score'] < reversed_result['maxScore']


def test_analysis_store_expires_snapshots() -> None:
    store = AnalysisStore(ttl_seconds=1)
    snapshot = store.save({'repository': {'repo': 'demo'}}, {'flows': {}})
    assert store.get(snapshot.analysis_id) is not None

    expired = AnalysisSnapshot(
        analysis_id=snapshot.analysis_id,
        learner_payload=snapshot.learner_payload,
        answer_keys=snapshot.answer_keys,
        created_at=datetime.now(UTC) - timedelta(seconds=5),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    store._snapshots[snapshot.analysis_id] = expired  # noqa: SLF001
    assert store.get(snapshot.analysis_id) is None
