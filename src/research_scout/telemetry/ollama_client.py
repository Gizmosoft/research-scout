import json
import logging
import re
import time

import ollama

from research_scout.telemetry.metrics import RunMetrics

log = logging.getLogger("research_scout")


def _field(response, name: str) -> int:
    if isinstance(response, dict):
        value = response.get(name, 0)
    else:
        value = getattr(response, name, 0)
    return int(value or 0)


def _content(response) -> str:
    if isinstance(response, dict):
        message = response.get("message") or {}
        if isinstance(message, dict):
            return message.get("content") or ""
        return getattr(message, "content", "") or ""
    message = getattr(response, "message", None)
    return getattr(message, "content", "") or ""


def parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model returned a non-object")
    return data


class OllamaClient:
    def __init__(self, host: str, model: str, metrics: RunMetrics):
        self.host = host
        self.model = model
        self.metrics = metrics
        self._client = ollama.Client(host=host)

    def ready(self) -> bool:
        try:
            listed = self._client.list()
        except Exception:
            return False
        return self.model in _model_names(listed)

    def chat_json(self, system: str, user: str, *, task: str) -> dict:
        started = time.perf_counter()
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format="json",
            options={"temperature": 0},
        )
        prompt_tokens = _field(response, "prompt_eval_count")
        completion_tokens = _field(response, "eval_count")
        self.metrics.add_llm(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            load_ns=_field(response, "load_duration"),
            prompt_eval_ns=_field(response, "prompt_eval_duration"),
            eval_ns=_field(response, "eval_duration"),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        log.info(
            "llm task=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s",
            task,
            latency_ms,
            prompt_tokens,
            completion_tokens,
        )
        return parse_json_object(_content(response))


def _model_names(listed) -> list[str]:
    models = listed.get("models", []) if isinstance(listed, dict) else getattr(listed, "models", [])
    names = []
    for model in models or []:
        if isinstance(model, dict):
            names.append(model.get("model") or model.get("name") or "")
        else:
            names.append(getattr(model, "model", None) or getattr(model, "name", "") or "")
    return [name for name in names if name]
