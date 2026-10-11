import json

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.schemas import DecisionCreate
from app.repository import DecisionRepository
from app.providers.prompts import build_prompt
from app.providers.demo import DemoModelProvider
from app.providers.contracts import validate_stage_output
from app.markdown_export import render_decision_markdown
from tests.test_api import payload


def general_payload(**updates):
    return dict(question='是否应该为工作室招聘第一个全职设计师？', scenario='general',
                horizon_days=90, budget_limit=30000, primary_goal='提高接单产能',
                known_risks=['单量不稳'], assumptions=[dict(label='新增收入', category='revenue',
                value=20000, unit='元/月', confidence=70)]) | updates


@pytest.mark.parametrize('days', [7, 14, 30, 90, 180, 365])
def test_new_horizons_roundtrip_and_server_assumption_ids(tmp_path, days):
    repository = DecisionRepository(tmp_path / 'db')
    created = repository.create(DecisionCreate(**general_payload(horizon_days=days)))
    recovered = repository.get(created.id)
    assert recovered.time_window == f'{days} 天'
    assert recovered.scenario == 'general'
    assert recovered.horizon_days == days
    assert recovered.assumptions[0].id == 'A1'
    assert recovered.known_risks == ['单量不稳']
    assert recovered.objection_labels == {} and recovered.outcomes == []
    assert recovered.is_retrospective is False
    context = recovered.model_dump(mode='json')
    output = DemoModelProvider().generate('clarifying', context)
    assert validate_stage_output('clarifying', output, context)['time_window'] == f'{days} 天'
    output['time_window'] = '999 天'
    with pytest.raises(ValueError):
        validate_stage_output('clarifying', output, context)


@pytest.mark.parametrize('update', [
    {'horizon_days': 8}, {'scenario': 'unknown'}, {'known_risks': ['x'] * 6},
    {'known_risks': ['x' * 201]}, {'assumptions': [dict(label='x', category='bad', value=1, unit='元', confidence=70)]},
    {'assumptions': [dict(label='x', category='cost', value=1, unit='元', confidence=49)]},
    {'assumptions': [dict(id='A9', label='x', category='cost', value=1, unit='元', confidence=70)]},
    {'assumptions': [dict(label='x', category='cost', value=float('inf'), unit='元', confidence=70)]},
    {'time_window': '14 天'},
])
def test_frozen_input_limits(update):
    with pytest.raises(ValidationError):
        DecisionCreate(**(general_payload() | update))


def test_legacy_request_and_repeat_migration_export(tmp_path):
    repo = DecisionRepository(tmp_path / 'db')
    old = repo.create(DecisionCreate(**payload()))
    repo.save_stage_output(old.id, 'delivering', {'recommendation': 'do_not_pilot'})
    new_columns = ['scenario', 'horizon_days', 'known_risks_json', 'assumptions_json',
                   'objection_labels_json', 'outcomes_json', 'is_retrospective']
    with repo._engine.begin() as conn:
        for column in new_columns:
            conn.execute(text(f'ALTER TABLE decisions DROP COLUMN {column}'))
    repo._engine.dispose()
    for _ in range(2):
        repo = DecisionRepository(tmp_path / 'db')
        recovered = repo.get(old.id)
        assert recovered.scenario == 'ai_tool_pilot' and recovered.horizon_days == 14
        assert recovered.assumptions == []
        assert '不建议试点' in render_decision_markdown(recovered)
        repo.append_event(old.id, stage='legacy', status='read', summary='still writable')
        repo._engine.dispose()


def test_general_prompt_whitelists_assumptions_but_excludes_support_baseline():
    context = DecisionCreate(**general_payload()).model_dump(mode='json')
    context['assumptions'][0]['private_debug'] = 'secret-debug'
    _, value = build_prompt('clarifying', context)
    selected = json.loads(value)['context']
    assert selected['scenario'] == 'general'
    assert selected['horizon_days'] == 90
    assert selected['known_risks'] == ['单量不稳']
    assert selected['assumptions'][0]['value'] == 20000
    assert 'secret-debug' not in value
    assert 'business_baseline' not in selected and 'baseline_analysis' not in selected
