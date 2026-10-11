"""DeepSeek Responses API adapter with bounded retries and strict parsing."""

import json
import time
from dataclasses import replace
from collections.abc import Callable, Mapping
from typing import Any

import httpx2
from pydantic import SecretStr

from app.providers.base import AttemptRecorder, ProviderCallContext, ProviderError
from app.providers.contracts import stage_schema, validate_stage_output
from app.providers.prompts import build_prompt
from app.providers.output_validation import ModelOutputError, incomplete, validation_failure


_RETRY_DELAYS = (0.25, 0.75)


class DeepSeekModelProvider:
    _provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "deepseek-v4-flash",
        timeout_seconds: int = 30,
        max_output_tokens: int = 8192,
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
        _, schema = stage_schema(stage, member=context.get("_council_member"))
        repair_errors = None
        payload = {}
        for repair in range(2):
            operation = (replace(call_context, logical_operation=call_context.logical_operation + ":repair")
                         if repair and call_context else call_context)
            prior_format = payload.get("response_format")
            payload = self._build_payload(stage, context, repair_errors=repair_errors)
            if prior_format == {"type": "json_object"}:
                payload["response_format"] = prior_format
            call_id = None
            try:
                body, call_id = self._request(payload, call_context=operation, max_attempts=1 if repair else 3)
                result = validate_stage_output(stage, json.loads(self._extract_output_text(body)), context)
            except (ModelOutputError, ValueError, TypeError, KeyError, IndexError) as error:
                failure = error if isinstance(error, ModelOutputError) else validation_failure(error, schema)
                # _request closes attempts for envelope/transport failures itself.
                if call_id is not None:
                    self._finish_attempt(call_id, status="failed", error_code=failure.code,
                                         incomplete_reason=failure.incomplete_reason)
                if repair:
                    raise failure from None
                repair_errors = failure.issues
                continue
            self._finish_attempt(call_id, status="succeeded")
            return result

    def _build_payload(self, stage, context, *, repair_errors=None):
        schema_name, schema = stage_schema(stage, member=context.get("_council_member"))
        instructions, prompt_input = build_prompt(stage, context, repair_errors=repair_errors)
        return {
            "model": self._model, "instructions": instructions, "input": prompt_input,
            "reasoning": {"effort": "low"}, "max_output_tokens": self._max_output_tokens,
            "stream": False,
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema}},
        }

    def _request(
        self,
        payload: dict[str, Any],
        *,
        call_context: ProviderCallContext | None,
        max_attempts: int = 3,
    ) -> tuple[dict[str, Any], int | None]:
        for attempt in range(max_attempts):
            call_id = self._start_attempt(call_context, attempt + 1)
            try:
                response = self._client.post("/responses", json=payload)
            except httpx2.TimeoutException as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_timeout",
                )
                if attempt < max_attempts - 1:
                    self._sleeper(_RETRY_DELAYS[attempt])
                    continue
                raise ProviderError("model_timeout") from error
            except httpx2.TransportError as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_transport_error",
                )
                if attempt < max_attempts - 1:
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
                if retryable and attempt < max_attempts - 1:
                    self._sleeper(_RETRY_DELAYS[attempt])
                    continue
                raise ProviderError(error_code)

            try:
                body = response.json()
            except ValueError:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_invalid_json",
                )
                raise ModelOutputError("model_invalid_json", ["response: invalid json"]) from None
            if not isinstance(body, dict):
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="model_contract_violation",
                )
                raise ModelOutputError("model_contract_violation", ["response: object required"])
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
        incomplete_reason: str | None = None,
    ) -> None:
        if call_id is None:
            return
        try:
            self._recorder.finish_provider_attempt(
                call_id,
                status=status,
                error_code=error_code,
                **({"incomplete_reason": incomplete_reason} if incomplete_reason else {}),
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
            details = body.get("incomplete_details")
            raise incomplete(details.get("reason") if isinstance(details, dict) else None)
        output = body.get("output")
        if not isinstance(output, list):
            raise ModelOutputError("model_contract_violation", ["response.output: list required"])
        texts = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            if item.get("status", "completed") != "completed":
                raise incomplete(None)
            content = item.get("content")
            if not isinstance(content, list):
                raise ModelOutputError("model_contract_violation", ["response.output.content: list required"])
            texts.extend(part["text"] for part in content if isinstance(part, dict)
                         and part.get("type") == "output_text" and isinstance(part.get("text"), str))
        if len(texts) != 1:
            raise ModelOutputError("model_contract_violation", ["response.output_text: exactly one required"])
        return texts[0]

    def close(self) -> None:
        self._client.close()
