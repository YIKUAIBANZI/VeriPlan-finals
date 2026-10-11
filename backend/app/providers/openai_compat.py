"""Allowlisted Chat Completions adapter with a bounded schema fallback."""
import json
import time
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

from app.providers.base import ProviderError
from app.providers.contracts import stage_schema, validate_stage_output
from app.providers.deepseek import DeepSeekModelProvider
from app.providers.prompts import build_prompt


def validate_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname in {'dashscope.aliyuncs.com', 'api.deepseek.com'}
                 and parsed.port in {None, 443} and parsed.username is None and parsed.password is None
                 and not parsed.query and not parsed.fragment and not any(ord(c) < 33 for c in value)
                 and '\\' not in value)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('OpenAI-compatible base URL must use an allowlisted HTTPS host')
    return value.rstrip('/')


class OpenAICompatModelProvider(DeepSeekModelProvider):
    # Reuse the existing redacted attempt recorder and status classification only.
    _provider_name = 'openai_compat'

    def __init__(self, *, api_key: SecretStr, base_url: str, model: str,
                 timeout_seconds: int = 30, max_output_tokens: int = 4096,
                 transport=None, sleeper=time.sleep, recorder=None):
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

    def generate(self, stage, context, *, call_context=None):
        name, schema = stage_schema(stage, member=context.get('_council_member'))
        system, prompt = build_prompt(stage, context)
        # Schema remains in the system message when the server only supports JSON mode.
        payload = dict(model=self._model, stream=False, max_tokens=self._max_output_tokens,
            messages=[{'role': 'system', 'content': system + '\nJSON Schema: ' + json.dumps(schema, ensure_ascii=False)},
                      {'role': 'user', 'content': prompt}],
            response_format={'type': 'json_schema', 'json_schema': {'name': name, 'schema': schema}})
        body, call_id = self._request(payload, call_context=call_context)
        try:
            choices = body['choices']
            if not isinstance(choices, list) or len(choices) != 1 or choices[0]['finish_reason'] != 'stop':
                raise ValueError('incomplete completion')
            message = choices[0]['message']
            if message.get('refusal') or message.get('tool_calls') or message.get('role') != 'assistant':
                raise ValueError('unsupported completion')
            decoded = json.loads(message['content'])
            if not isinstance(decoded, dict):
                raise ValueError('output must be an object')
            result = validate_stage_output(stage, decoded, context)
        except (KeyError, IndexError, TypeError, ValueError):
            self._finish_attempt(call_id, status='failed', error_code='model_invalid_response')
            raise ProviderError('model_invalid_response') from None
        self._finish_attempt(call_id, status='succeeded')
        return result

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

    def _request(self, payload, *, call_context):
        fallback = False
        for attempt in range(3):
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
                    if attempt == 2:
                        raise ProviderError('model_schema_unsupported')
                    fallback = True
                    payload = payload | {'response_format': {'type': 'json_object'}}
                    continue
                code = 'model_auth_failed' if response.status_code == 403 else self._http_error_code(response.status_code)
                retryable = response.status_code in {429, 500, 502, 503, 504}
                if code is None:
                    try:
                        body = response.json()
                        if not isinstance(body, dict):
                            raise ValueError('invalid envelope')
                    except ValueError:
                        code = 'model_invalid_response'
                    else:
                        return body, call_id
            self._finish_attempt(call_id, status='failed', error_code=code)
            if retryable and attempt < 2:
                self._sleeper((0.25, 0.75)[attempt])
                continue
            raise ProviderError(code) from None
        raise ProviderError('model_upstream_error')
