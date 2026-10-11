import json
from collections import Counter
from threading import Barrier, Lock

import pytest

from app.providers.base import ProviderError
from app.providers.contracts import validate_stage_output
from app.providers.demo import DemoModelProvider
from app.providers.prompts import build_prompt
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from app.workflow import WorkflowEngine
from tests.test_finals_scenarios import general_payload


def test_three_members_overlap_and_receive_isolated_identical_context(tmp_path):
    barrier, lock = Barrier(3), Lock()
    seen = {}

    class Council(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            if stage == 'analyzing':
                role = context['_council_member']
                assert call_context.logical_operation == f'analyzing:{role}'
                assert set(context['outputs']) <= {'planning', 'researching'}
                assert 'events' not in context and 'memo' not in context
                instructions, prompt = build_prompt(stage, context, member=role)
                with lock:
                    seen[role] = json.loads(prompt)['context']
                barrier.wait(timeout=3)  # sequential implementation cannot pass
            return super().generate(stage, context, call_context=call_context)

    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, model_provider=Council())
    decision = repo.create(DecisionCreate(**general_payload()))
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    result = engine.run(decision.id)
    assert result.status == 'awaiting_review', result.failure
    assert seen['opportunity'] == seen['cfo'] == seen['risk']
    analysis = result.outputs['analyzing']
    assert [x['role'] for x in analysis['members']] == ['opportunity', 'cfo', 'risk']
    assert analysis['disagreement']['is_split'] is True
    for role in seen:
        assert [e.status for e in result.events if e.stage == f'council:{role}'] == ['started', 'completed']


def test_member_failure_retries_whole_council_without_partial_output(tmp_path):
    calls = Counter()
    class Failing(DemoModelProvider):
        fail = True
        def generate(self, stage, context, *, call_context=None):
            if stage == 'analyzing':
                role = context['_council_member']
                calls[role] += 1
                if role == 'cfo' and self.fail:
                    raise ProviderError('model_timeout')
            return super().generate(stage, context, call_context=call_context)
    model = Failing()
    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, model_provider=model)
    decision = repo.create(DecisionCreate(**general_payload()))
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    failed = engine.run(decision.id)
    assert failed.failure['stage'] == 'analyzing'
    assert 'analyzing' not in failed.outputs
    model.fail = False
    assert engine.retry(decision.id).status == 'awaiting_review'
    assert calls == Counter(opportunity=2, cfo=2, risk=2)


@pytest.mark.parametrize('field,value', [('role', 'cfo'), ('evidence_ids', ['missing']),
                                          ('challenged_assumption_ids', ['A9'])])
def test_member_contract_rejects_wrong_role_or_references(tmp_path, field, value):
    repo = DecisionRepository(tmp_path / 'db')
    context = repo.create(DecisionCreate(**general_payload())).model_dump(mode='json')
    context['_council_member'] = 'opportunity'
    output = DemoModelProvider().generate('analyzing', context)
    output[field] = value
    with pytest.raises(ValueError):
        validate_stage_output('analyzing', output, context)


def test_prompt_never_includes_other_member_products(tmp_path):
    repo = DecisionRepository(tmp_path / 'db')
    context = repo.create(DecisionCreate(**general_payload())).model_dump(mode='json')
    context['outputs']['analyzing'] = {'members': ['OTHER_MEMBER_SECRET']}
    context['memo'] = {'summary': 'OTHER_MEMBER_SECRET'}
    for role in ('opportunity', 'cfo', 'risk'):
        system, prompt = build_prompt('analyzing', context, member=role)
        assert 'OTHER_MEMBER_SECRET' not in prompt
        assert role in system
