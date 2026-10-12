"""Claude adapter on the official Anthropic SDK, sharing the base repair/ledger flow."""
import time

import anthropic
from pydantic import SecretStr

from app.providers.base import ProviderError
from app.providers.contracts import stage_schema
from app.providers.deepseek import DeepSeekModelProvider
from app.providers.output_validation import ModelOutputError, incomplete
from app.providers.prompts import build_prompt

DEFAULT_MODEL = 'claude-sonnet-5-5'
_RETRY_DELAYS = (0.25, 0.75)
# Server-side refusal fallback: routes by refusal category, no model list to maintain.
_FALLBACK_BETA = 'server-side-fallback-2026-07-01'


class AnthropicModelProvider(DeepSeekModelProvider):
    _provider_name = 'anthropic'
    profile = 'anthropic'

    def __init__(self, *, api_key: SecretStr, model: str = DEFAULT_MODEL, timeout_seconds: int = 60,
                 max_output_tokens: int = 8192, effort: str = 'medium', client=None,
                 sleeper=time.sleep, recorder=None, profile='anthropic'):
        secret = api_key.get_secret_value().strip()
        if not secret:
            raise ValueError('Anthropic API key must not be empty')
        self.profile = profile
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._effort = effort
        self._sleeper = sleeper
        self._recorder = recorder
        # Retries are owned here so every physical attempt lands in the ledger.
        self._client = client or anthropic.Anthropic(api_key=secret, timeout=float(timeout_seconds), max_retries=0)
        self._schema_supported = True

    def _build_payload(self, stage, context, *, repair_errors=None):
        _, schema = stage_schema(stage, member=context.get('_council_member'), followup=bool(context.get('_research_followup')))
        system, prompt = build_prompt(stage, context, repair_errors=repair_errors)
        output_config = {'effort': self._effort}
        if self._schema_supported:
            output_config['format'] = {'type': 'json_schema', 'schema': schema}
        else:
            # Fallback when the schema uses keywords structured outputs rejects:
            # the schema goes in the prompt and validate_stage_output still enforces it.
            import json
            system += '\nJSON Schema: ' + json.dumps(schema, ensure_ascii=False)
        return dict(model=self._model, max_tokens=self._max_output_tokens, system=system,
                    messages=[{'role': 'user', 'content': prompt}], output_config=output_config,
                    betas=[_FALLBACK_BETA], fallbacks='default')

    def _request(self, payload, *, call_context, max_attempts=3):
        for attempt in range(max_attempts):
            call_id = self._start_attempt(call_context, attempt + 1)
            code, retryable = None, False
            try:
                message = self._client.beta.messages.create(**payload)
                return message.model_dump(mode='json'), call_id
            except anthropic.APITimeoutError:
                code, retryable = 'model_timeout', True
            except anthropic.APIConnectionError:
                code, retryable = 'model_transport_error', True
            except anthropic.BadRequestError as error:
                if self._schema_supported and _is_schema_rejection(error):
                    self._finish_attempt(call_id, status='failed', error_code='model_schema_unsupported')
                    self._schema_supported = False
                    payload.update(self._schema_free(payload))
                    continue
                code = 'model_invalid_request'
            except anthropic.AuthenticationError:
                code = 'model_auth_failed'
            except anthropic.PermissionDeniedError:
                code = 'model_auth_failed'
            except anthropic.RateLimitError:
                code, retryable = 'model_rate_limited', True
            except anthropic.InternalServerError:
                code, retryable = 'model_upstream_unavailable', True
            except anthropic.APIStatusError:
                code = 'model_upstream_error'
            self._finish_attempt(call_id, status='failed', error_code=code)
            if retryable and attempt < max_attempts - 1:
                self._sleeper(_RETRY_DELAYS[attempt])
                continue
            raise ProviderError(code) from None
        raise ProviderError('model_upstream_error')

    @staticmethod
    def _schema_free(payload):
        import json
        output_config = {k: v for k, v in payload['output_config'].items() if k != 'format'}
        schema = payload['output_config'].get('format', {}).get('schema')
        system = payload['system'] + ('\nJSON Schema: ' + json.dumps(schema, ensure_ascii=False) if schema else '')
        return {'output_config': output_config, 'system': system}

    @staticmethod
    def _extract_output_text(body):
        stop_reason = body.get('stop_reason')
        if stop_reason == 'refusal':
            raise ProviderError('model_refusal')
        if stop_reason == 'max_tokens':
            raise incomplete('max_output_tokens')
        texts = [block.get('text', '') for block in body.get('content', [])
                 if isinstance(block, dict) and block.get('type') == 'text' and block.get('text', '').strip()]
        if len(texts) != 1:
            raise ModelOutputError('model_contract_violation', ['response.content: exactly one text block required'])
        return texts[0]


def _is_schema_rejection(error) -> bool:
    message = str(getattr(error, 'message', '') or error).casefold()
    return 'schema' in message or 'output_config' in message or 'format' in message
