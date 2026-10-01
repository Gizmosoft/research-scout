import logging

from research_scout.models import Item, Profile, clean_text
from research_scout.telemetry.jev_client import JevClient

log = logging.getLogger("research_scout")

# One call judges every item in the chunk at once. The chunk stays well under
# Jev's 64k-token request budget. Each item is one Score question.
ITEMS_PER_CALL = 16

# Ordered from no overlap to a direct match. Jev's score is a position on this scale.
LEVELS = ("weak", "adjacent", "direct")
RUBRIC = {
    "weak": "Little overlap with the user's domain or interests",
    "adjacent": "Neighboring topic that is not the stated focus",
    "direct": "Matches the user's domain and research interests",
}


class JevScorer:
    def __init__(self, client: JevClient):
        self.client = client

    def score_batch(self, profile: Profile, items: list[Item]) -> None:
        if not items:
            return
        log.info(
            "agent=relevancy provider=jev task=score items=%s per_call=%s questions_per_item=1",
            len(items),
            ITEMS_PER_CALL,
        )
        calls = 0
        for start in range(0, len(items), ITEMS_PER_CALL):
            chunk = items[start : start + ITEMS_PER_CALL]
            batch = start // ITEMS_PER_CALL + 1
            calls += 1
            questions = _questions(chunk)
            try:
                payload = self.client.ask(
                    _state(profile),
                    questions,
                    task=f"score batch={batch}",
                )
            except Exception:
                log.info("agent=relevancy provider=jev task=score batch=%s failed", batch)
                for item in chunk:
                    _unavailable(item)
                continue
            matched = _apply(chunk, payload)
            if matched < len(chunk):
                log.info(
                    "agent=relevancy provider=jev task=score batch=%s unmatched=%s",
                    batch,
                    len(chunk) - matched,
                )
        log.info("agent=relevancy provider=jev task=score calls=%s", calls)


def _state(profile: Profile) -> dict:
    return {
        "domain": profile.domain,
        "research_interests": profile.research_interests,
        "goals": profile.goals,
        "key_skills": profile.key_skills,
    }


def _questions(items: list[Item]) -> dict:
    questions = {}
    for index, item in enumerate(items):
        shown = {
            "kind": item.kind,
            "title": item.title,
            "excerpt": clean_text(item.excerpt, 280),
        }
        questions[f"i{index}"] = {
            "type": "score",
            "instructions": {
                "item": shown,
                "question": "How closely does `item` match the user's domain, interests, goals, and skills?",
            },
            "criteria": [RUBRIC[level] for level in LEVELS],
        }
    return questions


def _apply(chunk: list[Item], payload: dict) -> int:
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        answers = {}
    matched = 0
    for index, item in enumerate(chunk):
        if _apply_one(item, answers, index):
            matched += 1
        else:
            _unavailable(item)
    return matched


def _apply_one(item: Item, answers: dict, index: int) -> bool:
    row = answers.get(f"i{index}")
    if not isinstance(row, dict):
        return False
    position = row.get("score")
    if isinstance(position, bool) or not isinstance(position, (int, float)):
        return False
    level = _level(row.get("probabilities"), float(position))
    if level is None:
        return False
    item.relevancy_score = _points(float(position))
    item.band = level
    item.reason = clean_text(RUBRIC[level], 80)
    return True


def _level(probabilities, position: float) -> str | None:
    best_index = None
    best_weight = None
    if isinstance(probabilities, dict):
        for key, weight in probabilities.items():
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                continue
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            if not 0 <= index < len(LEVELS):
                continue
            rank = (float(weight), -abs(index - position))
            if best_weight is None or rank > best_weight:
                best_weight = rank
                best_index = index
    if best_index is None:
        best_index = int(position + 0.5)
    if 0 <= best_index < len(LEVELS):
        return LEVELS[best_index]
    return None


def _unavailable(item: Item) -> None:
    item.relevancy_score = 0
    item.band = "weak"
    item.reason = "score unavailable"


def _points(position: float) -> int:
    span = len(LEVELS) - 1
    points = int(position / span * 100 + 0.5)
    return max(0, min(100, points))
