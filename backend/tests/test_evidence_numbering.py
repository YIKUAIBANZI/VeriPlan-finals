"""Local model/display citations must never change persisted evidence identity."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.markdown_export import render_decision_markdown
from app.providers.base import ProviderCallContext
from app.providers.contracts import COUNCIL_ROLES, validate_stage_output
from app.providers.demo import DemoModelProvider
from app.providers.output_validation import ModelOutputError
from app.providers.prompts import build_prompt
from app.repository import DecisionRepository
from tests.test_anthropic_provider import _Message, _provider, _text
from tests.test_deepseek_provider import AttemptSpy
from tests.test_depth import run_decision
from tests.test_live_hardening import build_adapter, envelope
from tests.test_stage_contracts import context_with_evidence
from app.workflow import WorkflowEngine


TEXT = '证据1、2提示风险；预算35元，14天后复核（2）。'


def numbered_context(ids=('35', '14')):
    context = context_with_evidence()
    for card, ref in zip(context['evidence'], ids, strict=True):
        card['id'] = ref
    context['assumptions'] = [{'id': 'A1'}]
    context['outputs']['researching']['evidence_ids'] = list(ids)
    for stage in ('planning', 'analyzing', 'challenging'):
        context['outputs'][stage] = DemoModelProvider().generate(stage, context)
    return context


def evidence_references(value):
    if isinstance(value, dict):
        return [ref for key, item in value.items()
                for ref in (item if key == 'evidence_ids' else evidence_references(item))]
    if isinstance(value, list):
        return [ref for item in value for ref in evidence_references(item)]
    return []


CASES = [
    ('analyzing', {}),
    *[('analyzing', {'_council_member': role}) for role in COUNCIL_ROLES],
    ('challenging', {}),
    ('challenging', {'_skeptic_input': 'independent'}),
    ('challenging', {'_review': True}),
    ('challenging', {'_review': True, '_skeptic_input': 'independent'}),
    ('delivering', {}),
    ('planning', {'_research_followup': True}),
    ('ablation', {}),
    ('ablation', {'_ablation_variant': 'skeptic_prompt'}),
]


@pytest.mark.parametrize('stage,flags', CASES)
def test_prompt_uses_ordered_local_ids_in_evidence_history_and_review(stage, flags):
    context = numbered_context() | flags
    context['outputs']['analyzing']['summary'] = TEXT
    if context.pop('_review', False):
        context['_challenge_draft'] = deepcopy(context['outputs']['challenging'])
        context['_challenge_draft']['premortem'] = TEXT
    original = deepcopy(context)

    instructions, prompt = build_prompt(stage, context)
    selected = json.loads(prompt)['context']

    assert [card['id'] for card in selected['evidence']] == ['1', '2']
    assert [card['title'] for card in selected['evidence']] == [card['title'] for card in context['evidence']]
    assert set(evidence_references(selected)) <= {'1', '2'}
    if 'challenge_draft' in selected:
        assert selected['challenge_draft']['objections'][0]['evidence_ids'] == ['1', '2']
        assert selected['challenge_draft']['premortem'] == TEXT
    if 'analysis' in selected:
        assert selected['analysis']['summary'] == TEXT
        assert selected['analysis']['members'][0]['challenged_assumption_ids'] == ['A1']
    assert '从 1 开始' in instructions
    assert context == original


def stub_provider(adapter, respond, recorder=None):
    """Return model JSON through the real adapter's parsing and repair loop."""
    if adapter == 'anthropic':
        def create(**body):
            return _Message(_text(respond(json.loads(body['messages'][0]['content']), body['system'])))
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)), close=lambda: None)
        model = _provider(client)
        model._recorder = recorder
        return model

    def handler(request):
        body = json.loads(request.content)
        prompt = body['input'] if adapter == 'deepseek' else body['messages'][1]['content']
        instructions = body['instructions'] if adapter == 'deepseek' else body['messages'][0]['content']
        return envelope(adapter, respond(json.loads(prompt), instructions))
    return build_adapter(adapter, handler, recorder)


