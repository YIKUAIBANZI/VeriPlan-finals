"""Allowlisted Chat Completions adapter with a bounded schema fallback."""
import json
import re
import time
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

from app.providers.base import ProviderError
from app.providers.contracts import stage_schema
from app.providers.output_validation import ModelOutputError, incomplete
from app.providers.deepseek import DeepSeekModelProvider
from app.providers.prompts import build_prompt


def validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname in {'dashscope.aliyuncs.com', 'api.deepseek.com', 'api.minimaxi.com', 'api.moonshot.cn', 'llmapi.paratera.com'}
                 and parsed.port in {None, 443} and parsed.username is None and parsed.password is None
                 and not parsed.query and not parsed.fragment and not any(ord(c) < 33 for c in value)
                 and '\\' not in value)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('OpenAI-compatible base URL must use an allowlisted HTTPS host')
    return value.rstrip('/')


class OpenAICompatModelProvider(DeepSeekModelProvider):
    # Share validation, one repair, and the redacted attempt recorder.
    _provider_name = 'openai_compat'
    profile = 'openai_compat'

    def __init__(self, *, api_key: SecretStr, base_url: str, model: str,
                 timeout_seconds: int = 30, max_output_tokens: int = 8192,
                 transport=None, sleeper=time.sleep, recorder=None, profile="openai_compat"):
        from app.providers.profiles import PROFILE_URLS
        if profile != "openai_compat" and (profile not in PROFILE_URLS or base_url != PROFILE_URLS[profile]):
            raise ValueError("Invalid provider profile URL")
        self.profile = profile
        self._url = validate_base_url(base_url) + '/chat/completions'
        if not api_key.get_secret_value().strip():
            raise ValueError('Model API key must not be empty')
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._sleeper = sleeper
        self._recorder = recorder
        self._client = httpx2.Client(timeout=timeout_seconds, transport=transport,
            follow_redirects=False, trust_env=False,
            headers={'Authorization': f'Bearer {api_key.get_secret_value().strip()}', 'Content-Type': 'application/json'})

    def _build_payload(self, stage, context, *, repair_errors=None):
        name, schema = stage_schema(stage, member=context.get('_council_member'))
        system, prompt = build_prompt(stage, context, repair_errors=repair_errors)
        payload = dict(model=self._model, stream=False, max_tokens=self._max_output_tokens,
            messages=[{'role': 'system', 'content': system + '\nJSON Schema: ' + json.dumps(schema, ensure_ascii=False)},
                      {'role': 'user', 'content': prompt}],
            response_format={'type': 'json_schema', 'json_schema': {'name': name, 'schema': schema}})
        host = urlsplit(self._url).hostname
        if host == 'dashscope.aliyuncs.com' and self._model.lower().startswith('qwen3'):
            payload['enable_thinking'] = False
        if host == 'api.moonshot.cn':
            payload['temperature'] = 1
        return payload

    @staticmethod
    def _extract_output_text(body):
        choices = body.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ModelOutputError('model_contract_violation', ['response.choices: exactly one required'])
        choice = choices[0]
        if choice.get('finish_reason') != 'stop':
            raise incomplete({'length': 'max_output_tokens', 'content_filter': 'content_filter'}.get(
                choice.get('finish_reason') if isinstance(choice.get('finish_reason'), str) else ''))
        message = choice.get('message')
        if (not isinstance(message, dict) or message.get('refusal') or message.get('tool_calls')
                or message.get('role') != 'assistant' or not isinstance(message.get('content'), str)):
            raise ModelOutputError('model_contract_violation', ['response.message: assistant text required'])
        return _strip_reasoning_wrapper(message['content'])

    @staticmethod
    def _schema_unsupported(response):
        if response.status_code not in {400, 422}:
            return False
        try:
            error = response.json().get('error', {})
            message = str(error.get('message', '')).casefold()
            return ('json_schema' in message or error.get('param') == 'response_format') and any(
                term in message for term in ('not supported', 'unsupported', '不支持'))
        except (ValueError, AttributeError):
            return False

    def _request(self, payload, *, call_context, max_attempts=3):
        fallback = payload.get('response_format') == {'type': 'json_object'}
        for attempt in range(max_attempts):
            call_id = self._start_attempt(call_context, attempt + 1)
            code, retryable = None, False
            try:
                response = self._client.post(self._url, json=payload)
            except httpx2.TimeoutException:
                code, retryable = 'model_timeout', True
            except httpx2.TransportError:
                code, retryable = 'model_transport_error', True
            else:
                if not fallback and self._schema_unsupported(response):
                    self._finish_attempt(call_id, status='failed', error_code='model_schema_unsupported')
                    if attempt == max_attempts - 1:
                        raise ProviderError('model_schema_unsupported')
                    fallback = True
                    payload['response_format'] = {'type': 'json_object'}
                    continue
                code = 'model_auth_failed' if response.status_code == 403 else self._http_error_code(response.status_code)
                retryable = response.status_code in {429, 500, 502, 503, 504}
                if code is None:
                    try:
                        body = response.json()
                    except ValueError:
                        code = 'model_invalid_json'
                    else:
                        if isinstance(body, dict):
                            return body, call_id
                        code = 'model_contract_violation'
            self._finish_attempt(call_id, status='failed', error_code=code)
            if retryable and attempt < max_attempts - 1:
                self._sleeper((0.25, 0.75)[attempt])
                continue
            if code in {'model_invalid_json', 'model_contract_violation'}:
                raise ModelOutputError(code, ['response: invalid json' if code == 'model_invalid_json' else 'response: object required']) from None
            raise ProviderError(code) from None
        raise ProviderError('model_upstream_error')


_THINK_BLOCK = re.compile(r'^\s*<think>.*?</think>\s*', re.DOTALL)
_JSON_FENCE = re.compile(r'^```(?:json)?\s*\n(.*)\n```$', re.DOTALL)


def _strip_reasoning_wrapper(text):
    # Some providers (e.g. MiniMax M2.5) ignore response_format: they prepend a
    # <think> block and fence the JSON. Only that outer wrapper is removed; the
    # remaining text still goes through json.loads and the full contract.
    text = _THINK_BLOCK.sub('', text, count=1).strip()
    fenced = _JSON_FENCE.match(text)
    return fenced.group(1) if fenced else text
