import json

import httpx2
import pytest
from pydantic import SecretStr

from app.providers.base import ProviderCallContext, ProviderError
from app.providers.deepseek import DeepSeekModelProvider
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_repository import sample_decision


@pytest.fixture
def context() -> dict:
    value = sample_decision().model_dump(mode="json")
    value["evidence"] = [
        card.model_copy(update={"id": str(index)}).model_dump(mode="json")
        for index, card in enumerate(DemoSearchProvider().search("baseline"), 1)
    ]
    value["outputs"] = {
        "researching": {"research_gaps": ["仍缺少真实数据"]},
        "challenging": {"objection": "证据不足"},
    }
    value["events"] = [{"summary": "must not leave the process"}]
    value["review_note"] = "private review note"
    value["failure"] = {"message": "private failure"}
    value["database_internal"] = "private database field"
    return value


def completed_response(payload: dict) -> dict:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1_787_000_000,
        "status": "completed",
        "model": "deepseek-v4-flash",
        "output": [
            {
                "type": "reasoning",
                "id": "rs_1",
                "status": "completed",
                "content": [
                    {"type": "reasoning_text", "text": "private chain of thought"}
                ],
            },
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        "error": None,
        "incomplete_details": None,
    }


class AttemptSpy:
    def __init__(self):
        self.started = []
        self.finished = []

    def start_provider_attempt(self, *, context, provider, attempt_number, profile=None, model=None):
        self.started.append((context, provider, attempt_number))
        return len(self.started)

    def finish_provider_attempt(self, call_id, *, status, error_code=None, incomplete_reason=None):
        self.finished.append((call_id, status, error_code))


def make_provider(handler, *, delays: list[float] | None = None, recorder=None):
    return DeepSeekModelProvider(
        api_key=SecretStr("unit-secret"),
        transport=httpx2.MockTransport(handler),
        sleeper=(delays.append if delays is not None else lambda _: None),
        recorder=recorder,
    )


def test_provider_uses_responses_json_schema_and_minimal_context(context):
    requests = []
    expected = DemoModelProvider().generate("clarifying", context)

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=completed_response(expected))

    provider = make_provider(handler)
    try:
        result = provider.generate("clarifying", context)
    finally:
        provider.close()

    assert result == expected
    assert "private chain of thought" not in repr(result)
    assert len(requests) == 1
    request = requests[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.deepseek.com/responses"
    assert request.headers["authorization"] == "Bearer unit-secret"
    assert body["model"] == "deepseek-v4-flash"
    assert body["stream"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 8192
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["name"] == "veriplan_clarifying"
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert "tools" not in body
    prompt = json.loads(body["input"])
    assert prompt["stage"] == "clarifying"
    assert set(prompt["context"]) == {
        "question",
        "time_window",
        "budget_limit",
        "primary_goal",
        "business_baseline",
        "baseline_analysis",
        "scenario", "horizon_days", "known_risks", "assumptions",
    }
    assert "private" not in body["input"]


def test_planning_request_uses_bounded_queries_and_research_questions(context):
    requests = []
    expected = DemoModelProvider().generate("planning", context)

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=completed_response(expected))

    provider = make_provider(handler)
    try:
        assert provider.generate("planning", context) == expected
    finally:
        provider.close()

    schema = json.loads(requests[0].content)["text"]["format"]["schema"]
    assert schema["properties"]["queries"]["items"]["maxLength"] == 400
    assert "research_questions" in schema["required"]
    assert "research_gaps" not in schema["properties"]


def test_unsupported_stage_never_calls_transport(context):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(500)

    provider = make_provider(handler)
    try:
        with pytest.raises(ValueError, match="Unsupported model stage"):
            provider.generate("researching", context)
    finally:
        provider.close()

    assert calls == 0


@pytest.mark.parametrize(
    ("status", "code", "expected_calls"),
    [
        (400, "model_invalid_request", 1),
        (401, "model_auth_failed", 1),
        (402, "model_balance_exhausted", 1),
        (422, "model_invalid_request", 1),
        (429, "model_rate_limited", 3),
        (500, "model_upstream_unavailable", 3),
        (503, "model_upstream_unavailable", 3),
        (418, "model_upstream_error", 1),
    ],
)
def test_http_error_classification_is_bounded_and_redacted(
    status, code, expected_calls, context
):
    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            status,
            json={"error": {"message": "unit-secret private customer data"}},
        )

    provider = make_provider(handler, delays=delays)
    try:
        with pytest.raises(ProviderError) as raised:
            provider.generate("clarifying", context)
    finally:
        provider.close()

    assert raised.value.code == code
    assert calls == expected_calls
    assert delays == ([0.25, 0.75] if expected_calls == 3 else [])
    assert "unit-secret" not in str(raised.value)
    assert "private customer data" not in str(raised.value)


@pytest.mark.parametrize(
    ("exception_type", "code"),
    [
        (httpx2.ReadTimeout, "model_timeout"),
        (httpx2.ConnectError, "model_transport_error"),
    ],
)
def test_transport_failures_retry_three_times(exception_type, code, context):
    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        raise exception_type("unit-secret private transport detail", request=request)

    provider = make_provider(handler, delays=delays)
    try:
        with pytest.raises(ProviderError) as raised:
            provider.generate("clarifying", context)
    finally:
        provider.close()

    assert raised.value.code == code
    assert calls == 3
    assert delays == [0.25, 0.75]
    assert "unit-secret" not in str(raised.value)


def invalid_response_cases(valid_payload: dict):
    response = completed_response(valid_payload)
    return [
        {**response, "status": "failed", "error": {"message": "private"}},
        {
            **response,
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
        },
        {**response, "output": []},
        {
            **response,
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "  "}],
                }
            ],
        },
        {
            **response,
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "not-json"}],
                }
            ],
        },
        {
            **response,
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(valid_payload)},
                        {"type": "output_text", "text": json.dumps(valid_payload)},
                    ],
                }
            ],
        },
        completed_response({"summary": "missing required fields"}),
    ]


def test_invalid_responses_receive_one_repair_without_leaks(context):
    valid = DemoModelProvider().generate("clarifying", context)

    codes = ["model_incomplete", "model_incomplete", "model_contract_violation", "model_invalid_json", "model_invalid_json", "model_contract_violation", "model_contract_violation"]
    for response_body, code in zip(invalid_response_cases(valid), codes):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx2.Response(200, json=response_body)

        provider = make_provider(handler)
        try:
            with pytest.raises(ProviderError) as raised:
                provider.generate("clarifying", context)
        finally:
            provider.close()

        assert raised.value.code == code
        assert calls == 2
        assert "private" not in str(raised.value)


def test_retry_attempts_are_audited_without_payloads_or_secrets(context):
    spy = AttemptSpy()
    expected = DemoModelProvider().generate("clarifying", context)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(
                429,
                json={"error": {"message": "unit-secret private response"}},
            )
        return httpx2.Response(200, json=completed_response(expected))

    provider = make_provider(handler, recorder=spy)
    call_context = ProviderCallContext(
        decision_id="decision-id",
        logical_operation="clarifying",
        stage="clarifying",
    )
    try:
        assert provider.generate(
            "clarifying",
            context,
            call_context=call_context,
        ) == expected
    finally:
        provider.close()

    assert spy.started == [
        (call_context, "deepseek", 1),
        (call_context, "deepseek", 2),
    ]
    assert spy.finished == [
        (1, "failed", "model_rate_limited"),
        (2, "succeeded", None),
    ]
    assert "unit-secret" not in repr(spy.__dict__)
    assert "private response" not in repr(spy.__dict__)