@pytest.mark.parametrize('adapter', ['deepseek', 'compat', 'anthropic'])
@pytest.mark.parametrize('stage,flags', [
    ('analyzing', {}), ('analyzing', {'_council_member': 'cfo'}),
    ('challenging', {}), ('delivering', {}),
])
def test_adapter_restores_all_structured_ids_without_rewriting_text(adapter, stage, flags):
    context = numbered_context() | flags
    local = numbered_context(('1', '2')) | flags
    output = DemoModelProvider().generate(stage, local)
    expected = DemoModelProvider().generate(stage, context)
    for payload in (output, expected):
        if stage == 'analyzing':
            for member in payload.get('members', [payload]):
                member.update(reasoning=TEXT, key_points=[TEXT])
        else:
            payload['summary'] = TEXT
        if stage == 'challenging':
            payload['premortem'] = payload['objections'][0]['text'] = TEXT
        if stage == 'delivering':
            payload['facts'][0]['text'] = payload['inferences'][0]['text'] = TEXT
    original = deepcopy(context)
    model = stub_provider(adapter, lambda *_: output)
    try:
        result = model.generate(stage, context)
    finally:
        model.close()

    assert result == expected
    assert set(evidence_references(result)) <= {'35', '14'}
    assert context == original
    # Workflow validates again using global IDs; this must not remap them twice.
    assert validate_stage_output(stage, result, context) == result


@pytest.mark.parametrize('adapter', ['deepseek', 'compat', 'anthropic'])
@pytest.mark.parametrize('invalid', ['0', '3', '35', '14', '-1', '01'])
def test_invalid_ordinal_including_global_id_collision_is_unknown_and_repaired(adapter, invalid):
    context = numbered_context()
    output = DemoModelProvider().generate('challenging', numbered_context(('1', '2')))
    seen, spy = [], AttemptSpy()

    def respond(message, _):
        seen.append(message)
        result = deepcopy(output)
        if len(seen) == 1:
            result['objections'][0]['evidence_ids'] = [invalid]
        return result

    model = stub_provider(adapter, respond, spy)
    try:
        result = model.generate('challenging', context,
            call_context=ProviderCallContext('decision', 'challenging'))
    finally:
        model.close()
    assert result['objections'][0]['evidence_ids'] == ['35', '14']
    assert len(seen) == 2
    assert seen[0]['context'] == seen[1]['context']
    assert seen[1]['repair_errors'] == ['evidence_ids: unknown id']
    assert [call[0].logical_operation for call in spy.started] == ['challenging', 'challenging:repair']
    assert spy.finished == [(1, 'failed', 'model_contract_violation'), (2, 'succeeded', None)]


@pytest.mark.parametrize('single_attempt', [False, True])
def test_persistent_unknown_id_fails_with_bounded_repair(single_attempt):
    context = numbered_context()
    output = DemoModelProvider().generate('challenging', context)
    seen = []
    def respond(message, _):
        seen.append(message)
        return output  # Global IDs are invalid model-facing ordinals.
    model = stub_provider('deepseek', respond)
    try:
        with pytest.raises(ModelOutputError) as error:
            model.generate('challenging', context, call_context=ProviderCallContext(
                'decision', 'challenging', single_attempt=single_attempt))
    finally:
        model.close()
    assert error.value.issues == ['evidence_ids: unknown id']
    assert len(seen) == (1 if single_attempt else 2)


