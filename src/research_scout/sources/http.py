import json
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from research_scout.config import MAX_RETRIES

log = logging.getLogger("research_scout")


def get_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    on_retry: Callable[[], None] | None = None,
) -> dict | list | None:
    text = get_text(client, url, params=params, headers=headers, on_retry=on_retry)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.info("http bad_json host=%s", urlsplit(url).netloc)
        return None
    if isinstance(data, (dict, list)):
        return data
    return None


def get_text(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    on_retry: Callable[[], None] | None = None,
) -> str | None:
    host = urlsplit(url).netloc
    last_error = "unknown"
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            if attempt >= MAX_RETRIES:
                break
            if on_retry:
                on_retry()
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                time.sleep(1)
    log.info("http failed host=%s error=%s", host, last_error)
    return None
