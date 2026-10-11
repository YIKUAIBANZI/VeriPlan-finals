"""DeepSeek Responses API adapter with bounded retries and strict parsing."""

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx2
from pydantic import SecretStr, ValidationError

from app.providers.base import AttemptRecorder, ProviderCallContext, ProviderError
from app.providers.contracts import stage_schema, validate_stage_output
from app.providers.prompts import build_prompt


_RETRY_DELAYS = (0.25, 0.75)


class DeepSeekModelProvider:
    _provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "deepseek-v4-flash",
        timeout_seconds: int = 30,
        max_output_tokens: int = 4096,
        transport: httpx2.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        recorder: AttemptRecorder | None = None,
    ):
        secret = api_key.get_secret_value().strip()
        if not secret:
            raise ValueError("DeepSeek API key must not be empty")
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._sleeper = sleeper
        self._recorder = recorder
        self._client = httpx2.Client(
            base_url="https://api.deepseek.com",
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
        )

    def generate(
        self,
        stage: str,
        context: Mapping[str, Any],
        *,
        call_context: ProviderCallContext | None = None,
    ) -> dict[str, Any]:
        schema_name, schema = stage_schema(stage)
        instructions, prompt_input = build_prompt(stage, context)
        response_body, call_id = self._request(
            {
                "model": self._model,
                "instructions": instructions,
                "input": prompt_input,
                "reasoning": {"effort": "low"},
                "max_output_tokens": self._max_output_tokens,
                "stream": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                    }
                },
            },
            call_context=call_context,
        )
        try:
            output_text = self._extract_output_text(response_body)
            decoded = json.loads(output_text)
            if not isinstance(decoded, dict):
                raise TypeError("model JSON output must be an object")
            result = validate_stage_output(stage, decoded, context)
        except ProviderError as error:
            self._finish_attempt(call_id, status="failed", error_code=error.code)
            raise
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
            self._finish_attempt(
                call_id,
                status="failed",
                error_code="model_invalid_response",
            )
            raise ProviderError("model_invalid_response") from error
        self._finish_attempt(call_id, status="succeeded")
        return result

    def _request(
        self,
        payload: dict[str, Any],
        *,
        call_context: ProviderCallContext | None,
    ) -> tuple[dict[str, Any], int | None]:
        for attempt in range(3):
            call_id = self._start_attempt(call_context, attempt + 1)
            try:
                response = self._client.post("/responses", json=payload)
            except httpx2.TimeoutException as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_timeout",
                )
                if attempt < 2:
                    self._sleeper(_RETRY_DELAYS[attempt])
                    continue
                raise ProviderError("model_timeout") from error
            except httpx2.TransportError as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_transport_error",
                )
                if attempt < 2:
                    self._sleeper(_RETRY_DELAYS[attempt])
                    continue
                raise ProviderError("model_transport_error") from error

            error_code = self._http_error_code(response.status_code)
            retryable = response.status_code in {429, 500, 503}
            if error_code is not None:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code=error_code,
                )
                if retryable and attempt < 2:
                    self._sleeper(_RETRY_DELAYS[attempt])
                    continue
                raise ProviderError(error_code)

            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError) as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_invalid_response",
                )
                raise ProviderError("model_invalid_response") from error
            if not isinstance(body, dict):
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_invalid_response",
                )
                raise ProviderError("model_invalid_response")
            return body, call_id

        raise ProviderError("model_upstream_error")

    def _start_attempt(
        self,
        context: ProviderCallContext | None,
        attempt_number: int,
    ) -> int | None:
        if self._recorder is None or context is None:
            return None
        try:
            return self._recorder.start_provider_attempt(
                context=context,
                provider=self._provider_name,
                attempt_number=attempt_number,
            )
        except Exception as error:
            raise ProviderError("provider_audit_failed") from error

    def _finish_attempt(
        self,
        call_id: int | None,
        *,
        status: str,
        error_code: str | None = None,
    ) -> None:
        if call_id is None:
            return
        try:
            self._recorder.finish_provider_attempt(
                call_id,
                status=status,
                error_code=error_code,
            )
        except Exception as error:
            raise ProviderError("provider_audit_failed") from error

    @staticmethod
    def _http_error_code(status_code: int) -> str | None:
        if 200 <= status_code < 300:
            return None
        if status_code in {400, 422}:
            return "model_invalid_request"
        if status_code == 401:
            return "model_auth_failed"
        if status_code == 402:
            return "model_balance_exhausted"
        if status_code == 429:
            return "model_rate_limited"
        if status_code in {500, 503}:
            return "model_upstream_unavailable"
        return "model_upstream_error"

    @staticmethod
    def _extract_output_text(body: Mapping[str, Any]) -> str:
        if body.get("status") != "completed":
            raise ProviderError("model_invalid_response")
        texts = [
            part.get("text", "")
            for item in body.get("output", [])
            if isinstance(item, dict) and item.get("type") == "message"
            for part in item.get("content", [])
            if isinstance(part, dict) and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
            and part["text"].strip()
        ]
        if len(texts) != 1:
            raise ProviderError("model_invalid_response")
        return texts[0]

    def close(self) -> None:
        self._client.close()
