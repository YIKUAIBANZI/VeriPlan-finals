"""Cost-bounded Tavily Search API adapter."""

import math
import time
import unicodedata
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

from app.providers.base import AttemptRecorder, ProviderCallContext, ProviderError
from app.providers.search_safety import (
    canonicalize_public_https_url,
    host_matches_domain,
    normalize_domains,
)
from app.schemas import EvidenceCard


_CONNECT_RETRY_DELAY = 0.1
_HIGH_SCORE = 0.7
_MEDIUM_SCORE = 0.4


class TavilySearchProvider:
    _provider_name = "tavily"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        timeout_seconds: int = 15,
        trusted_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
        transport: httpx2.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        recorder: AttemptRecorder | None = None,
    ):
        secret = api_key.get_secret_value().strip()
        if not secret:
            raise ValueError("Tavily API key must not be empty")
        self._trusted_domains = normalize_domains(trusted_domains)
        self._blocked_domains = normalize_domains(blocked_domains)
        self._sleeper = sleeper
        self._recorder = recorder
        self._client = httpx2.Client(
            base_url="https://api.tavily.com",
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
        )

    def search(
        self,
        query: str,
        *,
        call_context: ProviderCallContext | None = None,
    ) -> list[EvidenceCard]:
        normalized_query = query.strip() if isinstance(query, str) else ""
        if not normalized_query or len(normalized_query) > 400:
            raise ProviderError("search_invalid_request")
        body, call_id = self._request(
            {
                "query": normalized_query,
                "search_depth": "basic",
                "chunks_per_source": 2,
                "max_results": 5,
                "topic": "general",
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
                "include_image_descriptions": False,
                "include_favicon": False,
                "auto_parameters": False,
                "safe_search": True,
                "exclude_domains": list(self._blocked_domains),
            },
            call_context=call_context,
        )
        try:
            raw_results = body.get("results")
            if not isinstance(raw_results, list):
                raise ProviderError("search_invalid_response")

            cards: list[EvidenceCard] = []
            seen_urls: set[str] = set()
            for raw_result in raw_results:
                try:
                    card = self._parse_result(raw_result)
                except (TypeError, ValueError):
                    continue
                if card.source_url in seen_urls:
                    continue
                seen_urls.add(card.source_url)
                cards.append(card)
            if raw_results and not cards:
                raise ProviderError("search_invalid_response")
        except ProviderError as error:
            self._finish_attempt(call_id, status="failed", error_code=error.code)
            raise
        self._finish_attempt(call_id, status="succeeded")
        return cards

    def _request(
        self,
        payload: dict[str, Any],
        *,
        call_context: ProviderCallContext | None,
    ) -> tuple[Mapping[str, Any], int | None]:
        for attempt in range(2):
            call_id = self._start_attempt(call_context, attempt + 1)
            try:
                response = self._client.post("/search", json=payload)
            except httpx2.ConnectError as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="search_transport_error",
                )
                if attempt == 0:
                    self._sleeper(_CONNECT_RETRY_DELAY)
                    continue
                raise ProviderError("search_transport_error") from error
            except httpx2.TimeoutException as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="search_timeout",
                )
                raise ProviderError("search_timeout") from error
            except httpx2.TransportError as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="search_transport_error",
                )
                raise ProviderError("search_transport_error") from error

            error_code = self._http_error_code(response.status_code)
            if error_code is not None:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code=error_code,
                )
                raise ProviderError(error_code)
            try:
                body = response.json()
            except ValueError as error:
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="search_invalid_response",
                )
                raise ProviderError("search_invalid_response") from error
            if not isinstance(body, dict):
                self._finish_attempt(
                    call_id,
                    status="failed",
                    error_code="search_invalid_response",
                )
                raise ProviderError("search_invalid_response")
            return body, call_id
        raise ProviderError("search_transport_error")

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

    def _parse_result(self, value: Any) -> EvidenceCard:
        if not isinstance(value, dict):
            raise TypeError("result must be an object")
        title = self._clean_text(value.get("title"), max_length=160)
        summary = self._clean_text(value.get("content"), max_length=1_000)
        url = value.get("url")
        score = value.get("score")
        if not isinstance(url, str):
            raise TypeError("result URL must be text")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError("result score must be numeric")
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("result score is outside the allowed range")
        source_url = canonicalize_public_https_url(
            url,
            blocked_domains=self._blocked_domains,
        )
        host = urlsplit(source_url).hostname or ""
        trusted = any(
            host_matches_domain(host, domain) for domain in self._trusted_domains
        )
        if trusted and score >= _HIGH_SCORE:
            reliability = "high"
        elif score >= _MEDIUM_SCORE:
            reliability = "medium"
        else:
            reliability = "low"
        return EvidenceCard(
            is_demo=False,
            title=title,
            summary=summary,
            source_url=source_url,
            stance="context",
            reliability=reliability,
        )

    @staticmethod
    def _clean_text(value: Any, *, max_length: int) -> str:
        if not isinstance(value, str):
            raise TypeError("result text must be a string")
        without_controls = "".join(
            " " if unicodedata.category(character).startswith("C") else character
            for character in value
        )
        cleaned = " ".join(without_controls.split())[:max_length].rstrip()
        if not cleaned:
            raise ValueError("result text must not be empty")
        return cleaned

    @staticmethod
    def _http_error_code(status_code: int) -> str | None:
        if 200 <= status_code < 300:
            return None
        if status_code in {400, 422}:
            return "search_invalid_request"
        if status_code in {401, 403}:
            return "search_auth_failed"
        if status_code in {432, 433}:
            return "search_usage_exhausted"
        if status_code == 429:
            return "search_rate_limited"
        if status_code in {500, 502, 503}:
            return "search_upstream_unavailable"
        return "search_upstream_error"

    def close(self) -> None:
        self._client.close()
