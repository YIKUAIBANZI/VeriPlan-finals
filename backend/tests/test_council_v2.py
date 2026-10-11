from copy import deepcopy
import json
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.contracts import validate_stage_output
from app.providers.demo import DemoModelProvider
from app.providers.prompts import build_prompt
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from app.workflow import WorkflowEngine
from tests.test_finals_scenarios import general_payload
from tests.test_stage_contracts import context_with_evidence


DEFAULTS = {'first_hire': 'legal_compliance', 'big_order': 'operations',
            'marketing_spend': 'platform_rules', 'ai_tool_pilot': 'customer',
            'general': 'personal_longterm'}


@pytest.mark.parametrize('scenario,kind', DEFAULTS.items())
@pytest.mark.parametrize('invalid', [None, 'invented', [], 123])
def test_planning_invalid_expert_defaults_without_failure(scenario, kind, invalid):
    context = context_with_evidence() | {'scenario': scenario}
    output = DemoModelProvider().generate('planning', context)
    output.pop('expert_kind', None)
    if invalid is not None:
        output['expert_kind'] = invalid
    output['expert_reason'] = '模型理由'
    original = deepcopy(output)
    result = validate_stage_output('planning', output, context)
    assert (result['expert_kind'], result['expert_reason'], result['expert_source']) == (kind, '按场景默认', 'scenario_default')
    assert output == original
    assert validate_stage_output('planning', result, context) == result


@pytest.mark.parametrize('kind', DEFAULTS.values())
def test_model_expert_selection_and_role_instructions(kind):
    context = context_with_evidence()
    output = DemoModelProvider().generate('planning', context)
    output.update(expert_kind=kind, expert_reason='这个问题需要专业审查')
    selected = validate_stage_output('planning', output, context)
    assert selected['expert_source'] == 'model'
    context['outputs']['planning'] = selected
    context['_council_member'] = 'expert'
    opinion = DemoModelProvider().generate('analyzing', context)
    assert opinion['role'] == 'expert' and opinion['expert_kind'] == kind
    instructions, prompt = build_prompt('analyzing', context)
    assert kind in instructions
    assert json.loads(prompt)['context']['planning'] == selected
    opinion['expert_kind'] = next(k for k in DEFAULTS.values() if k != kind)
    with pytest.raises(ValueError, match='expert'):
        validate_stage_output('analyzing', opinion, context)


@pytest.mark.parametrize('reason', [None, '', 'x' * 81, {}])
def test_invalid_expert_reason_uses_bounded_scenario_default(reason):
    context = context_with_evidence() | {'scenario': 'first_hire'}
    payload = DemoModelProvider().generate('planning', context)
    payload.update(expert_kind='customer', expert_reason=reason)
    result = validate_stage_output('planning', payload, context)
    assert result['expert_kind'] == 'legal_compliance'
    assert result['expert_reason'] == '按场景默认'


def test_four_seats_overlap_isolate_and_reach_challenger(tmp_path):
    barrier = Barrier(4)
    seen = {}
    class Model(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            if stage == 'analyzing':
                role = context['_council_member']
                assert set(context['outputs']) == {'planning', 'researching'}
                seen[role] = json.loads(build_prompt(stage, context)[1])['context']
                context['known_risks'].append(role)  # Each worker owns a deep copy.
                barrier.wait(timeout=3)
            if stage == 'challenging':
                assert len(context['outputs']['analyzing']['members']) == 4
            return super().generate(stage, context, call_context=call_context)
    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, model_provider=Model())
    decision = repo.create(DecisionCreate(**general_payload()))
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    result = engine.run(decision.id)
    assert result.status == 'awaiting_review', result.failure
    assert len(seen) == 4 and all(c == seen['expert'] for c in seen.values())
    assert set(result.outputs['analyzing']['disagreement']['stances']) == {'opportunity', 'cfo', 'risk', 'expert'}
    events = [e for e in result.events if e.stage == 'council:expert']
    assert [e.status for e in events] == ['started', 'completed']
    assert '专家：' in events[-1].summary


def test_old_three_seat_record_reads_exports_but_new_contract_requires_four(tmp_path):
    app = create_app(tmp_path / 'db')
    with TestClient(app) as client:
        row = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + row['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        snapshot = client.get(url).json()
        analysis = snapshot['outputs']['analyzing']
        analysis['members'] = [m for m in analysis['members'] if m['role'] != 'expert']
        analysis['disagreement']['stances'].pop('expert', None)
        app.state.repository.save_stage_output(row['id'], 'analyzing', analysis)
        assert len(client.get(url).json()['outputs']['analyzing']['members']) == 3
        assert client.get(url + '/export.md').status_code == 200
        with pytest.raises(ValueError):
            validate_stage_output('analyzing', analysis, snapshot)


def test_valid_model_choice_is_model_sourced_even_when_reason_uses_default_wording():
    context = context_with_evidence() | {'scenario': 'first_hire'}
    output = {'summary': '研究计划', 'queries': ['成本证据', '风险证据'], 'research_questions': ['需要哪些证据？'],
              'expert_kind': 'legal_compliance', 'expert_reason': '按场景默认'}
    result = validate_stage_output('planning', output, context)
    assert result['expert_source'] == 'model'
    assert validate_stage_output('planning', result, context) == result
