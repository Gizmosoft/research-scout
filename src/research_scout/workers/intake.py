import csv
import logging
from datetime import datetime, timezone

from research_scout.config import Settings
from research_scout.models import USER_FIELDS, USERNAME_RE, Profile

log = logging.getLogger("research_scout")


class IntakeWorker:
    def __init__(self, settings: Settings):
        self.path = settings.data_dir / "users.csv"

    def run(self) -> Profile:
        username = self._ask_username()
        existing = self._load().get(username)
        if existing:
            self._show(existing)
            print("This profile is fixed and cannot be edited.")
            log.info("intake username=%s created=false", username)
            return existing
        profile = Profile(
            username=username,
            domain=_ask("Domain of work"),
            research_interests=_ask("Research interests"),
            goals=_ask("Goals"),
            key_skills=_ask("Key skills"),
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._append(profile)
        log.info("intake username=%s created=true", username)
        return profile

    def _ask_username(self) -> str:
        while True:
            username = input("Username: ").strip()
            if USERNAME_RE.fullmatch(username):
                return username
            print("Use 1-32 letters, numbers, underscores, or hyphens.")

    def _load(self) -> dict[str, Profile]:
        if not self.path.exists():
            return {}
        profiles: dict[str, Profile] = {}
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                username = (row.get("username") or "").strip()
                if username and username not in profiles:
                    profiles[username] = Profile(
                        username=username,
                        domain=row.get("domain") or "",
                        research_interests=row.get("research_interests") or "",
                        goals=row.get("goals") or "",
                        key_skills=row.get("key_skills") or "",
                        created_at=row.get("created_at") or "",
                    )
        return profiles

    def _append(self, profile: Profile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, USER_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(profile.model_dump())

    def _show(self, profile: Profile) -> None:
        print(f"Welcome back, {profile.username}.")
        print(f"Domain: {profile.domain}")
        print(f"Interests: {profile.research_interests}")
        print(f"Goals: {profile.goals}")
        print(f"Skills: {profile.key_skills}")


def _ask(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Enter a value.")
