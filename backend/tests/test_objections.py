from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from tests.helpers import login

from app.main import create_app
from app.providers.contracts import validate_stage_output
from app.providers.demo import DemoModelProvider
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from tests.test_finals_scenarios import general_payload


@pytest.fixture
def context(tmp_path):
    repo = DecisionRepository(tmp_path / 'db')
    context = repo.create(DecisionCreate(**general_payload())).model_dump(mode='json')
    context['calibration_warnings'] = [dict(category='revenue', bias_pct=-40.0, sample_size=2,
        assumption_ids=['A1'], adjusted_reference={'A1': 12000}, message='历史收入高估')]
    context['outputs']['researching'] = {'research_gaps': ['缺少真实证据']}
    return context


def test_challenge_injects_code_numbers_and_counts_novel_risks(context):
    output = DemoModelProvider().generate('challenging', context)
    assert output['premortem']
    assert output['calibration_warnings'] == context['calibration_warnings']
    assert output['novel_objection_count'] == sum(o['overlaps_known_risk_index'] is None for o in output['objections'])
    assert output['novel_objection_count'] >= 1
    assert any(o['severity'] == 'blocker' for o in output['objections'])


@pytest.mark.parametrize('mutation', ['assumption', 'risk', 'evidence', 'warning', 'coverage', 'duplicate', 'novel'])
def test_challenge_rejects_invalid_links_and_rewritten_code_numbers(context, mutation):
    output = DemoModelProvider().generate('challenging', context)
    if mutation == 'assumption': output['objections'][0]['targets_assumption_ids'] = ['A9']
    if mutation == 'risk': output['objections'][0]['overlaps_known_risk_index'] = 1
    if mutation == 'evidence': output['objections'][0]['evidence_ids'] = ['missing']
    if mutation == 'warning': output['calibration_warnings'][0]['bias_pct'] = 99
    if mutation == 'coverage':
        for obj in output['objections']: obj['targets_assumption_ids'] = []
    if mutation == 'duplicate': output['objections'].append(deepcopy(output['objections'][0]))
    if mutation == 'novel': output['novel_objection_count'] = 99
    with pytest.raises(ValueError): validate_stage_output('challenging', output, context)


def test_blockers_cannot_go_and_conditions_cover_each_blocker(context):
    context['outputs']['challenging'] = DemoModelProvider().generate('challenging', context)
    output = DemoModelProvider().generate('delivering', context)
    assert output['recommendation'] in {'go_with_conditions', 'small_test_first', 'defer', 'no_go'}
    output['recommendation'] = 'go'
    with pytest.raises(ValueError, match='blocker'): validate_stage_output('delivering', output, context)
    output['recommendation'] = 'no_go'
    output['conditions'] = []
    with pytest.raises(ValueError, match='blocker'): validate_stage_output('delivering', output, context)


def test_label_endpoint_requires_review_gate_existing_ids_and_overwrites(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        created = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + created['id']
        assert client.post(url + '/objection-labels', json={'labels': {'O1': 'adopted'}}).status_code == 409
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        result = client.post(url + '/objection-labels', json={'labels': {'O1': 'adopted'}})
        assert result.status_code == 200
        assert result.json()['objection_labels'] == {'O1': 'adopted'}
        assert client.post(url + '/objection-labels', json={'labels': {'O9': 'adopted'}}).status_code == 422
        assert client.post(url + '/objection-labels', json={'labels': {'O1': 'invalid'}}).status_code == 422
        client.post(url + '/review', json={'action': 'accepted'})
        result = client.post(url + '/objection-labels', json={'labels': {'O1': 'disagree'}})
        assert result.json()['objection_labels']['O1'] == 'disagree'
