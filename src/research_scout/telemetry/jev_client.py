import logging
import time

import httpx

from research_scout.config import MAX_RETRIES, Settings
from research_scout.telemetry.metrics import RunMetrics

log = logging.getLogger("research_scout")

_TIMEOUT = 40.0
_RETRY_STATUS = {429, 529}


class JevError(Exception):
    """A System One call failed before a usable answer came back."""


class JevClient:
    def __init__(self, settings: Settings, metrics: RunMetrics):
        self.base_url = settings.jev_base_url.rstrip("/")
        self.model = settings.jev_model
        self._api_key = settings.jev_api_key
        self.metrics = metrics
        self._client = httpx.Client(timeout=_TIMEOUT)

    def close(self) -> None:
        self._client.close()

    def ready(self) -> bool:
        if not self._api_key:
            return False
        try:
            response = self._client.get(f"{self.base_url}/v1/models", headers=self._headers())
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def ask(self, state: dict, questions: dict, *, task: str) -> dict:
        started = time.perf_counter()
        payload = self._post({"model": self.model, "state": state, "questions": questions})
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        prompt_tokens = _count(usage.get("input_tokens"))
        completion_tokens = _count(usage.get("output_tokens"))
        resolved = str(payload.get("model") or self.model)
        self.metrics.add_scorer(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            model=resolved,
        )
        log.info(
            "llm provider=jev task=%s latency_ms=%s model=%s prompt_tokens=%s completion_tokens=%s questions=%s",
            task,
            latency_ms,
            resolved,
            prompt_tokens,
            completion_tokens,
            len(questions),
        )
        return payload

    def _post(self, body: dict) -> dict:
        last_error = "unknown"
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.post(
                    f"{self.base_url}/v1/systemone",
                    headers=self._headers(),
                    json=body,
                )
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                if attempt >= MAX_RETRIES:
                    break
                self.metrics.add_retry()
                log.info("jev retry error=%s", last_error)
                continue
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, dict):
                    raise JevError("invalid response")
                return data
            last_error = f"HTTP{response.status_code}"
            if response.status_code not in _RETRY_STATUS or attempt >= MAX_RETRIES:
                log.info("jev failed status=%s", response.status_code)
                raise JevError(last_error)
            self.metrics.add_retry()
            log.info("jev retry status=%s", response.status_code)
            time.sleep(_retry_delay(response))
        log.info("jev failed error=%s", last_error)
        raise JevError(last_error)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


def _count(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _retry_delay(response: httpx.Response) -> float:
    header = response.headers.get("retry-after") or ""
    if header.isdigit():
        return min(int(header), 10)
    return 1.0
