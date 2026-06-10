"""Tests for the execution-flow learning routes."""
from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient


FIXTURE_URL = 'https://github.com/copilot-fixtures/code-tour-buggy-portal'


class TestLearningPage:
    """Tests for the explorer homepage shell."""

    def test_homepage_renders_explorer_shell(self, client: FlaskClient[Any]) -> None:
        response = client.get('/')
        assert response.status_code == 200
        assert b'Execution Flow Explorer' in response.data
        assert b'data-island="learning"' in response.data

    def test_learn_alias_renders_explorer_shell(self, client: FlaskClient[Any]) -> None:
        response = client.get('/learn')
        assert response.status_code == 200
        assert b'Execution Flow Explorer' in response.data


class TestLearningApi:
    """API tests for analysis creation and flow scoring."""

    def test_create_analysis_returns_flow_payload(self, client: FlaskClient[Any]) -> None:
        response = client.post(
            '/api/learning/analyses',
            json={'repositoryUrl': FIXTURE_URL},
            headers={'Accept': 'application/json'},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data is not None
        assert data['repository']['repo'] == 'code-tour-buggy-portal'
        assert data['flowsAvailable'] is True
        assert data['flows']
        assert data['graph']['nodes']
        assert data['analysisId']

    def test_create_analysis_rejects_non_root_url(self, client: FlaskClient[Any]) -> None:
        response = client.post(
            '/api/learning/analyses',
            json={'repositoryUrl': f'{FIXTURE_URL}/tree/main'},
            headers={'Accept': 'application/json'},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data is not None
        assert 'Only root GitHub repository URLs are supported' in data['message']

    def test_flow_scoring_round_trip(self, client: FlaskClient[Any]) -> None:
        create_response = client.post(
            '/api/learning/analyses',
            json={'repositoryUrl': FIXTURE_URL},
            headers={'Accept': 'application/json'},
        )
        analysis = create_response.get_json()
        analysis_id = analysis['analysisId']
        flow = analysis['flows'][0]

        # The learner sees steps sorted by path; the correct execution order is
        # view -> template -> main entry -> island module.
        correct_order = [
            'file:src/app/views/dashboard.py',
            'file:src/app/templates/dashboard.html',
            'file:frontend/src/main.ts',
            'file:frontend/src/islands/dashboard/index.tsx',
        ]
        score_response = client.post(
            f'/api/learning/analyses/{analysis_id}/score',
            json={'flowId': flow['id'], 'orderedStepIds': correct_order},
            headers={'Accept': 'application/json'},
        )

        assert score_response.status_code == 200
        result = score_response.get_json()
        assert result['isCorrect'] is True
        assert result['score'] == result['maxScore']

    def test_score_rejects_unknown_flow(self, client: FlaskClient[Any]) -> None:
        create_response = client.post(
            '/api/learning/analyses',
            json={'repositoryUrl': FIXTURE_URL},
            headers={'Accept': 'application/json'},
        )
        analysis_id = create_response.get_json()['analysisId']

        response = client.post(
            f'/api/learning/analyses/{analysis_id}/score',
            json={'flowId': 'flow:does-not-exist', 'orderedStepIds': []},
            headers={'Accept': 'application/json'},
        )
        assert response.status_code == 400
