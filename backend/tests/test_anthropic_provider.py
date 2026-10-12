import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.providers.anthropic_provider import AnthropicModelProvider
from app.providers.base import ProviderError
from app.providers.profiles import model_label, parse_council_model_map


class _Message:
    def __init__(self, body):
        self._body = body

    def model_dump(self, mode='json'):
        return self._body


class _FakeClient:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **payload):
        self.calls.append(payload)
        return _Message(self.bodies.pop(0))


def _text(payload):
    return {'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': ''},
                                                   {'type': 'text', 'text': json.dumps(payload)}]}


def _provider(client):
    return AnthropicModelProvider(api_key=SecretStr('test-key'), client=client, sleeper=lambda _: None)


def test_payload_uses_structured_output_effort_and_refusal_fallback():
    client = _FakeClient([_text({'risks': ['预算不足以覆盖 90 天成本']})])
    result = _provider(client).generate('ablation', {'question': 'q' * 20, 'time_window': '90 天',
                                                      'budget_limit': 1, 'primary_goal': 'g'})
    assert result == {'risks': ['预算不足以覆盖 90 天成本']}
    call = client.calls[0]
    assert call['model'] == 'claude-sonnet-5-5'
    assert call['output_config']['effort'] == 'medium'
    assert call['output_config']['format']['type'] == 'json_schema'
    assert call['fallbacks'] == 'default' and call['betas'] == ['server-side-fallback-2026-07-01']


def test_refusal_is_a_stable_error_code():
    client = _FakeClient([{'stop_reason': 'refusal', 'content': []}])
    with pytest.raises(ProviderError) as error:
        _provider(client).generate('ablation', {'question': 'q' * 20, 'time_window': '90 天',
                                                'budget_limit': 1, 'primary_goal': 'g'})
    assert error.value.code == 'model_refusal'


def test_invalid_output_gets_one_repair_call():
    client = _FakeClient([_text({'wrong': 1}), _text({'risks': ['r']})])
    assert _provider(client).generate('ablation', {'question': 'q' * 20, 'time_window': '90 天',
                                                   'budget_limit': 1, 'primary_goal': 'g'}) == {'risks': ['r']}
    assert len(client.calls) == 2


def test_anthropic_profile_routes_and_labels():
    assert parse_council_model_map('cfo=anthropic') == {'cfo': ('anthropic', None)}
    assert model_label('anthropic', 'claude-sonnet-5-5') == 'Claude sonnet-5-5'
