import logging
from typing import Protocol

from research_scout.models import Item, Profile, clean_text
from research_scout.telemetry.ollama_client import OllamaClient

log = logging.getLogger("research_scout")

_SYSTEM = (
    "Score how well each item matches the user. "
    'Reply with JSON only: {"scores": [{"n": 1, "score": 0, "band": "direct", "reason": ""}]}. '
    "n is the item number. score is an integer from 0 to 100. "
    "band is direct, adjacent, or weak. reason is at most 12 words."
)
_BATCH = 4
_BANDS = {"direct", "adjacent", "weak"}


class Scorer(Protocol):
    def score_batch(self, profile: Profile, items: list[Item]) -> None:
        """Set relevancy_score, band, and reason on each item."""


class LlamaScorer:
    def __init__(self, llm: OllamaClient):
        self.llm = llm

    def score_batch(self, profile: Profile, items: list[Item]) -> None:
        if not items:
            return
        for start in range(0, len(items), _BATCH):
            chunk = items[start : start + _BATCH]
            batch = start // _BATCH + 1
            try:
                payload = self.llm.chat_json(
                    _SYSTEM,
                    _prompt(profile, chunk),
                    task=f"score batch={batch}",
                )
            except Exception:
                log.info("agent=relevancy task=score batch=%s failed", batch)
                for item in chunk:
                    item.relevancy_score = 0
                    item.band = "weak"
                    item.reason = "score unavailable"
                continue
            matched = _apply(chunk, payload)
            if matched < len(chunk):
                log.info(
                    "agent=relevancy task=score batch=%s unmatched=%s",
                    batch,
                    len(chunk) - matched,
                )
        log.info("agent=relevancy task=score items=%s", len(items))


def _prompt(profile: Profile, items: list[Item]) -> str:
    lines = [
        f"Domain: {profile.domain}",
        f"Interests: {profile.research_interests}",
        f"Goals: {profile.goals}",
        f"Skills: {profile.key_skills}",
        "",
    ]
    for number, item in enumerate(items, start=1):
        lines.append(
            f"n={number} kind={item.kind} title={item.title} "
            f"excerpt={clean_text(item.excerpt, 280)}"
        )
    return "\n".join(lines)


def _apply(chunk: list[Item], payload: dict) -> int:
    rows = _aligned_rows(chunk, payload)
    matched = 0
    for item, row in zip(chunk, rows):
        if not row:
            item.relevancy_score = 0
            item.band = "weak"
            item.reason = "score unavailable"
            continue
        matched += 1
        item.relevancy_score = _score(row.get("score"))
        band = str(row.get("band") or "weak")
        item.band = band if band in _BANDS else "weak"
        item.reason = clean_text(str(row.get("reason") or "no reason given"), 80)
    return matched


def _aligned_rows(chunk: list[Item], payload: dict) -> list[dict]:
    raw = [row for row in payload.get("scores") or [] if isinstance(row, dict)]
    by_number = {}
    by_id = {}
    for row in raw:
        number = _number(row.get("n"))
        if number is not None:
            by_number[number] = row
        if row.get("canonical_id"):
            by_id[str(row["canonical_id"])] = row
    if by_number or by_id:
        return [
            by_number.get(number) or by_id.get(item.canonical_id) or {}
            for number, item in enumerate(chunk, start=1)
        ]
    if len(raw) == len(chunk):
        return raw
    return [{} for _ in chunk]


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _score(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))