@pytest.mark.parametrize('adapter', ['deepseek', 'compat', 'anthropic'])
def test_second_decision_persists_globals_and_exports_local_ids_across_depth_stages(tmp_path, adapter):
    repo = DecisionRepository(tmp_path / 'numbering.db')
    seen = []

    def respond(message, instructions):
        seen.append(deepcopy(message))
        stage, selected = message['stage'], deepcopy(message['context'])
        selected.setdefault('evidence', [])
        ids = [card['id'] for card in selected['evidence']]
        assert ids == [str(index) for index in range(1, len(ids) + 1)]
        assert set(evidence_references(selected)) <= set(ids)
        selected['outputs'] = {'planning': selected.get('planning', {}),
            'researching': selected.get('research', {}), 'challenging': selected.get('challenge', {})}
        if stage == 'analyzing':
            selected['_council_member'] = next(role for role in COUNCIL_ROLES if f'本次独立席位 {role}' in instructions)
        if stage == 'planning' and 'existing_queries' in selected:
            selected['_research_followup'] = True
        result = DemoModelProvider().generate(stage, selected)
        if stage == 'challenging' and 'challenge_draft' in selected:
            assert selected['challenge_draft']['objections'][0]['evidence_ids'] == ids
            if 'repair_errors' not in message:
                result['objections'][0]['evidence_ids'] = ['999']
        if stage == 'delivering':
            result['facts'][0]['text'] = TEXT
            result['inferences'][0]['text'] = TEXT
        if stage == 'ablation':
            result['risks'] = [TEXT]
        return result

    model = stub_provider(adapter, respond, repo)
    engine = WorkflowEngine(repo, model_provider=model, settings=Settings(
        research_rounds=2, skeptic_review_pass=True, skeptic_input='independent'))
    try:
        first = run_decision(repo, engine)
        assert first.status == 'awaiting_review', first.failure
        first_before = first.model_dump(mode='json')
        seen.clear()
        second = run_decision(repo, engine)
        assert second.status == 'awaiting_review', second.failure
        for variant in ('default', 'skeptic_prompt'):
            assert model.generate('ablation', second.model_dump(mode='json') | {
                '_ablation_variant': variant}) == {'risks': [TEXT]}
    finally:
        model.close()

    second = repo.get(second.id)
    global_ids = [card.id for card in second.evidence]
    assert int(global_ids[0]) > len(first.evidence)
    assert len(global_ids) == 5  # Three initial sources plus two followups.
    assert all(member['evidence_ids'] == global_ids[:1] for member in second.outputs['analyzing']['members'])
    assert second.outputs['challenging']['objections'][0]['evidence_ids'] == global_ids
    assert [fact['evidence_ids'] for fact in second.memo['facts']] == [[ref] for ref in global_ids]
    assert second.memo['inferences'][0]['evidence_ids'] == global_ids
    assert second.memo['facts'][0]['text'] == second.memo['inferences'][0]['text'] == TEXT
    assert repo.get(first.id).model_dump(mode='json') == first_before
    assert any(message['stage'] == 'planning' and len(message['context'].get('evidence', [])) == 3 for message in seen)
    reviews = [message for message in seen if 'challenge_draft' in message['context']]
    assert len(reviews) == 2 and reviews[1]['repair_errors'] == ['evidence_ids: unknown id']
    calls = repo.list_provider_calls(second.id)
    assert all(call['status'] != 'running' for call in calls)
    assert {call['logical_operation'] for call in calls} >= {
        'planning:followup', 'challenging:review', 'challenging:review:repair',
        *[f'analyzing:{role}' for role in COUNCIL_ROLES],
    }

    original = second.model_dump(mode='json')
    markdown = render_decision_markdown(second)
    assert f'{TEXT}（证据：1）' in markdown
    assert f'{TEXT}（证据：1, 2, 3, 4, 5）' in markdown
    assert '；证据：1\n' in markdown  # Council members.
    assert '；证据：1, 2, 3, 4, 5）' in markdown  # Skeptic objections.
    for ordinal, card in enumerate(second.evidence, 1):
        assert f'证据 ID：{ordinal}）' in markdown
        assert f'证据 ID：{card.id}）' not in markdown
    assert second.model_dump(mode='json') == original
    assert repo.get(second.id).model_dump(mode='json') == original
